"""E-mail over IMAP/SMTP: list, search, read, clean, reply, contacts, send with confirmation."""

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime
from datetime import timedelta
from email.utils import parsedate_to_datetime
import time

from . import mailslot, mailtriage
from .core import db, log, scrub
from . import callbacks

# ---------------------------------------------------------------- emails (lecture seule, IMAP)
_HOSTS = {"yahoo": "imap.mail.yahoo.com", "gmail": "imap.gmail.com", "googlemail": "imap.gmail.com",
          "outlook": "outlook.office365.com", "hotmail": "outlook.office365.com", "live": "outlook.office365.com",
          "icloud": "imap.mail.me.com", "me": "imap.mail.me.com", "orange": "imap.orange.fr", "free": "imap.free.fr"}
def _mail_accounts():
    """Boites configurees : MAIL_USER/MAIL_PASS puis MAIL_USER_2/MAIL_PASS_2, _3, _4 (host devine d'apres l'adresse)."""
    out = []
    for i, sfx in enumerate(["", "_2", "_3", "_4"], 1):
        u, pw = os.environ.get("MAIL_USER" + sfx, ""), os.environ.get("MAIL_PASS" + sfx, "")
        host = os.environ.get("MAIL_HOST" + sfx) or _HOSTS.get(u.split("@")[-1].split(".")[0].lower(), "")
        if u and pw and host:
            out.append({"n": i, "user": u, "pw": pw, "host": host})
    return out


def _imap_q(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _mail_open(n=1, folder="INBOX", readonly=True):
    import imaplib
    acc = next((a for a in _mail_accounts() if a["n"] == n), None)
    if not acc:
        raise RuntimeError("boite mail non configuree (MAIL_USER / MAIL_PASS dans .env)")
    c = imaplib.IMAP4_SSL(acc["host"], timeout=20)
    c.login(acc["user"], acc["pw"])
    c.select(_imap_q(folder), readonly=readonly)     # lecture seule par defaut : rien n'est marque comme lu, rien n'est supprime
    return c


def _mail_dec(v):
    from email.header import Header, decode_header, make_header
    try:
        if isinstance(v, Header):       # raw 8-bit header: the email library only gives it back as question marks
            data = b"".join(p if isinstance(p, bytes) else p.encode() for p, _ in decode_header(v))
            try:
                v = data.decode()
            except UnicodeDecodeError:
                v = data.decode("latin-1")
        return str(make_header(decode_header(v or ""))).strip()
    except Exception:
        return str(v or "")


_HDRS = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-UNSUBSCRIBE PRECEDENCE MESSAGE-ID)])"


def _bulk(h):
    """True if the mail is a mass mailing (List-Unsubscribe header or Precedence: bulk/list/junk)."""
    return bool(h["List-Unsubscribe"]) or str(h["Precedence"] or "").strip().lower() in ("bulk", "list", "junk")


def _tri(de, sujet, h, body=""):
    return mailtriage.classify(de, sujet, body, _bulk(h))


