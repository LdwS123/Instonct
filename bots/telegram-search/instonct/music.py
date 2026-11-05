"""Music on the Mac mini or the TV (mpv + yt-dlp), sound output choice and the quick music commands."""

import json
import os
import re
import socket
import subprocess
import sys
import threading

from .core import db, log, norm, scrub
from . import cast, life, sound, television

# ---------------------------------------------------------------- musique (YouTube sur le Mac mini)
YTDLP = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
MUSIC_SOCK = "/tmp/mpv-bot.sock"
_music = {"proc": None, "title": "", "url": "", "paused": False}
_music_lock = threading.Lock()


def _mpv_cmd(*cmd):
    """Envoie une commande au lecteur mpv (pause, position...). Renvoie sa reponse ou None."""
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(2)
    try:
        s.connect(MUSIC_SOCK)
        s.sendall(json.dumps({"command": list(cmd)}).encode() + b"\n")
        for line in s.recv(8192).decode().splitlines():
            j = json.loads(line)
            if "error" in j:
                return j.get("data")
    except (OSError, ValueError):
        pass
    finally:
        s.close()
    return None


def music_playing():
    if _music.get("tv"):
        i = cast.catt_info()
        return i.get("content_id") == _music["url"] and i.get("player_state") in ("PLAYING", "PAUSED", "BUFFERING")
    p = _music["proc"]
    return bool(p and p.poll() is None)


def music_pos():
    if _music.get("tv"):
        return float(cast.catt_info().get("current_time") or 0)
    return _mpv_cmd("get_property", "time-pos") or 0


def _music_launch(url, title, start=0, paused=False):
    if cast.use_tv():
        cast.catt("cast", *(["-t", str(int(start))] if start else []), url)
        if paused:
            cast.catt("pause")
        _music.update(proc=None, tv=True, title=title, url=url, paused=paused)
        return
    cmd = ["mpv", "--no-video", "--no-terminal", "--ytdl=no", "--audio-device=alsa/plughw:0,0",
           "--audio-samplerate=48000", f"--input-ipc-server={MUSIC_SOCK}", f"--start={int(start)}"]
    if paused:
        cmd.append("--pause")
    _music.update(proc=subprocess.Popen(cmd + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                  tv=False, title=title, url=url, paused=paused)


def _music_kill():
    if _music.get("tv"):
        cast.catt("stop")
        _music["tv"] = False
        return
    p = _music["proc"]
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
    _music["proc"] = None


def music_suspend():
    """Avant de parler, on met la musique de cote en notant ou elle en est (la carte son ne sert qu'a un
    programme a la fois, et une voix envoyee a la tele remplace la musique). Renvoie l'etat a restaurer."""
    with _music_lock:
        if not music_playing():
            return None
        state = dict(url=_music["url"], title=_music["title"], start=music_pos(), paused=_music["paused"])
        if not _music.get("tv"):
            _music_kill()
        return state


def music_restore(state):
    with _music_lock:
        _music_launch(state["url"], state["title"], state["start"], state["paused"])


def set_output(mode):
    """Choisit ou sort le son : 'auto' (tele si allumee, sinon Mac mini), 'tv' ou 'mac'. La musique suit."""
    mode = mode if mode in ("tv", "mac") else "auto"
    if mode == "tv" and not cast.tv_up():
        return "La tele ne repond pas. Allume-la d'abord."
    state = music_suspend()
    if state and _music.get("tv"):
        with _music_lock:
            _music_kill()
    db.set("sortie", mode)
    cast._tv_cache["t"] = 0.0                                # on refait la verification tout de suite
    if state:
        music_restore(state)
    if mode == "auto":
        return "C'est fait : le son sort sur la tele quand elle est allumee, sinon sur le Mac mini."
    return "C'est fait, le son sort maintenant sur " + ("la tele." if mode == "tv" else "le Mac mini.")


def music_find(query):
    """Cherche sur YouTube (sans rien telecharger). Renvoie (titre, duree, url audio directe) ou None."""
    target = query if query.startswith("http") else f"ytsearch1:{query}"
    out = subprocess.run([YTDLP, "--no-playlist", "--no-warnings", "-f", "bestaudio/best", "--print",
                          "%(title)s\t%(duration_string)s\t%(url)s", target],
                         capture_output=True, text=True, timeout=60).stdout.strip().splitlines()
    for line in reversed(out):
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].startswith("http"):
            return parts
    return None


def music_play(query, track=True):
    found = music_find(query)
    if not found:
        return "Je n'ai rien trouve sur YouTube pour : " + query
    title, dur, url = found
    if track:
        life.note("music", query)
    def go():                                 # le lancement sur la tele prend ~10 s : on repond tout de suite et on le fait en fond
        try:
            with sound._speak_lock, _music_lock:    # attend la fin d'une phrase parlee avant de prendre la carte son
                _music_kill()
                _music_launch(url, title)
        except Exception as e:
            log.warning("lancement musique : %s", scrub(e))
    threading.Thread(target=go, daemon=True).start()
    return f"Je lance : {title} ({dur})"


