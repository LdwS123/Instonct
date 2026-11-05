"""Local full-text index of every mail: the bot can answer about the whole mailbox, not just what IMAP search returns.

The Mac mini reads each mailbox in small batches, in the background and read-only (BODY.PEEK marks nothing as read). Each pass compares the UIDs on
the server with the UIDs indexed, so new mails are added and mails gone from the server (trash, deletion) are dropped: the index repairs itself.
"""

import email
import html
import json
import os
import re
import time
from contextlib import closing
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime

from . import localdb, mail, mailtriage
from .core import db, log, norm, scrub

PATH = os.environ.get("MAIL_INDEX_PATH") or os.path.join(os.path.expanduser("~"), "bots", "mail_index.sqlite")
BATCH = 100                 # mails per pass
FETCH_BYTES = 32768         # start of each mail: enough for the text, never the attachments
BODY_CHARS = 6000
BUSY_PAUSE = 20             # seconds between passes while catching up
IDLE_PAUSE = 300            # seconds between passes once everything is indexed
STATUS = "mailindex:status"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mails(id INTEGER PRIMARY KEY, acc INTEGER, folder TEXT, uid INTEGER, uidvalidity INTEGER, mid TEXT, date INTEGER,
    de TEXT, dest TEXT, sujet TEXT, type TEXT, niveau TEXT, body TEXT, refs TEXT, UNIQUE(acc, folder, uid, uidvalidity));
CREATE INDEX IF NOT EXISTS mails_date ON mails(date);
CREATE VIRTUAL TABLE IF NOT EXISTS mails_fts USING fts5(de, dest, sujet, body, content='mails', content_rowid='id', tokenize="unicode61 remove_diacritics 2");
CREATE TRIGGER IF NOT EXISTS mails_ai AFTER INSERT ON mails BEGIN
    INSERT INTO mails_fts(rowid, de, dest, sujet, body) VALUES (new.id, new.de, new.dest, new.sujet, new.body); END;
CREATE TRIGGER IF NOT EXISTS mails_ad AFTER DELETE ON mails BEGIN
    INSERT INTO mails_fts(mails_fts, rowid, de, dest, sujet, body) VALUES ('delete', old.id, old.de, old.dest, old.sujet, old.body); END;
