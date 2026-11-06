"""The hour of an interview is often only in the .ics file attached to the mail. These tests use made-up invitations, no real mail."""

import email
from datetime import datetime
from email.message import EmailMessage

from instonct import ics, mail, mailslot, meetings


def _ics(start, end="", method="REQUEST", extra=""):
    return ("BEGIN:VCALENDAR\r\nMETHOD:" + method + "\r\nBEGIN:VEVENT\r\nSUMMARY:Recruiter Interview @ Exemple\\, visio\r\n" + start + "\r\n" + end + "\r\n"
            + extra + "LOCATION:https://visio.example.com/j/123\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


def _mail(raw_ics, name="interview.ics"):
    m = EmailMessage()
    m["Subject"], m["From"], m["Date"] = "Recruiter Interview @ Exemple", "Recruteur <jobs@example.com>", "Mon, 02 Nov 2026 14:01:00 +0000"
    m.set_content("Bonjour, voici l'invitation.")
    m.add_attachment(raw_ics.encode(), maintype="text", subtype="calendar", filename=name)
    return email.message_from_bytes(m.as_bytes())


def test_utc_time_becomes_paris_time():
    ev = ics.events(_ics("DTSTART:20261106T090000Z", "DTEND:20261106T093000Z"))[0]
    assert ev["debut"] == datetime(2026, 11, 6, 10, 0) and ev["fin"] == datetime(2026, 11, 6, 10, 30)
    assert ev["titre"] == "Recruiter Interview @ Exemple, visio"


def test_summer_time_is_two_hours():
    assert ics.events(_ics("DTSTART:20260706T080000Z"))[0]["debut"] == datetime(2026, 7, 6, 10, 0)


def test_named_zone_is_converted():
    ev = ics.events(_ics("DTSTART;TZID=America/New_York:20261106T040000"))[0]
    assert ev["debut"] == datetime(2026, 11, 6, 10, 0)


def test_unknown_zone_or_floating_time_gives_no_hour():
    assert ics.events(_ics("DTSTART;TZID=Romance Standard Time:20261106T100000"))[0]["debut"] is None
    assert ics.events(_ics("DTSTART:20261106T100000"))[0]["debut"] is None
    assert ics.line(_ics("DTSTART:20261106T100000")) == ""


def test_whole_day_has_no_hour():
    assert ics.events(_ics("DTSTART;VALUE=DATE:20261106"))[0]["debut"] is None


def test_cancelled_invitation_is_not_a_time():
    text = ics.line(_ics("DTSTART:20261106T090000Z", method="CANCEL"))
    assert "annulee" in text and "DATE/TIME" not in text


def test_folded_lines_are_joined():
    raw = _ics("DTSTART:20261106T090000Z").replace("SUMMARY:Recruiter", "SUMMARY:Recr\r\n uiter")
    assert ics.events(raw)[0]["titre"].startswith("Recruiter Interview")


def test_the_mail_body_carries_the_hour_and_mailslot_reads_it():
    body = mail._body_text(_mail(_ics("DTSTART:20261106T090000Z", "DTEND:20261106T093000Z")))
    assert "DATE/TIME: 2026-11-06 10:00-10:30" in body and "invitation" in body.lower()
    sent = datetime(2026, 11, 2, 15, 1).timestamp()
    slot = mailslot.parse("Recruiter Interview @ Exemple", body, sent)
    assert slot and slot["debut"] == datetime(2026, 11, 6, 10, 0) and slot["fin"] == datetime(2026, 11, 6, 10, 30) and slot["sur"]
    assert mailslot.label(slot["debut"], slot["fin"], datetime(2026, 11, 6, 8, 0)) == "aujourd'hui (vendredi 6 novembre) de 10h00 à 10h30"


def test_a_mail_without_invitation_is_unchanged():
    m = EmailMessage()
    m["Subject"] = "Bonjour"
    m.set_content("Juste du texte.")
    assert mail._body_text(email.message_from_bytes(m.as_bytes())) == "Juste du texte."


def test_the_interview_shows_in_upcoming_meetings(tmp_path, monkeypatch):
    """From the stored body to the answer: the hour that only the .ics knew is what the bot says."""
    body = mail._body_text(_mail(_ics("DTSTART:20261106T090000Z", "DTEND:20261106T093000Z")))
    row = {"acc": 1, "folder": "INBOX", "uid": 1, "de": "Recruteur <jobs@example.com>", "sujet": "Recruiter Interview @ Exemple", "type": "etape",
           "body": body, "date": int(datetime(2026, 11, 2, 15, 1).timestamp())}
    monkeypatch.setattr("instonct.mailindex._db", lambda: _FakeDb([row]))
    monkeypatch.setattr("instonct.mailindex._unique", lambda rows: rows)
    monkeypatch.setattr("instonct.mailindex._own_addresses", lambda: set())
    monkeypatch.setattr("instonct.meetings._from_calendar", lambda days: [])
    found, _ = meetings.upcoming(7, datetime(2026, 11, 6, 8, 0))
    assert len(found) == 1 and found[0]["debut"] == datetime(2026, 11, 6, 10, 0)


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return self

    def fetchall(self):
        return self.rows


def test_mail_search_tells_the_model_where_the_hour_is():
    """The bot once answered an interview question from a plain mail search and invented the hour."""
    assert "rdv_a_venir" in mail.hour_hint("interview")
    assert mail.hour_hint("facture edf") == ""
