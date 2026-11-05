"""Interview times read from mails written the way hiring tools write them. The bot used to take the time a mail was sent for the time of the meeting."""
import sqlite3
from datetime import datetime

import pytest

from instonct import llm, mail, mailindex, mailslot, meetings, monitor, plus
from instonct.core import db

SENT = int(datetime(2026, 11, 4, 12, 0).timestamp())
NOW = datetime(2026, 11, 5, 16, 0)
ACME_REMINDER = "Bonjour, nous souhaitons vous rappeler que vous avez un entretien avec Acme.\n---------------------------------------------\n1er échange visio avec Pat - Sales\nDATE/HEURE\n05/11/2026 16:30 - 17:00 CET\nChoisir une heure https://acme.teamtailor.com/fr/schedule/00000000-0000-4000-8000-000000000001/edit\nPARTICIPANTS\nPat Doe\nLOCALISATION\nGoogle Meet.\nDétails https://acme.teamtailor.com/fr/schedule/00000000-0000-4000-8000-000000000001\n"
GLOBEX_OLD = "we want to remind you\n---------------------------------------------\nFirst interview Globex\nDATE/TIME\n2026-11-05 12:30 - 13:15 CET\nATTENDEES\nSam Roe\nLOCATION\nGoogle Meet\n"
GLOBEX_MOVED = "Globex has made an update to your meeting.\n---------------------------------------------\nFirst interview Globex\nDATE/TIME\n2026-11-06 10:30 - 11:15 CET\nATTENDEES\nSam Roe\nLOCATION\nGoogle Meet\n"
INITECH = "we want to remind you\n-----------------\nInitech - Business Developer\nDATE/TIME\n06-11-2026 14:40 - 15:00 CET\nATTENDEES\nAlex Kim\nLOCATION\nvideo call\n"


@pytest.mark.parametrize("subject,body,start,end", [
    ("Rappel d'entretien", ACME_REMINDER, (2026, 11, 5, 16, 30), (17, 0)),
    ("Time confirmed: First interview Globex", GLOBEX_MOVED, (2026, 11, 6, 10, 30), (11, 15)),
    ("Meeting reminder", INITECH, (2026, 11, 6, 14, 40), (15, 0)),
    ("Invitation: Pat and Alex @ Mon Nov 9,\r\n 2026 11:30am - 12pm (GMT+1) (me@gmail.com)", "", (2026, 11, 9, 11, 30), (12, 0)),
    ("Invitation: x @ Wed Aug 5,\r\n 2026 7pm - 8pm (GMT+2) (me@gmail.com)", "", (2026, 8, 5, 19, 0), (20, 0)),
    ("Invitation", "Alex and Pat\nMonday Nov 9, 2026 ⋅ 11:30am – 12pm Central European Time - Paris\nLocation", (2026, 11, 9, 11, 30), (12, 0)),
    ("Registration confirmed for Meetup", "You have registered\nThursday, November 12 7:00 PM - 9:30 PM GMT+1\nLocation: In Person", (2026, 11, 12, 19, 0), (21, 30)),
])
def test_the_time_comes_from_the_text(subject, body, start, end):
    slot = mailslot.parse(subject, body, SENT)
    assert slot["debut"] == datetime(*start) and slot["fin"] == datetime(*start[:3], *end) and slot["sur"]


def test_another_time_zone_is_converted_to_paris_time():
    assert mailslot.parse("Invitation: x @ Mon Nov 9, 2026 10am - 11am (GMT-5) (me@gmail.com)", "", SENT)["debut"] == datetime(2026, 11, 9, 16, 0)


def test_a_date_in_a_sentence_may_only_be_a_proposal():
    slot = mailslot.parse("On se voit ?", "Je te propose jeudi 5 novembre à 16h30, ça te va ?", SENT)
    assert slot["debut"] == datetime(2026, 11, 5, 16, 30) and not slot["sur"]


@pytest.mark.parametrize("subject,body", [
    ("Thank you for applying", "Sent Wed, 04 Nov 2026 10:09:00 +0100. We will reply soon."),
    ("Meeting invite: First interview Globex", "Choose a time for this meeting"),
    ("Invitation", "Monday Nov 9, 2026 ⋅ 9am – 10am Eastern Time"),         # better nothing than a wrong hour
    ("Rendez-vous", "mardi 5 novembre à 16h30"),                             # 5 November 2026 is a Thursday: we misread something
    ("Re: Entretien", "Merci !\n\nLe mar. 3 nov. 2026 à 10:00, Pat a écrit :\nDATE/TIME 2026-11-06 10:30 - 11:15 CET"),
])
def test_no_time_is_invented(subject, body):
    assert mailslot.parse(subject, body, SENT) is None


