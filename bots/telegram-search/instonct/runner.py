"""Entry point: WhatsApp dispatch, safe message handling and the Telegram polling loop."""

import os
import threading
import time

from .optional import whatsapp
from .config import ALL_MODELS, GEMINI_KEY
from .texts import MENU
from .core import db, log, scrub, send, tg
from . import callbacks, handlers, monitor, reminders, remote_access, sound

def wa_dispatch(m):
    """One WhatsApp message (already checked: signature, allowed number, not a duplicate) -> same code path as Telegram."""
    chat_id = "wa:" + m["from"]
    try:
        if m["button"].startswith("ok:"):                                  # tap on the Yes / No buttons
            _, yn, pid = (m["button"].split(":") + ["", ""])[:3]
            callbacks.confirm_yes(chat_id, pid) if yn == "yes" else callbacks.confirm_no(chat_id)
            return
        msg = {"chat": {"id": chat_id, "type": "private"}, "caption": m["caption"]}
        if m["type"] == "text":
            msg["text"] = m["text"]
        elif m["type"] == "audio":
            msg["voice"] = {"file_id": m["media"], "mime_type": m["mime"] or "audio/ogg", "duration": 0}
        elif m["type"] == "image":
            msg["photo"] = [{"file_id": m["media"], "file_size": 0}]
        elif m["type"] == "document":
            msg["document"] = {"file_id": m["media"], "file_name": m["name"], "mime_type": m["mime"], "file_size": 0}
        else:
            send(chat_id, "I can't read this kind of message yet. Text, voice notes, photos and files work.")
            return
        handlers.handle(msg)
    except Exception as e:
        log.error("whatsapp message error: %s", scrub(e))
        try:
            send(chat_id, "Oups, une erreur est survenue.")
        except Exception:
            pass


def safe_handle(msg):
    try:
        handlers.handle(msg)
    except Exception as e:  # une erreur sur un message ne doit pas tuer le bot
        log.error("erreur message : %s", scrub(e))
        try:
            send(msg["chat"]["id"], "Oups, une erreur est survenue.")
        except Exception:
            pass


def main():
    if not ALL_MODELS and not GEMINI_KEY:
        raise SystemExit("No AI provider configured: set LLM_API_KEY (or GROQ_API_KEY) and/or GEMINI_API_KEY in the .env file.")
    log.info("bot started (models: %s | backup: %s)", ", ".join(ALL_MODELS) or "none",
             "gemini" if GEMINI_KEY else "none")
    if whatsapp is not None and whatsapp.configured():
        whatsapp.serve(wa_dispatch, lambda i: not db.set(f"wa_seen:{i}", 1, nx=True, ex=86400))
        log.info("WhatsApp channel on")
    elif os.environ.get("WA_TOKEN"):
        log.warning("WhatsApp: WA_TOKEN is set but WA_PHONE_ID, WA_VERIFY_TOKEN, WA_APP_SECRET or WA_OWNER is missing: channel off")
    try:
        tg("setMyCommands", commands=[{"command": c, "description": d} for c, d in MENU])
    except Exception as e:
        log.warning("menu des commandes non mis a jour : %s", scrub(e))
    if db.get("volume"):
        sound.set_volume(int(db.get("volume")), mac_only=True)       # le volume memorise est celui du Mac mini, pas de la tele
    threading.Thread(target=reminders.reminder_loop, daemon=True).start()
    remote_access.start_siri_server()
    threading.Thread(target=monitor.watch_loop, daemon=True).start()
    offset = None
    while True:
        try:
            params = {"timeout": 50, "allowed_updates": ["message", "callback_query"]}
            if offset:
                params["offset"] = offset
            for upd in tg("getUpdates", **params).get("result", []):
                offset = upd["update_id"] + 1
                if "callback_query" in upd:
                    threading.Thread(target=callbacks.handle_callback, args=(upd["callback_query"],), daemon=True).start()
                if "message" in upd:
                    # un thread par message : une commande lente (voix, recherche) ne bloque plus les suivantes
                    threading.Thread(target=safe_handle, args=(upd["message"],), daemon=True).start()
        except Exception as e:
            log.error("erreur reseau : %s", scrub(e))
            time.sleep(5)


if __name__ == "__main__":
    main()
