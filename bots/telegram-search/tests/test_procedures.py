"""Procedures and calls: the bot prepares everything, and neither pays nor pretends. Fictional data only."""
import json
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from instonct import demarche, dispatch, llm, web
from instonct.core import db


def start(**args):
    return demarche.tool(7, "demarche", {"action": "start", "objectif": "Week-end", **args}, [])


def test_a_trip_gets_working_links_with_dates_and_people():
    out = start(type="voyage", depart="Paris", arrivee="New York", date="2026-12-01", retour="2026-12-05", personnes=2)
    assert "New York" in unquote(out["liens"]["vols"]) and "through 2026-12-05" in unquote(out["liens"]["vols"])
    hotel = parse_qs(urlparse(out["liens"]["hotel"]).query)
    assert hotel["ss"] == ["New York"] and hotel["checkin"] == ["2026-12-01"] and hotel["group_adults"] == ["2"]
    assert " " not in out["liens"]["trajets"]


def test_a_wrong_date_is_refused_rather_than_shown_as_a_good_link():
    assert "erreur" in start(type="voyage", arrivee="Lyon", date="1er decembre")
    assert db.hlen(demarche.KEY) == 0


def test_a_trip_without_a_destination_asks_for_it():
    assert "arrivee" in start(type="voyage")["erreur"]
    assert db.hlen(demarche.KEY) == 0


def test_groceries_without_a_list_ask_for_it():
    assert "produits" in start(type="courses")["erreur"]


def test_groceries_give_one_link_per_product():
    out = start(type="courses", produits=["lait demi-ecreme", "pates"])
    assert set(out["liens"]) == {"lait demi-ecreme", "pates"}
    assert "lait%20demi-ecreme" in out["liens"]["lait demi-ecreme"]["auchan"]


def test_every_kind_of_procedure_says_paying_stays_with_the_user():
    for kind in demarche.STEPS:
        assert "ne paies jamais" in start(type=kind, arrivee="Lyon", produits=["lait"])["regle"]


def test_notes_are_kept_capped_and_the_dossier_survives():
    ident = start()["id"]
    for i in range(demarche.MAX_NOTES + 5):
        demarche.tool(7, "demarche", {"action": "note", "id": ident, "texte": f"note {i}"}, [])
    again = demarche.tool(7, "demarche", {"action": "resume", "id": ident}, [])
    assert len(again["notes"]) == demarche.MAX_NOTES and again["notes"][-1]["texte"] == f"note {demarche.MAX_NOTES + 4}"


def test_notes_taken_from_a_page_stay_marked_as_coming_from_a_stranger():
    ident = start()["id"]
    demarche.tool(7, "demarche", {"action": "note", "id": ident, "texte": "prix 40 euros"}, ["(page web)"])
    links = []
    demarche.tool(7, "demarche", {"action": "resume", "id": ident}, links)
    assert links == ["(page web)"]


def test_old_finished_dossiers_go_first(monkeypatch):
    monkeypatch.setattr(demarche, "KEEP", 2)
    first = start(objectif="ancien")["id"]
    demarche.tool(7, "demarche", {"action": "finish", "id": first}, [])
    second, third = start(objectif="b")["id"], start(objectif="c")["id"]
    assert not db.hexists(demarche.KEY, first) and db.hexists(demarche.KEY, second) and db.hexists(demarche.KEY, third)


@pytest.fixture
def screen_opens(monkeypatch):
    opened, sent = [], []
    monkeypatch.setattr(demarche.remote_access, "open_screen", lambda chat, url: opened.append(url) or "Mot de passe de l'ecran : Secret12")
    monkeypatch.setattr(demarche, "send", lambda chat, text: sent.append(text))
    return opened, sent


def test_handing_over_never_gives_the_password_to_the_model(screen_opens):
    opened, sent = screen_opens
    out = demarche.tool(7, "demarche", {"action": "main", "url": "https://shop.example/panier"}, [])
    assert opened == ["https://shop.example/panier"]
    assert "Secret12" in sent[0] and "Secret12" not in json.dumps(out)


def test_after_reading_a_page_a_stranger_cannot_choose_the_address_opened_for_the_user(screen_opens):
    opened, _ = screen_opens
    demarche.tool(7, "demarche", {"action": "main", "url": "https://evil.example/fake-login"}, ["(page web)"])
    assert opened == ["about:blank"]


