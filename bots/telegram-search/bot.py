#!/usr/bin/env python3
"""Bot Telegram : recherche web + reponse via Gemini.

- Long polling : aucun port ouvert sur le serveur.
- Prive : seul le premier utilisateur qui envoie /start devient proprietaire.
- Redis : memoire courte de la conversation + limite de messages par minute.
Secrets lus dans l'environnement (EnvironmentFile du service systemd), jamais dans le code.
"""
import glob
import json
import logging
import os
import subprocess
import time

import redis
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
MAX_PER_MIN = 10
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


def status():
    up = float(open("/proc/uptime").read().split()[0])
    load = open("/proc/loadavg").read().split()[:3]
    mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
    temp = "?"
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(f"{h}/name").read().strip() == "coretemp":
                temp = f"{int(open(f'{h}/temp2_input').read()) // 1000} C"
        except OSError:
            pass
    svc = subprocess.run(
        "systemctl list-units 'bot-*' --no-legend --plain | awk '{print \"  \"$1\" \"$3}'",
        shell=True, capture_output=True, text=True).stdout.strip()
    try:
        rd = "ok" if db.ping() else "KO"
    except redis.RedisError:
        rd = "KO"
    return (f"Uptime : {int(up // 3600)} h {int(up % 3600 // 60)} min\n"
            f"Charge : {' '.join(load)}\n"
            f"CPU    : {temp}\n"
            f"RAM    : {mem['MemAvailable'] // 1024} Mo dispo / {mem['MemTotal'] // 1024} Mo\n"
            f"Redis  : {rd}\n"
            f"Services :\n{svc}")


def speak(text, times=1):
    text = text[:200]
    for _ in range(times):
        tts = subprocess.Popen(["espeak-ng", "-v", "en-us", "-s", "125", "-a", "200", "--stdout", text],
                               stdout=subprocess.PIPE)
        subprocess.run(["aplay", "-q", "-D", "plughw:0,0"], stdin=tts.stdout, timeout=40)
        tts.wait()
        time.sleep(1)


def handle(msg):
    chat = msg["chat"]
    chat_id = chat["id"]
    text = (msg.get("text") or "").strip()
    if chat.get("type") != "private" or not text:
        return
    owner = db.get("owner_id")
    if owner is None:
        if text.startswith("/start"):
            db.set("owner_id", chat_id)
            send(chat_id, "Salut ! Je suis maintenant lie a toi seul.\n\n"
                          "Ecris-moi une question et je cherche sur le web.\n"
                          "/status : etat du Mac mini\n"
                          "/dis <texte> : le Mac mini le dit a voix haute (x3)\n"
                          "/reset : oublier la conversation")
        else:
            send(chat_id, "Envoie /start pour commencer.")
        return
    if str(chat_id) != owner:
        log.info("message ignore (chat non autorise)")
        return
    if text.startswith("/status"):
        send(chat_id, status())
    elif text.startswith("/reset"):
        db.delete(f"hist:{chat_id}")
        send(chat_id, "Conversation effacee.")
    elif text.startswith("/dis"):
        phrase = text[4:].strip()
        if not phrase:
            send(chat_id, "Utilisation : /dis I love Jessica")
        else:
            send(chat_id, "Le Mac mini parle...")
            speak(phrase, times=3)
    elif text.startswith("/"):
        send(chat_id, "Commande inconnue. Essaie /status, /dis ou /reset.")
    else:
        slot = f"rl:{chat_id}:{int(time.time() // 60)}"
        if db.incr(slot) == 1:
            db.expire(slot, 90)
        if int(db.get(slot)) > MAX_PER_MIN:
            send(chat_id, "Doucement : trop de messages cette minute.")
            return
        tg("sendChatAction", chat_id=chat_id, action="typing")
        send(chat_id, ask(chat_id, text))


def main():
    log.info("bot demarre (modele %s)", MODEL)
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
