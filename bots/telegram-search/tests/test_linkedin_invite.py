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


# ---------------------------------------------------------------- the plain connection request (no note), asked on 2026-11-06
class PlainLinkedIn(FakeLinkedIn):
    """Same fake LinkedIn, but the dialog offers « Send without a note » (or, with instant=True, no dialog: the account sends at once)."""

    def __init__(self, pages, instant=False, dialog_text="", no_button=False, **kw):
        super().__init__(pages, **kw)
        self.instant, self.dialog_text, self.no_button = instant, dialog_text, no_button

    def call(self, tool, **a):
        if tool == "click" and a["selector"].startswith("[data-lpi="):
            self.clicks += 1
            n = int(re.search(r'"(\d+)"', a["selector"]).group(1))
            person = self.pages[self.page][n - 1]
            if self.instant:
                self.sent.append((person, ""))
            else:
                self.dialog = {"person": person, "textarea": False, "text": self.dialog_text}
            return ""
        if tool == "click" and a["selector"] == "PLAIN":
            self.sent.append((self.dialog["person"], ""))
            self.dialog = None
            return ""
        return super().call(tool, **a)

    def js(self, script):
        marker = re.match(r"/\*([a-z:]+)\*/", script).group(1)
        if marker == "tag:plain":
            return "PLAIN" if self.dialog and not self.no_button else ""
        if marker == "gone":
            return "1" if self.sent else ""
        return super().js(script)


@pytest.fixture
def plain(monkeypatch, fake):
    def install(**kw):
        said = fake(pages={})[1]                                          # the silent Telegram / no-pause patches
        b = PlainLinkedIn(**kw)
        monkeypatch.setattr("instonct.linkedin_invite._driver", lambda: b)
        return b, said
    return install


def test_plain_requests_go_out_without_any_note(plain):
    b, said = plain(pages={1: people(4)})
    li._run(1, "YC founder", "", 3)
    assert len(b.sent) == 3 and all(note == "" for _, note in b.sent)
    assert len({p[1] for p, _ in b.sent}) == 3 and li.counted_today() == 3 and "sans note" in said[-1]


def test_an_account_that_sends_at_once_is_checked_not_assumed(plain):
    b, _ = plain(pages={1: people(3)}, instant=True)
    li._run(1, "YC founder", "", 2)
    assert len(b.sent) == 2 and li.counted_today() == 2


def test_no_send_button_means_nothing_sent_and_the_job_says_so(plain):
    b, said = plain(pages={1: people(5)}, no_button=True)
    li._run(1, "YC founder", "", 5)
    assert b.sent == [] and li.counted_today() == 0 and said


def test_the_weekly_limit_dialog_stops_a_plain_job(plain):
    b, said = plain(pages={1: people(3)}, dialog_text="You have reached the weekly invitation limit")
    li._run(1, "YC founder", "", 3)
    assert b.sent == [] and "limite" in said[-1]


def test_a_short_note_is_still_refused_but_no_note_is_fine():
    assert "erreur" in li._check("YC founder", "trop court", 5)[0]
    assert li._check("YC founder", "", 5)[0] is None


def test_the_user_sees_that_there_is_no_note_before_saying_yes(monkeypatch):
    launched = []
    monkeypatch.setattr("instonct.linkedin_invite._spawn", lambda *a: launched.append(a))
    monkeypatch.setattr("instonct.linkedin.logged_in", lambda: True)
    token = guard.begin_turn(42, "Tu peux envoyer 10 demande de connexion à 10 founder yc sans note juste la demande de connexion")
    try:
        forgot = kit_linkedin.linkedin_inviter(42, {"action": "lancer", "recherche": "YC founder", "nombre": 10})
        assert "sans_note" in forgot["erreur"] and not db.exists(li.PENDING_KEY)            # the model may not drop the note silently
        r = kit_linkedin.linkedin_inviter(42, {"action": "lancer", "recherche": "YC founder", "sans_note": True, "nombre": 10})
    finally:
        guard.end_turn(token)
    assert r["statut"] == "a_confirmer" and "SANS note" in r["dis_a_l_utilisateur"] and "OUI" in r["dis_a_l_utilisateur"] and launched == []
    token = guard.begin_turn(42, "oui")
    try:
        r = kit_linkedin.linkedin_inviter(42, {"action": "lancer"})
    finally:
        guard.end_turn(token)
    assert r["statut"] == "lance en arriere-plan" and launched[0][1:4] == ("YC founder", "", 10) and "sans note" in r["dis_a_l_utilisateur"]


