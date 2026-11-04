#!/usr/bin/env python3
"""Bot Telegram : recherche web + reponse via Gemini, et commandes gratuites pour le Mac mini.

- Long polling : aucun port ouvert sur le serveur.
- Prive : seul le premier utilisateur qui envoie /start devient proprietaire.
- Redis : memoire courte de la conversation, limite de messages, rappels, message d'ecran.
Secrets lus dans l'environnement (EnvironmentFile du service systemd), jamais dans le code.
"""
import array
import base64
import glob
import json
import logging
import os
import random
import re
import subprocess
import threading
import time
import uuid
import wave
from datetime import datetime

import redis
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
# Limites du palier gratuit Gemini (page AI Studio) : 5 requetes/min et 20 requetes/jour par modele.
# On garde une petite marge sous ces plafonds.
MAX_PER_MIN = 4
MAX_PER_DAY = 18
HISTORY_TURNS = 6          # nombre d'echanges gardes en memoire
HISTORY_TTL = 3600         # 1 h

TG = f"https://api.telegram.org/bot{TOKEN}"
GEMINI = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
SYSTEM = (
    "Tu es Jessica-OS, un majordome numerique dans le style de Jarvis : calme, poli, une pointe d'humour "
    "elegant. Tes reponses sont aussi lues a voix haute : phrases courtes, 4 phrases maximum sauf si on te "
    "demande du detail, aucun symbole ni liste. Reponds en francais. "
    "Des resultats de recherche web te sont fournis avec la question : appuie-toi dessus pour les faits "
    "recents ou verifiables, et dis-le honnetement s'ils ne suffisent pas. "
    "Ecris en texte brut, sans markdown (pas d'asterisques ni de dieses)."
)

AIDE = (
    "Ecris-moi une question : je cherche sur le web et je reponds.\n"
    "Ou envoie-moi un MESSAGE VOCAL (micro de Telegram) : je t'ecoute et je te reponds a voix haute.\n\n"
    "Commandes (toutes gratuites) :\n"
    "/status : etat du Mac mini\n"
    "/temp : temperature du processeur\n"
    "/dis <texte> : le Mac mini le dit en anglais, 3 fois\n"
    "/parle <texte> : pareil, avec une voix francaise\n"
    "/voix on|off : le Mac mini lit mes reponses a voix haute (active par defaut)\n"
    "/volume <0-100> : volume du Mac mini (baisse-le si ca grésille)\n"
    "/ecran <texte> : affiche un message sur l'ecran du Mac mini (1 min)\n"
    "/rappel <minutes> <texte> : je te previens (et le Mac mini parle)\n"
    "/meteo <ville> : meteo du moment\n"
    "/blague : une blague\n"
    "/de [faces] : lance un de (6 par defaut)\n"
    "/pile : pile ou face\n"
    "/heure : date et heure du serveur\n"
    "/reset : oublier la conversation"
)

MENU = [
    ("aide", "Liste des commandes"), ("status", "Etat du Mac mini"), ("temp", "Temperature CPU"),
    ("dis", "Le Mac mini parle (anglais)"), ("parle", "Le Mac mini parle (francais)"),
    ("voix", "Voix du Mac mini : on / off"), ("volume", "Volume du Mac mini 0-100"), ("ecran", "Message sur l'ecran du Mac mini"), ("rappel", "Rappel : minutes + texte"),
    ("meteo", "Meteo d'une ville"), ("blague", "Une blague"), ("de", "Lancer un de"),
    ("pile", "Pile ou face"), ("heure", "Date et heure"), ("reset", "Oublier la conversation"),
]

