"""The heavy scraping kit (kit_scrape_pro). NOTHING real runs: the engines (Scrapy, Crawl4AI, Scrapling) are replaced by a fake child process that writes canned
JSON lines, no website is contacted, no Chromium starts, nothing is sent to a chat."""
import csv
import json
import os
import signal
import subprocess
import sys
import types

import pytest

from instonct import kit_media, kit_scrape, kit_scrape_pro as pro


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """`engine.reply[script] = (rows, stdout)` is what the fake child writes; `engine.calls` records (script, cfg)."""
    work = tmp_path / "work"
    work.mkdir()
    state = types.SimpleNamespace(reply={}, calls=[], sent=[], work=work, timed_out=False, stderr="")

    def fake_child(script, cfg, seconds):
        state.calls.append((script, cfg, seconds))
        rows, stdout = state.reply.get(script, ([], ""))
        if "out" in cfg:
            with open(cfg["out"], "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
        return stdout, state.stderr, state.timed_out

    monkeypatch.setattr(pro, "_child", fake_child)
    monkeypatch.setattr(pro, "VENV_PYTHON", sys.executable)
    monkeypatch.setattr(pro, "WORK", str(work))
    monkeypatch.setattr(kit_scrape, "WORK", str(work))
    monkeypatch.setattr(kit_media, "WORK", str(work))
    monkeypatch.setattr(pro, "_send", lambda chat, path: state.sent.append(path) or True)
    monkeypatch.setattr(kit_scrape, "_send", lambda chat, path: state.sent.append(path) or True)
    monkeypatch.setattr(pro.web, "url_ok", lambda u: u.startswith("http") and not u.split("://", 1)[-1].startswith(("192.168.", "localhost", "127.")))
    return state


def run(name, **args):
    return pro.FUNCS[name](1, args)


def test_crawl_gros_writes_a_csv_and_limits_the_pages(engine):
    engine.reply["scrapy_run.py"] = ([{"page": "https://shop.test/a", "nom": "Chaise", "prix": "=12"}, {"page": "https://shop.test/b", "nom": "Table", "prix": "30"}], "")
    out = run("crawl_gros", url="shop.test", pages=9999, item="div.p", champs='{"nom": "h2", "prix": ".prix"}', motif="a.b(")
    script, cfg, seconds = engine.calls[0]
    assert script == "scrapy_run.py" and cfg["pages"] == 300 and cfg["url"] == "https://shop.test" and seconds <= 280
    assert cfg["follow"] == "a\\.b\\("                                           # the pattern is plain text, never a regex handed to the engine
    assert out["lignes"] == 2 and out["envoye"] is True
    with open(engine.sent[0], encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["prix"] == "'=12"                                           # no spreadsheet formula
    assert os.listdir(engine.work) == ["scrapes"]                             # the job's temporary folder is gone


@pytest.mark.parametrize("url", ["http://192.168.1.64/", "http://localhost:8080", "ftp://x.test", "file:///etc/passwd", ""])
@pytest.mark.parametrize("name", ["crawl_gros", "aspirer_js", "selecteur_adaptatif"])
def test_private_or_odd_addresses_never_reach_an_engine(engine, name, url):
    out = run(name, url=url, selecteur="h1", nom="x")
    assert "erreur" in out and not engine.calls


def test_item_without_fields_or_the_opposite_is_refused(engine):
    assert "erreur" in run("crawl_gros", url="https://shop.test", item="div")
    assert "erreur" in run("aspirer_js", url="https://shop.test", champs='{"a": "b"}')
    assert "erreur" in run("crawl_gros", url="https://shop.test", item="div", champs="pas du json")
    assert not engine.calls


def test_a_timeout_keeps_the_partial_result_and_says_so(engine):
    engine.reply["scrapy_run.py"] = ([{"url": "https://shop.test/", "statut": 200}], "")
    engine.timed_out = True
    out = run("crawl_gros", url="https://shop.test")
    assert out["lignes"] == 1 and "partiel" in out["note"]


def test_an_engine_that_fails_gives_its_last_error_line(engine):
    engine.stderr = "Traceback...\nValueError: boum"
    out = run("crawl_gros", url="https://shop.test")
    assert out["erreur"] == "ValueError: boum"


def test_only_one_heavy_job_at_a_time(engine):
    assert pro.BUSY.acquire(blocking=False)
    try:
        assert "deja en cours" in run("crawl_gros", url="https://shop.test")["erreur"]
        assert not engine.calls
    finally:
        pro.BUSY.release()
    assert pro.BUSY.acquire(blocking=False)                                  # and the lock is free again after a job
    pro.BUSY.release()


def test_the_lock_is_released_even_when_the_engine_crashes(engine, monkeypatch):
    monkeypatch.setattr(pro, "_child", lambda *a: (_ for _ in ()).throw(OSError("no fork")))
    with pytest.raises(OSError):
        run("crawl_gros", url="https://shop.test")
    assert pro.BUSY.acquire(blocking=False)
    pro.BUSY.release()


def test_aspirer_js_markdown_is_saved_and_sent(engine):
    engine.reply["crawl4ai_run.py"] = ([{"url": "https://app.test/", "ok": True, "titre": "App", "markdown": "# Bonjour\n\ntexte"}, {"url": "https://app.test/x", "ok": False, "erreur": "timeout"}], "")
    out = run("aspirer_js", url="https://app.test", pages=500, defiler=99, attendre=".liste")
    cfg = engine.calls[0][1]
    assert cfg["pages"] == 20 and cfg["scroll"] == 12 and cfg["wait_for"] == ".liste"
    assert out["pages_lues"] == 1 and out["pages_en_echec"] == 1 and out["apercu"].startswith("# Bonjour")
    assert engine.sent[0].endswith(".md") and "# Bonjour" in open(engine.sent[0], encoding="utf-8").read()


def test_aspirer_js_items_become_a_csv_with_the_page_address(engine):
    engine.reply["crawl4ai_run.py"] = ([{"url": "https://app.test/", "ok": True, "items": [{"nom": "A"}, {"nom": "B"}]}], "")
    out = run("aspirer_js", url="https://app.test", item="li", champs='{"nom": "span"}')
    assert out["lignes"] == 2 and out["envoye"]
    with open(engine.sent[0], encoding="utf-8-sig") as f:
        assert [r["page"] for r in csv.DictReader(f)] == ["https://app.test/"] * 2


def test_selecteur_adaptatif_remember_then_find(engine, monkeypatch):
    monkeypatch.setattr(kit_scrape, "_html_page", lambda url, js: (url, b"<html><span class='p'>12 EUR</span></html>"))
    engine.reply["scrapling_run.py"] = ([], json.dumps({"found": ["12 EUR"], "adaptive": False, "saved": True}))
    out = run("selecteur_adaptatif", url="https://shop.test/p", selecteur=".p", nom="prix chaise!", memorise=True)
    script, cfg, _ = engine.calls[0]
    assert cfg["save"] is True and cfg["name"] == "prix_chaise_" and cfg["db"].endswith("adaptive.db") and "<span" in cfg["html"]
    assert out["memorise"] is True and out["trouve"] == ["12 EUR"]
    engine.reply["scrapling_run.py"] = ([], json.dumps({"found": ["13 EUR"], "adaptive": True}))
    out = run("selecteur_adaptatif", url="https://shop.test/p", selecteur=".p", nom="prix chaise!")
    assert out["trouve"] == ["13 EUR"] and out["retrouve_par_la_forme"] is True


def test_selecteur_adaptatif_says_when_nothing_is_found(engine, monkeypatch):
    monkeypatch.setattr(kit_scrape, "_html_page", lambda url, js: (url, b"<html></html>"))
    engine.reply["scrapling_run.py"] = ([], json.dumps({"found": [], "adaptive": True}))
    assert "rien trouve" in run("selecteur_adaptatif", url="https://shop.test/p", selecteur=".p", nom="x")["note"]


def test_the_page_is_downloaded_by_the_bot_not_by_scrapling(engine, monkeypatch):
    """The Scrapling runner only parses: the bot fetches (public addresses only) and the runner file must not contain any fetcher import."""
    src = open(os.path.join(pro.SCRIPTS, "scrapling_run.py"), encoding="utf-8").read()
    imports = [line for line in src.splitlines() if line.startswith(("import ", "from "))]
    assert "from scrapling.parser import Selector" in imports and not any("fetch" in line.lower() or "stealth" in line.lower() for line in imports)
    monkeypatch.setattr(kit_scrape, "_html_page", lambda url, js: (None, b"le site repond 403"))
    assert "403" in run("selecteur_adaptatif", url="https://shop.test/p", selecteur=".p", nom="x")["erreur"]
    assert not engine.calls


def test_missing_virtualenv_is_reported_not_crashed(engine, monkeypatch):
    monkeypatch.setattr(pro, "VENV_PYTHON", "/nonexistent/python")
    assert "pas installe" in run("crawl_gros", url="https://shop.test")["erreur"]


def test_child_gets_no_secret_and_is_killed_as_a_group_on_timeout(monkeypatch):
    seen = {}

    class FakePopen:
        pid = 4242

        def __init__(self, cmd, **kw):
            seen.update(cmd=cmd, **kw)
            self.calls = 0

        def communicate(self, data=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("x", timeout)
            return "partial", "err"

    killed = []
    monkeypatch.setattr(pro.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(pro.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setenv("TELEGRAM_TOKEN", "secret-token")
    stdout, stderr, timed_out = pro._child("scrapy_run.py", {"url": "https://x.test"}, 5)
    assert timed_out and stdout == "partial" and killed == [(4242, signal.SIGKILL)]
    assert "TELEGRAM_TOKEN" not in seen["env"] and seen["start_new_session"] is True and seen["cmd"][:3] == ["nice", "-n", "10"]


def test_the_runners_exist_and_are_not_python_modules_of_the_bot():
    for name in ("scrapy_run.py", "crawl4ai_run.py", "scrapling_run.py"):
        assert os.path.exists(os.path.join(pro.SCRIPTS, name))
    assert not os.path.exists(os.path.join(pro.SCRIPTS, "__init__.py"))
