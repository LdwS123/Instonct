#!/usr/bin/env python3
"""Bot Telegram : recherche web + reponse via Gemini, et commandes gratuites pour le Mac mini.

- Long polling : aucun port ouvert sur le serveur.
- Prive : seul le premier utilisateur qui envoie /start devient proprietaire.
- Redis : memoire courte de la conversation, limite de messages, rappels, message d'ecran.
Secrets lus dans l'environnement (EnvironmentFile du service systemd), jamais dans le code.
"""
import glob
import json
import logging
import os
import random
import subprocess
import threading
import time
import uuid
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
    "Tu es un assistant personnel sur Telegram. Reponds en francais, de facon claire et concise. "
    "Des resultats de recherche web te sont fournis avec la question : appuie-toi dessus pour les faits "
    "recents ou verifiables, et dis-le honnetement s'ils ne suffisent pas. "
    "Ecris en texte brut, sans markdown (pas d'asterisques ni de dieses)."
)

AIDE = (
    "Ecris-moi une question : je cherche sur le web et je reponds.\n\n"
    "Commandes (toutes gratuites) :\n"
    "/status : etat du Mac mini\n"
    "/temp : temperature du processeur\n"
    "/dis <texte> : le Mac mini le dit en anglais, 3 fois\n"
    "/parle <texte> : pareil, avec une voix francaise\n"
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
    ("ecran", "Message sur l'ecran du Mac mini"), ("rappel", "Rappel : minutes + texte"),
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
logging.getLogger("urllib3").setLevel(logging.WARNING)
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
        return DDGS().text(query, max_results=n, region="fr-fr") or []
    except Exception as e:
        log.warning("recherche web indisponible : %s", scrub(e))
        return []


def call_gemini(body):
    """Appelle Gemini, avec un nouvel essai si le service est sature (503)."""
    for attempt in range(3):
        resp = requests.post(GEMINI, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=60)
        if resp.status_code != 503:
            return resp
        time.sleep(2 * (attempt + 1))
    return resp


def ask(chat_id, question):
    key = f"hist:{chat_id}"
    history = [json.loads(x) for x in db.lrange(key, 0, -1)]
    results = web_search(question)
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


def speak(text, times=1, voice="en-us", speed=125):
    """Fait parler le Mac mini (espeak-ng -> carte son). Sans effet si rien n'est branche."""
    text = text[:200]
    for _ in range(times):
        tts = subprocess.Popen(["espeak-ng", "-v", voice, "-s", str(speed), "-a", "200", "--stdout", text],
                               stdout=subprocess.PIPE)
        subprocess.run(["aplay", "-q", "-D", "plughw:0,0"], stdin=tts.stdout, timeout=40)
        tts.wait()
        time.sleep(1)


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
                        speak(r["text"], times=2, voice="fr")
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
    if chat.get("type") != "private" or not text:
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

    if cmd in ("/start", "/aide", "/help"):
        send(chat_id, AIDE)
    elif cmd == "/status":
        send(chat_id, status())
    elif cmd == "/temp":
        send(chat_id, f"CPU : {cpu_temp()}")
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
            speak(arg, times=3, voice="fr", speed=135)
    elif cmd == "/ecran":
        if not arg:
            send(chat_id, "Utilisation : /ecran Coucou Jessica")
        else:
            screen_message(arg)
            send(chat_id, "Affiche sur l'ecran du Mac mini pendant 1 minute.")
    elif cmd == "/rappel":
        send(chat_id, add_reminder(chat_id, arg))
    elif cmd == "/meteo":
        send(chat_id, meteo(arg) if arg else "Utilisation : /meteo Paris")
    elif cmd == "/blague":
        send(chat_id, random.choice(BLAGUES))
    elif cmd == "/de":
        faces = int(arg) if arg.isdigit() and 2 <= int(arg) <= 1000 else 6
        send(chat_id, f"Un de a {faces} faces : {random.randint(1, faces)}")
    elif cmd == "/pile":
        send(chat_id, random.choice(["Pile", "Face"]))
    elif cmd == "/heure":
        send(chat_id, datetime.now().strftime("%d/%m/%Y %H:%M:%S") + " (heure du serveur)")
    elif cmd.startswith("/"):
        send(chat_id, "Commande inconnue. Tape /aide pour la liste.")
    else:
        slot = f"rl:{chat_id}:{int(time.time() // 60)}"
        if db.incr(slot) == 1:
            db.expire(slot, 90)
        if int(db.get(slot)) > MAX_PER_MIN:
            send(chat_id, "Doucement : 4 questions par minute maximum (limite gratuite de Gemini).")
            return
        day = f"rl:day:{datetime.now():%Y-%m-%d}"
        if db.incr(day) == 1:
            db.expire(day, 90000)
        if int(db.get(day)) > MAX_PER_DAY:
            send(chat_id, f"Tu as utilise tes {MAX_PER_DAY} questions IA gratuites d'aujourd'hui. "
                          "Les commandes (/meteo, /blague, /dis...) restent illimitees. Reviens demain !")
            return
        tg("sendChatAction", chat_id=chat_id, action="typing")
        send(chat_id, ask(chat_id, text))


def main():
    log.info("bot demarre (modele %s)", MODEL)
    try:
        tg("setMyCommands", commands=[{"command": c, "description": d} for c, d in MENU])
    except Exception as e:
        log.warning("menu des commandes non mis a jour : %s", scrub(e))
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