BLAGUES = [
    "Pourquoi les plongeurs plongent-ils toujours en arriere ? Parce que sinon ils tombent dans le bateau.",
    "Que dit un ordinateur qui a froid ? J'ai attrape un virus... et j'ai besoin d'un reboot.",
    "Quel est le comble pour un electricien ? De ne pas etre au courant.",
    "Pourquoi les developpeurs confondent Halloween et Noel ? Parce que Oct 31 = Dec 25.",
    "Un Mac mini de 2010 entre dans un bar. Le barman dit : on ne sert pas les vieux. Il repond : je tourne 24h/24.",
    "Que fait un geek quand il a froid ? Il se rapproche de son processeur.",
    "Pourquoi le livre de maths est-il triste ? Il a trop de problemes.",
    "Comment appelle-t-on un chat tombe dans un pot de peinture le jour de Noel ? Un chat-peint de Noel.",
]

METEO_CODES = {
    0: "ciel degage", 1: "plutot degage", 2: "partiellement nuageux", 3: "couvert", 45: "brouillard",
    48: "brouillard givrant", 51: "bruine legere", 53: "bruine", 55: "forte bruine", 61: "pluie legere",
    63: "pluie", 65: "forte pluie", 71: "neige legere", 73: "neige", 75: "forte neige",
    80: "averses", 81: "averses fortes", 82: "averses violentes", 95: "orage", 96: "orage et grele",
    99: "orage violent",
}

db = redis.Redis(decode_responses=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for noisy in ("urllib3", "primp", "ddgs", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("bot")


def scrub(e):
    """Retire les secrets d'un message d'erreur avant de le journaliser."""
    return str(e).replace(TOKEN, "***").replace(GEMINI_KEY, "***")


def tg(method, **params):
    resp = requests.post(f"{TG}/{method}", json=params, timeout=70)
    return resp.json()


def send(chat_id, text):
    text = text.strip() or "(reponse vide)"
    for i in range(0, len(text), 4000):
        tg("sendMessage", chat_id=chat_id, text=text[i:i + 4000], disable_web_page_preview=True)


# ---------------------------------------------------------------- recherche + Gemini
def web_search(query, n=5):
    """Recherche DuckDuckGo (gratuite, sans cle). Renvoie [] en cas d'echec."""
    try:
        from ddgs import DDGS
        return DDGS(timeout=4).text(query, max_results=n, region="fr-fr") or []
    except Exception as e:
        log.warning("recherche web indisponible : %s", scrub(e))
        return []


def call_gemini(body):
    """Appelle Gemini, avec un nouvel essai si le service est sature (503)."""
    # "thinkingLevel: low" : Gemini reflechit moins longtemps -> reponse nettement plus rapide
    body = {**body, "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
    t0 = time.time()
    for attempt in range(3):
        resp = requests.post(GEMINI, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=60)
        if resp.status_code == 400 and "generationConfig" in body:   # reglage non accepte : on s'en passe
            body = {k: v for k, v in body.items() if k != "generationConfig"}
            continue
        if resp.status_code != 503:
            break
        time.sleep(2 * (attempt + 1))
    log.info("temps Gemini : %.1f s (code %s)", time.time() - t0, resp.status_code)
    return resp


def ask(chat_id, question):
    key = f"hist:{chat_id}"
    history = [json.loads(x) for x in db.lrange(key, 0, -1)]
    t0 = time.time()
    # pas de recherche web pour les messages tres courts (bonjour, ca va...) : gain de plusieurs secondes
    results = web_search(question) if len(question.split()) >= 3 else []
    log.info("temps recherche web : %.1f s", time.time() - t0)
    context = "\n\n".join(f"[{i}] {r.get('title', '')}\n{r.get('body', '')}\n{r.get('href', '')}"
                          for i, r in enumerate(results, 1)) or "(aucun resultat de recherche)"
    prompt = f"Question : {question}\n\nResultats de recherche web :\n{context}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": history + [{"role": "user", "parts": [{"text": prompt}]}],
    }
    resp = call_gemini(body)
    if resp.status_code == 429:
        return "Limite gratuite Gemini atteinte pour le moment, reessaie dans une minute."
    if resp.status_code == 503:
        return "Gemini est sature en ce moment, reessaie dans un instant."
    resp.raise_for_status()
    cand = resp.json()["candidates"][0]
    answer = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])).strip()
    if not answer:
        return "Je n'ai pas pu formuler de reponse."
    # memoire courte : on garde la question seule (pas les pages de resultats)
    db.rpush(key, json.dumps({"role": "user", "parts": [{"text": question}]}),
             json.dumps({"role": "model", "parts": [{"text": answer}]}))
    db.ltrim(key, -2 * HISTORY_TURNS, -1)
    db.expire(key, HISTORY_TTL)
    links = [r["href"] for r in results if r.get("href")][:3]
    if links:
        answer += "\n\nSources :\n" + "\n".join(links)
    return answer