def test_the_label_says_the_day_in_words():
    assert mailslot.label(datetime(2026, 11, 5, 16, 30), datetime(2026, 11, 5, 17, 0), NOW) == "aujourd'hui (jeudi 5 novembre) de 16h30 à 17h00"
    assert mailslot.label(datetime(2026, 11, 6, 10, 30), None, NOW) == "demain (vendredi 6 novembre) à 10h30"
    assert mailslot.label(datetime(2026, 11, 9, 11, 30), None, NOW) == "lundi 9 novembre à 11h30"


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(mailindex, "PATH", str(tmp_path / "index.sqlite"))
    monkeypatch.setattr(mail, "_mail_accounts", lambda: [{"n": 1, "user": "me@gmail.com", "host": "imap.gmail.com"}])
    monkeypatch.setattr(meetings.gcal, "connected", lambda: False)
    uid = [0]

    def add(de, sujet, body, typ="etape", when=SENT):
        uid[0] += 1
        with mailindex._db() as con:
            con.execute("INSERT INTO mails(acc,folder,uid,uidvalidity,mid,date,de,dest,sujet,type,niveau,body,refs) VALUES(1,'All',?,1,?,?,?,'',?,?,'important',?,'')",
                        (uid[0], f"<{uid[0]}@x>", when, de, sujet, typ, body))
            con.commit()
    return add


def test_the_latest_mail_wins_when_a_meeting_moves(box):
    box("Globex <no-reply@globex.teamtailor-mail.com>", "Meeting reminder", GLOBEX_OLD, when=SENT - 3000)
    box("Sam Roe - Globex <sam.roe@globex.teamtailor-mail.com>", "Time confirmed: First interview Globex", GLOBEX_MOVED)
    found, _ = meetings.upcoming(14, datetime(2026, 11, 5, 9, 0))
    assert [(m["entreprise"], m["debut"], m["avec"]) for m in found] == [("Globex", datetime(2026, 11, 6, 10, 30), "Sam Roe")]


def test_a_cancelled_or_refused_meeting_is_not_shown(box):
    box("Acme <hr@acme.com>", "Invitation: Interview @ Mon Nov 9, 2026 11am - 12pm (GMT+1) (me@gmail.com)", "", when=SENT - 900)
    box("Acme <hr@acme.com>", "Canceled event: Interview @ Mon Nov 9, 2026 11am - 12pm (GMT+1) (me@gmail.com)", "")
    box("Beta <hr@beta.com>", "Invitation: Interview @ Mon Nov 9, 2026 3pm - 4pm (GMT+1) (me@gmail.com)", "", when=SENT - 900)
    box("Beta <hr@beta.com>", "Your application", "We regret to inform you", typ="refus")
    assert meetings.upcoming(14, NOW)[0] == []


def test_a_meeting_that_is_over_is_not_shown(box):
    box("Acme <no-reply@acme.teamtailor-mail.com>", "Rappel d'entretien", ACME_REMINDER)
    assert meetings.upcoming(14, datetime(2026, 11, 5, 17, 1))[0] == []


def test_each_event_keeps_its_own_time_and_a_waitlist_is_not_a_seat(box):
    box("Luma <x@calendar.luma-mail.com>", "Registration confirmed for Meetup A", "Thursday, November 12 7:00 PM - 9:30 PM GMT+1")
    box("Luma <x@calendar.luma-mail.com>", "Registration confirmed for Meetup B", "Tuesday, November 17 7:00 PM - 9:30 PM GMT+1")
    box("Luma <x@calendar.luma-mail.com>", "You’re on the waitlist for Dinner", "Saturday, November 21 7:00 PM - 9:00 PM GMT+1")
    found = meetings.upcoming(30, NOW)[0]
    assert [m["titre"] for m in found] == ["Meetup A", "Meetup B"] and all(m["event"] for m in found)


def test_the_tool_gives_ready_words_and_the_link(box):
    box("Acme <no-reply@acme.teamtailor-mail.com>", "Rappel d'entretien", ACME_REMINDER)
    box("Initech <no-reply@initech.teamtailor-mail.com>", "Meeting reminder", INITECH)
    item = meetings.tool({"entreprise": "acme"})["rendez_vous"]
    assert len(item) <= 1
    meetings_now = meetings.upcoming(14, NOW)[0]
    assert meetings_now[0]["lien"].endswith("0001") and "edit" not in meetings_now[0]["lien"]
    assert meetings.reminder(meetings_now[0], 30).startswith("Dans 30 minutes : Acme")


