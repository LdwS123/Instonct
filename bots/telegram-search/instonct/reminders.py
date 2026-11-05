"""Reminders and scheduled tasks."""

import json
import threading
import time
import uuid

from .core import db, log, scrub, send
from . import brain, commands, life, sound

def add_reminder(chat_id, arg):
    parts = arg.split(None, 1)
    if len(parts) < 2 or not parts[0].isdigit():
        return "Utilisation : /rappel 10 sortir le linge   (10 = minutes)"
    minutes = int(parts[0])
    if not 1 <= minutes <= 86400:
        return "Choisis entre 1 minute et 60 jours."
    item = json.dumps({"chat": chat_id, "text": parts[1][:200], "id": uuid.uuid4().hex})
    db.zadd("reminders", {item: time.time() + minutes * 60})
    return f"C'est note, je te previens dans {minutes} min."


def run_task(t):
    """Execute une tache programmee : l'agent la realise puis envoie le resultat."""
    try:
        if t.get("action"):
            return life.run_habit(t)
        sound.reply(t["chat"], brain.ask(t["chat"], "[Tache programmee, execute-la maintenant] " + t["prompt"]))
    except Exception as e:
        log.error("tache en erreur : %s", scrub(e))


def reminder_loop():
    """Thread : envoie les rappels arrives a echeance (stockes dans Redis, survivent a un redemarrage)."""
    while True:
        try:
            for raw in db.zrangebyscore("reminders", 0, time.time()):
                if db.zrem("reminders", raw):
                    r = json.loads(raw)
                    send(r["chat"], "Rappel : " + r["text"])
                    commands.screen_message("RAPPEL : " + r["text"])
                    try:
                        sound.speak(r["text"], times=2, voice=sound.VOICE_FR, speed=150)
                    except Exception as e:
                        log.warning("voix indisponible : %s", scrub(e))
            life.check_briefing()
            for raw in db.zrangebyscore("tasks", 0, time.time()):
                if db.zrem("tasks", raw):
                    t = json.loads(raw)
                    if t["repeat"]:
                        db.zadd("tasks", {raw: time.time() + t["repeat"] * 60})
                    threading.Thread(target=run_task, args=(t,), daemon=True).start()
        except Exception as e:
            log.error("erreur rappels : %s", scrub(e))
        time.sleep(5)
