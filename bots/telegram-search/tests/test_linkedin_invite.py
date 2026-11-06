"""LinkedIn invitations with a note. The browser is a FAKE LinkedIn: no real page is opened and no real invitation can ever leave the test.
Every pause is skipped, nothing is sent to Telegram, nothing touches the screen, the TV or the speakers."""
import json
import re
import time
import types

import pytest

from instonct import guard, kit_linkedin, linkedin, linkedin_invite as li, realbrowser
from instonct.core import db

NOTE = "Bonjour {prenom}, j'ai vu que vous etes fondateur chez YC : je construis un assistant personnel et j'aimerais echanger avec vous."


class FakeLinkedIn:
    """Pages of people, a Connect button per person, the note dialog and the Send button. Records every invitation actually sent."""

    def __init__(self, pages, notes_allowed=True, dialog_opens=True, blocked_after=None):
        self.pages = pages                       # {1: [("Alice Martin", "https://www.linkedin.com/in/alice"), ...], 2: [...]}
        self.notes_allowed, self.dialog_opens, self.blocked_after = notes_allowed, dialog_opens, blocked_after
        self.page, self.dialog, self.value, self.sent, self.clicks, self.url = 1, None, "", [], 0, ""

    # the browser interface used by linkedin_invite
    def call(self, tool, **a):
        if tool == "goto":
            self.url = a["url"]
            self.page = int(re.search(r"page=(\d+)", a["url"]).group(1))
            self.dialog = None
        elif tool == "click":
            self.clicks += 1
            sel = a["selector"]
            if sel.startswith("[data-lpi=") and self.dialog_opens:
                n = int(re.search(r'"(\d+)"', sel).group(1))
                self.dialog = {"person": self.pages[self.page][n - 1], "textarea": False, "text": ""}
                if not self.notes_allowed:
                    self.dialog["text"] = "Vous avez atteint la limite : passez a Premium pour ajouter des notes"
            elif sel == "NOTE":
                self.dialog["textarea"] = True
            elif sel == "SEND":
                self.sent.append((self.dialog["person"], self.value))
                self.dialog, self.value = None, ""
        elif tool == "fill":
            self.value = a["value"]
        elif tool == "press":
            self.dialog = None
        return ""

    def js(self, script):
        marker = re.match(r"/\*([a-z:]+)\*/", script).group(1)
        if marker == "state":
            if self.blocked_after is not None and len(self.sent) >= self.blocked_after:
                return json.dumps({"url": "https://www.linkedin.com/checkpoint/challenge/xyz", "title": "Security Verification", "body": "Quick security check"})
            return json.dumps({"url": self.url, "title": "Search | LinkedIn", "body": "Results"})
        if marker == "find":
            done = {p[1] for p, _ in self.sent}
            return json.dumps([{"sel": f'[data-lpi="{i + 1}"]', "name": n, "url": u} for i, (n, u) in enumerate(self.pages.get(self.page, [])) if u not in done])
        if marker == "dialog":
            return json.dumps({"text": self.dialog["text"], "textarea": self.dialog["textarea"]}) if self.dialog else ""
        if marker == "value":
            return self.value
        if marker == "tag:note":
            return "NOTE" if self.dialog and self.notes_allowed else ""
        if marker == "tag:text":
            return "AREA" if self.dialog and self.dialog["textarea"] else ""
        if marker == "tag:send":
            return "SEND" if self.dialog and self.dialog["textarea"] and self.value else ""
        return "ok"


FIRST = ["Alice", "Bruno", "Chloe", "David", "Emma", "Felix", "Gaelle", "Hugo"]


def people(n, offset=0):
    return [(f"{FIRST[offset + i]} Nom", f"https://www.linkedin.com/in/p{offset + i}") for i in range(n)]


@pytest.fixture
def fake(monkeypatch):
    """Returns a function that installs a fake LinkedIn and gives back (browser, messages sent to Telegram)."""
    said = []
    monkeypatch.setattr("instonct.linkedin_invite.send", lambda chat, text: said.append(text))
    monkeypatch.setattr("instonct.linkedin_invite._pause", lambda seconds: None)
    monkeypatch.setattr("instonct.linkedin_invite.screen.extend", lambda minutes: True)
    monkeypatch.setattr("instonct.linkedin_invite.time", types.SimpleNamespace(time=time.time, sleep=lambda s: None))     # no waiting, even in the poll loops

    def install(**kw):
        b = FakeLinkedIn(**kw)
        monkeypatch.setattr("instonct.linkedin_invite._driver", lambda: b)
        return b, said
    return install


