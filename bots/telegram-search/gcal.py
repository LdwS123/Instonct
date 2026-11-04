"""Google Agenda (+ liens Google Meet) pour le bot, sans bibliotheque Google : juste des appels web (requests).

Le jeton est dans ~/bots/google_token.json (client_id, client_secret, refresh_token), cree une seule fois
par scripts/google-auth.py. Tout est en heure de Paris.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", os.path.expanduser("~/bots/google_token.json"))
TZ = ZoneInfo("Europe/Paris")
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_cache = {"tok": None, "exp": 0.0}


def connected():
    return os.path.exists(TOKEN_FILE)


def _token():
    if _cache["tok"] and time.time() < _cache["exp"] - 60:
        return _cache["tok"]
    cfg = json.load(open(TOKEN_FILE))
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError("autorisation Google refusee ou expiree : relancer scripts/google-auth.py")
    d = r.json()
    _cache.update(tok=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)))
    return _cache["tok"]


def _call(method, url, **kw):
    r = requests.request(method, url, headers={"Authorization": "Bearer " + _token()}, timeout=20, **kw)
    if r.status_code == 204:
        return {}
    if r.status_code >= 300:
        raise RuntimeError(f"Google Agenda {r.status_code} : {r.text[:150]}")
    return r.json()


def parse_dt(s):
    """'2026-11-05 14:30' ou '2026-11-05T14:30' -> datetime heure de Paris."""
    s = s.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise ValueError("date non comprise (format attendu : AAAA-MM-JJ HH:MM)")


def _fmt(ev):
    st = ev.get("start", {})
    when = st.get("dateTime") or st.get("date") or ""
    out = {"id": ev["id"], "titre": ev.get("summary", "(sans titre)"), "debut": when[:16].replace("T", " ")}
    end = ev.get("end", {}).get("dateTime")
    if end:
        out["fin"] = end[11:16]
    if ev.get("location"):
        out["lieu"] = ev["location"][:80]
    meet = ev.get("hangoutLink")
    if meet:
        out["meet"] = meet
    if ev.get("attendees"):
        out["invites"] = [a.get("email") for a in ev["attendees"]][:8]
    return out


def list_events(days=1, start=None):
    t0 = parse_dt(start) if start else datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    t1 = t0 + timedelta(days=max(1, min(int(days), 31)))
    d = _call("GET", API, params={"timeMin": t0.isoformat(), "timeMax": t1.isoformat(), "singleEvents": "true",
                                  "orderBy": "startTime", "maxResults": 30})
    return [_fmt(e) for e in d.get("items", [])]


def create_event(title, start, duration_min=60, invites=None, meet=False, description="", location=""):
    t0 = parse_dt(start)
    body = {"summary": title[:200], "start": {"dateTime": t0.isoformat(), "timeZone": "Europe/Paris"},
            "end": {"dateTime": (t0 + timedelta(minutes=max(5, min(int(duration_min), 1440)))).isoformat(),
                    "timeZone": "Europe/Paris"}}
    if description:
        body["description"] = description[:2000]
    if location:
        body["location"] = location[:200]
    mails = [m for m in (invites or []) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(m))]
    if mails:
        body["attendees"] = [{"email": m} for m in mails]
    params = {"sendUpdates": "all" if mails else "none"}
    if meet:
        body["conferenceData"] = {"createRequest": {"requestId": uuid.uuid4().hex,
                                                    "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
        params["conferenceDataVersion"] = 1
    return _fmt(_call("POST", API, params=params, json=body))


def delete_event(event_id):
    _call("DELETE", f"{API}/{re.sub(r'[^A-Za-z0-9_]', '', event_id)}", params={"sendUpdates": "none"})
    return True