"""

_STOP = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "a", "au", "aux", "en", "mon", "ma", "mes", "ce", "cet", "cette", "ces", "pour", "sur", "dans", "avec",
         "que", "qui", "quoi", "mail", "mails", "email", "emails", "message", "messages", "the", "of", "to", "my"}


def _db():
    return closing(localdb.connect(PATH, SCHEMA))


# ---------------------------------------------------------------- reading the mailbox
def _parse(raw):
    """One mail from its first bytes. Never raises: a mail we cannot read still gets a row, otherwise it would be fetched again at every pass."""
    out = {"mid": "", "date": 0, "de": "", "dest": "", "sujet": "", "type": "", "niveau": "", "body": "", "refs": ""}
    try:
        m = email.message_from_bytes(raw)
        out["de"], out["dest"], out["sujet"] = mail._mail_dec(m["From"]), mail._mail_dec(m["To"]), mail._mail_dec(m["Subject"])
        out["mid"] = str(m["Message-ID"] or "").strip()
        out["refs"] = f"{m['In-Reply-To'] or ''} {m['References'] or ''}".strip()
        try:
            out["date"] = int(parsedate_to_datetime(str(m["Date"])).timestamp())
        except (TypeError, ValueError, OverflowError):
            pass
        out["body"] = html.unescape(mail._body_text(m))[:BODY_CHARS]
        tri = mailtriage.classify(out["de"], out["sujet"], out["body"], mail._bulk(m))
        out["type"], out["niveau"] = tri["type"], tri["niveau"]
    except Exception as e:
        log.info("index mail illisible : %s", scrub(e)[:100])
    return out


def _fetch(c, uids):
    """{uid: raw bytes}. The server may put the UID before or after the message body."""
    typ, data = c.uid("fetch", ",".join(str(u) for u in uids), f"(BODY.PEEK[]<0.{FETCH_BYTES}>)")
    if typ != "OK":
        raise RuntimeError(f"fetch refuse : {typ}")
    found, items = {}, list(data or [])
    for i, item in enumerate(items):
        if isinstance(item, tuple):
            m = re.search(rb"\bUID (\d+)", item[0])
            if not m and i + 1 < len(items) and isinstance(items[i + 1], bytes):
                m = re.search(rb"\bUID (\d+)", items[i + 1])
            if m:
                found[int(m.group(1))] = item[1] or b""
    return found


def _status_of(c, folder):
    typ, data = c.status(mail._imap_q(folder), "(UIDVALIDITY)")
    m = re.search(rb"UIDVALIDITY (\d+)", b" ".join(x for x in (data or []) if isinstance(x, bytes)))
    if typ != "OK" or not m:
        raise RuntimeError(f"dossier illisible : {folder}")
    return int(m.group(1))


def _sync_folder(c, n, folder, budget):
    """Brings one folder closer to the server. Returns (mails still to fetch, mails on the server)."""
    validity = _status_of(c, folder)
    typ, _ = c.select(mail._imap_q(folder), readonly=True)
    if typ != "OK":
        raise RuntimeError(f"dossier illisible : {folder}")
    typ, data = c.uid("search", None, "ALL")
    if typ != "OK":
        raise RuntimeError(f"recherche refusee : {folder}")
    server = {int(u) for u in (data[0] or b"").split()} if data else set()
    with _db() as con:
        con.execute("DELETE FROM mails WHERE acc=? AND folder=? AND uidvalidity!=?", (n, folder, validity))      # UIDs restarted: they no longer mean the same mails
        known = {r[0] for r in con.execute("SELECT uid FROM mails WHERE acc=? AND folder=?", (n, folder))}
        gone = known - server
        con.executemany("DELETE FROM mails WHERE acc=? AND folder=? AND uid=?", [(n, folder, u) for u in gone])
        con.commit()
    missing = sorted(server - known, reverse=True)                                                                 # newest mails first
    batch = missing[:budget]                    # a UID the server does not return stays "missing" and is simply tried again next pass
    if batch:
        raws = _fetch(c, batch)
        if not raws:
            raise RuntimeError(f"le serveur n'a renvoye aucun mail : {folder}")          # otherwise this would silently spin forever
        rows = [{"acc": n, "folder": folder, "uid": u, "uidvalidity": validity, **_parse(raw)} for u, raw in raws.items()]
        with _db() as con:
            con.executemany("INSERT OR IGNORE INTO mails(acc, folder, uid, uidvalidity, mid, date, de, dest, sujet, type, niveau, body, refs) "
                            "VALUES (:acc, :folder, :uid, :uidvalidity, :mid, :date, :de, :dest, :sujet, :type, :niveau, :body, :refs)", rows)
            con.commit()
    return len(missing) - len(batch), len(server)


def _wanted_folders(c, gmail):
    return [f for f in mail._mail_folders(c, gmail) if not re.search(r"spam|junk|indesirable|indésirable", f, re.I)]


def sync_once(budget=BATCH):
    """One pass over every mailbox. Returns how many mails are still to fetch."""
    todo, total = 0, 0
    for acc in mail._mail_accounts():
        n = acc["n"]
        c = mail._mail_open(n)
        try:
            folders = _wanted_folders(c, "gmail" in acc["host"] or "google" in acc["host"])
            for folder in folders:
                left, count = _sync_folder(c, n, folder, budget)
                todo, total = todo + left, total + count
            if folders:
                with _db() as con:
                    marks = ",".join("?" * len(folders))
                    con.execute(f"DELETE FROM mails WHERE acc=? AND folder NOT IN ({marks})", (n, *folders))     # a folder that no longer exists
                    con.commit()
        finally:
            try:
                c.logout()
            except Exception:
                pass
    db.set(STATUS, json.dumps({"a_faire": todo, "sur_le_serveur": total, "at": int(time.time())}))
    return todo


def index_loop():
    """Background thread: catches up quickly, then just follows new mails. Errors only slow it down, they never reach the user."""
    time.sleep(60)
    errors = 0
    while True:
        try:
            todo = sync_once()
            errors = 0
            time.sleep(BUSY_PAUSE if todo else IDLE_PAUSE)
        except Exception as e:
            errors += 1
            log.warning("index des mails : %s", scrub(e)[:200])
            time.sleep(min(3600, 60 * 2 ** min(errors, 6)))


# ---------------------------------------------------------------- answering
def _when(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _row(r, extrait=None):
    out = {"id": f"{r['acc']}:{r['uid']}@{r['folder']}", "date": _when(r["date"]), "de": (r["de"] or "")[:80], "sujet": (r["sujet"] or "")[:120], "type": r["type"]}
    if extrait:
        out["extrait"] = re.sub(r"\s+", " ", extrait)[:220]
    return out


def _unique(rows):
    seen, out = set(), []
    for r in rows:
        key = r["mid"] or (r["acc"], r["folder"], r["uid"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def search(query="", de="", typ="", days=0, limit=15):
    """All the words first, then any of them. Good matches and recent mails come first."""
    limit = max(1, min(int(limit or 15), 30))
    where, params = ["1=1"], []
    if de:
        where.append("m.de LIKE ? ESCAPE '\\'")
        params.append("%" + re.sub(r"([%_\\])", r"\\\1", str(de)) + "%")
    if typ:
        where.append("m.type=?")
        params.append(str(typ))
    if days:
        where.append("m.date>=?")
        params.append(int(time.time()) - int(days) * 86400)
    filters = " AND ".join(where)
    with _db() as con:
        if not localdb.match_query(query, _STOP):
            rows = con.execute(f"SELECT m.* FROM mails m WHERE {filters} AND m.de!='' ORDER BY m.date DESC LIMIT ?", (*params, limit * 3)).fetchall()
            return {"resultats": [_row(r) for r in _unique(rows)[:limit]]} | _progress_note()
        sql = ("SELECT m.*, snippet(mails_fts, 3, '[', ']', '...', 24) AS extrait FROM mails_fts JOIN mails m ON m.id=mails_fts.rowid "
               f"WHERE mails_fts MATCH ? AND {filters} ORDER BY bm25(mails_fts, 3.0, 1.0, 5.0, 1.0) - m.date / 15768000.0 LIMIT ?")
        rows = con.execute(sql, (localdb.match_query(query, _STOP), *params, limit * 3)).fetchall()
        wider = False
        if not rows:
            rows, wider = con.execute(sql, (localdb.match_query(query, _STOP, any_word=True), *params, limit * 3)).fetchall(), True
    out = {"resultats": [_row(r, r["extrait"]) for r in _unique(rows)[:limit]]}
    if wider and out["resultats"]:
        out["note"] = "aucun mail n'a tous les mots : resultats avec au moins un mot"
    return out | _progress_note()


def _progress_note():
    st = status()
    return {"attention": f"index pas fini, {st['a_faire']} mails pas encore lus : la reponse peut etre incomplete"} if st.get("a_faire") else {}


def status():
    with _db() as con:
        n = con.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
    st = json.loads(db.get(STATUS) or "{}")
    return {"mails_dans_l_index": n, "a_faire": st.get("a_faire"), "sur_le_serveur": st.get("sur_le_serveur"), "dernier_passage": _when(st.get("at", 0))}


def stats():
    with _db() as con:
        first, last = con.execute("SELECT MIN(date), MAX(date) FROM mails WHERE date>0").fetchone()
        types = dict(con.execute("SELECT type, COUNT(*) FROM mails WHERE type!='' GROUP BY type ORDER BY 2 DESC LIMIT 15").fetchall())
        people = con.execute("SELECT de, COUNT(*) AS n FROM mails WHERE niveau='important' AND de!='' GROUP BY de ORDER BY n DESC LIMIT 10").fetchall()
    return status() | {"du": _when(first or 0)[:10], "au": _when(last or 0)[:10], "par_type": types, "qui_ecrit_le_plus": [{"de": r["de"][:70], "mails": r["n"]} for r in people]}


# ---------------------------------------------------------------- job applications, from what the mailbox says
_APPLICATION_TYPES = ("candidature", "etape", "acceptation", "refus")
_STATUS_WORD = {"candidature": "accuse de reception", "etape": "entretien / prochaine etape", "acceptation": "acceptation", "refus": "refus"}
_ATS = re.compile(r"greenhouse|lever\.co|workday|ashby|smartrecruiters|teamtailor|icims|jobvite|recruitee|workable|taleo|successfactors|bamboohr|breezy|jazzhr|"
                  r"welcomekit|welcometothejungle|talentsoft|indeed|linkedin|hellowork|apec", re.I)
_FREE_MAIL = re.compile(r"gmail|yahoo|outlook|hotmail|icloud|live\.|orange\.fr|free\.fr|protonmail|proton\.me", re.I)
_COMPANY = r"\s+([A-Z0-9][\w&.'’-]*(?:\s+[A-Z0-9][\w&.'’-]*){0,3})"
_AT_COMPANY = re.compile(r"(?:\bat|\bchez|\baupr[eè]s de)" + _COMPANY)
_TO_COMPANY = re.compile(r"(?:\bto|\bà)" + _COMPANY)                                  # weaker: "applied to Senior Manager" is not a company
_NAME_NOISE = re.compile(r"\b(?:recruiting|recruitment|recrutement|talent(?:s)?(?:\s+acquisition)?|careers?|carrieres?|hiring|team|equipe|rh|hr|jobs?|no-?reply|via|the|l'equipe|service|people)\b", re.I)
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gouv"}


def _domain_name(domain):
    labels = domain.lower().split(".")
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL:
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else domain


def company_of(de, sujet):
    """Best guess of the company behind an application mail: the subject's 'at X', then the sender's domain, then the sender's name."""
    name, addr = parseaddr(de or "")
    domain = addr.rpartition("@")[2]
    said = _AT_COMPANY.search(sujet or "")
    if said:
        return said.group(1).strip(" .,:;!-'’")
    if domain and not _ATS.search(domain) and not _FREE_MAIL.search(domain):
        return _domain_name(domain).capitalize()
    said = _TO_COMPANY.search(sujet or "")
    if said:
        return said.group(1).strip(" .,:;!-'’")
    cleaned = re.sub(r"\s+", " ", _NAME_NOISE.sub(" ", name)).strip(" -|,.")
    return cleaned or (domain and _domain_name(domain).capitalize()) or "inconnu"