def music_control(action):
    with _music_lock:
        if not music_playing():
            return "Aucune musique en cours."
        if action == "stop":
            _music_kill()
            return "Musique arretee."
        if _music.get("tv"):
            cast.catt("pause" if action == "pause" else "play")
        else:
            _mpv_cmd("set_property", "pause", action == "pause")
        _music["paused"] = action == "pause"
        return "Musique en pause." if action == "pause" else "Musique reprise."


RE_STOP = re.compile(r"(?:jessica )?(?:stop|stoppe|arrete|coupe|eteins|silence)(?: la| le| ca)?(?: musique| son| chanson| video)?")
RE_PAUSE = re.compile(r"(?:jessica )?(?:pause|mets? (?:la )?(?:musique )?en pause)")
RE_RESUME = re.compile(r"(?:jessica )?(?:reprends?|continue|play|relance)(?: la)?(?: musique)?")
RE_PLAY = re.compile(r"(?:jessica )?(?:peux tu |tu peux )?(?:mets|met|joue|lance|passe)(?: moi)?(?: (?:une|un|la|le|du|de la|des)\b)?"
                     r"(?: (?:musique|morceau|chanson|titre|video)\b)?(?: (?:de|du|des|sur youtube)\b| d')? ?(.+)")


_OUT = r"(?:jessica )?(?:re)?(?:mets|met|passe|envoie|bascule|joue)(?: moi)?(?: le| la| du| les)?(?: son| musique| audio| voix)?(?: sur| a| dans)(?: la| le| les| l)? ?"
RE_OUT_TV = re.compile(_OUT + r"(?:tele|television|tv|chromecast)")
RE_OUT_MAC = re.compile(_OUT + r"(?:mac|mac mini|ordinateur|ordi|haut parleurs?|enceintes?)")
RE_OUT_AUTO = re.compile(_OUT.replace("(?: sur| a| dans)", "(?: en| sur)") + r"(?:auto|automatique)|sortie (?:en )?auto(?:matique)?")


_FILLER = (r"(?:jessica|steve|voila|euh|heu|bah|ben|bon|alors|du coup|en fait|ok|okay|hey|he|eh|oh|dis moi|dis|ecoute|frerot|frero|mon frere|mec|wesh|allez|vas y|va y|"
           r"stp|svp|s il te plait|s il vous plait|please|merci|bref|maintenant|tout de suite|rapidement|vite)")
_FILLER_START = re.compile(rf"^{_FILLER}\b\s*")
_FILLER_END = re.compile(rf"\s*\b(?:{_FILLER}|la)$")
_ASKING = re.compile(r"^(?:est ce que )?(?:tu peux|tu pourrais|tu veux bien|peux tu|pourrais tu|veux tu|je veux que tu|je voudrais que tu|j aimerais que tu|"
                     r"il faut que tu|il faudrait que tu|faudrait que tu|tu vas|il faut)\b(?: me)?\s*")
NOT_MUSIC = re.compile(r"\b(?:rappel|agenda|calendrier|mails?|emails?|messages?|taches?|todo|liste|recherche|notes?|alarme|reunion|rendez vous|rdv|fichier|lien|"
                       r"hdmi|photo|image|code|commande|script|ecran|serveur|question|reponse|document|numero|adresse)\b")


def order_words(text):
    """What a person really orders, without punctuation, politeness and hesitations. Only the two ends are trimmed: "mets bon jovi" must keep its "bon"."""
    t = " ".join(re.sub(r"[^\w\s]", " ", norm(text)).split())
    while True:
        cut = _FILLER_END.sub("", _ASKING.sub("", _FILLER_START.sub("", t))).strip()
        if cut == t:
            return t
        t = cut


def quick_music(text):
    """Raccourci instantane (sans IA) pour les ordres simples, ecrits ou dits : tele, son, musique. Renvoie la reponse ou None."""
    t = order_words(text)
    if len(t.split()) > 12:
        return None
    tv = [television.tv_order(t)]                        # the whole sentence first: "chaine d apres" holds a joining word
    if not tv[0]:
        tv = [television.tv_order(order_words(part)) for part in re.split(r"\b(?:et|puis|ensuite|apres)\b", t)]
    if all(tv):                                          # "allume la tele et mets netflix" : in that order
        return " ".join(order() for order in tv)
    if RE_OUT_TV.fullmatch(t):
        return set_output("tv")
    if RE_OUT_MAC.fullmatch(t):
        return set_output("mac")
    if RE_OUT_AUTO.fullmatch(t):
        return set_output("auto")
    vol = sound.quick_volume(t)
    if vol:
        return vol
    if RE_STOP.fullmatch(t):
        return music_control("stop")
    if RE_PAUSE.fullmatch(t):
        return music_control("pause")
    if RE_RESUME.fullmatch(t) and (t != "continue" or _music.get("paused")):      # "continue" alone is usually said to the bot, not to the music
        return music_control("resume")
    m = RE_PLAY.fullmatch(t) if not NOT_MUSIC.search(t) else None
    q = m.group(1).strip() if m else ""
    if len(q) >= 3 and q not in ("de", "pile ou face"):
        return music_play("hits musique populaire" if q in ("musique", "de la musique", "une musique") else q)
    return None
