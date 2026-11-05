"""A spoken order takes the same instant path as a written one: Whisper's text, then the action, with no model in between. The TV is always fake here."""
import pytest

from instonct import brain, cast, handlers, music, sound, television


@pytest.fixture
def tv(monkeypatch):
    done = []
    monkeypatch.setattr(television, "tv_power", lambda want: done.append(("power", want)) or f"tele {want}")
    monkeypatch.setattr(television, "tv_channel", lambda n: done.append(("channel", int(n))) or f"chaine {n}")
    monkeypatch.setattr(television, "tv_do", lambda key, times=1: done.append(("key", key)) or ("J'ouvre l'appli." if key.startswith("app:") else "OK"))
    monkeypatch.setattr(music, "music_play", lambda q: done.append(("play", q)) or f"musique {q}")
    monkeypatch.setattr(music, "music_control", lambda a: done.append(("music", a)) or a)
    return done


@pytest.fixture
def spoken(monkeypatch, tv):
    """Runs a voice note whose transcription is the given text. Returns what was written and spoken back."""
    out = {"written": [], "spoken": [], "model": []}
    monkeypatch.setattr(handlers, "tg", lambda *a, **k: {})
    monkeypatch.setattr(handlers, "fetch_file", lambda chat, file_id: b"audio")
    monkeypatch.setattr(handlers, "send", lambda chat, text: out["written"].append(text))
    monkeypatch.setattr(handlers, "STT_API_KEY", "x")
    monkeypatch.setattr(handlers, "quota_exceeded", lambda chat: False)
    monkeypatch.setattr(sound, "send_voice", lambda chat, text: out["spoken"].append(text) or True)
    monkeypatch.setattr(brain, "remember", lambda *a, **k: None)

    def ask(chat, question, oral=False, taint=False):
        out["model"].append((question, oral))
        return "reponse du modele"
    monkeypatch.setattr(brain, "ask", ask)

    def run(text):
        monkeypatch.setattr(sound, "transcribe", lambda audio: text)
        handlers.handle_voice(7, {"file_id": "f", "duration": 3})
        return out
    return run


@pytest.mark.parametrize("heard", [
    "Allume la télé.", "Allume la télé s'il te plaît.", "Voilà, allume la télé.", "Steve, allume la télé.", "Tu peux allumer la télé ?",
    "Allume-moi la télé frérot.", "Est-ce que tu peux allumer la TV ?", "Vas-y, allume la télé là.", "Bah du coup allume la télé, merci.", "Rallume la télévision", "Il faut allumer la télé",
])
def test_every_way_of_saying_turn_on_the_tv(spoken, tv, heard):
    out = spoken(heard)
    assert tv == [("power", "on")] and out["written"] == ["tele on"]
    assert not out["model"] and not out["spoken"]


@pytest.mark.parametrize("heard", ["Éteins la télé.", "Éteint la télé", "Eteindre la télé.", "Coupe la télé !", "Steve, éteins-moi la télé s'il te plaît.", "Ferme la télé"])
def test_every_way_of_saying_turn_off_the_tv(spoken, tv, heard):
    spoken(heard)
    assert tv == [("power", "off")]


@pytest.mark.parametrize("heard,expected", [
    ("Mets Netflix sur la télé.", [("key", "app:netflix")]),
    ("Lance YouTube", [("key", "app:youtube")]),
    ("Ouvre Prime Video", [("key", "app:prime")]),
    ("Mets la chaîne 5.", [("channel", 5)]),
    ("Mets la chaîne cinq.", [("channel", 5)]),
    ("Mais la chaîne 5.", [("channel", 5)]),
    ("Mais Netflix sur la télé.", [("key", "app:netflix")]),
    ("mes Netflix.", [("key", "app:netflix")]),
    ("Chaîne d'après", [("key", "ch_up")]),
    ("Monte le son de la télé", [("key", "volume_up")]),
    ("Baisse le son de la télé.", [("key", "volume_down")]),
    ("Passe sur HDMI 2.", [("key", "hdmi2")]),
    ("Mets la source HDMI deux", [("key", "hdmi2")]),
    ("Chaîne suivante", [("key", "ch_up")]),
    ("Mets Netflix en pause", [("key", "play_pause")]),
    ("Allume la télé et mets Netflix.", [("power", "on"), ("key", "app:netflix")]),
    ("Mets Bon Jovi", [("play", "bon jovi")]),
])
def test_other_simple_orders(spoken, tv, heard, expected):
    out = spoken(heard)
    assert tv == expected and not out["model"]
    assert "OK" not in out["written"]


