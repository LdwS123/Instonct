"""LinkedIn is read slowly, read-only, and the bot stops the moment LinkedIn pushes back."""
import sqlite3

import pytest

from instonct import dispatch, linkedin, screen
from instonct.core import db

CARD = """<li><div class="base-card" data-entity-urn="urn:li:jobPosting:{id}"><a class="base-card__full-link" href="https://fr.linkedin.com/jobs/view/x-{id}?refId=abc"></a>
<h3 class="base-search-card__title"> Customer Success </h3><h4 class="base-search-card__subtitle"><a> Acme </a></h4>
<span class="job-search-card__location"> Paris </span><time datetime="2026-11-01"></time></div></li>"""


class Reply:
    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")


@pytest.fixture
def web(monkeypatch):
    calls = []
    answers = []
    monkeypatch.setattr(linkedin.time, "sleep", lambda s: None)
    monkeypatch.setattr(linkedin.requests, "get", lambda url, params=None, headers=None, timeout=None: calls.append((url, params)) or answers.pop(0))
    return calls, answers


def test_public_jobs_are_parsed_without_tracking_junk(web):
    calls, answers = web
    answers.append(Reply(CARD.format(id=42)))
    out = linkedin.jobs("customer success", "Paris", days=7)
    assert out["offres"] == [{"id": "42", "titre": "Customer Success", "entreprise": "Acme", "lieu": "Paris", "date": "2026-11-01", "lien": "https://fr.linkedin.com/jobs/view/x-42"}]
    assert calls[0][1]["f_TPR"] == "r604800"


def test_several_pages_stop_when_the_results_end(web):
    calls, answers = web
    answers += [Reply("".join(CARD.format(id=i) for i in range(10))), Reply(CARD.format(id=99))]
    assert linkedin.jobs("x", limit=30)["nb"] == 11 and len(calls) == 2


def test_one_offer(web):
    _, answers = web
    answers.append(Reply('<h2 class="top-card-layout__title">Poste</h2><a class="topcard__org-name-link">Acme</a><div class="show-more-less-html__markup"> Le <b>texte</b> </div>'
                         '<li class="description__job-criteria-item"><h3 class="description__job-criteria-subheader">Niveau</h3><span class="description__job-criteria-text">Junior</span></li>'))
    out = linkedin.job("https://x/jobs/view/customer-success-42")
    assert out["titre"] == "Poste" and out["texte"] == "Le texte" and out["criteres"] == {"Niveau": "Junior"} and out["id"] == "42"


@pytest.mark.parametrize("status", [403, 429, 999])
def test_a_refusal_stops_everything_for_an_hour(web, status):
    calls, answers = web
    answers.append(Reply(status=status))
    assert "erreur" in linkedin.tool({"action": "jobs", "keywords": "x"})
    assert "erreur" in linkedin.tool({"action": "jobs", "keywords": "x"})
    assert len(calls) == 1 and db.ttl(linkedin.STOP_KEY) > 3000


def test_hourly_limit(web):
    calls, answers = web
    answers += [Reply(CARD.format(id=1)) for _ in range(linkedin.HOURLY + 5)]
    results = [linkedin.tool({"action": "jobs", "keywords": "x"}) for _ in range(linkedin.HOURLY + 2)]
    assert len(calls) == linkedin.HOURLY and "limite" in results[-1]["erreur"]


@pytest.mark.parametrize("url", ["http://www.linkedin.com/feed", "https://linkedin.com.evil.fr/feed", "https://evil.fr/?linkedin.com", "file:///etc/passwd", "--headless", ""])
def test_only_linkedin_pages_can_be_opened(monkeypatch, url):
    monkeypatch.setattr(linkedin, "_dump_dom", lambda u: pytest.fail("must not open " + u))
    assert "erreur" in linkedin.page(url)


def _session(monkeypatch, tmp_path, cookie="li_at"):
    (tmp_path / "Default").mkdir()
    con = sqlite3.connect(tmp_path / "Default" / "Cookies")
    con.execute("CREATE TABLE cookies(host_key TEXT, name TEXT, value TEXT)")
    con.execute("INSERT INTO cookies VALUES ('.www.linkedin.com', ?, 'secret')", (cookie,))
    con.commit()
    con.close()
    monkeypatch.setattr(screen, "PROFILE", str(tmp_path))


def test_not_logged_in_says_how_to_do_it_without_opening_anything(monkeypatch, tmp_path):
    _session(monkeypatch, tmp_path, cookie="bcookie")
    monkeypatch.setattr(linkedin, "_dump_dom", lambda u: pytest.fail("must not open"))
    assert "/connexion linkedin" in linkedin.page("https://www.linkedin.com/feed/")["erreur"]
    assert linkedin.tool({"action": "status"})["connecte"] is False


def test_status_never_reveals_the_cookie(monkeypatch, tmp_path):
    _session(monkeypatch, tmp_path)
    out = linkedin.tool({"action": "status"})
    assert out["connecte"] is True and "secret" not in str(out)


def test_never_shares_the_browser_with_the_remote_screen(monkeypatch, tmp_path):
    _session(monkeypatch, tmp_path)
    monkeypatch.setattr(screen, "active", lambda: True)
    monkeypatch.setattr(linkedin, "_dump_dom", lambda u: pytest.fail("must not open"))
    assert "ecran distant" in linkedin.page("https://www.linkedin.com/feed/")["erreur"]


def test_logged_in_page_gives_text_and_links(monkeypatch, tmp_path):
    _session(monkeypatch, tmp_path)
    monkeypatch.setattr(screen, "active", lambda: False)
    monkeypatch.setattr(linkedin, "_dump_dom", lambda u: '<html><head><title>Jane | LinkedIn</title><script>x()</script></head><body><main>Jane  Doe</main>'
                        '<a href="/in/jane?trk=1">p</a><a href="/in/jane">p</a><a href="/help">h</a></body></html>')
    out = linkedin.page("https://www.linkedin.com/in/jane/")
    assert out["texte"].startswith("Jane Doe") and out["liens"] == ["/in/jane"] and "x()" not in out["texte"]


@pytest.mark.parametrize("dom,word", [
    ('<title>Jane</title><form><input name="session_key"></form>', "/connexion"),
    ('<title>Sign In</title>', "/connexion"),
    ('<title>Security Verification | LinkedIn</title>', "verification"),
    ('<title>x</title><form action="/checkpoint/challenge"></form>', "verification"),
])
def test_login_wall_and_security_check_stop_the_bot(monkeypatch, tmp_path, dom, word):
    _session(monkeypatch, tmp_path)
    monkeypatch.setattr(screen, "active", lambda: False)
    monkeypatch.setattr(linkedin, "_dump_dom", lambda u: dom)
    assert word in linkedin.tool({"action": "page", "url": "https://www.linkedin.com/feed/"})["erreur"]


def test_results_count_as_external_content(web):
    _, answers = web
    answers.append(Reply(CARD.format(id=1)))
    links = []
    assert dispatch.run_tool(7, "linkedin", {"action": "jobs", "keywords": "x"}, links)["nb"] == 1
    assert links == ["(page web)"]
