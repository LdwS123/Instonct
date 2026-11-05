"""Upcoming meetings, from the mailbox and the calendar. For each company the latest mail wins: a moved or cancelled slot must never be shown."""

import re
import time
from datetime import datetime, timedelta
from email.utils import parseaddr

from . import gcal, mailindex, mailslot, mailtriage
from .core import log, norm, scrub

LOOK_BACK_DAYS = 60
_TYPES = ("etape", "rdv", "personne", "acceptation", "candidature", "refus")
_OFF = re.compile(r"^(canceled|cancelled|annule|annulation)\b|canceled event|cancelled event|(has|was|been) cancell?ed|(a ete|est) annule|"
                  r"waitlist|pending approval|not accepted|registration (declined|cancell?ed)|declined")
_EVENT = re.compile(r"luma-mail|lu\.ma|partiful|eventbrite")
_EVENT_WORDS = re.compile(r"^.*?\b(?:confirmed for|approved for|pending approval for|not accepted for|declined for|waitlist for|registered for|invited to)\s+", re.I)
_TEAMTAILOR = re.compile(r"@([\w-]+)\.teamtailor-mail\.")
_PREFIX = re.compile(r"^\s*(invitation( from an unknown sender)?|updated invitation|time confirmed|meeting invite|meeting reminder|rappel d.entretien|re|fwd?)\s*:\s*", re.I)
_TITLE = re.compile(r"-{5,}\s*([^\n]{5,140}?)\s+DATE/(?:TIME|HEURE)")
_WITH = re.compile(r"(?:ATTENDEES|PARTICIPANTS)\s*:?\s+(.{3,80}?)\s+(?:LOCATION|LOCALISATION|RECORDING|ENREGISTREMENT)", re.S)
_VIDEO = re.compile(r"https?://(?:meet\.google\.com/[a-z-]+|[\w.-]*zoom\.us/j/[^\s)>\]]+|teams\.(?:microsoft\.com/l/meetup|live\.com/)[^\s)>\]]*)")
_DETAILS = re.compile(r"https?://[^\s)>\]]+/schedule/[0-9a-f-]{36}(?!/|[0-9a-f-])")
_SYMBOLS = re.compile(r"[^\w\s\-–'’()/.,:&+@]")


def _clean(text):
    return re.sub(r"\s+", " ", _SYMBOLS.sub("", text or "")).strip(" -")


def _is_event(de):
    return bool(_EVENT.search(parseaddr(de or "")[1].lower()))


def _key(r):
    """Which meeting this mail is about. Events are told apart by their name, the rest by company."""
    if _is_event(r["de"]):
        return "evt:" + norm(_EVENT_WORDS.sub("", re.sub(r"\s+", " ", r["sujet"] or "")))[:60]
    return norm(_company(r))


def _company(r):
    if _is_event(r["de"]):
        return _clean(parseaddr(r["de"])[0]) or "evenement"
    m = _TEAMTAILOR.search(r["de"] or "")
    return m.group(1).capitalize() if m else mailindex.company_of(r["de"], r["sujet"])


def _title(r):
    body = r["body"] or ""
    m = _TITLE.search(body)
    if m:
        return _clean(m.group(1))[:110]
    subject = _EVENT_WORDS.sub("", _PREFIX.sub("", re.sub(r"\s+", " ", r["sujet"] or "")))
    return _clean(subject.split(" @ ")[0])[:110]


def _link(body):
    m = _VIDEO.search(body or "")
    return m.group(0) if m else ""


def _from_mails():
    """Newest mail first: the first mail that settles a meeting (new time, cancellation, refusal) decides for all the older ones."""
    since = int(time.time()) - LOOK_BACK_DAYS * 86400
    marks = ",".join("?" * len(_TYPES))
    with mailindex._db() as con:
        rows = con.execute(f"SELECT * FROM mails WHERE date>=? AND type IN ({marks}) ORDER BY date DESC", (since, *_TYPES)).fetchall()
    own = mailindex._own_addresses()
    settled, video, details, undated = {}, {}, {}, []
    for r in mailindex._unique(rows):
        if mailindex._same_mailbox(parseaddr(r["de"])[1]) in own:
            continue
        key, body = _key(r), r["body"] or ""
        video[key] = video.get(key) or _link(body)
        if key not in details:
            m = _DETAILS.search(body)
            if m:
                details[key] = m.group(0)
        if key in settled:
            continue
        if r["type"] == "refus" or _OFF.search(norm(re.sub(r"\s+", " ", r["sujet"] or ""))):
            settled[key] = None
            continue
        slot = mailslot.parse(r["sujet"], body, r["date"])
        if slot:
            with_whom = _WITH.search(body)
            settled[key] = slot | {"entreprise": _company(r), "titre": _title(r), "avec": _clean(with_whom.group(1))[:60] if with_whom else "",
                                   "id": f"{r['acc']}:{r['uid']}@{r['folder']}", "source": "mail", "event": _is_event(r["de"])}
        elif r["type"] == "etape":
            undated.append((key, r))
    found = [dict(v, lien=video.get(k) or details.get(k, "")) for k, v in settled.items() if v]
    no_time = [{"entreprise": _company(r), "sujet": _clean(r["sujet"])[:90], "recu_le": f"{datetime.fromtimestamp(r['date']):%d/%m}"}
               for k, r in undated if k not in settled and r["date"] >= time.time() - 14 * 86400]
    return found, no_time


