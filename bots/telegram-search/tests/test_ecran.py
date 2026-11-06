"""Computer use (kit_ecran). No real screen, no real Gemini call: a fake browser and a fake picture model. Nothing is clicked, typed or paid for real."""
import json
import types

import pytest

from instonct import catalog, guard, kit_ecran, kits
from instonct.core import db


class FakeScreen:
    """A page with a few things on it. `under` is what the real DOM would answer for the point that is clicked."""

    def __init__(self, under=None, active=None):
        self.under, self.active = under or {"tag": "button", "label": "Rechercher", "href": ""}, active or {"tag": "input", "type": "text", "editable": True, "field": "q", "submit": ""}
        self.events, self.typed, self.urls = [], [], []

    def js(self, script):
        if "innerWidth" in script:
            return json.dumps({"w": 1000, "h": 500, "url": "https://exemple.fr/", "title": "Exemple"})
        if "elementFromPoint" in script:
            return json.dumps(self.under)
        if "activeElement" in script:
            return json.dumps(self.active)
        return ""

    def _send(self, method, timeout=30, **p):
        if method == "Page.captureScreenshot":
            return {"data": "aGVsbG8="}
        if method == "Input.insertText":
            self.typed.append(p["text"])
        self.events.append((method, p))
        return {}

    def call(self, tool, **a):
        self.urls.append(a.get("url"))
        return ""

    def _settle(self):
        pass


VISION = {"resume": "Une page de recherche.", "elements": [
    {"label": "Rechercher", "type": "bouton", "box": [100, 200, 200, 400]},
    {"label": "Champ de recherche", "type": "champ", "box": [300, 0, 400, 1000]},
    {"label": "mauvais", "type": "bouton", "box": [5, 5]}]}


@pytest.fixture
def screen(monkeypatch):
    s = FakeScreen()
    monkeypatch.setattr(kit_ecran, "_browser", lambda: s)
    monkeypatch.setattr(kit_ecran, "_alive", lambda: None)
    monkeypatch.setattr(kit_ecran, "_vision", lambda data: (VISION["resume"], VISION["elements"]))
    monkeypatch.setattr("instonct.web.url_ok", lambda u: "localhost" not in u and "192.168" not in u)
    return s


def turn(text, taint=False):
    return guard.begin_turn(5, text, taint=taint)


def run(text, **a):
    token = turn(text)
    try:
        return kit_ecran.ecran(5, a)
    finally:
        guard.end_turn(token)


def test_seeing_gives_numbered_click_points_and_drops_broken_boxes(screen):
    token = turn("regarde l'ecran")
    try:
        r = kit_ecran.ecran(5, {"action": "voir"})
        assert r["resume"].startswith("Une page") and [e["n"] for e in r["elements"]] == [1, 2] and "x" not in r["elements"][0]     # the model sees no pixels
        assert kit_ecran._stored(5)[0]["x"] == 300.0 and kit_ecran._stored(5)[0]["y"] == 75.0                                    # centre of the box, in CSS pixels
        links = []
        kits.tool(5, "ecran", {"action": "voir"}, links)
        assert links                                                                                                              # looking locks the guarded tools
    finally:
        guard.end_turn(token)


def test_a_click_by_number_hits_the_centre_and_forgets_the_old_picture(screen):
    token = turn("clique sur rechercher")
    try:
        kit_ecran.ecran(5, {"action": "voir"})
        r = kit_ecran.ecran(5, {"action": "cliquer", "numero": 1})
        assert r["ok"] and [e[1]["type"] for e in screen.events if e[0] == "Input.dispatchMouseEvent"] == ["mouseMoved", "mousePressed", "mouseReleased"]
        assert "erreur" in kit_ecran.ecran(5, {"action": "cliquer", "numero": 1})                                                   # stale list: look again first
    finally:
        guard.end_turn(token)


def test_a_mail_a_file_or_an_automatism_cannot_drive_the_screen(screen):
    token = turn("clique sur rechercher", taint=True)
    try:
        assert "refuse" in kit_ecran.ecran(5, {"action": "voir"})["erreur"] and screen.events == []
    finally:
        guard.end_turn(token)
    assert "refuse" in kit_ecran.ecran(5, {"action": "voir"})["erreur"]                                                              # no turn at all


def test_paying_subscribing_and_creating_an_account_are_refused_whatever_the_user_says(screen):
    for label, href in (("Payer maintenant", ""), ("Place your order", ""), ("Continuer", "https://shop.fr/checkout/pay"), ("Creer un compte", ""), ("Sign up", ""), ("S'abonner", "")):
        screen.under = {"tag": "button", "label": label, "href": href}
        r = run("valide et paie la commande, envoie tout", action="cliquer", x=500, y=500)
        assert "refuse" in r["erreur"] and "utilisateur" in r["erreur"], label
    assert not [e for e in screen.events if e[1].get("type") == "mousePressed"]