def ask_voice(chat_id, audio, mime):
    """Envoie le message vocal a Gemini (il transcrit ET repond en un seul appel)."""
    key = f"hist:{chat_id}"
    history = [json.loads(x) for x in db.lrange(key, 0, -1)]
    instruction = ("Voici un message vocal de l'utilisateur. Reponds-lui. Format strict : une premiere ligne "
                   "'Q: ' suivie de la transcription exacte de ce qu'il a dit, puis une ligne 'R: ' suivie "
                   "de ta reponse.")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": history + [{"role": "user", "parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
            {"text": instruction}]}],
    }
    resp = call_gemini(body)
    if resp.status_code == 429:
        return "Limite gratuite Gemini atteinte pour le moment, reessaie dans une minute."
    if resp.status_code == 503:
        return "Gemini est sature en ce moment, reessaie dans un instant."
    resp.raise_for_status()
    cand = resp.json()["candidates"][0]
    raw = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])).strip()
    m = re.search(r"Q:\s*(.*?)\s*\n\s*R:\s*(.*)", raw, re.S)
    question, answer = (m.group(1), m.group(2).strip()) if m else ("(message vocal)", raw)
    if not answer:
        return "Je n'ai pas compris le message vocal."
    db.rpush(key, json.dumps({"role": "user", "parts": [{"text": question}]}),
             json.dumps({"role": "model", "parts": [{"text": answer}]}))
    db.ltrim(key, -2 * HISTORY_TURNS, -1)
    db.expire(key, HISTORY_TTL)
    return answer


# ---------------------------------------------------------------- commandes gratuites
def cpu_temp():
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(f"{h}/name").read().strip() == "coretemp":
                return f"{int(open(f'{h}/temp2_input').read()) // 1000} C"
        except OSError:
            pass
    return "?"


def status():
    up = float(open("/proc/uptime").read().split()[0])
    load = open("/proc/loadavg").read().split()[:3]
    mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
    svc = subprocess.run(
        "systemctl list-units 'bot-*' --no-legend --plain | awk '{print \"  \"$1\" \"$3}'",
        shell=True, capture_output=True, text=True).stdout.strip()
    try:
        rd = "ok" if db.ping() else "KO"
    except redis.RedisError:
        rd = "KO"
    return (f"Uptime : {int(up // 3600)} h {int(up % 3600 // 60)} min\n"
            f"Charge : {' '.join(load)}\n"
            f"CPU    : {cpu_temp()}\n"
            f"RAM    : {mem['MemAvailable'] // 1024} Mo dispo / {mem['MemTotal'] // 1024} Mo\n"
            f"Redis  : {rd}\n"
            f"Questions IA aujourd'hui : {db.get(f'rl:day:{datetime.now():%Y-%m-%d}') or 0}/{MAX_PER_DAY}\n"
            f"Services :\n{svc}")


VOICE_FR = os.environ.get("VOICE_FR", "mb-fr1")  # voix francaise masculine MBROLA, plus naturelle
_speak_lock = threading.Lock()                    # une seule voix a la fois