def test_a_room_made_in_the_calendar_never_replaces_the_senders_link(box, monkeypatch):
    box("Acme <no-reply@acme.teamtailor-mail.com>", "Rappel d'entretien", ACME_REMINDER)
    own = {"debut": datetime(2026, 11, 5, 16, 30), "fin": datetime(2026, 11, 5, 17, 30), "sur": True, "entreprise": "", "titre": "Entretien Acme", "avec": "",
           "id": "x", "source": "agenda", "event": False, "lien": "https://meet.google.com/aaa-bbbb-ccc", "lieu": ""}
    other = dict(own, titre="Dentiste", id="y", lien="")
    monkeypatch.setattr(meetings, "_from_calendar", lambda days: [own, dict(own, id="z"), other])
    found = meetings.upcoming(14, NOW)[0]
    assert [m["titre"] for m in found if m["debut"] == own["debut"]][1:] == ["Dentiste"] and len(found) == 2
    assert "teamtailor" in found[0]["lien"]


def test_a_reminder_goes_out_once_and_not_for_events(box, monkeypatch):
    box("Acme <no-reply@acme.teamtailor-mail.com>", "Rappel d'entretien", ACME_REMINDER)
    box("Luma <x@calendar.luma-mail.com>", "Registration confirmed for Cocktails", "Thursday, November 5 4:30 PM - 8:00 PM GMT+1")
    sent = []
    monkeypatch.setattr(monitor, "send", lambda chat, text: sent.append(text))
    monkeypatch.setattr(monitor.plus, "due", lambda *a: [])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(monitor, "datetime", Clock)
    assert plus.setting(db, "rappel_rdv")
    monitor.check_plus(7)
    monitor.check_plus(7)
    assert len(sent) == 1 and "Acme" in sent[0] and "16h30" in sent[0] and "Pat Doe" in sent[0]


def test_trashing_refusals_reads_the_whole_index_and_says_the_truth(box, monkeypatch):
    for n in range(200):
        box("Acme <hr@acme.com>", f"Update {n}", "", typ="candidature")
    box("Beta <hr@beta.com>", "Your application", "no", typ="refus")
    box("Gamma <hr@gamma.com>", "Your interview", "yes", typ="etape")
    box("Me <m.e+x@gmail.com>", "Re: refus", "no", typ="refus")
    trashed = []
    monkeypatch.setattr(mailindex, "sync_once", lambda *a: 0)
    monkeypatch.setattr(mail, "mail_manage", lambda ids, action: trashed.extend(ids) or {"fait": len(ids)})
    look = mailindex.trash_refusals(dry_run=True)
    assert look["mails_regardes"] == 203 and look["refus_trouves"] == 1 and trashed == []
    res = mailindex.trash_refusals()
    assert res["mis_a_la_corbeille"] == 1 and len(trashed) == 1 and "Beta" in res["liste"][0]


@pytest.mark.parametrize("raw,clean", [
    ("Ils sont récupérables si besoin.Check.All set.Done.", "Ils sont récupérables si besoin."),
    ("Rendez-vous de Globex.C'est noté. Bonne chance.", "Rendez-vous de Globex. C'est noté. Bonne chance."),
    ("Désolé, vraiment.Voici le lien https://a.b/Cd.Ef merci.", "Désolé, vraiment. Voici le lien https://a.b/Cd.Ef merci."),
    ("C'est noté.Bonne chance.", "C'est noté."),
    ("Bonne chance. Tu vas assurer.", "Bonne chance. Tu vas assurer."),
])
def test_junk_at_the_end_of_an_answer_goes_away(raw, clean):
    assert llm.clean_answer(raw) == clean


def test_an_action_announced_without_its_tool_is_caught():
    assert llm.false_claim("Voici le rappel demandé : à 13 h et à 18 h.", set())
    assert llm.false_claim("Tes mails ont été mis à la corbeille.", {"mail_search"})
    assert not llm.false_claim("Tes mails ont été mis à la corbeille.", {"mail_clean"})
    assert not llm.false_claim("Je supprime tous les mails de refus. Confirme ?", set())
    assert not llm.false_claim("Ton entretien est à 16h30.", set())


def test_the_index_row_says_sent_not_date(box):
    box("Acme <no-reply@acme.teamtailor-mail.com>", "Rappel d'entretien", ACME_REMINDER)
    with mailindex._db() as con:
        con.row_factory = sqlite3.Row
        row = mailindex._row(con.execute("SELECT * FROM mails").fetchone())
    assert "date" not in row and row["envoye_le"] and "16h30" in row["rendez_vous"]
