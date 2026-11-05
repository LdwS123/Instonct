"""/sante says what works without leaking a key, and the installer's questions keep what is already there."""
import importlib.util
import os
import stat

import pytest
import requests

from instonct import google, health
from instonct.core import db

FOUND = [p for p in (os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "setup_wizard.py"), os.path.join(os.path.dirname(__file__), "..", "scripts", "setup_wizard.py")) if os.path.exists(p)]


@pytest.fixture
def wizard():
    spec = importlib.util.spec_from_file_location("setup_wizard", FOUND[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Resp:
    def __init__(self, code):
        self.status_code = code


def test_a_refused_key_is_named_without_showing_it(monkeypatch):
    monkeypatch.setattr(health, "MODEL_API", {"m": ("https://api.example/v1", "sk-very-secret")})
    monkeypatch.setattr(health.requests, "get", lambda *a, **k: Resp(401))
    state, detail = health._providers()
    assert state == health.BAD and "cle refusee" in detail and "api.example" in detail and "sk-very" not in detail


def test_one_working_provider_is_enough_and_resting_models_are_listed(monkeypatch):
    monkeypatch.setattr(health, "MODEL_API", {"a": ("https://good.example/v1", "k1"), "b": ("https://bad.example/v1", "k2")})
    monkeypatch.setattr(health.requests, "get", lambda url, **k: Resp(200 if "good" in url else 500))
    db.set("cool:a", 1)
    state, detail = health._providers()
    assert state == health.OK and "en pause : a" in detail and "code 500" in detail


def test_an_unreachable_provider_does_not_print_the_address_with_its_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("https://x.example/bot123:SECRET/ failed")
    monkeypatch.setattr(health.requests, "get", boom)
    state, detail = health._key_works("https://api.example/v1", "k")
    assert state == health.BAD and "SECRET" not in detail


def test_a_crashing_check_is_a_failed_check(monkeypatch):
    def boom():
        raise RuntimeError("casse")
    monkeypatch.setattr(health, "CHECKS", (("Redis", boom), ("Autre", lambda: (health.OK, "bien"))))
    rows = health.run()
    assert rows[0][1] == health.BAD and rows[1][1] == health.OK
    assert "1 chose(s) en panne" in health.report(rows)


def test_the_exit_code_only_fails_for_what_is_required(monkeypatch, capsys):
    monkeypatch.setattr(health, "CHECKS", (("Redis", lambda: (health.OK, "")), ("Agenda", lambda: (health.BAD, "expire"))))
    assert health.main() == 0
    monkeypatch.setattr(health, "CHECKS", (("Redis", lambda: (health.BAD, "non")),))
    assert health.main() == 1
    capsys.readouterr()


def test_the_real_report_runs_and_shows_no_key(monkeypatch):
    monkeypatch.setattr(health, "tg", lambda m: {"result": {"username": "testbot"}})
    monkeypatch.setattr(health.requests, "get", lambda *a, **k: Resp(200))
    out = health.report()
    assert "test-key" not in out and "@testbot" in out


def test_two_identical_events_are_not_created():
    class Cal:
        def parse_dt(self, s):
            from datetime import datetime
            return datetime.strptime(s, "%Y-%m-%d %H:%M")

        def list_events(self, days, day):
            return [{"debut": "2030-01-02 16:30", "titre": "Entretien Acme"}, {"debut": "2030-01-02 18:00", "titre": "Diner"}]
    assert google._same_event(Cal(), "Entretien Acme (visio)", "2030-01-02 16:30")["titre"] == "Entretien Acme"
    assert google._same_event(Cal(), "Entretien Acme", "2030-01-02 17:00") is None
    assert google._same_event(Cal(), "Autre chose", "2030-01-02 16:30") is None


def test_env_file_is_private_and_keeps_what_exists(tmp_path, wizard):
    path = tmp_path / "bots" / ".env"
    path.parent.mkdir()
    path.write_text("# mes notes\nTELEGRAM_TOKEN=ancien\n")
    wizard.add_to_env(str(path), {"TELEGRAM_TOKEN": "nouveau", "LLM_API_KEY": 'a b"c\\d'})
    text = path.read_text()
    assert "# mes notes" in text and "TELEGRAM_TOKEN=ancien" in text and "nouveau" not in text
    assert 'LLM_API_KEY="a b\\"c\\\\d"' in text
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == [".env"]


def test_a_value_with_a_new_line_cannot_inject_a_setting(tmp_path, wizard):
    with pytest.raises(ValueError):
        wizard.add_to_env(str(tmp_path / ".env"), {"LLM_API_KEY": "x\nTELEGRAM_TOKEN=evil"})


def test_the_questions_never_print_a_key(tmp_path, wizard, monkeypatch, capsys):
    secrets = iter(["123:tokensecret", "sk-keysecret", ""])
    monkeypatch.setattr(wizard.getpass, "getpass", lambda prompt="": next(secrets))
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    monkeypatch.setattr(wizard, "telegram_ok", lambda t: "monbot")
    monkeypatch.setattr(wizard, "model_key_ok", lambda b, k: True)
    path = tmp_path / ".env"
    wizard.wizard(str(path))
    out = capsys.readouterr().out
    assert "tokensecret" not in out and "keysecret" not in out and "@monbot" in out
    assert wizard.read_env(str(path)) == {"TELEGRAM_TOKEN", "LLM_API_KEY"}


def test_a_second_run_asks_nothing_already_set(tmp_path, wizard, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("TELEGRAM_TOKEN=a\nLLM_API_KEY=b\nGEMINI_API_KEY=c\nMAIL_USER=d\n")
    def no(*a, **k):
        raise AssertionError("ne devrait rien demander")
    monkeypatch.setattr(wizard.getpass, "getpass", no)
    monkeypatch.setattr("builtins.input", no)
    wizard.wizard(str(path))


def test_a_refused_token_stops_after_a_few_tries(tmp_path, wizard, monkeypatch, capsys):
    monkeypatch.setattr(wizard.getpass, "getpass", lambda prompt="": "mauvais")
    monkeypatch.setattr(wizard, "telegram_ok", lambda t: None)
    with pytest.raises(SystemExit):
        wizard.wizard(str(tmp_path / ".env"))
    assert not (tmp_path / ".env").exists() and "mauvais" not in capsys.readouterr().out
