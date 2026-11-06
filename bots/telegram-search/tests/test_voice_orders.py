"""Spoken orders must become real actions. The TV, the speakers and the music are all fakes here: nothing can make a sound."""
import pytest

from instonct import cast, llm, music, sound, television


@pytest.fixture
def done(monkeypatch):
    """What the order really did, in order. The TV and the player are fakes."""
    seen = []
    monkeypatch.setattr(television, "tv_do", lambda action, times=1: (seen.append("do:" + action), "OK")[1])
    monkeypatch.setattr(television, "tv_channel", lambda n: (seen.append(f"channel:{n}"), "ok")[1])
    monkeypatch.setattr(television, "tv_power", lambda want: (seen.append("power:" + want), "ok")[1])
    monkeypatch.setattr(music, "music_play", lambda q, track=True: (seen.append("MUSIC:" + q), "ok")[1])
    monkeypatch.setattr(music, "stop_all", lambda tv=False: (seen.append(f"stop_all:{tv}"), "ok")[1])
    monkeypatch.setattr(music, "music_control", lambda a: (seen.append("control:" + a), "ok")[1])
    monkeypatch.setattr(sound, "quick_volume", lambda t: None)
    monkeypatch.setattr(cast, "catt", lambda *a, **k: "")
    monkeypatch.setattr(cast, "catt_info", lambda: {})
    return seen


OFF = ["Arrête la télé.", "Éteins la télé.", "Eteins la télé s'il te plaît", "Coupe la télé", "Stoppe la télé", "Ferme la télé", "Éteins la télévision", "Éteins le téléviseur",
       "Éteins la TV", "Jessica, éteins la télé", "Tu peux éteindre la télé ?", "Est-ce que tu peux arrêter la télé ?", "Éteins-moi la télé", "Arrêtes la télé", "Éteignez la télé",
       "Je veux que tu éteignes la télé", "Il faut que tu éteignes la télé", "Tu peux m'éteindre la télé", "Mets la télé en veille", "Mets en veille la télé",
       "Mets la télé off", "Télé off", "Arrête-la, la télé", "Éteins la télé du salon", "Éteins le poste"]
ON = ["Allume la télé.", "Allume la télévision", "Allume le téléviseur", "Allumes la télé", "Allumez la télé", "Réveille la télé", "Je veux que tu allumes la télé",
      "Tu peux allumer la télé ?", "Mets la télé", "Télé on", "Allume le poste"]


@pytest.mark.parametrize("phrase", OFF)
def test_every_way_to_say_turn_the_tv_off_turns_it_off(done, phrase):
    assert music.quick_music(phrase)
    assert done == ["power:off"]


@pytest.mark.parametrize("phrase", ON)
def test_every_way_to_say_turn_the_tv_on_turns_it_on(done, phrase):
    assert music.quick_music(phrase)
    assert done == ["power:on"]


@pytest.mark.parametrize("phrase, expected", [("Mets TF1", "channel:1"), ("Mets la une", "channel:1"), ("Mets France 2", "channel:2"), ("Mets M6", "channel:6"),
                                              ("Passe sur la 6", "channel:6"), ("Arrête YouTube", "do:home"), ("Ferme Netflix", "do:home"), ("Quitte YouTube", "do:home"),
                                              ("Mets pause", "control:pause")])
def test_channels_apps_and_pause_are_real_actions_not_a_song_search(done, phrase, expected):
    assert music.quick_music(phrase)
    assert done == [expected]


@pytest.mark.parametrize("phrase, query", [("Mets Bohemian Rhapsody", "bohemian rhapsody"), ("Joue du Daft Punk", "daft punk"), ("Mets du jazz", "jazz")])
def test_real_songs_are_still_played(done, phrase, query):
    assert music.quick_music(phrase)
    assert done == ["MUSIC:" + query]


def test_stop_the_music_on_the_tv_is_not_a_power_off(done):
    assert music.quick_music("Arrête la musique sur la télé")
    assert done == ["stop_all:True"]


@pytest.mark.parametrize("claim, tools", [
    ("J'éteins la télé.", set()), ("La télé est éteinte.", set()), ("C'est bon, j'ai allumé la télé.", {"web_search"}),
    ("Musique arrêtée.", set()), ("J'ai mis la musique en pause.", {"web_search"}), ("Le volume est monté.", set()), ("J'ai baissé le son.", {"mail_search"})])
def test_announcing_a_tv_music_or_volume_action_needs_its_tool(claim, tools):
    assert llm.false_claim(claim, tools)


@pytest.mark.parametrize("claim, tools", [
    ("J'éteins la télé.", {"tv_remote"}), ("Musique arrêtée.", {"music_control"}), ("Le volume est monté.", {"change_volume"}),
    ("Je peux éteindre la télé si tu veux.", set()), ("La télé de Julie est grande.", set())])
def test_the_same_words_are_fine_when_the_tool_ran_or_nothing_is_claimed(claim, tools):
    assert not llm.false_claim(claim, tools)


def test_the_tests_themselves_cannot_make_a_sound():
    import subprocess
    assert subprocess.run(["aplay", "-q", "/nonexistent.wav"]).returncode == 0          # swallowed by the silence fixture
    assert subprocess.run(["amixer", "-c", "0", "-q", "sset", "Master", "100%", "unmute"]).returncode == 0