# ---------------------------------------------------------------- the plain helpers
def test_the_note_gets_the_first_name_or_drops_the_gap():
    assert li.make_note("Bonjour {prenom}, ravi de vous connaitre", "alice MARTIN") == "Bonjour Alice, ravi de vous connaitre"
    assert li.make_note("Bonjour {prenom}, ravi de vous connaitre", "") == "Bonjour, ravi de vous connaitre"
    assert li.make_note("Salut {prenom} !", "LinkedIn Member") == "Salut!"            # hidden name: no « Linkedin » in the note
    assert "{prenom}" not in li.make_note("Salut {prenom} !", "123")


def test_a_login_wall_or_security_check_is_recognised_and_never_bypassed():
    assert li.blocker({"url": "https://www.linkedin.com/search/results/people/", "title": "Search | LinkedIn", "body": "Results"}) == ""
    assert "connexion linkedin" in li.blocker({"url": "https://www.linkedin.com/authwall?x=1", "title": "", "body": ""})
    assert "securite" in li.blocker({"url": "https://www.linkedin.com/checkpoint/challenge/1", "title": "Security Verification", "body": ""})
    assert db.exists(linkedin.STOP_KEY)                      # the whole bot leaves LinkedIn alone for a while
    assert "limite" in li.blocker({"url": "https://www.linkedin.com/search/", "title": "x", "body": "You have reached the weekly invitation limit"})


# ---------------------------------------------------------------- start(): everything checked before the browser is touched
def test_start_refuses_bad_requests_and_launches_nothing(monkeypatch):
    launched = []
    monkeypatch.setattr("instonct.linkedin_invite._spawn", lambda *a: launched.append(a))
    assert "erreur" in li.start(1, "", NOTE, 5)
    assert "20 caracteres" in li.start(1, "YC founder", "salut", 5)["erreur"]
    assert "300" in li.start(1, "YC founder", "x" * 301, 5)["erreur"]
    assert "300" in li.start(1, "YC founder", "{prenom} " + "x" * 295, 5)["erreur"]          # {prenom} may grow to 20 letters
    db.set(linkedin.STOP_KEY, 1, ex=60)
    assert "ralentir" in li.start(1, "YC founder", NOTE, 5)["erreur"]
    db.delete(linkedin.STOP_KEY)
    db.set(li.JOB_KEY, "{}", ex=60)
    assert "deja en cours" in li.start(1, "YC founder", NOTE, 5)["erreur"]
    db.delete(li.JOB_KEY)
    assert launched == []


def test_the_daily_cap_is_never_exceeded(monkeypatch):
    launched = []
    monkeypatch.setattr("instonct.linkedin_invite._spawn", lambda *a: launched.append(a))
    for _ in range(li.DAY_MAX - 2):
        li._count_one()
    r = li.start(1, "YC founder", NOTE, 30)
    assert r["invitations_prevues"] == 2 and launched[0][3] == 2        # asked 30, only 2 left today
    db.delete(li.JOB_KEY)
    li._count_one()
    li._count_one()
    assert "limite" in li.start(1, "YC founder", NOTE, 5)["erreur"]


def test_start_reports_a_sample_note_and_the_real_duration(monkeypatch):
    monkeypatch.setattr("instonct.linkedin_invite._spawn", lambda *a: None)
    r = li.start(1, "YC founder", NOTE, 30)
    assert r["invitations_prevues"] == 30 and r["note_exemple"].startswith("Bonjour Alex,") and r["duree_environ_minutes"] >= 15
    assert "stop linkedin" in r["dis_a_l_utilisateur"].lower() and "compte" in r["dis_a_l_utilisateur"]


# ---------------------------------------------------------------- the job itself, against the fake LinkedIn
def test_every_invitation_goes_out_with_the_note_and_only_once(fake):
    b, said = fake(pages={1: people(4), 2: people(4, 4)})
    li._run(1, "YC founder", NOTE, 6)
    assert len(b.sent) == 6
    for person, note in b.sent:
        assert note.startswith("Bonjour " + person[0].split()[0] + ",") and 20 <= len(note) <= li.NOTE_MAX                 # never without a note
    assert len({p[1] for p, _ in b.sent}) == 6                         # nobody twice
    assert db.scard(li.DONE_KEY) == 6 and li.counted_today() == 6 and li.counted_week() == 6
    assert "6 invitation(s)" in said[-1] and not db.exists(li.JOB_KEY)


