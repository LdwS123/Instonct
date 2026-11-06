"""Reads the calendar invitation (.ics) that comes with an interview mail. The real date and hour are often ONLY in this file, never in the mail text.

Pure text work, no network. A time we cannot place with certainty is left out: better no time than a wrong one.
"""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
_PROP = re.compile(r"^([A-Z-]+)((?:;[^:]*)*):(.*)$")


def _unfold(raw):
    return re.sub(r"\r?\n[ \t]", "", raw or "").replace("\r", "")


def _unescape(v):
    return re.sub(r"\\([nN,;\\])", lambda m: " " if m.group(1) in "nN" else m.group(1), v).strip()


def _when(value, params):
    """A DTSTART/DTEND value as a naive Paris datetime, or None when the zone is unknown."""
    value = value.strip()
    if "VALUE=DATE" in params.upper() and len(value) == 8:
        return None                                               # a whole day: no hour to give
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", value)
    if not m:
        return None
    y, mo, d, h, mi, s, z = m.groups()
    try:
        naive = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0))
    except ValueError:
        return None
    if z:
        return naive.replace(tzinfo=timezone.utc).astimezone(PARIS).replace(tzinfo=None)
    tz = re.search(r"TZID=([^;:]+)", params)
    if not tz:
        return None                                               # floating time: nobody knows whose clock
    try:
        return naive.replace(tzinfo=ZoneInfo(tz.group(1).strip('"'))).astimezone(PARIS).replace(tzinfo=None)
    except Exception:
        return None                                               # a Windows zone name or a typo: do not guess


def events(raw):
    """Every VEVENT of an .ics text: [{'titre', 'debut', 'fin', 'lieu', 'annule'}]. debut/fin are naive Paris times or None."""
    out, cur, method = [], None, ""
    for line in _unfold(raw).split("\n"):
        line = line.strip()
        if line.upper() == "BEGIN:VEVENT":
            cur = {"titre": "", "debut": None, "fin": None, "lieu": "", "annule": False}
        elif line.upper() == "END:VEVENT":
            if cur is not None:
                cur["annule"] = cur["annule"] or method == "CANCEL"
                out.append(cur)
            cur = None
        else:
            m = _PROP.match(line)
            if not m:
                continue
            name, params, value = m.group(1).upper(), m.group(2), m.group(3)
            if name == "METHOD":
                method = value.strip().upper()
            elif cur is None:
                continue
            elif name == "SUMMARY":
                cur["titre"] = _unescape(value)[:120]
            elif name == "LOCATION":
                cur["lieu"] = _unescape(value)[:160]
            elif name == "STATUS":
                cur["annule"] = value.strip().upper() == "CANCELLED"
            elif name == "DTSTART":
                cur["debut"] = _when(value, params)
            elif name == "DTEND":
                cur["fin"] = _when(value, params)
    return out


def line(raw):
    """The words added to a mail body, in the form mailslot.parse reads: 'DATE/TIME: 2026-11-04 10:00-11:00'. '' when there is no usable event."""
    parts = []
    for ev in events(raw)[:2]:
        if ev["annule"]:
            parts.append(f"Invitation annulee : {ev['titre']}")
        elif ev["debut"]:
            end = ev["fin"] if ev["fin"] and ev["fin"].date() == ev["debut"].date() and ev["fin"] > ev["debut"] else None
            span = f"{ev['debut']:%Y-%m-%d %H:%M}" + (f"-{end:%H:%M}" if end else "")
            parts.append(f"Invitation calendrier (.ics) : {ev['titre']} DATE/TIME: {span}" + (f" LOCATION: {ev['lieu']}" if ev["lieu"] else ""))
    return " ".join(parts)


def of_message(msg):
    """The .ics text of a parsed email message (a text/calendar part or an attachment named *.ics), or ''."""
    for part in msg.walk():
        name = (part.get_filename() or "").lower()
        if part.get_content_type() in ("text/calendar", "application/ics") or name.endswith(".ics"):
            try:
                data = part.get_payload(decode=True)
                if data:
                    return data.decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                continue
    return ""
