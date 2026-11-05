"""Voice: speech-to-text, text-to-speech (Edge TTS), volume, voice notes."""

import os
import re
import subprocess
import threading
import time
import uuid

import requests

from .optional import whatsapp
from .config import STT_API_KEY, STT_BASE_URL, STT_LANGUAGE, STT_MODEL, TG
from .texts import SILENT
from .core import db, is_wa, log, scrub, send, wa_to
from . import cast, music

STT_RETRY_AFTER = 3


def transcribe(audio):
    """Message vocal -> texte avec Whisper sur Groq (environ 1 s). None si impossible."""
    for attempt in range(2):
        try:
            r = requests.post(f"{STT_BASE_URL}/audio/transcriptions", timeout=15,
                              headers={"Authorization": f"Bearer {STT_API_KEY}"},
                              data={"model": STT_MODEL, **({"language": STT_LANGUAGE} if STT_LANGUAGE else {})},
                              files={"file": ("voice.ogg", audio, "audio/ogg")})
            if r.status_code == 200:
                text = r.json().get("text", "").strip()
                return text if re.search(r"\w", text) else None   # on noise, Whisper answers "..."
            log.warning("speech-to-text code %s", r.status_code)
            if r.status_code != 429 or attempt:
                return None
            time.sleep(STT_RETRY_AFTER)                     # the free tier allows a few per minute: a short wait beats the much slower way round
        except requests.RequestException as e:
            log.warning("whisper injoignable : %s", scrub(e))
            return None
    return None


EDGE_VOICE = os.environ.get("EDGE_VOICE", "fr-FR-HenriNeural")
VOICE_FR = os.environ.get("VOICE_FR", "mb-fr1")  # voix francaise masculine MBROLA, plus naturelle
_speak_lock = threading.Lock()                    # une seule voix a la fois


def set_volume(pct, mac_only=False):
    """Regle le volume (0-100 %) de la tele ou de la carte son du Mac mini. Trop fort, ca peut grésiller."""
    if not mac_only and cast.use_tv():
        cast.cast_dev().set_volume(pct / 100)
        return
    for ctl in ("Master", "Speaker", "Headphone", "PCM"):
        subprocess.run(["amixer", "-c", "0", "-q", "sset", ctl, f"{pct}%", "unmute"],
                       capture_output=True, timeout=10)
    db.set("volume", pct)


def get_volume():
    """Volume reel de la tele ou de la carte son (lu dans ALSA)."""
    if cast.use_tv():
        return int(round((cast.cast_dev().status.volume_level or 0) * 100))
    out = subprocess.run(["amixer", "-c", "0", "sget", "Master"], capture_output=True, text=True, timeout=10).stdout
    m = re.search(r"\[(\d+)%\]", out)
    return int(m.group(1)) if m else int(db.get("volume") or 100)


def change_volume(delta):
    """Monte ou baisse le volume de `delta` points. Renvoie une phrase."""
    old = get_volume()
    new = max(0, min(100, old + delta))
    if new == old:
        return f"Le volume est deja au {'maximum' if delta > 0 else 'minimum'} ({old} %)."
    set_volume(new)
    return f"Volume : {old} % -> {new} %." + (" C'est le maximum." if new == 100 else "")


def quick_volume(t):
    """Ordres de volume simples (texte normalise) : 'monte le son', 'plus fort', 'volume 50', 'au max'..."""
    w = t.split()
    if len(w) > 7 or not re.search(r"\b(son|volume|fort|bas|musique)\b", t) and not re.search(r"\b(montes?|baisses?|augmente|diminue)\b", t):
        return None
    if re.search(r"\b(montes?|baisses?|augmente|diminue|fort|bas)\b|doucement", t) or re.search(r"\b(volume|son)\b", t):
        m = re.search(r"\b(\d{1,3})\b", t)
        if m and re.search(r"\b(volume|son)\b", t) and not re.search(r"\b(montes?|baisses?|augmente|diminue)\b", t):
            set_volume(min(100, int(m.group(1))))
            return f"Volume regle a {min(100, int(m.group(1)))} %."
        if re.search(r"a fond|au max|maximum", t):
            return change_volume(100)
        step = 30 if "beaucoup" in t else 8 if re.search(r"un peu|legerement", t) else 15
        if re.search(r"\b(baisses?|diminue|moins fort|plus bas|doucement)\b|moins fort|plus bas", t):
            return change_volume(-step)
        if re.search(r"\b(montes?|augmente|plus fort|plus haut)\b|plus fort|plus haut", t):
            return change_volume(step)
    return None


def tts_wav(text, voice, speed, path, rate=48000):
    """Synthese vocale vers un fichier WAV propre et fort.
    - espeak est lance doucement (-a 40) : a -a 200 il saturait (grésillement) ;
    - sox convertit en haute qualite vers 48 kHz (la carte son lit nativement a 48 kHz ; le
      convertisseur rapide d'ALSA 16->48 kHz ajoute des parasites aigus) puis amplifie sans depasser."""
    raw = path + ".raw.wav"
    try:
        subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-a", "40", "-w", raw, text],
                       check=True, timeout=60)
        cmd = ["sox", raw, path]
        if rate:
            cmd += ["rate", "-h", str(rate)]
        subprocess.run(cmd + ["gain", "-n", "-1"], check=True, timeout=60)
    finally:
        if os.path.exists(raw):
            os.remove(raw)


