"""Infrastructure shared by everything: Redis, logging, the HTTP session, Telegram/WhatsApp sending."""

import logging
import os
import unicodedata

import redis
import requests

from .optional import whatsapp
from .config import GEMINI_KEY, LLM2_API_KEY, LLM3_API_KEY, LLM_API_KEY, STT_API_KEY, TG, TOKEN
from .texts import SILENT

db = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=int(os.environ.get("REDIS_PORT", "6379")),
                 db=int(os.environ.get("REDIS_DB", "0")), decode_responses=True)       # REDIS_DB lets tests use their own database
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for noisy in ("urllib3", "primp", "ddgs", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("bot")


def scrub(e):
    """Retire les secrets d'un message d'erreur avant de le journaliser."""
    s = str(e)
    for secret in (TOKEN, GEMINI_KEY, LLM_API_KEY, LLM2_API_KEY, LLM3_API_KEY, STT_API_KEY, os.environ.get("WA_TOKEN", ""), os.environ.get("WA_APP_SECRET", "")):
        if secret:
            s = s.replace(secret, "***")
    return s


def _session():
    from requests.adapters import HTTPAdapter
    sess = requests.Session()
    sess.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=24))
    return sess


NET = _session()        # connexions gardees ouvertes vers Telegram et Groq : plus de poignee de main a chaque appel


def is_wa(chat_id):
    """WhatsApp conversations use ids like 'wa:33612345678'; Telegram ones are plain numbers."""
    return isinstance(chat_id, str) and chat_id.startswith("wa:")


def wa_to(chat_id):
    return chat_id[3:]


def tg(method, **params):
    if is_wa(params.get("chat_id")):               # Telegram-only call (typing, buttons editing...) : nothing to do on WhatsApp
        return {}
    resp = NET.post(f"{TG}/{method}", json=params, timeout=70)
    return resp.json()


def fetch_file(chat_id, file_id):
    """Download a voice note / photo / document the user sent, from Telegram or WhatsApp. Returns bytes or None."""
    if is_wa(chat_id):
        data, _ = whatsapp.download(file_id)
        return data
    info = tg("getFile", file_id=file_id).get("result") or {}
    if not info.get("file_path"):
        return None
    return requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}", timeout=90).content


def send(chat_id, text):
    if text == SILENT:
        return
    text = text.strip() or "(reponse vide)"
    if is_wa(chat_id):
        whatsapp.send_text(wa_to(chat_id), text)
        return
    for i in range(0, len(text), 4000):
        tg("sendMessage", chat_id=chat_id, text=text[i:i + 4000], disable_web_page_preview=True)


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip(" .!?,;")