def set_volume(pct):
    """Regle le volume de la carte son (0-100 %). Un volume trop fort peut saturer l'ampli et faire grésiller."""
    for ctl in ("Master", "Speaker", "Headphone", "PCM"):
        subprocess.run(["amixer", "-c", "0", "-q", "sset", ctl, f"{pct}%", "unmute"],
                       capture_output=True, timeout=10)
    db.set("volume", pct)


def tts_wav(text, voice, speed, path):
    """Synthese vocale vers un fichier WAV, normalise au volume maximum SANS saturation.
    (-a 200 d'espeak saturait le signal : c'est ce qui faisait grésiller la voix.)"""
    subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-a", "40", "-w", path, text],
                   check=True, timeout=60)
    with wave.open(path, "rb") as w:
        params = w.getparams()
        samples = array.array("h", w.readframes(w.getnframes()))
    peak = max((abs(s) for s in samples), default=0)
    if peak:
        gain = 30000 / peak          # pic a ~92 % : fort mais propre
        samples = array.array("h", (int(s * gain) for s in samples))
    with wave.open(path, "wb") as w:
        w.setparams(params)
        w.writeframes(samples.tobytes())


def speak(text, times=1, voice="en-us", speed=125, limit=200):
    """Fait parler le Mac mini (espeak-ng -> carte son). Sans effet si rien n'est branche."""
    text = text[:limit]
    path = f"/tmp/tts-{uuid.uuid4().hex}.wav"
    with _speak_lock:
        try:
            tts_wav(text, voice, speed, path)
            for _ in range(times):
                subprocess.run(["aplay", "-q", "-D", "plughw:0,0", path], timeout=90)
                time.sleep(1 if times > 1 else 0)
        finally:
            if os.path.exists(path):
                os.remove(path)


def voice_note(text):
    """Fabrique une note vocale Telegram (OGG/Opus) a partir du texte. Renvoie les octets."""
    wav = f"/tmp/vn-{uuid.uuid4().hex}.wav"
    ogg = wav.replace(".wav", ".ogg")
    try:
        tts_wav(text, VOICE_FR, 150, wav)
        subprocess.run(["opusenc", "--quiet", wav, ogg], check=True, timeout=60)
        with open(ogg, "rb") as f:
            return f.read()
    finally:
        for p in (wav, ogg):
            if os.path.exists(p):
                os.remove(p)


def send_voice(chat_id, text):
    """Envoie la reponse en note vocale Telegram (s'entend sur le telephone)."""
    text = clean_for_speech(text)
    if not text:
        return
    try:
        audio = voice_note(text)
        requests.post(f"{TG}/sendVoice", data={"chat_id": chat_id},
                      files={"voice": ("reponse.ogg", audio, "audio/ogg")}, timeout=60)
    except Exception as e:
        log.warning("note vocale impossible : %s", scrub(e))


def clean_for_speech(text):
    """Enleve liens et symboles, garde les premieres phrases (max ~400 caracteres)."""
    text = text.split("\n\nSources :")[0]
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>\[\]{}|~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 400:
        cut = text[:400]
        text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut
    return text


def say_async(text):
    """Lit le texte a voix haute (en arriere-plan) si le mode voix est actif."""
    if db.get("voice_off"):
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
    send(chat_id, text)
    say_async(text)


def screen_message(text):
    """Affiche un message sur le tableau de bord de l'ecran (lu par ecran-status via Redis)."""
    text = "".join(c for c in text if c.isprintable())[:120]
    db.setex("ecran_msg", 60, text)


def meteo(city):
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1, "language": "fr"}, timeout=15).json()
    if not g.get("results"):
        return f"Ville introuvable : {city}"
    p = g["results"][0]
    w = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code"}, timeout=15).json()["current"]
    return (f"Meteo a {p['name']} ({p.get('country', '')}) :\n"
            f"{METEO_CODES.get(w['weather_code'], 'conditions variables')}, {w['temperature_2m']} C "
            f"(ressenti {w['apparent_temperature']} C), vent {w['wind_speed_10m']} km/h")