def speak(text, times=1, voice="en-us", speed=125, limit=200):
    """Fait parler le Mac mini (espeak-ng -> carte son) ou la tele (Chromecast), selon la sortie choisie."""
    text = text[:limit]
    with _speak_lock:
        tv = cast.use_tv()
        if tv:
            cast.cast_serve()
        path = f"{cast.CAST_DIR if tv else '/tmp'}/tts-{uuid.uuid4().hex}.wav"
        resume = music.music_suspend()                       # la carte son ne sert qu'a un programme a la fois
        try:
            tts_wav(text, voice, speed, path)
            for _ in range(times):
                if tv:
                    cast.cast_say(f"http://{cast.my_ip()}:{cast.CAST_PORT}/{os.path.basename(path)}")
                else:
                    subprocess.run(["aplay", "-q", "-D", "plughw:0,0", path], timeout=90)
                time.sleep(1 if times > 1 else 0)
        finally:
            if os.path.exists(path):
                os.remove(path)
            if resume:
                music.music_restore(resume)


def test_voices():
    """Joue la meme phrase de 4 façons numerotees, pour trouver laquelle ne grésille pas."""
    phrase = "Bonjour monsieur, tous les systemes sont operationnels."
    variants = [("Un", "fr", 48000), ("Deux", "mb-fr1", None), ("Trois", "mb-fr1", 48000), ("Quatre", "mb-fr4", 48000)]
    with _speak_lock:
        resume = music.music_suspend()
        for num, voice, rate in variants:
            path = f"/tmp/tv-{uuid.uuid4().hex}.wav"
            try:
                tts_wav(f"{num}. {phrase}", voice, 150, path, rate=rate)
                subprocess.run(["aplay", "-q", "-D", "plughw:0,0", path], timeout=60)
            finally:
                if os.path.exists(path):
                    os.remove(path)
            time.sleep(1)
        if resume:
            music.music_restore(resume)


def edge_wav(text, path):
    """Voix neuronale francaise (Edge TTS, gratuite, bien plus naturelle qu'espeak). Leve une erreur si injoignable."""
    import asyncio
    import edge_tts
    mp3 = path + ".mp3"
    try:
        asyncio.run(asyncio.wait_for(edge_tts.Communicate(text, EDGE_VOICE, rate="+8%").save(mp3), timeout=15))
        subprocess.run(["sox", mp3, "-r", "48000", "-c", "1", path], check=True, timeout=30, stderr=subprocess.DEVNULL)
    finally:
        if os.path.exists(mp3):
            os.remove(mp3)


def voice_note(text):
    """Fabrique une note vocale Telegram (OGG/Opus) a partir du texte. Renvoie les octets."""
    wav = f"/tmp/vn-{uuid.uuid4().hex}.wav"
    ogg = wav.replace(".wav", ".ogg")
    try:
        try:
            edge_wav(text, wav)
        except Exception as e:                        # pas d'internet / service coupe : on retombe sur la voix locale
            log.warning("voix Edge indisponible (%s), voix locale", scrub(e))
            tts_wav(text, VOICE_FR, 150, wav)
        subprocess.run(["opusenc", "--quiet", wav, ogg], check=True, timeout=60)
        with open(ogg, "rb") as f:
            return f.read()
    finally:
        for p in (wav, ogg):
            if os.path.exists(p):
                os.remove(p)


def send_voice(chat_id, text):
    """Envoie la reponse en note vocale Telegram (s'entend sur le telephone). True si elle est bien partie."""
    text = clean_for_speech(text, 900)
    if not text:
        return False
    try:
        audio = voice_note(text)
        if is_wa(chat_id):
            return whatsapp.send_audio(wa_to(chat_id), audio)
        r = requests.post(f"{TG}/sendVoice", data={"chat_id": chat_id},
                          files={"voice": ("reponse.ogg", audio, "audio/ogg")}, timeout=60)
        return r.status_code == 200
    except Exception as e:
        log.warning("note vocale impossible : %s", scrub(e))
        return False


def clean_for_speech(text, limit=400):
    """Enleve liens et symboles, garde les premieres phrases (max ~400 caracteres)."""
    text = text.split("\n\nSources :")[0]
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>\[\]{}|~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut
    return text


def say_async(text):
    """Lit le texte a voix haute (en arriere-plan) si le mode voix est actif."""
    if not db.get("voice_on"):                 # par defaut le Mac mini reste muet : la discussion se passe sur Telegram
        return
    text = clean_for_speech(text)
    if text:
        def run():
            try:
                speak(text, voice=VOICE_FR, speed=150, limit=400)
            except Exception as e:
                log.warning("voix indisponible : %s", scrub(e))
        threading.Thread(target=run, daemon=True).start()


def reply(chat_id, text):
    """Repond sur Telegram ET a voix haute sur le Mac mini."""
    if text == SILENT:
        return
    send(chat_id, text)
    say_async(text)
