"""The journal tells what a tool really did, and the search has a second try before giving up."""
import sys
import types

from instonct import dispatch, journal, llm
from instonct.core import db


def test_a_failed_tool_shows_as_failed_and_a_good_one_as_ok(monkeypatch):
    db.delete(journal.KEY)
    monkeypatch.setattr(dispatch, "_run_tool", lambda chat, name, args, links: {"erreur": "page bloquee"} if name == "browser" else {"resultat": "fait"})
    dispatch.run_tool(1, "browser", {"url": "https://secret.example/?token=abc"}, [])
    dispatch.run_tool(1, "set_volume", {"level": 30}, [])
    text = journal.report()
    assert "RATE" in text and "browser : page bloquee" in text and "OK " in text and "set_volume" in text
    assert "secret.example" not in text and "token" not in text          # arguments are never kept


def test_a_crashing_tool_is_written_down_and_still_raises(monkeypatch):
    db.delete(journal.KEY)
    def boom(*a):
        raise RuntimeError("x")
    monkeypatch.setattr(dispatch, "_run_tool", boom)
    try:
        dispatch.run_tool(1, "browser", {}, [])
    except RuntimeError:
        pass
    assert "plantage" in journal.report()


def test_reads_do_not_drown_the_actions(monkeypatch):
    db.delete(journal.KEY)
    journal.tool("calcul", {"resultat": "4"})
    assert "rien fait" in journal.report()


def test_the_journal_keeps_only_the_last_entries():
    db.delete(journal.KEY)
    for i in range(journal.KEEP + 20):
        journal.tool("set_volume", {"resultat": str(i)})
    assert db.llen(journal.KEY) == journal.KEEP


def test_a_direct_order_is_written_with_its_answer():
    db.delete(journal.KEY)
    journal.order("arrete la tele", "Tele eteinte.")
    assert "ordre : arrete la tele : Tele eteinte." in journal.report()


def test_search_tries_the_spare_engines_when_the_usual_mix_finds_nothing(monkeypatch):
    seen = []

    class Fake:
        def __init__(self, timeout=5):
            pass

        def text(self, query, **k):
            seen.append(k.get("backend"))
            return [{"title": "t", "href": "https://a.example/", "body": "b"}] if k.get("backend") else []
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=Fake))
    monkeypatch.setattr(llm, "SEARXNG_URL", "")
    assert llm.web_search("test")[0]["href"] == "https://a.example/" and seen == [None, llm.SPARE_ENGINES]


def test_search_does_not_retry_when_the_first_try_works(monkeypatch):
    seen = []

    class Fake:
        def __init__(self, timeout=5):
            pass

        def text(self, query, **k):
            seen.append(1)
            return [{"title": "t", "href": "https://a.example/", "body": "b"}]
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=Fake))
    llm.web_search("test")
    assert len(seen) == 1


def test_our_own_search_engine_answers_before_the_spare_engines(monkeypatch):
    class Fake:
        def __init__(self, timeout=5):
            pass

        def text(self, query, **k):
            assert not k.get("backend"), "the spare engines must not be asked when SearXNG answered"
            return []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"title": "T", "content": "C", "url": "https://s.example/x", "publishedDate": "2026-11-01T00:00:00"}, {"title": "pub", "url": "https://duckduckgo.com/y.js?x"}]}
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=Fake))
    monkeypatch.setattr(llm, "SEARXNG_URL", "http://x")
    monkeypatch.setattr(llm.requests, "get", lambda *a, **k: Reply())
    assert llm.web_search("test") == [{"title": "T", "body": "C", "href": "https://s.example/x", "date": "2026-11-01"}]


def test_a_dead_searxng_does_not_break_the_search(monkeypatch):
    monkeypatch.setattr(llm, "SEARXNG_URL", "http://x")
    def down(*a, **k):
        raise llm.requests.ConnectionError("refused")
    monkeypatch.setattr(llm.requests, "get", down)
    assert llm.searxng("test", 5, "text") == []