def test_the_words_the_user_really_used_bring_the_tool_and_the_permission():
    """The 2026-11-06 failure: no « linkedin » in the message, so the tool was never offered and the bot said « impossible »."""
    from instonct import catalog
    for said in ("Tu peux envoyer 10 demande de connexion à 10 founder yc sans note juste la demande de connexion",
                 "envoie 20 demandes de connexion à des YC founders", "ajoute des fondateurs yc"):
        names = {t["function"]["name"] for t in catalog.select_tools(said)}
        assert "linkedin_inviter" in names, said
        assert guard._ordered(guard._VERBS["linkedin_invite"], guard._simplify(said)), said


# ---- regression: seen on the real page (2026-11-06), LinkedIn draws its dialogs inside the shadow root of #interop-outlet, so every
# `document.querySelector('[role=dialog]')` found nothing and the bot reported "LinkedIn n'a pas valide l'envoi" for every person.
def test_page_scripts_look_inside_the_shadow_root_of_the_dialog_outlet():
    from instonct import linkedin_invite as li, realbrowser
    for script in (li.DIALOG_JS, li.VALUE_JS, li.tag_js("plain"), li.tag_js("note"), li.tag_js("text"), li.tag_js("send"), realbrowser._CENTER):
        assert "#interop-outlet" in script and "shadowRoot" in script
    assert "interop-outlet" in realbrowser._QS


@pytest.mark.parametrize("label", ["Envoyer sans note", "Send without a note", "envoyer sans note"])
def test_plain_button_label_of_the_real_dialog_matches(label):
    import re
    from instonct import linkedin_invite as li
    assert re.match(li._BUTTONS["plain"], label, re.I)


# ---- the bot must never say "invitations sent" when nothing left (real case, 2026-11-06: 10 invented names) ----
from instonct import llm


@pytest.mark.parametrize("claim", [
    "Les 10 invitations aux fondateurs YC ont été envoyées sans note.",
    "Les invitations ont bien été envoyées ; elles restent en attente.",
    "Oui, ils sont partis.",
    "J'ai envoyé 10 invitations LinkedIn.",
    "Tes demandes de connexion sont envoyées.",
])
def test_an_invitations_sent_claim_needs_a_real_send(claim):
    assert llm.false_claim(claim, set())
    assert llm.false_claim(claim, {"linkedin", "browser", "mail_search", "linkedin_inviter"})     # a search, a page or a mere proposal is not a send
    assert not llm.false_claim(claim, {"linkedin_envoye"})


@pytest.mark.parametrize("said", [
    "Je te propose d'envoyer 10 invitations, tu confirmes ?",
    "Voici la liste des fondateurs trouvés.",
    "Les invitations partiront une par une, ça prend environ 10 minutes.",
])
def test_plans_and_launches_are_not_claims(said):
    assert not llm.false_claim(said, set())


def test_only_the_real_counters_count_as_proof():
    assert llm.proof("linkedin_inviter", {"en_cours": True, "envoyees": 3, "aujourdhui": 3}) == {"linkedin_envoye"}
    assert llm.proof("linkedin_inviter", {"en_cours": False, "aujourdhui": 2}) == {"linkedin_envoye"}
    assert llm.proof("linkedin_inviter", {"en_cours": False, "aujourdhui": 0, "cette_semaine": 5}) == set()
    assert llm.proof("linkedin_inviter", {"statut": "a_confirmer", "invitations_prevues": 10}) == set()
    assert llm.proof("linkedin", {"aujourdhui": 9}) == set()          # another tool never proves it


def test_the_read_only_linkedin_tool_does_not_pretend_to_send():
    """The model once called linkedin(action='lancer'): the tool silently ran a job search in 0.0 s and the model announced a send."""
    for action in ("lancer", "inviter", "envoyer", "connect"):
        out = linkedin.tool({"action": action, "keywords": "YC founder"})
        assert "erreur" in out and "linkedin_inviter" in out["erreur"]


def test_a_refused_linkedin_call_does_not_lock_the_inviter(monkeypatch):
    from instonct import dispatch
    links = []
    out = dispatch._run_tool(1, "linkedin", {"action": "lancer"}, links)
    assert "erreur" in out and links == []
    monkeypatch.setattr(linkedin, "tool", lambda args: {"texte": "une page"})
    dispatch._run_tool(1, "linkedin", {"action": "page"}, links)
    assert links == ["(page web)"]