def test_sending_needs_the_users_own_word(screen):
    screen.under = {"tag": "button", "label": "Envoyer", "href": ""}
    assert "pas demande" in run("regarde ce formulaire", action="cliquer", x=1, y=1)["erreur"]
    assert run("remplis et envoie le formulaire", action="cliquer", x=1, y=1)["ok"]
    assert "pas demande" in run("ne l'envoie pas encore", action="cliquer", x=1, y=1)["erreur"]


def test_nothing_is_typed_in_a_password_or_card_field(screen):
    for active in ({"editable": True, "type": "password", "field": ""}, {"editable": True, "type": "text", "field": "Mot de passe"},
                   {"editable": True, "type": "text", "field": "cc-number"}, {"editable": True, "type": "text", "field": "email", "card": True}):
        screen.active = active
        assert "refuse" in run("connecte-toi", action="taper", texte="secret")["erreur"], active
    assert screen.typed == []
    screen.active = {"editable": True, "type": "text", "field": "q", "submit": ""}
    assert run("cherche des chaussures", action="taper", texte="chaussures")["ok"] and screen.typed == ["chaussures"]


def test_typing_without_a_selected_field_says_so(screen):
    screen.active = {}
    assert "champ" in run("ecris bonjour", action="taper", texte="bonjour")["erreur"]


def test_enter_submits_only_what_a_click_on_its_button_would_be_allowed_to(screen):
    screen.active = {"editable": True, "type": "text", "field": "message", "submit": "Envoyer"}
    assert "pas demande" in run("regarde", action="touche", touche="entree")["erreur"]
    assert run("ecris et envoie le message", action="touche", touche="entree")["ok"]
    screen.active = {"editable": True, "type": "text", "field": "q", "submit": "Rechercher"}
    assert run("cherche", action="touche", touche="Enter")["ok"]
    screen.active = {"editable": True, "type": "text", "field": "q", "submit": "Payer"}
    assert "refuse" in run("cherche", action="touche", touche="Enter")["erreur"]
    assert "inconnue" in run("x", action="touche", touche="F13")["erreur"]


def test_only_public_sites_and_short_addresses_after_reading_a_page(screen):
    assert run("va sur exemple.fr", action="aller", url="exemple.fr")["ok"] and screen.urls == ["https://exemple.fr"]
    for bad in ("http://localhost:8080/", "http://192.168.1.64/", "javascript:alert(1)", "file:///etc/passwd"):
        assert "refuse" in run("va sur ce site", action="aller", url=bad)["erreur"], bad
    db.set("ecran:seen:5", 1, ex=60)
    assert "trop longue" in run("va sur ce site", action="aller", url="https://exemple.fr/?d=" + "a" * 200)["erreur"]


def test_thirty_gestures_per_message_and_no_more(screen):
    token = turn("fais defiler la page")
    try:
        outs = [kit_ecran.ecran(5, {"action": "defiler"}) for _ in range(kit_ecran.MAX_ACTIONS + 1)]
    finally:
        guard.end_turn(token)
    assert all(o.get("ok") for o in outs[:-1]) and "limite" in outs[-1]["erreur"]
    assert run("defile", action="defiler", sens="haut")["ok"]                                                                          # the next message starts again


def test_a_dead_screen_is_reported_not_crashed(monkeypatch):
    def boom():
        raise RuntimeError("l'ecran ne demarre pas")
    monkeypatch.setattr(kit_ecran, "_browser", boom)
    monkeypatch.setattr(kit_ecran, "_alive", lambda: None)
    assert "ne demarre pas" in run("regarde l'ecran", action="voir")["erreur"]


def test_unknown_actions_are_refused(screen):
    assert "inconnue" in run("fais un truc", action="exploser")["erreur"]


def test_the_picture_model_answer_is_cleaned(monkeypatch):
    fake = types.SimpleNamespace(status_code=200, json=lambda: {"candidates": [{"content": {"parts": [{"text": "Voici :\n```json\n" + json.dumps(VISION) + "\n```"}]}}]})
    monkeypatch.setattr("instonct.llm.call_gemini", lambda body: (setattr(fake, "body", body), fake)[1])
    resume, elements = kit_ecran._vision("aGVsbG8=")
    assert resume.startswith("Une page") and len(elements) == 3 and fake.body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"
    fake.json = lambda: {"candidates": [{"content": {"parts": [{"text": "pas de json"}]}}]}
    assert kit_ecran._vision("x") == ("", [])
    fake.status_code = 429
    with pytest.raises(RuntimeError):
        kit_ecran._vision("x")


def test_the_users_words_bring_the_tool_and_its_rules():
    for said in ("clique sur le bouton vert", "Il faut qu'on lui rajoute du computer use", "va sur le site de la CAF et remplis le formulaire", "regarde l'ecran"):
        names = {t["function"]["name"] for t in catalog.select_tools(said)}
        assert "ecran" in names, said
        assert "ECRAN (computer use)" in catalog.build_system(False, catalog.select_tools(said), said), said
