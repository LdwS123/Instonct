"""News, research, time and holidays: all mocked here, and a source that fails is said, never filled in."""
from instonct import llm, mailindex, meetings, monde, web
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RSS = """<rss><channel><title>ignored</title>
<item><title>Un titre &amp; une suite - Le Journal</title><link>https://news.example/1</link><pubDate>Thu, 05 Nov 2026 08:00:00 GMT</pubDate><source url="https://j.example">Le Journal</source></item>
<item><title><![CDATA[Second titre]]></title><link>https://news.example/2</link></item>
</channel></rss>"""


class Resp:
    def __init__(self, text="", data=None, code=200):
        self.text, self._data, self.status_code = text, data, code

    def json(self):
        return self._data


def test_news_are_parsed_and_marked_as_external(monkeypatch):
    monkeypatch.setattr(web, "safe_get", lambda url, **k: Resp(RSS))
    links = []
    out = monde.tool("actu", {"sujet": "ia"}, links)
    assert out["nouvelles"][0]["titre"] == "Un titre & une suite - Le Journal" and out["nouvelles"][0]["source"] == "Le Journal"
    assert out["nouvelles"][1]["titre"] == "Second titre"
    assert links == ["(page web)"]


def test_news_fall_back_when_google_fails(monkeypatch):
    def boom(url, **k):
        raise OSError("coupure")
    monkeypatch.setattr(web, "safe_get", boom)
    monkeypatch.setattr(llm, "web_search", lambda q, n=5, kind="text": [{"title": "Autre", "href": "https://x.example", "source": "X", "date": "hier"}])
    assert monde.tool("actu", {"sujet": "ia"}, [])["nouvelles"][0]["titre"] == "Autre"


def test_no_news_is_said_plainly(monkeypatch):
    monkeypatch.setattr(web, "safe_get", lambda url, **k: Resp("<rss></rss>"))
    monkeypatch.setattr(llm, "web_search", lambda *a, **k: [])
    assert "erreur" in monde.tool("actu", {"sujet": "ia"}, [])


def test_research_reads_the_top_pages_and_uses_the_snippet_when_a_page_fails(monkeypatch):
    hits = [{"title": f"T{i}", "href": f"https://s{i}.example", "body": f"extrait {i}"} for i in range(5)]
    monkeypatch.setattr(llm, "web_search", lambda q, n=5, kind="text": hits)
    monkeypatch.setattr(web, "browse", lambda url: "Page illisible : non" if "s1" in url else "contenu " * 2000)
    links = []
    out = monde.tool("recherche_approfondie", {"question": "pourquoi ?"}, links)
    assert [p["lue"] for p in out["sources"]] == [True, False, True]
    assert out["sources"][1]["texte"] == "extrait 1" and len(out["sources"][0]["texte"]) == monde.PAGE_CHARS
    assert len(out["autres_resultats"]) == 2 and links == ["(page web)"]


def test_research_says_when_the_search_is_down(monkeypatch):
    monkeypatch.setattr(llm, "web_search", lambda *a, **k: [])
    assert "erreur" in monde.tool("recherche_approfondie", {"question": "x"}, [])


def test_world_time(monkeypatch):
    monkeypatch.setattr(web, "safe_get", lambda url, **k: Resp(data={"results": [{"name": "Tokyo", "country": "Japon", "timezone": "Asia/Tokyo"}]}))
    out = monde.tool("heure_monde", {"ville": "Tokyo"}, [])
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
    assert out["fuseau"] == "Asia/Tokyo" and out["decalage_utc"] == "+0900" and f"{now:%d/%m}" in out["heure"]


def test_unknown_city(monkeypatch):
    monkeypatch.setattr(web, "safe_get", lambda url, **k: Resp(data={}))
    assert "introuvable" in monde.tool("heure_monde", {"ville": "Zzz"}, [])["erreur"]


def test_holidays_are_sorted_with_their_day(monkeypatch):
    monkeypatch.setattr(web, "safe_get", lambda url, **k: Resp(data={"2030-12-25": "Noel", "2030-01-01": "Jour de l'an"}))
    out = monde.tool("feries", {"annee": 2030}, [])
    assert out["jours"][0].endswith("2030-01-01 : Jour de l'an") and out["jours"][0].startswith("mardi")
    assert out["prochain"] == "2030-01-01 : Jour de l'an"


def test_holidays_failure_is_said(monkeypatch):
    monkeypatch.setattr(web, "safe_get", lambda url, **k: Resp(code=500))
    assert "erreur" in monde.tool("feries", {"annee": 2030}, [])


def test_interview_prep_gathers_everything_and_says_what_failed(monkeypatch):
    monkeypatch.setattr(meetings, "tool", lambda a: {"rendez_vous": [{"entreprise": a["entreprise"]}]})
    def boom(*a, **k):
        raise OSError("index absent")
    monkeypatch.setattr(mailindex, "search", boom)
    monkeypatch.setattr(llm, "web_search", lambda q, n=5, kind="text": [{"title": "Site", "body": "fait des choses", "href": "https://a.example"}])
    monkeypatch.setattr(monde, "news", lambda subject, limit=6: [{"titre": "Levee"}])
    links = []
    out = monde.tool("prepare_entretien", {"entreprise": "Acme"}, links)
    assert out["rendez_vous"]["rendez_vous"][0]["entreprise"] == "Acme"
    assert "index absent" in out["mails"]["erreur"]
    assert out["presentation"][0]["titre"] == "Site" and out["actualite"][0]["titre"] == "Levee"
    assert links == ["(email lu)"] and "Ne donne une heure" in out["consigne"]


def test_empty_questions_are_refused():
    for name in ("actu", "recherche_approfondie", "heure_monde", "prepare_entretien"):
        assert "erreur" in monde.tool(name, {}, [])


def test_adverts_are_dropped_from_search_results(monkeypatch):
    import sys
    import types

    class Fake:
        def __init__(self, timeout=0):
            pass

        def text(self, query, max_results=5, region=""):
            return [{"title": "Pub", "href": "https://www.bing.com/aclick?ld=x"}, {"title": "Vrai", "href": "https://a.example"}]
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=Fake))
    assert [r["title"] for r in llm.web_search("x")] == ["Vrai"]