def _from_calendar(days):
    try:
        if not (gcal.connected() and gcal.token_ok()):
            return []
        out = []
        for ev in gcal.list_events(days):
            try:
                start = datetime.strptime(ev["debut"], "%Y-%m-%d %H:%M")
            except ValueError:
                continue                                                        # a whole-day event has no time to remind
            end = None
            if ev.get("fin"):
                end = datetime.strptime(f"{ev['debut'][:10]} {ev['fin']}", "%Y-%m-%d %H:%M")
            link = ev.get("meet") or next(iter(re.findall(r"https?://\S+", ev.get("lieu", ""))), "")
            out.append({"debut": start, "fin": end, "sur": True, "entreprise": "", "titre": ev.get("titre", ""), "avec": "", "id": ev["id"],
                        "source": "agenda", "event": False, "lien": link, "lieu": ev.get("lieu", "")})
        return out
    except Exception as e:
        log.warning("agenda illisible pour les rendez-vous : %s", scrub(e))
        return []


def _not_over(m, now):
    return (m["fin"] or m["debut"] + timedelta(minutes=30)) > now


def _same_meeting(a, b):
    words = [{w for w in norm(f"{m['entreprise']} {m['titre']}").split() if len(w) >= 4} for m in (a, b)]
    return a["debut"] == b["debut"] and bool(words[0] & words[1])


def upcoming(days=14, now=None):
    """Meetings that are not over yet, soonest first. Returns (meetings, mails that speak of a meeting without a time)."""
    now = now or datetime.now()
    last = now + timedelta(days=days)
    try:
        mails, no_time = _from_mails()
    except Exception as e:
        log.warning("mails illisibles pour les rendez-vous : %s", scrub(e))
        mails, no_time = [], []
    found = [m for m in mails if _not_over(m, now) and m["debut"] <= last]
    for ev in _from_calendar(days):
        if not _not_over(ev, now) or ev["debut"] > last:
            continue
        twin = next((m for m in found if _same_meeting(m, ev)), None)
        if twin:                                                                # the sender's link wins: a Meet room made in the calendar may be empty
            twin["lien"] = twin["lien"] or ev["lien"]
            twin["lieu"] = twin.get("lieu") or ev["lieu"]
        else:
            found.append(ev)
    return sorted(found, key=lambda m: m["debut"]), no_time


def tool(args):
    days = max(1, min(int(args.get("days") or 14), LOOK_BACK_DAYS))
    wanted = norm(str(args.get("entreprise") or ""))
    now = datetime.now()
    found, no_time = upcoming(days, now)
    if wanted:
        found = [m for m in found if wanted in norm(f"{m['entreprise']} {m['titre']} {m['avec']}")]
        no_time = [x for x in no_time if wanted in norm(f"{x['entreprise']} {x['sujet']}")]
    items = []
    for m in sorted(sorted(found, key=lambda m: m["event"])[:20], key=lambda m: m["debut"]):    # a crowded week of events must not hide an interview
        item = {"quand": mailslot.label(m["debut"], m["fin"], now), "entreprise": m["entreprise"], "titre": m["titre"], "source": m["source"], "id": m["id"]}
        item.update({k: m[k] for k in ("avec", "lien", "lieu") if m.get(k)})
        if m["event"]:
            item["genre"] = "evenement"
        if not m["sur"]:
            item["attention"] = "date lue dans une phrase du mail : peut-etre une simple proposition, a verifier"
        items.append(item)
    out = {"maintenant": mailslot.label(now, None, now), "rendez_vous": items, "regle": "Recopie 'quand' tel quel, sans recalculer."}
    if no_time:
        out["sans_heure_dans_le_mail"] = no_time[:6]
    return out


def reminder(m, minutes):
    name = f"{m['entreprise']} : {m['titre']}" if m["entreprise"] and norm(m["entreprise"]) not in norm(m["titre"]) else (m["titre"] or m["entreprise"])
    text = f"Dans {int(minutes)} minutes : {name} à {m['debut']:%Hh%M}."
    if m.get("avec"):
        text += f"\nAvec : {m['avec']}"
    if m.get("lien"):
        text += f"\nLien : {m['lien']}"
    elif m.get("lieu"):
        text += f"\nLieu : {m['lieu']}"
    return text