def _same_mailbox(addr):
    """Gmail ignores dots and +tags: a.b+x@gmail.com and ab@gmail.com are the same inbox."""
    local, _, domain = str(addr or "").strip().lower().partition("@")
    if domain in ("gmail.com", "googlemail.com"):
        return local.split("+")[0].replace(".", "") + "@gmail.com"
    return f"{local}@{domain}"


def _own_addresses():
    return {_same_mailbox(a["user"]) for a in mail._mail_accounts()}


def applications(days=0, limit=25):
    """One line per company, with where things stand according to the latest mail."""
    limit = max(1, min(int(limit or 25), 60))
    marks = ",".join("?" * len(_APPLICATION_TYPES))
    since = int(time.time()) - int(days) * 86400 if days else 0
    with _db() as con:
        rows = con.execute(f"SELECT * FROM mails WHERE type IN ({marks}) AND date>=? ORDER BY date", (*_APPLICATION_TYPES, since)).fetchall()
    own, companies = _own_addresses(), {}
    for r in _unique(rows):
        if _same_mailbox(parseaddr(r["de"])[1]) in own:
            continue
        name = company_of(r["de"], r["sujet"])
        c = companies.setdefault(norm(name), {"entreprise": name, "premier_mail": _when(r["date"])[:10], "mails": 0})
        c["mails"] += 1
        c.update(statut=_STATUS_WORD[r["type"]], dernier_mail=_when(r["date"])[:10], sujet=(r["sujet"] or "")[:90], id=f"{r['acc']}:{r['uid']}@{r['folder']}")
    ordered = sorted(companies.values(), key=lambda x: x["dernier_mail"], reverse=True)
    counts = {}
    for c in ordered:
        counts[c["statut"]] = counts.get(c["statut"], 0) + 1
    return {"entreprises": len(ordered), "bilan": counts, "liste": ordered[:limit]} | _progress_note()


