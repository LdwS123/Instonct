"""Slow things must not hold the answer back, and the model's English thinking must never reach the user."""
import json
import threading
import time

import pytest

from instonct import handlers, llm, music, sound, core
from instonct.core import db


@pytest.mark.parametrize("raw,expected", [
    ("Quel jeu veux-tu ouvrir?User wants to play video games. Précise le jeu.", "Quel jeu veux-tu ouvrir? Précise le jeu."),
    ("Musique lancée. What else?Anything else you need?", "Musique lancée."),
    ('Je ne peux pas tout effacer. {"text":"tout"}{"erreur":"refuse : x"}Dis-moi quel souvenir.', "Je ne peux pas tout effacer. Dis-moi quel souvenir."),
    ("Hello, how are you? I am fine.", "Hello, how are you? I am fine."),            # an English answer stays whole
    ("Il fait beau. OK. Merci.", "Il fait beau. OK. Merci."),
])
def test_english_thinking_is_removed_from_french_answers(raw, expected):
    assert llm.clean_answer(raw) == expected


class Reply:
    status_code = 200
    def __init__(self, headers=None, code=200):
        self.headers, self.status_code = headers or {}, code
    def json(self):
        return {"usage": {"total_tokens": 100}}


def test_model_menu_shows_usage_speed_and_what_is_left():
    model = llm.ALL_MODELS[0]
    r = Reply({"x-ratelimit-remaining-requests": "14350", "x-ratelimit-limit-requests": "14400", "x-ratelimit-remaining-tokens": "7900", "x-ratelimit-limit-tokens": "8000"})
    llm._seen(model, r)
    llm._meter(model, r, 0.5)
    llm._seen(model, Reply(code=429))
    text = llm.model_command(1, "")
    assert "1 calls, 100 tokens, 0.5 s on average" in text and '1x "too many requests"' in text
    assert "requests 14,350/14,400" in text and "tokens 7,900/8,000" in text


def test_edge_is_skipped_for_five_minutes_after_a_failure(monkeypatch):
    import sys, types
    calls = []

    class Boom:
        def __init__(self, *a, **k):
            calls.append(1)
        async def save(self, path):
            raise OSError("no network")
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Boom))
    for _ in range(2):
        with pytest.raises(Exception):
            sound.edge_wav("bonjour", "/tmp/x.wav")
    assert len(calls) == 1 and db.ttl("edge:down") > 0


def test_same_song_is_searched_only_once(monkeypatch):
    runs = []

    class Out:
        stdout = "Titre\t3:00\thttp://audio/direct\n"
    monkeypatch.setattr(music.subprocess, "run", lambda *a, **k: runs.append(1) or Out())
    assert music.music_find("bon jovi") == music.music_find("Bon  Jovi")
    assert len(runs) == 1


def test_a_slow_voice_note_does_not_hold_the_text(monkeypatch):
    sent, done = [], threading.Event()
    monkeypatch.setattr(handlers, "tg", lambda *a, **k: {})
    monkeypatch.setattr(handlers, "fetch_file", lambda chat, fid: b"audio")
    monkeypatch.setattr(handlers, "send", lambda chat, text: sent.append(text))
    monkeypatch.setattr(handlers, "STT_API_KEY", "x")
    monkeypatch.setattr(handlers, "quota_exceeded", lambda chat: False)
    monkeypatch.setattr(sound, "transcribe", lambda audio: "raconte moi une histoire")
    monkeypatch.setattr(handlers, "instant_order", lambda chat, heard: None)
    monkeypatch.setattr(handlers.brain, "ask", lambda *a, **k: "Il etait une fois")
    monkeypatch.setattr(handlers.brain, "remember", lambda *a, **k: None)
    monkeypatch.setattr(sound, "send_voice", lambda chat, text: (done.wait(30), True)[1])
    real_join = threading.Thread.join
    monkeypatch.setattr(threading.Thread, "join", lambda self, timeout=None: real_join(self, min(timeout or 0.3, 0.3)))
    t0 = time.time()
    handlers.handle_voice(7, {"file_id": "f", "duration": 3})
    done.set()
    assert sent == ["Il etait une fois"] and time.time() - t0 < 5