def test_only_https_addresses_are_handed_over(screen_opens):
    opened, _ = screen_opens
    demarche.tool(7, "demarche", {"action": "main", "url": "file:///etc/passwd"}, [])
    assert opened == ["about:blank"]


def test_when_the_screen_cannot_open_the_model_is_told(monkeypatch):
    monkeypatch.setattr(demarche.remote_access, "open_screen", lambda chat, url: "Je n'arrive pas a ouvrir l'ecran : Tailscale")
    assert "Tailscale" in demarche.tool(7, "demarche", {"action": "main"}, [])["erreur"]


@pytest.mark.parametrize("raw, want", [("01 23 45 67 89", "+33123456789"), ("0033 1 23 45 67 89", "+33123456789"), ("+1 (415) 555-0100", "+14155550100"),
                                       ("12", ""), ("appelle-moi", ""), ("", ""), ("123456789", "")])
def test_phone_numbers(raw, want):
    assert demarche.phone_number(raw) == want


def test_a_call_is_prepared_and_never_claimed():
    out = demarche.tool(7, "appel", {"numero": "01 23 45 67 89", "objet": "contester la facture 123", "qui": "Service client"}, [])
    assert out["lien"] == "tel:+33123456789" and "facture 123" in out["a_lire"] and "Aucune ligne" in out["attention"]


def test_a_call_without_a_number_says_to_look_for_it():
    out = demarche.tool(7, "appel", {"objet": "x"}, [])
    assert out["lien"] == "" and "web_search" in out["numero"]


@pytest.mark.parametrize("answer", ["J'ai appele le service client.", "Je viens de payer ta commande.", "J'ai commande tes courses.", "C'est reserve pour vendredi."])
def test_the_bot_cannot_claim_what_it_did_not_do(answer):
    assert llm.false_claim(answer, set())


def test_offers_and_rules_are_not_mistaken_for_actions():
    for answer in ("Veux-tu que je reserve ?", "Ce tarif est reserve aux etudiants.", "Tu peux payer sur ce lien.", "Je te prepare l'appel."):
        assert not llm.false_claim(answer, set())


def test_the_tools_are_reachable_through_dispatch():
    out = dispatch.run_tool(7, "demarche", {"action": "start", "objectif": "test"}, [])
    assert out["id"]
    assert "lien" in dispatch.run_tool(7, "appel", {"numero": "0123456789"}, [])


class FakeBrowser:
    """A page with one button, in the real browser's interface."""

    def __init__(self, button_text, kind="btn"):
        self.clicked, self.text, self.kind = [], button_text, kind

    def js(self, script, *a, **k):
        return "none" if "tagName" in script and "type" in script else "non"

    def call(self, tool, **a):
        self.clicked.append((tool, a))
        return ""


@pytest.mark.parametrize("label", ["Passer la commande", "Payer 42 euros", "Acheter maintenant", "Valider mon panier"])
def test_the_browser_refuses_every_paying_button(monkeypatch, label):
    b = FakeBrowser(label)
    monkeypatch.setattr(web, "_engine", lambda moteur: b)
    monkeypatch.setattr(web, "web_probe", lambda br, sel: {"kind": "btn", "text": label})
    out = web.tool_browser(7, {"action": "click", "selector": "#x", "moteur": "chrome"}, [])
    assert "paiement" in out["erreur"] and b.clicked == []


def test_an_ordinary_button_is_still_clicked(monkeypatch):
    b = FakeBrowser("Ajouter au panier")
    monkeypatch.setattr(web, "_engine", lambda moteur: b)
    monkeypatch.setattr(web, "web_probe", lambda br, sel: {"kind": "btn", "text": "Ajouter au panier"})
    monkeypatch.setattr(web, "web_page", lambda br, **k: {"adresse": "x"})
    assert web.tool_browser(7, {"action": "click", "selector": "#x", "moteur": "chrome"}, []) == {"adresse": "x"}
    assert b.clicked == [("click", {"selector": "#x"})]


def test_the_real_browser_cannot_log_in_for_the_user(monkeypatch):
    monkeypatch.setattr(web, "_engine", lambda moteur: FakeBrowser(""))
    assert "connecte lui-meme" in web.tool_browser(7, {"action": "login", "site": "x", "moteur": "chrome"}, [])["erreur"]
