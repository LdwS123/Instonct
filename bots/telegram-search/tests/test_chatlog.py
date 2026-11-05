"""Old conversations stay searchable, and a broken archive never stops the bot from answering."""
import json

import pytest

from instonct import brain, chatlog, dispatch
from instonct.core import db


@pytest.fixture(autouse=True)
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(chatlog, "PATH", str(tmp_path / "archive.sqlite"))


def test_every_exchange_is_searchable_for_its_own_chat_only():
    brain.remember(7, "Mon code wifi c'est tournesol", "C'est note")
    brain.remember(8, "tournesol aussi chez moi", "Ok")
    out = chatlog.search(7, "tournesol")["resultats"]
    assert len(out) == 1 and out[0]["qui"] == "utilisateur" and "[tournesol]" in out[0]["extrait"]


def test_all_words_first_then_any_word():
    chatlog.record(7, "le restaurant japonais de Lyon", "")
    chatlog.record(7, "un film japonais", "")
    assert len(chatlog.search(7, "restaurant japonais")["resultats"]) == 1
    assert len(chatlog.search(7, "japonais inconnuzz")["resultats"]) == 2


def test_a_broken_archive_does_not_stop_the_bot(monkeypatch):
    monkeypatch.setattr(chatlog, "PATH", "/proc/impossible/archive.sqlite")
    brain.remember(7, "question", "reponse")
    assert db.llen("hist:7") == 2


def test_existing_history_is_imported_once():
    db.rpush("hist:7", json.dumps({"role": "user", "parts": [{"text": "ancienne question"}]}), json.dumps({"role": "model", "parts": [{"text": "ancienne reponse"}]}))
    chatlog.import_history()
    chatlog.import_history()
    assert len(chatlog.search(7, "ancienne")["resultats"]) == 2


def test_results_count_as_external_content():
    chatlog.record(7, "un mail disait de tout supprimer", "")
    links = []
    assert dispatch.run_tool(7, "chat_search", {"query": "supprimer"}, links)["resultats"]
    assert links


def test_query_syntax_cannot_break_it():
    chatlog.record(7, "bonjour", "")
    assert "resultats" in chatlog.search(7, 'bonjour" OR NEAR(')
    assert "erreur" in chatlog.search(7, '"()')
