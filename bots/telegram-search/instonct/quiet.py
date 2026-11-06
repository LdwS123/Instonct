"""Quiet hours: between two times the Mac mini stays silent (no spoken replies, no spoken reminders) and the bot stops sending non-urgent news.

Leaf module (only `core`): sound, reminders and monitor all ask it, so it must not import any of them.
The setting lives in the Redis hash `quiet`: on ("1"/"0"), start and end as "HH:MM".
"""

import re
from datetime import datetime

from .core import db, norm

_TIME = re.compile(r"(\d{1,2})\s*(?:h|:|heures?)\s*(\d{2})?")


def parse_time(text):
    """'23h', '7:30', '23 h 15' -> 'HH:MM' (None if it is not a valid time)."""
    m = _TIME.search(norm(text))
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2) or 0)
    return f"{hh:02d}:{mm:02d}" if hh < 24 and mm < 60 else None


def _minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def config():
    cfg = db.hgetall("quiet")
    return {"on": cfg.get("on") == "1", "start": cfg.get("start", "23:00"), "end": cfg.get("end", "07:00")}


def is_quiet(now=None):
    cfg = config()
    if not cfg["on"]:
        return False
    now = now or datetime.now()
    cur, a, b = now.hour * 60 + now.minute, _minutes(cfg["start"]), _minutes(cfg["end"])
    if a == b:
        return False
    return a <= cur < b if a < b else cur >= a or cur < b          # a night: 23:00 -> 07:00 crosses midnight


def command(arg):
    """/silence : show, switch off, or set 'start end'. Returns the sentence to send back."""
    n = norm(arg)
    cfg = config()
    if n in ("off", "stop", "non", "coupe", "desactive", "arrete"):
        db.hset("quiet", "on", "0")
        return "Mode silence coupé : le Mac mini peut reparler la nuit."
    if n in ("", "etat", "status"):
        if cfg["on"]:
            return (f"Mode silence actif de {cfg['start']} à {cfg['end']} : pas de voix sur le Mac mini et seulement les alertes importantes. "
                    f"{'(Là, il est en cours.) ' if is_quiet() else ''}/silence off pour l'arrêter.")
        return "Mode silence coupé. Pour la nuit : /silence 23:00 07:00 (ou juste /silence on pour 23h-7h)."
    if n in ("on", "oui", "active"):
        db.hset("quiet", mapping={"on": "1", "start": cfg["start"], "end": cfg["end"]})
        return f"Mode silence activé de {cfg['start']} à {cfg['end']}."
    times = _TIME.findall(norm(arg))
    if len(times) != 2:
        return "Utilisation : /silence 23:00 07:00   (ou /silence on, /silence off)"
    start, end = (f"{int(h):02d}:{int(m or 0):02d}" for h, m in times)
    if not all(int(x[:2]) < 24 and int(x[3:]) < 60 for x in (start, end)):
        return "Ces heures ne sont pas valides. Exemple : /silence 23:00 07:00"
    db.hset("quiet", mapping={"on": "1", "start": start, "end": end})
    return f"Mode silence activé de {start} à {end} : pas de voix sur le Mac mini et seulement les alertes importantes."
