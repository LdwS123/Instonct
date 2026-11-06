"""The model can ask for the tool it needs: no request is stuck because its words did not bring the right tool."""
import json

import pytest

from instonct import brain, catalog, dispatch, llm


class Reply:
    status_code = 200
    text = "{}"

    def __init__(self, message):
        self.message = message

    def json(self):
        return {"choices": [{"message": self.message}], "usage": {"total_tokens": 50}}


def names(tools):
    return [x["function"]["name"] for x in tools]


@pytest.mark.parametrize("need, expected", [
    ("reveiller mon ordinateur sur le reseau", "wake_on_lan"),
    ("convertir des euros en dollars", "money"),
    ("ajouter des gens sur linkedin avec une note", "linkedin_inviter"),
    ("quand est mon entretien", "rdv_a_venir"),
])
def test_find_tools_returns_the_tool_that_fits(need, expected):
    assert expected in names(catalog.find_tools(need))


def test_find_tools_never_returns_itself_or_more_than_the_limit():
    found = names(catalog.find_tools("cherche un outil pour faire des choses", limit=3))
    assert len(found) <= 3 and "chercher_outil" not in found


def test_nothing_matches_gives_an_empty_list():
    assert catalog.find_tools("zzzz qqqq") == []


def test_the_tool_is_always_offered_and_the_tool_itself_answers():
    assert "chercher_outil" in names(catalog.select_tools("bonjour mon ami"))
    out = dispatch.run_tool(1, "chercher_outil", {"besoin": "convertir des euros en dollars"}, [])
    assert "money" in [o["nom"] for o in out["outils_ajoutes"]]
    assert "erreur" in dispatch.run_tool(1, "chercher_outil", {"besoin": "zzzz qqqq"}, [])


def test_the_found_tools_are_offered_on_the_next_step_only_for_this_turn(monkeypatch):
    seen = []

    def fake(messages, question, oral, tools=True, toolset=None, plain=False):
        seen.append(names(toolset or []))
        if len(seen) == 1:
            return Reply({"content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "chercher_outil", "arguments": json.dumps({"besoin": "reveiller mon ordinateur"})}}]})
        return Reply({"content": "Voila, j'ai trouve l'outil."})

    monkeypatch.setattr(llm, "llm_call", fake)
    before = list(catalog.GROQ_TOOLS)
    brain.agent_groq(5, "fais un truc bizarre que personne n'a prevu")
    assert "wake_on_lan" not in seen[0] and "wake_on_lan" in seen[1]
    assert catalog.GROQ_TOOLS == before                      # the shared list is never changed
