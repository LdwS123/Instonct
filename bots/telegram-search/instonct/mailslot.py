"""Reads the date and time of a meeting out of a mail. This is never the date the mail was sent: confusing the two gave wrong interview times."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import mailtriage

PARIS = ZoneInfo("Europe/Paris")
_EN_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_EN_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_FR_MONTHS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre")
FR_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")

_FORM = re.compile(r"date ?/ ?(?:time|heure)\s*:?\s*(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}))\s+(\d{1,2}):(\d{2})(?:(?:\s*[-–]\s*|\s+)(\d{1,2}):(\d{2}))?")
_TIME = r"(\d{1,2})(?::(\d{2}))?\s?(am|pm)"
_EN = re.compile(rf"\b(?:(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?"
                 rf"[^\w]{{0,6}}(?:at\s+)?{_TIME}(?:(?:\s*(?:[-–]|to)\s*|\s+){_TIME})?(?:\s*\(?(?:gmt|utc)\s?([+-]\d{{1,2}})(?::?\d\d)?\)?)?")
_FR = re.compile(rf"\b({'|'.join(FR_DAYS)})\s+(\d{{1,2}})(?:er)?\s+({'|'.join(_FR_MONTHS)})(?:\s+(\d{{4}}))?\s*(?:,|a|de|des|at)?\s*(\d{{1,2}})\s?h\s?(\d{{2}})?"
                 r"(?:(?:\s*(?:-|–|a|et)\s*|\s+)(\d{1,2})\s?h\s?(\d{2})?)?")
_ELSEWHERE = re.compile(r"^\W*((eastern|pacific|mountain|central)(?! european)|(et|est|edt|pt|pst|pdt|ct|cst|bst|gmt|utc)\b)")     # better no time than a wrong one


def _flat(text):
    return re.sub(r"\s+", " ", mailtriage.own_words(text or ""))


def _day(year, month, day, weekday, days, sent):
    """The date itself. Without a year: the first one not before the mail. A weekday that does not fit means we misread it."""
    try:
        for y in ([int(year)] if year else [sent.year, sent.year + 1]):
            d = datetime(y, month, int(day))
            if year or d.date() >= sent.date():
                return d if not weekday or days[d.weekday()] == weekday else None
    except ValueError:
        pass
    return None


def _h24(hour, ampm):
    hour = int(hour) % 12 if ampm else int(hour)
    return hour + 12 if ampm == "pm" else hour


def _at(day, hour, minute):
    try:
        return day.replace(hour=int(hour), minute=int(minute or 0))
    except (ValueError, AttributeError):
        return None


def _slot(start, end, offset=None, sure=True):
    if not start:
        return None
    if offset is not None:
        tz = timezone(timedelta(hours=int(offset)))
        start = start.replace(tzinfo=tz).astimezone(PARIS).replace(tzinfo=None)
        end = end.replace(tzinfo=tz).astimezone(PARIS).replace(tzinfo=None) if end else None
    return {"debut": start, "fin": end if end and end > start else None, "sur": sure}


def _english(text, sent):
    for m in _EN.finditer(text):
        wd, mon, dd, yy, h1, m1, ap1, h2, m2, ap2, off = m.groups()
        if (not wd and not yy) or _ELSEWHERE.search(text[m.end():m.end() + 25]):
            continue
        day = _day(yy, _EN_MONTHS.index(mon) + 1, dd, wd, _EN_DAYS, sent)
        slot = day and _slot(_at(day, _h24(h1, ap1), m1), _at(day, _h24(h2, ap2), m2) if h2 else None, off)
        if slot:
            return slot
    return None


def parse(subject, body, sent_ts):
    """{'debut', 'fin', 'sur'} in Paris time, or None. 'sur' is False for a date found in a sentence: it may only be a proposal."""
    sent = datetime.fromtimestamp(sent_ts or 0, PARIS).replace(tzinfo=None)
    subject, text = _flat(subject), _flat(body)
    m = _FORM.search(text)
    if m:
        y1, m1, d1, d2, m2, y2, hh, mm, h2, m3 = m.groups()
        try:
            day = datetime(int(y1), int(m1), int(d1)) if y1 else datetime(int(y2), int(m2), int(d2))    # dd-mm-yyyy: that is how these mails write it
        except ValueError:
            day = None
        slot = day and _slot(_at(day, hh, mm), _at(day, h2, m3) if h2 else None)
        if slot:
            return slot
    for part in (subject, text):
        slot = _english(part, sent)
        if slot:
            return slot
    for part in (subject, text):
        m = _FR.search(part)
        if m:
            wd, dd, mon, yy, h1, m1, h2, m2 = m.groups()
            day = _day(yy, _FR_MONTHS.index(mon) + 1, dd, wd, FR_DAYS, sent)
            slot = day and _slot(_at(day, h1, m1), _at(day, h2, m2) if h2 else None, sure=False)
            if slot:
                return slot
    return None


def label(start, end=None, now=None):
    """The words the bot must repeat: computed here, so the model has no date arithmetic to get wrong."""
    now = now or datetime.now()
    name = f"{FR_DAYS[start.weekday()]} {start.day} {MOIS[start.month - 1]}"
    delta = (start.date() - now.date()).days
    day = f"aujourd'hui ({name})" if delta == 0 else f"demain ({name})" if delta == 1 else name if delta > 0 else f"{name} (passé)"
    if start.year != now.year:
        day += f" {start.year}"
    return f"{day} de {start:%Hh%M} à {end:%Hh%M}" if end else f"{day} à {start:%Hh%M}"