def mail_list(query, unread_only, limit, important_only=False, raw=False):
    """important_only : ne garde que les mails importants (pas les pubs). raw : garde les infos internes (pour check_mail)."""
    import email
    accounts = _mail_accounts()
    if not accounts:
        return {"erreur": "boite mail non configuree"}
    out, errs = [], []
    for acc in accounts:
        try:
            c = _mail_open(acc["n"])
            try:
                crit = ["UNSEEN"] if unread_only else ["ALL"]
                q = re.sub(r'[^A-Za-z0-9@._ -]', "", query).strip()
                if q:
                    crit += ["OR", "FROM", f'"{q}"', "SUBJECT", f'"{q}"']
                typ, data = c.uid("search", None, *crit)
                cap = 40 if important_only else 15
                for u in data[0].split()[-max(1, min(limit, cap)):][::-1]:
                    typ, d = c.uid("fetch", u, _HDRS)
                    h = email.message_from_bytes(d[0][1])
                    de, sujet = _mail_dec(h["From"])[:80], _mail_dec(h["Subject"])[:120]
                    t = _tri(de, sujet, h)
                    if important_only and t["niveau"] != "important":
                        continue
                    e = {"id": f"{acc['n']}:{u.decode()}", "boite": acc["user"], "de": de, "sujet": sujet, "envoye_le": (h["Date"] or "")[:25],
                         "tri": t["label"] if t["niveau"] == "important" else "PUB"}
                    if raw:
                        e["_tri"], e["_bulk"] = t, _bulk(h)
                    out.append(e)
            finally:
                c.logout()
        except Exception as e:
            errs.append(f"{acc['user']} : {scrub(e)[:120]}")
    res = {"emails": out or ("aucun email important" if important_only else "aucun email correspondant")}
    if errs:
        res["erreurs"] = errs
    return res


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mail_folders(c, gmail):
    """Dossiers a fouiller. Gmail : 'Tous les messages' + Spam (le reste y est deja). Les autres : tout sauf corbeille et brouillons."""
    typ, data = c.list()
    out = []
    for raw in data or []:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        m = re.match(r'\((?P<fl>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.+)$', line)
        if not m:
            continue
        fl, name = m.group("fl").lower(), m.group("name").strip()
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if "\\noselect" in fl or "\\trash" in fl or "\\drafts" in fl:
            continue
        if re.search(r"trash|corbeille|deleted|brouillon|draft", name, re.I) and "\\junk" not in fl:
            continue
        if gmail and "\\all" not in fl and "\\junk" not in fl:
            continue
        out.append(name)
    if not out:
        out = ["INBOX"]
    return out[:15]


def mail_search(query, days=365):
    """Recherche large : tous les dossiers de toutes les boites, dans l'en-tete ET le texte. D'abord tous les mots, sinon l'un des mots."""
    import email
    from email.utils import parsedate_to_datetime
    accounts = _mail_accounts()
    if not accounts:
        return {"erreur": "boite mail non configuree"}
    ascii_q = unicodedata.normalize("NFKD", str(query or "")).encode("ascii", "ignore").decode()
    words = [w for w in re.findall(r"[A-Za-z0-9@._-]{3,}", ascii_q)][:5]
    if not words:
        return {"erreur": "donne au moins un mot-cle de 3 lettres ou plus"}
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        days = 365
    since = (datetime.now() - timedelta(days=days)) if days > 0 else None
    found, errs, folders_done, mode = {}, [], 0, "tous les mots"
    for strict in (True, False):
        if not strict and len(words) == 1:
            break
        mode = "tous les mots" if strict else "au moins un des mots"
        for acc in accounts:
            try:
                c = _mail_open(acc["n"])
                try:
                    gmail = "gmail" in acc["host"] or "google" in acc["host"]
                    for folder in _mail_folders(c, gmail):
                        typ, _ = c.select(_imap_q(folder), readonly=True)
                        if typ != "OK":
                            continue
                        folders_done += 1
                        crit = []
                        if since:
                            crit += ["SINCE", f"{since.day:02d}-{_MONTHS[since.month - 1]}-{since.year}"]
                        if gmail:
                            crit += ["X-GM-RAW", '"' + (" ".join(words) if strict else "(" + " OR ".join(words) + ")") + '"']
                        elif strict:
                            for w in words:
                                crit += ["TEXT", f'"{w}"']
                        else:
                            chain = [f'TEXT "{w}"' for w in words]
                            expr = chain[-1]
                            for part in reversed(chain[:-1]):
                                expr = f"OR {part} {expr}"
                            crit += re.findall(r'"[^"]*"|\S+', expr)
                        typ, data = c.uid("search", None, *crit)
                        if typ != "OK":
                            continue
                        for u in data[0].split()[-12:]:
                            typ, d = c.uid("fetch", u, _HDRS)
                            h = email.message_from_bytes(d[0][1])
                            try:
                                when = parsedate_to_datetime(h["Date"]).replace(tzinfo=None)
                            except Exception:
                                when = datetime(1970, 1, 1)
                            key = (acc["n"], _mail_dec(h["Subject"])[:60], str(h["Date"])[:25])      # meme mail vu dans 2 dossiers : une seule fois
                            if key not in found:
                                found[key] = (when, {"id": f"{acc['n']}:{u.decode()}" + ("" if folder == "INBOX" else "@" + folder),
                                                     "boite": acc["user"], "dossier": folder, "de": _mail_dec(h["From"])[:80],
                                                     "sujet": _mail_dec(h["Subject"])[:120], "envoye_le": str(h["Date"] or "")[:25],
                                                     "tri": (lambda t: t["label"] if t["niveau"] == "important" else "PUB")(
                                                         _tri(_mail_dec(h["From"])[:80], _mail_dec(h["Subject"])[:120], h))})
                finally:
                    try:
                        c.logout()
                    except Exception:
                        pass
            except Exception as e:
                errs.append(f"{acc['user']} : {scrub(e)[:120]}")
        if found:
            break
    emails = [v[1] for v in sorted(found.values(), key=lambda x: x[0], reverse=True)][:25]
    res = {"emails": emails or "aucun email trouve", "cherche": f"{folders_done} dossier(s), {len(accounts)} boite(s), mots : {', '.join(words)} ({mode})"}
    if not emails:
        res["conseil"] = "retente avec d'autres mots-cles (nom de l'entreprise, de la personne, du site) ou days=0 pour chercher depuis toujours"
    if errs:
        res["erreurs"] = errs
    return res


