"""Habit learning for Instonct: no AI call, no extra quota. Everything is simple counting in Redis.

What it learns (only from what the owner does with the bot):
  - which music, cities, tools he uses, and at which time of day
  - at what time he usually writes for the first time each day
What it does with it:
  - summary()  -> a few short lines added to the assistant's instructions, so answers fit his habits
  - detect()   -> a safe thing he does at the same hour on several days -> the bot OFFERS to do it by itself (he must press Yes)
Nothing is sent anywhere. forget() erases everything.
"""
import hashlib
import statistics
import time
import unicodedata
from datetime import datetime

KEEP_DAYS = 45            # how long a "this happened at this hour" trace is kept
WINDOW_DAYS = 14          # detect() only looks at the last 14 days
MIN_DAYS = 4              # same thing, same hour, on at least 4 different days -> worth offering
SUGGESTABLE = {"music", "weather", "agenda", "mail", "news", "todo"}     # never the TV: the family uses it
MAX_FIELDS = 400

LABEL = {"music": "musique", "tv": "tele", "weather": "meteo", "agenda": "agenda", "mail": "emails", "news": "actualites",
         "todo": "taches", "status": "etat du Mac mini", "routine": "routines", "list": "listes", "volume": "volume"}
PARTS = [(5, 12, "le matin"), (12, 18, "l'apres-midi"), (18, 24, "le soir"), (0, 5, "la nuit")]


def norm(s, n=60):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())[:n]


def part_of(hour):
    for a, b, name in PARTS:
        if a <= hour < b:
            return name
    return "le soir"


def hid(kind, key, hour):
    return hashlib.md5(f"{kind}|{key}|{hour}".encode()).hexdigest()[:8]


def track(db, kind, key="", now=None):
    """One thing happened (kind = music, weather, tv...; key = what exactly, e.g. a song title or a city)."""
    now = now or datetime.now()
    key = norm(key)
    field = f"{kind}|{key}"
    pipe = db.pipeline()
    pipe.zincrby("hab:top", 1, field)
    pipe.sadd("hab:kinds", kind)
    pipe.hincrby(f"hab:part:{kind}", part_of(now.hour), 1)
    pipe.zadd(f"hab:days:{field}|{now.hour}", {now.strftime("%Y-%m-%d"): now.timestamp()})
    pipe.expire(f"hab:days:{field}|{now.hour}", KEEP_DAYS * 86400)
    pipe.execute()
    if db.zcard("hab:top") > MAX_FIELDS:                      # keeps the memory small: drop the rarest
        db.zremrangebyrank("hab:top", 0, 49)


def message(db, now=None):
    """The owner wrote to the bot: remembers the hour of the first message of each day."""
    now = now or datetime.now()
    if now.hour >= 5 and db.set(f"hab:first:{now:%Y-%m-%d}", now.hour, nx=True, ex=3 * 86400):
        db.rpush("hab:firsts", now.hour)
        db.ltrim("hab:firsts", -30, -1)


def wake_hour(db):
    hours = [int(h) for h in db.lrange("hab:firsts", 0, -1)]
    return int(statistics.median(hours)) if len(hours) >= 3 else None


def _top(db, kind, n=3, min_count=2):
    out = []
    for field, c in db.zrevrange("hab:top", 0, -1, withscores=True):
        k, _, key = field.partition("|")
        if k == kind and key and c >= min_count:
            out.append((key, int(c)))
            if len(out) == n:
                break
    return out


def summary(db):
    """A few short lines (about 100 tokens) for the assistant's instructions. '' while there is not enough data."""
    lines = []
    music = _top(db, "music")
    if music:
        lines.append("Musique qu'il demande le plus : " + ", ".join(f"{k} ({c}x)" for k, c in music) + ".")
    cities = _top(db, "weather", 1)
    if cities:
        lines.append(f"Ville dont il demande la meteo : {cities[0][0]}.")
    by_part = {}
    for kind in db.smembers("hab:kinds"):
        for part, c in db.hgetall(f"hab:part:{kind}").items():
            if int(c) >= 3:
                by_part.setdefault(part, []).append((int(c), LABEL.get(kind, kind)))
    for _, _, part in PARTS[:3]:
        top = sorted(by_part.get(part, []), reverse=True)[:3]
        if top:
            lines.append(f"{part.capitalize()} il utilise surtout : " + ", ".join(f"{k} ({c}x)" for c, k in top) + ".")
    wake = wake_hour(db)
    if wake is not None:
        lines.append(f"Il ecrit en general pour la premiere fois vers {wake} h.")
    return "\n".join(lines)


def detect(db, now=None):
    """The strongest safe habit not yet offered: same action, same hour, >= MIN_DAYS different days. dict or None."""
    now = now or datetime.now()
    since = now.timestamp() - WINDOW_DAYS * 86400
    best = None
    for field, total in db.zrevrange("hab:top", 0, 80, withscores=True):
        kind, _, key = field.partition("|")
        if kind not in SUGGESTABLE or total < MIN_DAYS or (kind == "music" and not key):
            continue
        pipe = db.pipeline()
        for h in range(24):
            pipe.zcount(f"hab:days:{field}|{h}", since, "+inf")
        for h, days in enumerate(pipe.execute()):
            if days >= MIN_DAYS and not db.exists(f"hab:sugg:{hid(kind, key, h)}"):
                if best is None or days > best["days"]:
                    best = {"id": hid(kind, key, h), "kind": kind, "key": key, "hour": h, "days": int(days)}
    return best


def mark(db, sid, state):
    """state: 'asked' (ask again in 7 days), 'no' (not for 60 days), 'yes' (never ask again)."""
    ttl = {"asked": 7 * 86400, "no": 60 * 86400, "yes": None}[state]
    db.set(f"hab:sugg:{sid}", state, ex=ttl)


def forget(db):
    n = 0
    for key in db.scan_iter("hab:*"):
        n += db.delete(key)
    return n