# ---------------------------------------------------------------- mails that seem to wait for an answer
_ANSWER_TYPES = ("etape", "acceptation", "personne")
_EVENT_SENDER = re.compile(r"luma|eventbrite|meetup\.com|^(?:cal|usr)-|^(?:alerts?|invites?|notifications?)@", re.I)
_NO_ANSWER = re.compile(r"time confirmed|registration|reminder|rappel|confirm[ée]|automatic reply|absence|welcome|bienvenue", re.I)    # nothing to answer


def waiting_for_reply(days=14, min_age_hours=48):
    """Important mails from real senders, from the last days, that no mail of ours answered. A plain message only counts if it asks something."""
    now = int(time.time())
    own = _own_addresses()
    marks = ",".join("?" * len(_ANSWER_TYPES))
    with _db() as con:
        rows = con.execute(f"SELECT * FROM mails WHERE niveau='important' AND type IN ({marks}) AND mid!='' AND date BETWEEN ? AND ? ORDER BY date DESC",
                           (*_ANSWER_TYPES, now - days * 86400, now - min_age_hours * 3600)).fetchall()
        recent = con.execute("SELECT de, refs FROM mails WHERE date>=? AND refs!=''", (now - (days + 30) * 86400,)).fetchall()
    names = {parseaddr(r["de"])[0].lower() for r in recent if _same_mailbox(parseaddr(r["de"])[1]) in own} - {""}   # same person, other address

    def mine(de):
        name, addr = parseaddr(de)
        return _same_mailbox(addr) in own or name.lower() in names

    answered = set()
    for r in recent:
        if mine(r["de"]):
            answered.update(r["refs"].split())
    out = []
    for r in _unique(rows):
        addr = parseaddr(r["de"])[1].lower()
        if (mine(r["de"]) or r["mid"] in answered or mailtriage.NOREPLY.search(addr) or mailtriage.NOISE_SENDER.search(addr)
                or _EVENT_SENDER.search(addr) or _NO_ANSWER.search(r["sujet"] or "")):
            continue
        if r["type"] == "personne" and "?" not in (r["body"] or "")[:1500]:
            continue
        out.append(r)
    return out


def tool(args):
    action = str(args.get("action") or "search").lower()
    if action == "status":
        return status()
    if action == "stats":
        return stats()
    if action == "candidatures":
        return applications(args.get("days") or 0, args.get("limit") or 25)
    if action == "sans_reponse":
        return {"mails": [_row(r) for r in waiting_for_reply()[:15]]} | _progress_note()
    return search(str(args.get("query") or ""), str(args.get("de") or ""), str(args.get("type") or ""), args.get("days") or 0, args.get("limit") or 15)