_MEET = re.compile(r"meet\.google\.com|zoom\.us|teams\.microsoft\.com|teams\.live\.com|whereby\.com|calendly\.com|cal\.com|webex\.com|gotomeet|around\.co", re.I)
_JUNK_URL = re.compile(r"unsub|desabonn|d[eé]sinscri|optout|opt-out|preferences|\.(png|jpe?g|gif|svg|css|ico)(\?|$)|pixel|track(ing)?\.|/open\?|mailto:", re.I)


def _mail_links(raw):
    """Les VRAIS liens d'un mail : d'abord les liens de visio (Meet, Zoom, Teams...), puis quelques autres. Jamais les liens de desinscription."""
    import html as _html
    urls = []
    for u in re.findall(r"https?://[^\s\"'<>)\]]+", _html.unescape(raw or "")):
        u = u.rstrip(".,;")
        if u not in urls and not _JUNK_URL.search(u):
            urls.append(u)
    meet = [u for u in urls if _MEET.search(u)]
    return (meet + [u for u in urls if u not in meet][:4])[:6]


def _slot_words(subject, body, sent):
    """The meeting time written in the mail, in words. Never the date it was sent."""
    try:
        when = parsedate_to_datetime(sent).timestamp()
    except (TypeError, ValueError):
        when = 0
    slot = mailslot.parse(subject, body, when)
    return mailslot.label(slot["debut"], slot["fin"]) if slot else "aucune heure de rendez-vous dans ce mail"


def mail_read(uid):
    import email
    n, _, rest = (uid if ":" in uid else "1:" + uid).partition(":")
    num, _, folder = rest.partition("@")
    try:
        c = _mail_open(int(re.sub(r"\D", "", n) or 1), folder or "INBOX")
        try:
            typ, d = c.uid("fetch", re.sub(r"\D", "", num), "(BODY.PEEK[])")
            m = email.message_from_bytes(d[0][1])
            text = ""
            for part in m.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
            if not text:
                for part in m.walk():
                    if part.get_content_type() == "text/html":
                        html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                        text = re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", html, flags=re.S)
                        break
            files = [_mail_dec(p.get_filename()) for p in m.walk() if p.get_filename()][:8]
            raw_txt = []
            for part in m.walk():
                if part.get_content_type() in ("text/plain", "text/html") and not part.get_filename():
                    try:
                        raw_txt.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace"))
                    except Exception:
                        pass
            liens = _mail_links(" ".join(raw_txt))
            body = re.sub(r"\s+", " ", text).strip()
            de, sujet = _mail_dec(m["From"])[:80], _mail_dec(m["Subject"])[:120]
            t = _tri(de, sujet, m, body + (" invitation .ics" if any(f.lower().endswith(".ics") for f in files) else ""))
            return {"de": de, "a": _mail_dec(m["To"])[:80], "sujet": sujet,
                    "envoye_le": (m["Date"] or "")[:31], "pieces_jointes": files or "aucune",
                    "rendez_vous": _slot_words(sujet, text, m["Date"]),
                    "tri": f"{t['niveau'].upper()} - {t['label']} ({t['raison']})",
                    "liens": liens or "aucun", "texte": body[:4000]}
        finally:
            c.logout()
    except Exception as e:
        return {"erreur": scrub(e)[:200]}