@pytest.mark.parametrize("heard", [
    "N'allume pas la télé.", "Allume la télé demain à 8 h.", "Pourquoi la télé ne s'allume pas ?", "Éteins la télé après le film.", "Mets un rappel pour demain à 8 h.",
    "Passe-moi le mail de Julien.", "Lance une recherche sur Mistral.", "Il faut que je commande des piles.", "Continue.", "Mets HDMI 9",
])
def test_what_is_not_a_plain_order_goes_to_the_model(spoken, tv, heard):
    out = spoken(heard)
    assert tv == [] and out["model"] == [(heard, True)]


@pytest.mark.parametrize("heard,step", [("Monte le son.", 15), ("Montes le son", 15), ("Baisse le son un peu", -8), ("Baisses le son", -15)])
def test_the_sound_of_the_server_changes_by_voice(monkeypatch, spoken, heard, step):
    steps = []
    monkeypatch.setattr(sound, "change_volume", lambda delta: steps.append(delta) or "Volume change.")
    assert not spoken(heard)["model"] and steps == [step]


def test_an_answer_from_the_model_is_spoken_back(spoken):
    out = spoken("Quel temps fait-il ?")
    assert out["spoken"] == ["reponse du modele"] and out["written"] == []


def test_a_written_order_works_the_same(monkeypatch, tv):
    written = []
    monkeypatch.setattr(handlers, "send", lambda chat, text: written.append(text))
    monkeypatch.setattr(brain, "remember", lambda *a, **k: None)
    assert handlers.instant_order(7, "allume-moi la télé stp") and tv == [("power", "on")]


def test_asking_for_the_remote_by_voice_sends_the_buttons(monkeypatch, spoken):
    sent = []
    monkeypatch.setattr(television, "send_remote", lambda chat: sent.append(chat))
    assert not spoken("Passe-moi la télécommande.")["model"] and sent == [7]


def test_if_transcription_fails_the_audio_goes_to_the_model(monkeypatch, spoken):
    seen = []
    monkeypatch.setattr(brain, "ask_voice", lambda chat, audio, mime, heard: seen.append(heard) or ("ceci", "ok"))
    spoken(None)
    assert seen == [None]


def test_a_busy_transcription_service_is_retried_once(monkeypatch):
    class Reply:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return {"text": "Allume la télé."}
    replies = [Reply(429), Reply(200)]
    monkeypatch.setattr(sound.requests, "post", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(sound, "STT_RETRY_AFTER", 0)
    assert sound.transcribe(b"audio") == "Allume la télé."


def test_noise_counts_as_nothing_heard(monkeypatch):
    class Reply:
        status_code = 200

        def json(self):
            return {"text": " ..."}
    monkeypatch.setattr(sound.requests, "post", lambda *a, **k: Reply())
    assert sound.transcribe(b"audio") is None


def test_the_tv_voice_server_does_not_fight_siri_for_the_port(monkeypatch):
    bound = []

    class Server:
        def __init__(self, address, handler):
            bound.append(address)

        def serve_forever(self):
            pass
    monkeypatch.setattr(cast, "ThreadingHTTPServer", Server)
    monkeypatch.setattr(cast, "my_ip", lambda: "192.168.1.64")
    monkeypatch.setitem(cast._cast_srv, "on", False)
    cast.cast_serve()
    assert bound == [("192.168.1.64", cast.CAST_PORT)]