def add_reminder(chat_id, arg):
    parts = arg.split(None, 1)
    if len(parts) < 2 or not parts[0].isdigit():
        return "Utilisation : /rappel 10 sortir le linge   (10 = minutes)"
    minutes = int(parts[0])
    if not 1 <= minutes <= 1440:
        return "Choisis entre 1 et 1440 minutes (24 h)."
    item = json.dumps({"chat": chat_id, "text": parts[1][:200], "id": uuid.uuid4().hex})
    db.zadd("reminders", {item: time.time() + minutes * 60})
    return f"C'est note, je te previens dans {minutes} min."


def reminder_loop():
    """Thread : envoie les rappels arrives a echeance (stockes dans Redis, survivent a un redemarrage)."""
    while True:
        try:
            for raw in db.zrangebyscore("reminders", 0, time.time()):
                if db.zrem("reminders", raw):
                    r = json.loads(raw)
                    send(r["chat"], "Rappel : " + r["text"])
                    screen_message("RAPPEL : " + r["text"])
                    try:
                        speak(r["text"], times=2, voice=VOICE_FR, speed=150)
                    except Exception as e:
                        log.warning("voix indisponible : %s", scrub(e))
        except Exception as e:
            log.error("erreur rappels : %s", scrub(e))
        time.sleep(5)


# ---------------------------------------------------------------- messages
def handle(msg):
    chat = msg["chat"]
    chat_id = chat["id"]
    text = (msg.get("text") or "").strip()
    voice = msg.get("voice") or msg.get("audio")
    if chat.get("type") != "private" or not (text or voice):
        return
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()

    owner = db.get("owner_id")
    if owner is None:
        if cmd == "/start":
            db.set("owner_id", chat_id)
            send(chat_id, "Salut ! Je suis maintenant lie a toi seul.\n\n" + AIDE)
        else:
            send(chat_id, "Envoie /start pour commencer.")
        return
    if str(chat_id) != owner:
        log.info("message ignore (chat non autorise)")
        return

    if voice and not text:
        handle_voice(chat_id, voice)
    elif cmd in ("/start", "/aide", "/help"):
        send(chat_id, AIDE)
    elif cmd == "/status":
        send(chat_id, status())
    elif cmd == "/temp":
        reply(chat_id, f"Le processeur est a {cpu_temp().replace(' C', ' degres')}.")
    elif cmd == "/reset":
        db.delete(f"hist:{chat_id}")
        send(chat_id, "Conversation effacee.")
    elif cmd == "/dis":
        if not arg:
            send(chat_id, "Utilisation : /dis I love Jessica")
        else:
            send(chat_id, "Le Mac mini parle...")
            speak(arg, times=3)
    elif cmd == "/parle":
        if not arg:
            send(chat_id, "Utilisation : /parle Bonjour Jessica")
        else:
            send(chat_id, "Le Mac mini parle...")
            speak(arg, times=3, voice=VOICE_FR, speed=150)
    elif cmd == "/ecran":
        if not arg:
            send(chat_id, "Utilisation : /ecran Coucou Jessica")
        else:
            screen_message(arg)
            send(chat_id, "Affiche sur l'ecran du Mac mini pendant 1 minute.")
    elif cmd == "/rappel":
        send(chat_id, add_reminder(chat_id, arg))
    elif cmd == "/volume":
        if arg.isdigit() and 0 <= int(arg) <= 100:
            set_volume(int(arg))
            send(chat_id, f"Volume regle a {arg} %. Essaie /parle Bonjour monsieur pour entendre.")
        else:
            send(chat_id, f"Volume actuel : {db.get('volume') or 100} %. Utilisation : /volume 70")
    elif cmd == "/voix":
        if arg.lower() == "off":
            db.set("voice_off", 1)
            send(chat_id, "Voix coupee. (/voix on pour la remettre)")
        elif arg.lower() == "on":
            db.delete("voice_off")
            reply(chat_id, "Voix activee. A votre service.")
        else:
            send(chat_id, f"Voix : {'coupee' if db.get('voice_off') else 'activee'}. Utilisation : /voix on ou /voix off")
    elif cmd == "/meteo":
        reply(chat_id, meteo(arg) if arg else "Utilisation : /meteo Paris")
    elif cmd == "/blague":
        reply(chat_id, random.choice(BLAGUES))
    elif cmd == "/de":
        faces = int(arg) if arg.isdigit() and 2 <= int(arg) <= 1000 else 6
        reply(chat_id, f"Un de a {faces} faces : {random.randint(1, faces)}")
    elif cmd == "/pile":
        reply(chat_id, random.choice(["Pile", "Face"]))
    elif cmd == "/heure":
        now = datetime.now()
        reply(chat_id, f"Il est {now:%H} heures {now:%M}, le {now:%d/%m/%Y}.")
    elif cmd.startswith("/"):
        send(chat_id, "Commande inconnue. Tape /aide pour la liste.")
    else:
        if quota_exceeded(chat_id):
            return
        tg("sendChatAction", chat_id=chat_id, action="typing")
        reply(chat_id, ask(chat_id, text))