# ---------------------------------------------------------------- emails : agir (corbeille, archive, lu, spam, nettoyage, reponse)
def _parse_mid(mid):
    """'2:123@Dossier' -> (boite 2, uid '123', dossier)."""
    n, _, rest = (mid if ":" in mid else "1:" + mid).partition(":")
    num, _, folder = rest.partition("@")
    return int(re.sub(r"\D", "", n) or 1), re.sub(r"\D", "", num), folder or "INBOX"


def _special_folder(c, kind):
    """Nom du dossier corbeille / spam / archives de la boite (d'apres les drapeaux IMAP, sinon d'apres le nom)."""
    flag = {"trash": "\\trash", "junk": "\\junk", "archive": "\\archive"}[kind]
    rx = {"trash": r"trash|corbeille|deleted|supprim", "junk": r"junk|spam|bulk|indesirable", "archive": r"^archive|archiv"}[kind]
    typ, data = c.list()
    by_name = None
    for raw in data or []:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        m = re.match(r'\((?P<fl>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.+)$', line)
        if not m:
            continue
        name = m.group("name").strip().strip('"')
        if flag in m.group("fl").lower():
            return name
        if by_name is None and re.search(rx, name, re.I) and "\\noselect" not in m.group("fl").lower():
            by_name = name
    return by_name


def _mail_act(c, gmail, uid, action):
    """Une action sur un mail deja selectionne en ecriture. Rien n'est jamais efface pour de bon : 'supprimer' = corbeille (recuperable)."""
    if action in ("read", "unread"):
        c.uid("store", uid, "+FLAGS" if action == "read" else "-FLAGS", "(\\Seen)")
    elif action in ("star", "unstar"):
        c.uid("store", uid, "+FLAGS" if action == "star" else "-FLAGS", "(\\Flagged)")
    elif gmail and action == "delete":
        c.uid("store", uid, "+X-GM-LABELS", "(\\Trash)")
    elif gmail and action == "spam":
        c.uid("store", uid, "+X-GM-LABELS", "(\\Spam)")
        c.uid("store", uid, "-X-GM-LABELS", "(\\Inbox)")
    elif gmail and action == "archive":
        c.uid("store", uid, "-X-GM-LABELS", "(\\Inbox)")
    else:                                              # Yahoo, Outlook, iCloud... : on copie dans le bon dossier puis on retire de celui-ci
        dest = _special_folder(c, {"delete": "trash", "spam": "junk", "archive": "archive"}[action])
        if not dest:
            raise RuntimeError("dossier " + {"delete": "corbeille", "spam": "spam", "archive": "archives"}[action] + " introuvable")
        typ, _ = c.uid("copy", uid, _imap_q(dest))
        if typ != "OK":
            raise RuntimeError("copie vers " + dest + " refusee")
        c.uid("store", uid, "+FLAGS", "(\\Deleted)")


TRASH_LOG = "mail_trash_log"
TRASH_DAYS = 30                                        # Gmail empties its trash after about 30 days


def _log_trash(n, message_id, de, sujet):
    """Remembers what the bot put in the trash, so it can be put back."""
    if message_id:
        db.lpush(TRASH_LOG, json.dumps({"n": n, "mid": message_id, "de": de[:80], "sujet": sujet[:100], "at": time.time()}, ensure_ascii=False))
        db.ltrim(TRASH_LOG, 0, 199)