def test_people_already_invited_are_skipped(fake):
    db.sadd(li.DONE_KEY, "https://www.linkedin.com/in/p0", "https://www.linkedin.com/in/p1")
    b, said = fake(pages={1: people(4)})
    li._run(1, "YC founder", NOTE, 10)
    assert [p[1] for p, _ in b.sent] == ["https://www.linkedin.com/in/p2", "https://www.linkedin.com/in/p3"]


def test_a_security_check_stops_the_job_at_once_and_says_so(fake):
    b, said = fake(pages={1: people(6)}, blocked_after=2)
    li._run(1, "YC founder", NOTE, 6)
    assert len(b.sent) == 2
    assert "securite" in said[-1] and "toi-meme" in said[-1] and db.exists(linkedin.STOP_KEY)


def test_when_linkedin_refuses_notes_nothing_is_sent_without_one(fake):
    b, said = fake(pages={1: people(3)}, notes_allowed=False)
    li._run(1, "YC founder", NOTE, 3)
    assert b.sent == [] and "note" in said[-1] and "sans note" in said[-1]


def test_when_the_note_window_does_not_open_the_job_stops(fake):
    b, said = fake(pages={1: people(3)}, dialog_opens=False)
    li._run(1, "YC founder", NOTE, 3)
    assert b.sent == [] and b.clicks == 1 and "Arret" in said[-1]


def test_stop_ends_the_job_after_the_current_invitation(fake, monkeypatch):
    b, said = fake(pages={1: people(6)})
    original = b.call

    def call(tool, **a):
        out = original(tool, **a)
        if tool == "click" and a["selector"] == "SEND":
            li.stop()
        return out
    b.call = call
    db.set(li.JOB_KEY, json.dumps({"kw": "x", "want": 6, "sent": 0}), ex=60)
    li._run(1, "YC founder", NOTE, 6)
    assert len(b.sent) == 1 and "arrete comme demande" in said[-1] and not db.exists(li.STOP_KEY)


def test_a_search_with_nobody_left_ends_cleanly(fake):
    b, said = fake(pages={1: []})
    li._run(1, "YC founder", NOTE, 5)
    assert b.sent == [] and "plus trouve" in said[-1]


def test_a_dead_browser_is_reported_not_crashed(monkeypatch):
    said = []
    monkeypatch.setattr("instonct.linkedin_invite.send", lambda chat, text: said.append(text))

    def boom():
        raise realbrowser.Stop("l'ecran ne demarre pas")
    monkeypatch.setattr("instonct.linkedin_invite._driver", boom)
    li._run(1, "YC founder", NOTE, 3)
    assert "ne demarre pas" in said[-1] and not db.exists(li.JOB_KEY)


# ---------------------------------------------------------------- the model's tool: guarded
def test_the_model_cannot_invite_anyone_unless_the_user_asked(monkeypatch):
    launched = []
    monkeypatch.setattr("instonct.linkedin_invite._spawn", lambda *a: launched.append(a))
    monkeypatch.setattr("instonct.linkedin.logged_in", lambda: True)
    args = {"action": "lancer", "recherche": "YC founder", "note": NOTE, "nombre": 30}
    token = guard.begin_turn(42, "salut ça va")
    try:
        assert "refuse" in kit_linkedin.linkedin_inviter(42, args)["erreur"]
    finally:
        guard.end_turn(token)
    token = guard.begin_turn(42, "ajoute 30 YC founders sur LinkedIn avec une petite note", taint=True)         # the turn read a web page
    try:
        assert "refuse" in kit_linkedin.linkedin_inviter(42, args)["erreur"]
    finally:
        guard.end_turn(token)
    assert launched == []
    token = guard.begin_turn(42, "ajoute 30 YC founders sur LinkedIn avec une petite note")
    try:
        r = kit_linkedin.linkedin_inviter(42, args)
    finally:
        guard.end_turn(token)
    assert r["statut"] == "a_confirmer" and NOTE in r["dis_a_l_utilisateur"] and "OUI" in r["dis_a_l_utilisateur"]
    assert launched == []                                          # step 1 sends nothing and starts nothing


