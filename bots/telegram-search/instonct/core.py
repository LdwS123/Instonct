"""Infrastructure shared by everything: Redis, logging, the HTTP session, Telegram/WhatsApp sending."""

import logging
import os
import socket
import time
import unicodedata

import redis
import requests
import urllib3.util.connection

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


# The Mac mini's IPv6 route to Telegram randomly hangs (1 connection in ~15 never opens, measured 2026-11-06); IPv4 never failed.
# urllib3 tries IPv6 first and would wait the whole timeout, so every request of the bot uses IPv4 only.
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET


def _keepalive_options():
    """TCP keep-alive: a connection that the router silently dropped is noticed in about 30 s instead of hanging for a minute."""
    opts = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1), (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]
    for name, value in (("TCP_KEEPIDLE", 15), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 3)):
        if hasattr(socket, name):
            opts.append((socket.IPPROTO_TCP, getattr(socket, name), value))
    return opts


def _session():
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    class KeepAliveAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["socket_options"] = _keepalive_options()
            super().init_poolmanager(*args, **kwargs)
    # une connexion gardee ouverte peut avoir ete fermee par le serveur entre deux messages ("Remote end closed connection") : on reessaie sans bruit
    retry = Retry(total=2, connect=2, read=2, status=0, backoff_factor=0.4, allowed_methods=None, raise_on_status=False)
    sess = requests.Session()
    sess.mount("https://", KeepAliveAdapter(pool_connections=4, pool_maxsize=24, max_retries=retry))
    return sess


NET = _session()        # connexions gardees ouvertes vers Groq et les autres services : plus de poignee de main a chaque appel
TG_NET = _session()     # Telegram a part : l'attente longue (getUpdates) d'un cote, les envois de l'autre
POLL_NET = _session()
IDLE_RESET = 20         # secondes sans envoi : on repart d'une connexion neuve (une connexion dormante a pu mourir sans bruit)
UPLOADS = ("sendVoice", "sendAudio", "sendDocument", "sendPhoto", "sendVideo")
_last_send = [0.0]


def is_wa(chat_id):
    """WhatsApp conversations use ids like 'wa:33612345678'; Telegram ones are plain numbers."""
    return isinstance(chat_id, str) and chat_id.startswith("wa:")


def wa_to(chat_id):
    return chat_id[3:]


def tg(method, **params):
    if is_wa(params.get("chat_id")):               # Telegram-only call (typing, buttons editing...) : nothing to do on WhatsApp
        return {}
    if method == "getUpdates":
        return POLL_NET.post(f"{TG}/{method}", json=params, timeout=70).json()
    timeout = (5, 90 if method in UPLOADS else 25)
    if time.time() - _last_send[0] > IDLE_RESET:
        TG_NET.close()                                  # cheap (about 0.1 s) next to a reply that hangs for a minute
    try:
        resp = TG_NET.post(f"{TG}/{method}", json=params, timeout=timeout)
    except (requests.ConnectionError, requests.Timeout):
        TG_NET.close()                                  # the kept-alive connection was dead: once more on a fresh one
        resp = TG_NET.post(f"{TG}/{method}", json=params, timeout=timeout)
    _last_send[0] = time.time()
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