def _trash_mail(c, gmail, uid, n):
    """Puts one mail in the trash and logs it."""
    import email
    typ, d = c.uid("fetch", uid, _HDRS)
    h = email.message_from_bytes(d[0][1]) if typ == "OK" and d and d[0] and isinstance(d[0], tuple) else {}
    _mail_act(c, gmail, uid, "delete")
    if h:
        _log_trash(n, (h["Message-ID"] or "").strip(), _mail_dec(h["From"]), _mail_dec(h["Subject"]))


def mail_undo(query="", limit=10):
    """Puts mails the bot trashed back in the inbox. query = a word of the sender or subject; without it, the last batch. Never deletes anything."""
    now = time.time()
    entries = []
    for raw in db.lrange(TRASH_LOG, 0, -1):
        e = json.loads(raw)
        if now - e["at"] < TRASH_DAYS * 86400:
            entries.append((raw, e))
    q = _strip_accents(query).lower().strip()
    if q:
        entries = [x for x in entries if q in _strip_accents(x[1]["de"] + " " + x[1]["sujet"]).lower()]
    elif entries:
        newest = entries[0][1]["at"]
        entries = [x for x in entries if newest - x[1]["at"] < 180]    # same batch: trashed within three minutes of the last one
    entries = entries[:max(1, min(int(limit or 10), 30))]
    done, missing, errs = [], [], []
    for raw, e in entries:
        try:
            c = _mail_open(e["n"], "INBOX", readonly=False)
            try:
                trash = _special_folder(c, "trash")
                if not trash:
                    raise RuntimeError("corbeille introuvable")
                if hasattr(c, "select"):
                    c.select(_imap_q(trash), readonly=False)
                typ, data = c.uid("search", None, "HEADER", "Message-ID", _imap_q(e["mid"]))
                uids = data[0].split() if typ == "OK" and data and data[0] else []
                if not uids:
                    missing.append(e["sujet"])
                    db.lrem(TRASH_LOG, 1, raw)
                    continue
                uid = uids[-1].decode() if isinstance(uids[-1], bytes) else uids[-1]
                try:
                    typ, _ = c.uid("MOVE", uid, "INBOX")
                except Exception:
                    typ = "NO"
                if typ != "OK":                        # server without MOVE: a copy is enough, the trash is left alone
                    typ, _ = c.uid("COPY", uid, "INBOX")
                if typ != "OK":
                    raise RuntimeError("deplacement refuse")
                done.append(f"{e['de'].split('<')[0].strip()[:30]} : {e['sujet'][:55]}")
                db.lrem(TRASH_LOG, 1, raw)
            finally:
                try:
                    c.logout()
                except Exception:
                    pass
        except Exception as ex:
            errs.append(scrub(ex)[:100])
    res = {"remis_dans_la_boite": len(done), "mails": done or "aucun mail recent de ma part a remettre"}
    if missing:
        res["plus_dans_la_corbeille"] = missing[:5]
    if errs:
        res["erreurs"] = errs[:3]
    return res


def _strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(ch) != "Mn")


def important_among(ids):
    """The important mails among these ids (answers to applications, real people, invoices...). A mail that cannot be read counts as important."""
    import email
    groups = {}
    for mid in [str(i) for i in (ids or [])][:30]:
        n, uid, folder = _parse_mid(mid)
        if uid:
            groups.setdefault((n, folder), []).append((mid, uid))
    out = []
    for (n, folder), items in groups.items():
        try:
            c = _mail_open(n, folder, readonly=True)
        except Exception as e:
            log.warning("tri avant suppression : %s", scrub(e))
            out += [{"id": mid, "de": "?", "sujet": "?", "type": "illisible"} for mid, _ in items]
            continue
        try:
            for mid, uid in items:
                try:
                    typ, d = c.uid("fetch", uid, _HDRS)
                    h = email.message_from_bytes(d[0][1])
                    de, sujet = _mail_dec(h["From"])[:80], _mail_dec(h["Subject"])[:100]
                    t = _tri(de, sujet, h)
                    if t["niveau"] != "pub":
                        out.append({"id": mid, "de": de, "sujet": sujet, "type": t["type"]})
                except Exception:
                    out.append({"id": mid, "de": "?", "sujet": "?", "type": "illisible"})
        finally:
            try:
                c.logout()
            except Exception:
                pass
    return out