def quota_exceeded(chat_id):
    """Applique les limites du palier gratuit Gemini. Previent l'utilisateur et renvoie True si depassees."""
    slot = f"rl:{chat_id}:{int(time.time() // 60)}"
    if db.incr(slot) == 1:
        db.expire(slot, 90)
    if int(db.get(slot)) > MAX_PER_MIN:
        send(chat_id, "Doucement : 4 questions par minute maximum (limite gratuite de Gemini).")
        return True
    day = f"rl:day:{datetime.now():%Y-%m-%d}"
    if db.incr(day) == 1:
        db.expire(day, 90000)
    if int(db.get(day)) > MAX_PER_DAY:
        send(chat_id, f"Tu as utilise tes {MAX_PER_DAY} questions IA gratuites d'aujourd'hui. "
                      "Les commandes (/meteo, /blague, /dis...) restent illimitees. Reviens demain !")
        return True
    return False


def handle_voice(chat_id, voice):
    """Message vocal Telegram : Gemini ecoute, comprend et repond ; la reponse revient en texte + note vocale."""
    if voice.get("duration", 0) > 60:
        send(chat_id, "Message vocal trop long : 60 secondes maximum.")
        return
    if quota_exceeded(chat_id):
        return
    tg("sendChatAction", chat_id=chat_id, action="record_voice")
    info = tg("getFile", file_id=voice["file_id"]).get("result") or {}
    if not info.get("file_path"):
        send(chat_id, "Je n'ai pas pu recuperer ton message vocal.")
        return
    audio = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}", timeout=60).content
    answer = ask_voice(chat_id, audio, voice.get("mime_type") or "audio/ogg")
    send(chat_id, answer)
    send_voice(chat_id, answer)   # reponse parlee dans Telegram (s'entend sur le telephone)
    say_async(answer)             # et sur le Mac mini si la voix est active


def main():
    log.info("bot demarre (modele %s)", MODEL)
    try:
        tg("setMyCommands", commands=[{"command": c, "description": d} for c, d in MENU])
    except Exception as e:
        log.warning("menu des commandes non mis a jour : %s", scrub(e))
    if db.get("volume"):
        set_volume(int(db.get("volume")))
    threading.Thread(target=reminder_loop, daemon=True).start()
    offset = None
    while True:
        try:
            params = {"timeout": 50, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset
            for upd in tg("getUpdates", **params).get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        handle(upd["message"])
                except Exception as e:  # une erreur sur un message ne doit pas tuer le bot
                    log.error("erreur message : %s", scrub(e))
                    try:
                        send(upd["message"]["chat"]["id"], "Oups, une erreur est survenue.")
                    except Exception:
                        pass
        except Exception as e:
            log.error("erreur reseau : %s", scrub(e))
            time.sleep(5)


if __name__ == "__main__":
    main()