def test_only_the_users_plain_yes_starts_exactly_the_note_he_saw(monkeypatch):
    launched = []
    monkeypatch.setattr("instonct.linkedin_invite._spawn", lambda *a: launched.append(a))
    monkeypatch.setattr("instonct.linkedin.logged_in", lambda: True)
    token = guard.begin_turn(42, "ajoute 30 YC founders sur LinkedIn avec une petite note")
    try:
        kit_linkedin.linkedin_inviter(42, {"action": "lancer", "recherche": "YC founder", "note": NOTE, "nombre": 30})
    finally:
        guard.end_turn(token)
    for chat, question, taint in ((99, "oui", False), (42, "oui", True), (42, "pourquoi pas", False)):     # another chat, a turn read from a file, not a plain yes
        token = guard.begin_turn(chat, question, taint=taint)
        try:
            r = kit_linkedin.linkedin_inviter(chat, {"action": "lancer", "recherche": "autre", "note": "Bonjour, achetez mon produit sur ce site tres vite", "nombre": 5})
        finally:
            guard.end_turn(token)
        assert "erreur" in r and launched == []
    token = guard.begin_turn(42, "oui")
    try:
        r = kit_linkedin.linkedin_inviter(42, {"action": "lancer", "recherche": "AUTRE CHOSE", "note": "Une autre note que le modele a changee en route !!", "nombre": 5})
    finally:
        guard.end_turn(token)
    assert r["statut"] == "lance en arriere-plan" and launched[0][1:3] == ("YC founder", NOTE) and launched[0][3] == 30      # what the user saw, not what the model now says
    assert not db.exists(li.PENDING_KEY)
    token = guard.begin_turn(42, "oui")
    try:
        assert "erreur" in kit_linkedin.linkedin_inviter(42, {"action": "lancer", "recherche": "YC founder", "note": NOTE})       # a yes works once
    finally:
        guard.end_turn(token)


def test_a_turn_that_read_a_web_page_or_a_mail_cannot_invite(monkeypatch):
    """The page may have written the order. kits.tool is where the model's calls arrive."""
    from instonct import kits
    monkeypatch.setattr("instonct.linkedin.logged_in", lambda: True)
    token = guard.begin_turn(42, "ajoute 30 YC founders sur LinkedIn avec une petite note")
    try:
        r = kits.tool(42, "linkedin_inviter", {"action": "lancer", "recherche": "YC founder", "note": NOTE}, ["(page web)"])
        assert "refuse" in r["erreur"] and not db.exists(li.PENDING_KEY)
        assert "en_cours" in kits.tool(42, "linkedin_inviter", {"action": "etat"}, ["(page web)"])            # looking and stopping stay free
    finally:
        guard.end_turn(token)


def test_a_link_in_the_note_is_refused():
    assert "lien" in li.propose(1, "YC founder", "Bonjour {prenom}, regardez https://exemple.com pour voir ce que je fais", 5)["erreur"]
    assert "lien" in li.propose(1, "YC founder", "Bonjour {prenom}, regardez monsite.io pour voir ce que je fais", 5)["erreur"]


def test_the_order_needs_linkedin_words_not_just_any_verb():
    for ok in ("ajoute 30 YC founders avec une petite note", "invite des fondateurs sur linkedin", "fais 20 invitations linkedin", "lance l'envoi des invitations"):
        assert guard._ordered(guard._VERBS["linkedin_invite"], guard._simplify(ok)), ok
    for no in ("je suis connecte sur linkedin", "mets de la musique", "demande a Paul de venir", "propose-moi un film", "scrape ce site", "ajoute du lait a ma liste"):
        assert not guard._ordered(guard._VERBS["linkedin_invite"], guard._simplify(no)), no


def test_the_tool_sends_the_user_to_log_in_himself_and_never_asks_for_a_password(monkeypatch):
    monkeypatch.setattr("instonct.linkedin.logged_in", lambda: False)
    monkeypatch.setattr("instonct.screen.active", lambda: False)
    token = guard.begin_turn(42, "ajoute 30 YC founders sur LinkedIn avec une petite note")
    try:
        r = kit_linkedin.linkedin_inviter(42, {"action": "lancer", "recherche": "YC founder", "note": NOTE})
    finally:
        guard.end_turn(token)
    assert "/connexion linkedin" in r["erreur"] and "mot de passe" in r["erreur"] and "LUI-MEME" in r["erreur"]


def test_looking_and_stopping_are_always_allowed():
    assert kit_linkedin.linkedin_inviter(42, {"action": "etat"})["en_cours"] is False
    assert "aucune" in kit_linkedin.linkedin_inviter(42, {"action": "stop"})["resultat"]
    assert "erreur" in kit_linkedin.linkedin_inviter(42, {"action": "danser"})