def mail_manage(ids, action):
    """Supprime (corbeille), archive, marque lu / non lu, spam, etoile : jusqu'a 30 mails d'un coup."""
    if action not in ("delete", "archive", "read", "unread", "spam", "star", "unstar"):
        return {"erreur": "action inconnue : delete, archive, read, unread, spam, star"}
    ids = [str(i) for i in (ids or [])][:30]
    if not ids:
        return {"erreur": "aucun id de mail (utilise ceux de mail_list ou mail_search)"}
    groups = {}
    for mid in ids:
        n, uid, folder = _parse_mid(mid)
        if uid:
            groups.setdefault((n, folder), []).append(uid)
    done, errs = 0, []
    for (n, folder), uids in groups.items():
        try:
            acc = next(a for a in _mail_accounts() if a["n"] == n)
            gmail = "gmail" in acc["host"] or "google" in acc["host"]
            c = _mail_open(n, folder, readonly=False)
            try:
                for uid in uids:
                    try:
                        if action == "delete":
                            _trash_mail(c, gmail, uid, n)
                        else:
                            _mail_act(c, gmail, uid, action)
                        done += 1
                    except Exception as e:
                        errs.append(f"{uid} : {scrub(e)[:80]}")
                if not gmail and action in ("delete", "spam", "archive"):
                    c.expunge()
            finally:
                try:
                    c.logout()
                except Exception:
                    pass
        except Exception as e:
            errs.append(f"boite {n} : {scrub(e)[:100]}")
    res = {"fait": done, "action": action}
    if action == "delete":
        res["note"] = "mis a la corbeille, recuperable avec mail_undo"
    if errs:
        res["erreurs"] = errs[:5]
    return res


def mail_clean(days=30, limit=100, dry_run=False):
    """Nettoie la boite de reception : met a la corbeille toutes les PUBS et newsletters (jamais les mails importants), via le tri."""
    import email
    try:
        days, limit = max(1, int(days or 30)), max(1, min(int(limit or 100), 200))
    except (TypeError, ValueError):
        days, limit = 30, 100
    since = datetime.now() - timedelta(days=days)
    total, shown, errs, seen_inbox = 0, [], [], 0
    for acc in _mail_accounts():
        try:
            gmail = "gmail" in acc["host"] or "google" in acc["host"]
            c = _mail_open(acc["n"], "INBOX", readonly=dry_run)
            try:
                typ, data = c.uid("search", None, "SINCE", f"{since.day:02d}-{_MONTHS[since.month - 1]}-{since.year}")
                victims = []
                for u in data[0].split()[-limit:]:
                    typ, d = c.uid("fetch", u, _HDRS)
                    h = email.message_from_bytes(d[0][1])
                    de, sujet = _mail_dec(h["From"])[:80], _mail_dec(h["Subject"])[:100]
                    seen_inbox += 1
                    t = _tri(de, sujet, h)
                    if t["niveau"] == "pub" and t["type"] in ("pub", "alerte emploi"):
                        victims.append(u)
                        if len(shown) < 6:
                            shown.append(f"{de.split('<')[0].strip()[:30]} : {sujet[:50]}")
                if not dry_run:
                    for u in victims:
                        try:
                            _trash_mail(c, gmail, u, acc["n"])
                        except Exception as e:
                            errs.append(scrub(e)[:80])
                            victims = victims[:-1]
                    if not gmail and victims:
                        c.expunge()
                total += len(victims)
            finally:
                try:
                    c.logout()
                except Exception:
                    pass
        except Exception as e:
            errs.append(f"{acc['user']} : {scrub(e)[:100]}")
    res = {"pubs_trouvees" if dry_run else "mis_a_la_corbeille": total, "mails_examines": seen_inbox, "exemples": shown or "aucun"}
    if not dry_run:
        res["note"] = "recuperables dans la corbeille ; les mails importants n'ont pas ete touches"
    if errs:
        res["erreurs"] = errs[:3]
    return res


