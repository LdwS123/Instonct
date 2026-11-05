"""Tool catalogue and routing: the right tools are offered, unknown tools are refused, simple tools work."""
from instonct import catalog, dispatch


def names(tools):
    return {t["function"]["name"] if "function" in t else t["name"] for t in tools}


def test_mail_request_offers_mail_tools():
    assert "mail_clean" in names(catalog.select_tools("envoie un mail a paul"))


def test_volume_tool_only_when_relevant():
    assert "change_volume" in names(catalog.select_tools("monte le son"))
    assert "change_volume" not in names(catalog.select_tools("quelle heure est-il"))


def test_tool_list_stays_small_for_small_talk():
    assert len(catalog.select_tools("bonjour")) < 30


def test_system_prompt_has_an_oral_variant():
    a, b = catalog.build_system(False), catalog.build_system(True)
    assert isinstance(a, str) and len(a) > 1000 and a != b


def test_run_tool_calculation_and_unknown_tool():
    assert dispatch.run_tool(1, "calcul", {"expression": "(12+8)*3"}, []) == {"resultat": 60}
    assert dispatch.run_tool(1, "does_not_exist", {}, []) == {"erreur": "outil inconnu"}
