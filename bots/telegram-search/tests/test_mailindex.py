"""The whole mailbox becomes searchable, read-only, and the index follows what happens on the server."""
import json
import os
import stat
import time
from email.utils import formatdate

import pytest

from instonct import dispatch, mail, mailindex, monitor, plus
from instonct.core import db

ME = "moi@gmail.com"
ALL = "[Gmail]/All Mail"


def raw(de="Alice <alice@acme.fr>", sujet="Bonjour", body="Salut", age_days=1, to=ME, mid=None, refs="", extra=""):
    date = formatdate(time.time() - age_days * 86400)
    head = f"From: {de}\r\nTo: {to}\r\nSubject: {sujet}\r\nDate: {date}\r\nMessage-ID: {mid or '<' + str(abs(hash((de, sujet, body)))) + '@x>'}\r\n"
    head += f"References: {refs}\r\n" if refs else ""
    return (head + extra + "Content-Type: text/plain; charset=utf-8\r\n\r\n" + body).encode()


class FakeBox:
    """A mailbox that only answers read commands: anything else fails the test."""
    def __init__(self, mails, validity=12, uid_after_body=False):
        self.mails, self.validity, self.uid_after_body = dict(mails), validity, uid_after_body
        self.fetches, self.logged_out = [], 0

    def list(self):
        return "OK", [b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"', b'(\\Junk) "/" "[Gmail]/Spam"', b'(\\Trash) "/" "[Gmail]/Trash"', b'(\\HasNoChildren) "/" "INBOX"']

    def status(self, folder, what):
        return "OK", [f'{folder} (UIDVALIDITY {self.validity})'.encode()]

    def select(self, folder, readonly=False):
        assert readonly and folder == '"[Gmail]/All Mail"'
        return "OK", [str(len(self.mails)).encode()]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [" ".join(str(u) for u in sorted(self.mails)).encode()]
        assert command == "fetch" and "PEEK" in args[1], f"this must stay read-only: {command} {args}"
        wanted = [int(u) for u in args[0].split(",")]
        self.fetches.append(wanted)
        out = []
        for u in wanted:
            if u in self.mails:
                if self.uid_after_body:
                    out += [(f"1 (BODY[]<0> {{{len(self.mails[u])}}}".encode(), self.mails[u]), f" UID {u})".encode()]
                else:
                    out += [(f"1 (UID {u} BODY[]<0> {{{len(self.mails[u])}}}".encode(), self.mails[u]), b")"]
        return "OK", out

    def logout(self):
        self.logged_out += 1


@pytest.fixture(autouse=True)
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(mailindex, "PATH", str(tmp_path / "index.sqlite"))
    monkeypatch.setattr(mail, "_mail_accounts", lambda: [{"n": 1, "user": ME, "pw": "x", "host": "imap.gmail.com"}])


def box_with(mails, **kw):
    box = FakeBox(mails, **kw)
    mail._mail_open = lambda n=1, folder="INBOX", readonly=True: box
    return box


@pytest.fixture(autouse=True)
def restore_open():
    original = mail._mail_open
    yield
    mail._mail_open = original


def test_big_mailbox_is_read_in_batches_newest_first():
    box = box_with({u: raw(sujet=f"numero {u}") for u in range(1, 251)})
    assert mailindex.sync_once() == 150
    assert box.fetches[0][0] == 250 and box.logged_out == 1
    assert mailindex.status()["a_faire"] == 150
    assert mailindex.sync_once() == 50
    assert mailindex.sync_once() == 0
    assert mailindex.status() | {"dernier_passage": ""} == {"mails_dans_l_index": 250, "a_faire": 0, "sur_le_serveur": 250, "dernier_passage": ""}
    box.fetches.clear()
    assert mailindex.sync_once() == 0 and box.fetches == []             # nothing new: nothing downloaded


def test_spam_and_trash_are_not_indexed():
    box_with({1: raw()})
    c = mail._mail_open()
    assert mailindex._wanted_folders(c, True) == [ALL]


def test_new_mails_arrive_and_trashed_mails_leave():
    box = box_with({1: raw(sujet="ancien"), 2: raw(sujet="poubelle")})
    mailindex.sync_once()
    del box.mails[2]
    box.mails[3] = raw(sujet="nouveau")
    mailindex.sync_once()
    found = {r["sujet"] for r in mailindex.search()["resultats"]}
    assert found == {"ancien", "nouveau"}
    assert mailindex.search("poubelle")["resultats"] == []              # also gone from the full-text index


def test_uid_validity_change_starts_the_folder_again():
    box = box_with({1: raw(sujet="avant")})
    mailindex.sync_once()
    box.validity, box.mails = 13, {1: raw(sujet="apres")}
    mailindex.sync_once()
    assert [r["sujet"] for r in mailindex.search()["resultats"]] == ["apres"]


def test_uid_after_the_body_is_understood():
    box_with({7: raw(sujet="fin")}, uid_after_body=True)
    assert mailindex.sync_once() == 0
    assert mailindex.search("fin")["resultats"][0]["id"] == f"1:7@{ALL}"


def test_a_server_that_returns_nothing_is_an_error_not_a_silent_loop():
    box = box_with({1: raw()})
    box.uid = lambda command, *a: ("OK", [b"1"]) if command == "search" else ("OK", [None])
    with pytest.raises(RuntimeError):
        mailindex.sync_once()


def test_unreadable_mail_gets_a_row_so_it_is_not_fetched_forever():
    box = box_with({1: b"\xff\xfe pas un mail \x00"})
    assert mailindex.sync_once() == 0
    box.fetches.clear()
    mailindex.sync_once()
    assert box.fetches == []


def test_cut_off_html_leaves_no_css_in_the_text():
    html = 'From: a@b.fr\r\nSubject: x\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<html><style>.a{color:red}</style><p>Caf&eacute; ok</p><style>.b{color:blue'
    assert mailindex._parse(html.encode())["body"] == "Café ok"


@pytest.mark.parametrize("encoding", ["utf-8", "latin-1"])
def test_raw_accents_in_headers_are_readable(encoding):
    head = "From: Léa <lea@x.fr>\r\nSubject: Réunion\r\n\r\nok".encode(encoding)
    parsed = mailindex._parse(head)
    assert parsed["sujet"] == "Réunion" and parsed["de"].startswith("Léa")


def test_the_index_file_is_private():
    box_with({1: raw()})
    mailindex.sync_once()
    assert stat.S_IMODE(os.stat(mailindex.PATH).st_mode) == 0o600


def test_search_all_words_then_any_word_without_accents():
    box_with({1: raw(sujet="Réunion équipe", body="contrat signé"), 2: raw(sujet="Contrat", body="rien")})
    mailindex.sync_once()
    assert [r["sujet"] for r in mailindex.search("reunion contrat")["resultats"]] == ["Réunion équipe"]
    out = mailindex.search("contrat inexistantzz")
    assert "note" in out and len(out["resultats"]) == 2
    assert "[" in mailindex.search("signe")["resultats"][0]["extrait"]


@pytest.mark.parametrize("query", ['"', 'a"b OR', "NEAR(x y)", "de:alice*", "((", "-", "AND", "sujet:*", "'; DROP TABLE mails;--"])
def test_nothing_the_model_writes_breaks_the_search(query):
    box_with({1: raw()})
    mailindex.sync_once()
    assert "resultats" in mailindex.search(query)
    assert mailindex.status()["mails_dans_l_index"] == 1


def test_filters():
    box_with({1: raw(de="Bob <bob@x.fr>", sujet="vieux", age_days=100), 2: raw(de="100% Promo <p@y.fr>", sujet="recent", age_days=1)})
    mailindex.sync_once()
    assert [r["sujet"] for r in mailindex.search(days=30)["resultats"]] == ["recent"]
    assert [r["sujet"] for r in mailindex.search(de="bob")["resultats"]] == ["vieux"]
    assert mailindex.search(de="%")["resultats"][0]["sujet"] == "recent"     # % is a character here, not a wildcard


def test_tool_results_mark_the_conversation_as_external_content():
    box_with({1: raw()})
    mailindex.sync_once()
    links = []
    assert "resultats" in dispatch.run_tool(7, "mail_index", {"query": "bonjour"}, links)
    assert links == ["(email lu)"]


def test_incomplete_index_says_so():
    box_with({u: raw(sujet=f"n{u}") for u in range(1, 150)})
    mailindex.sync_once()
    assert "attention" in mailindex.search("n149")
    assert "attention" in mailindex.applications()


@pytest.mark.parametrize("de,sujet,company", [
    ("Stripe Recruiting <no-reply@greenhouse.io>", "Your application for our Community Operations Specialist role at Stripe", "Stripe"),
    ("noreply@cision.com", "Thank you for your application!", "Cision"),
    ("Doctolib Talent <notification@hire.lever.co>", "Merci pour votre candidature", "Doctolib"),
    ("Recrutement <jobs@mail.alan.com>", "Votre candidature", "Alan"),
    ("Workable <noreply@candidates.workablemail.com>", "Votre candidature à Qonto", "Qonto"),
    ("Jane <jane@gmail.com>", "Candidature", "Jane"),
    ("Acme <rh@acme.co.uk>", "Application", "Acme"),
])
def test_company_guess(de, sujet, company):
    assert mailindex.company_of(de, sujet) == company


def test_applications_are_one_line_per_company_with_the_latest_status():
    box_with({
        1: raw(de="noreply@cision.com", sujet="Thank you for your application!", body="We received your application", age_days=9),
        2: raw(de="Stripe <jobs@stripe.com>", sujet="Your application at Stripe", body="we received your application", age_days=8),
        3: raw(de="Stripe <jobs@stripe.com>", sujet="Your application at Stripe", body="Unfortunately we will not move forward with your application", age_days=2),
        4: raw(de=f"Moi <{ME}>", sujet="Ma candidature", body="ci-joint ma candidature", age_days=3),
        5: raw(de="Shop <promo@shop.fr>", sujet="-50% ce week-end", body="promo", age_days=1, extra="List-Unsubscribe: <x>\r\n"),
    })
    mailindex.sync_once()
    out = mailindex.applications()
    assert out["entreprises"] == 2
    stripe = next(c for c in out["liste"] if c["entreprise"] == "Stripe")
    assert stripe["statut"] == "refus" and stripe["mails"] == 2 and out["liste"][0]["entreprise"] == "Stripe"
    assert stripe["id"] == f"1:3@{ALL}"


def _waiting_box(**more):
    return box_with({
        1: raw(de="Paul <paul@acme.fr>", sujet="Une question", body="Tu peux me rappeler ?", age_days=4, mid="<paul@x>"),
        2: raw(de="Lea <lea@acme.fr>", sujet="Une autre", body="On se voit quand ?", age_days=4, mid="<lea@x>"),
        3: raw(de=f"Moi <{ME}>", sujet="Re: Une autre", body="Demain", age_days=3, mid="<moi@x>", refs="<lea@x>"),
        4: raw(de="Zoe <zoe@acme.fr>", sujet="Pour info", body="Aucune question ici.", age_days=4, mid="<zoe@x>"),
        5: raw(de="Max <max@acme.fr>", sujet="Trop recent", body="Ca va ?", age_days=0.5, mid="<max@x>"),
        6: raw(de="no-reply@acme.fr", sujet="Automatique", body="Une question ?", age_days=4, mid="<auto@x>"),
        7: raw(de="Tom <tom@acme.fr>", sujet="Trop vieux", body="Ca va ?", age_days=40, mid="<tom@x>"),
        **more})


def test_waiting_for_reply_only_keeps_real_unanswered_questions():
    _waiting_box()
    mailindex.sync_once()
    assert [r["mid"] for r in mailindex.waiting_for_reply()] == ["<paul@x>"]


def _ten_oclock(monkeypatch):
    real = monitor.datetime

    class At(real):
        @classmethod
        def now(cls, tz=None):
            return real.now().replace(hour=10)
    monkeypatch.setattr(monitor, "datetime", At)


def test_daily_reminder_is_sent_once_and_can_be_turned_off(monkeypatch):
    sent = []
    monkeypatch.setattr(monitor, "send", lambda chat, text: sent.append(text))
    _ten_oclock(monkeypatch)
    _waiting_box()
    mailindex.sync_once()
    monitor.check_followups(7)
    assert len(sent) == 1 and "Paul" in sent[0]
    monitor.check_followups(7)
    assert len(sent) == 1                                               # once a day
    db.flushdb()
    db.set(mailindex.STATUS, json.dumps({"a_faire": 0}))
    plus.t_reglage(db, {"nom": "mails sans reponse", "actif": False})
    monitor.check_followups(7)
    assert len(sent) == 1


def test_same_mail_is_never_mentioned_twice(monkeypatch):
    sent = []
    monkeypatch.setattr(monitor, "send", lambda chat, text: sent.append(text))
    _ten_oclock(monkeypatch)
    _waiting_box()
    mailindex.sync_once()
    monitor.check_followups(7)
    db.delete(f"followup:{monitor.datetime.now():%Y-%m-%d}")
    monitor.check_followups(7)
    assert len(sent) == 1


def test_no_reminder_while_the_index_is_incomplete(monkeypatch):
    sent = []
    monkeypatch.setattr(monitor, "send", lambda chat, text: sent.append(text))
    _ten_oclock(monkeypatch)
    _waiting_box()
    mailindex.sync_once(budget=1)
    monitor.check_followups(7)
    assert sent == []