def _body_text(m):
    """Texte lisible d'un mail (texte brut, sinon HTML sans balises)."""
    text = ""
    for ctype in ("text/plain", "text/html"):
        for part in m.walk():
            if part.get_content_type() == ctype and not part.get_filename():
                try:
                    raw = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
                text = raw if ctype == "text/plain" else re.sub(r"<(script|style)[^>]*>.*?(?:</\1>|$)|<!--.*?(?:-->|$)|<[^>]+>", " ", raw, flags=re.S)      # a cut-off mail may never close its style block
                if text.strip():
                    return re.sub(r"\s+", " ", text).strip()
    return ""


def mail_reply_request(chat_id, args):
    """Prepare la reponse a un mail (meme fil de discussion) : l'utilisateur voit le texte et appuie sur Envoyer."""
    import email
    from email.utils import parseaddr, getaddresses
    n, uid, folder = _parse_mid(str(args.get("id", "")))
    body = str(args.get("body", "")).strip()
    if not uid or not body:
        return {"erreur": "il faut l'id du mail et le texte de la reponse"}
    try:
        c = _mail_open(n, folder)
        try:
            typ, d = c.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM REPLY-TO TO CC SUBJECT MESSAGE-ID REFERENCES)])")
            h = email.message_from_bytes(d[0][1])
        finally:
            c.logout()
        acc = next(a for a in _mail_accounts() if a["n"] == n)
    except Exception as e:
        return {"erreur": "mail introuvable : " + scrub(e)[:120]}
    to = [parseaddr(_mail_dec(h["Reply-To"] or h["From"]))[1]]
    if args.get("reply_all") is True:
        extra = [a for _, a in getaddresses([str(h["To"] or ""), str(h["Cc"] or "")]) if a and a.lower() != acc["user"].lower()]
        to += [a for a in extra if a not in to]
    to = [x for x in to if re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", x)][:6]
    if not to:
        return {"erreur": "pas d'adresse de reponse dans ce mail"}
    subj = _mail_dec(h["Subject"])
    p = {"id": uuid.uuid4().hex[:6], "acc": n, "to": to, "subject": subj if re.match(r"(?i)^(re|rép|ref)\s*:", subj) else "Re: " + subj,
         "body": body[:5000], "in_reply_to": str(h["Message-ID"] or "").strip(),
         "references": (str(h["References"] or "") + " " + str(h["Message-ID"] or "")).strip()[-900:]}
    db.set(f"pending_mail:{chat_id}", json.dumps(p), ex=900)
    callbacks.send_confirm(chat_id, f"Reponse prete (depuis {acc['user']}) :\nA : {', '.join(to)}\nSujet : {p['subject']}\n\n{p['body']}\n\nJe l'envoie ?",
                 p["id"], "Envoyer")
    return {"statut": "brouillon de reponse montre a l'utilisateur avec des boutons Oui / Non. Ne dis rien de plus."}


_SMTP = {"gmail.com": "smtp.gmail.com", "googlemail.com": "smtp.gmail.com", "yahoo.com": "smtp.mail.yahoo.com", "yahoo.fr": "smtp.mail.yahoo.com",
         "outlook.com": "smtp.office365.com", "hotmail.com": "smtp.office365.com", "hotmail.fr": "smtp.office365.com", "icloud.com": "smtp.mail.me.com"}


def mail_contact(name):
    """Retrouve l'adresse d'une personne a partir de son prenom/nom, dans les mails recus ET envoyes (tous les dossiers).
    Retourne [(adresse, nom affiche, nombre de mails)], les plus frequents d'abord."""
    import email
    from email.utils import getaddresses
    q = re.sub(r"[^A-Za-z0-9 .-]", "", unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()).strip()
    if len(q) < 3:
        return []
    mine = {a["user"].lower() for a in _mail_accounts()}
    count, label = {}, {}
    for acc in _mail_accounts():
        try:
            gmail = "gmail" in acc["host"] or "google" in acc["host"]
            c = _mail_open(acc["n"])
            try:
                for folder in _mail_folders(c, gmail)[:6]:
                    typ, _ = c.select(_imap_q(folder), readonly=True)
                    if typ != "OK":
                        continue
                    typ, data = c.uid("search", None, "OR", "FROM", f'"{q}"', "OR", "TO", f'"{q}"', "CC", f'"{q}"')
                    if typ != "OK":
                        continue
                    for u in data[0].split()[-40:]:
                        typ, d = c.uid("fetch", u, "(BODY.PEEK[HEADER.FIELDS (FROM TO CC)])")
                        if typ != "OK" or not d or not isinstance(d[0], tuple):
                            continue
                        h = email.message_from_bytes(d[0][1])
                        for nm, ad in getaddresses([str(h.get(k) or "") for k in ("From", "To", "Cc")]):
                            ad = ad.lower().strip()
                            if not ad or ad in mine or re.search(r"no-?reply|noreply|notification|mailer-daemon", ad):
                                continue
                            nm = _mail_dec(nm)
                            if q.lower() in (nm + " " + ad).lower():
                                count[ad] = count.get(ad, 0) + 1
                                label.setdefault(ad, nm)
            finally:
                try:
                    c.logout()
                except Exception:
                    pass
        except Exception as e:
            log.info("contact %s : %s", name, scrub(e)[:80])
    return [(a, label.get(a, ""), n) for a, n in sorted(count.items(), key=lambda kv: -kv[1])]


def mail_send_request(chat_id, args):
    """Prepare un email et attend le /oui de l'humain : le texte exact lui est montre, le modele ne peut pas valider seul."""
    raw_to = [str(x).strip() for x in (args.get("to") or [])][:5]
    to, notes = [], []
    for x in raw_to:
        if re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", x):
            to.append(x)
        elif x:                                                    # juste un prenom ou un nom : on cherche l'adresse dans les mails
            found = mail_contact(x)
            if not found:
                return {"erreur": f"je n'ai trouve aucune adresse pour '{x}' dans les mails : demande-la a l'utilisateur"}
            if len(found) > 1 and found[0][2] < 2 * found[1][2]:
                return {"erreur": f"plusieurs adresses possibles pour '{x}' : " + " ; ".join(f"{a} ({n or '?'}, {c} mails)" for a, n, c in found[:4])
                        + ". Demande laquelle a l'utilisateur."}
            to.append(found[0][0])
            notes.append(f"{x} = {found[0][0]}")
    if not to:
        return {"erreur": "adresse du destinataire manquante ou invalide"}
    acc = next((a for a in _mail_accounts() if a["n"] == int(args.get("account", 1) or 1)), None)
    if not acc:
        return {"erreur": "boite mail inconnue"}
    p = {"id": uuid.uuid4().hex[:6], "acc": acc["n"], "to": to, "subject": str(args.get("subject", ""))[:200],
         "body": str(args.get("body", ""))[:5000]}
    db.set(f"pending_mail:{chat_id}", json.dumps(p), ex=900)
    callbacks.send_confirm(chat_id, f"Mail pret (depuis {acc['user']}) :\nA : {', '.join(to)}" + (" (adresse retrouvee dans tes mails)" if notes else "") + f"\nSujet : {p['subject']}\n\n{p['body']}\n\nJe l'envoie ?",
                 p["id"], "Envoyer")
    return {"statut": "brouillon montre a l'utilisateur avec des boutons Oui / Non. Ne dis rien de plus."}


def mail_send_now(p):
    import smtplib
    from email.message import EmailMessage
    acc = next(a for a in _mail_accounts() if a["n"] == p["acc"])
    host = os.environ.get("SMTP_HOST" + ("" if acc["n"] == 1 else f"_{acc['n']}")) or _SMTP.get(acc["user"].split("@")[-1].lower())
    if not host:
        raise RuntimeError("serveur d'envoi inconnu pour " + acc["user"])
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = acc["user"], ", ".join(p["to"]), p["subject"]
    if p.get("in_reply_to"):
        m["In-Reply-To"] = p["in_reply_to"]
        m["References"] = p.get("references") or p["in_reply_to"]
    m.set_content(p["body"])
    with smtplib.SMTP_SSL(host, 465, timeout=25) as s:
        s.login(acc["user"], acc["pw"])
        s.send_message(m)
