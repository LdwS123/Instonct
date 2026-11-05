"""A model writes a made-up hotel, price or link with full confidence. Plain code checks them against what the tools really returned."""
import json

from instonct import brain, catalog, dispatch, llm


class Reply:
    def __init__(self, content="", calls=None):
        self.message = {"content": content, **({"tool_calls": calls} if calls else {})}

    def json(self):
        return {"choices": [{"message": self.message}]}


def call(name, **args):
    return [{"id": "1", "function": {"name": name, "arguments": json.dumps(args)}}]


def script(monkeypatch, *replies):
    queue, sent = list(replies), []
    def fake(messages, *a, **k):
        sent.append([dict(m) for m in messages])
        return queue.pop(0)
    monkeypatch.setattr(llm, "llm_call", fake)
    monkeypatch.setattr(brain, "_recent_history", lambda chat: [])
    monkeypatch.setattr(catalog, "is_small_talk", lambda q: False)
    return sent


def test_a_link_from_a_tool_passes_and_a_made_up_one_does_not():
    known = '{"lien": "https://shop.example/produit/12?x=a%20b"}'
    assert llm.invented("Voici https://shop.example/produit/12?x=a%20b.", known) == []
    assert llm.invented("Voici https://shop.example/produit/99", known) == ["https://shop.example/produit/99"]


def test_a_home_page_is_not_treated_as_invented():
    assert llm.invented("Le site : https://www.service-public.fr/", "") == []


def test_prices_must_have_been_seen():
    assert llm.invented("Ca coute 129 € la nuit", "prix : 129") == []
    assert llm.invented("Ca coute 1 299 €", "prix : 1299") == []
    assert llm.invented("Ca coute 2,99 euros", "") == ["2,99 euros"]
    assert llm.invented("Ta facture de 45 euros", "ma facture de 45 euros") == []


def test_plain_numbers_and_hours_are_left_alone():
    assert llm.invented("Rendez-vous a 14 h, 3 personnes, salle 12", "") == []


def test_a_made_up_price_is_sent_back_once_and_the_second_answer_is_used(monkeypatch):
    sent = script(monkeypatch, Reply("Amazon : piles a 2,99 €"), Reply("Je n'ai pas pu verifier les prix."))
    text, _ = brain.agent_groq(7, "Trouve des piles")
    assert text == "Je n'ai pas pu verifier les prix."
    assert "2,99" in sent[1][-1]["content"]


def test_if_it_insists_the_user_is_warned(monkeypatch):
    script(monkeypatch, Reply("Hotel a 85 €"), Reply("Hotel a 85 €"))
    text, _ = brain.agent_groq(7, "Un hotel ?")
    assert "pas pu verifier" in text and "85 €" in text


def test_a_price_read_by_a_tool_goes_straight_through(monkeypatch):
    monkeypatch.setattr(dispatch, "run_tool", lambda chat, name, args, links: {"prix": "85 €", "lien": "https://h.example/chambre"})
    sent = script(monkeypatch, Reply("", call("web_search", query="hotel")), Reply("Chambre a 85 € : https://h.example/chambre"))
    text, _ = brain.agent_groq(7, "Un hotel ?")
    assert text == "Chambre a 85 € : https://h.example/chambre" and len(sent) == 2


def test_endless_searching_is_stopped(monkeypatch):
    done = []
    monkeypatch.setattr(dispatch, "run_tool", lambda chat, name, args, links: done.append(args) or {"resultats": []})
    calls = [Reply("", call("mail_search", query=f"mot {i}")) for i in range(brain.MAX_SEARCHES + 3)]
    script(monkeypatch, *calls, Reply("Rien trouve."))
    assert brain.agent_groq(7, "Trouve ma facture")[0] == "Rien trouve."
    assert len(done) == brain.MAX_SEARCHES


def test_model_citation_marks_are_removed():
    assert llm.clean_answer("Les prix montent【1†titre】.") == "Les prix montent."


def test_asking_for_real_research_offers_the_tool_that_reads_pages():
    names = {t["function"]["name"] for t in catalog.select_tools("Fais une vraie recherche sur la RAM")}
    assert "recherche_approfondie" in names and "web_search" not in names


def test_buying_offers_the_procedure_tool():
    assert "demarche" in {t["function"]["name"] for t in catalog.select_tools("Achete-moi des piles")}


def test_a_tool_that_failed_cannot_back_up_a_claim(monkeypatch):
    monkeypatch.setattr(dispatch, "run_tool", lambda chat, name, args, links: {"erreur": "page bloquee"})
    sent = script(monkeypatch, Reply("", call("browser", action="open")), Reply("J'ai ouvert la page."), Reply("La page est bloquee."))
    assert brain.agent_groq(7, "Ouvre la page")[0] == "La page est bloquee." and len(sent) == 3


def test_a_tool_that_worked_backs_up_the_claim(monkeypatch):
    monkeypatch.setattr(dispatch, "run_tool", lambda chat, name, args, links: {"page": "ok"})
    sent = script(monkeypatch, Reply("", call("browser", action="open")), Reply("J'ai ouvert la page."))
    assert brain.agent_groq(7, "Ouvre la page")[0] == "J'ai ouvert la page." and len(sent) == 2
