"""Pure text helpers: normalisation, cleaning of model answers, speech, time parsing."""
from instonct import core, life, llm, sound


def test_norm_strips_accents_and_case():
    assert core.norm("  Éléphant  À l'été ") == "elephant  a l'ete"


def test_clean_answer_removes_think_tags():
    assert llm.clean_answer("<think>secret</think>Salut **toi**") == "Salut **toi**"


def test_clean_for_speech_drops_links_and_markdown():
    out = sound.clean_for_speech("Voici https://a.fr/x **gras** fin")
    assert "http" not in out and "*" not in out and "gras" in out


def test_parse_hhmm():
    assert life.parse_hhmm("7h15") == "07:15"
    assert life.parse_hhmm("25h") is None
