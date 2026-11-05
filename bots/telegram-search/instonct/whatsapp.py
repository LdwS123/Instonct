"""WhatsApp channel for Instonct, through Meta's official WhatsApp Cloud API (no unofficial library, no ban risk).

Optional: it only starts when all of these variables are in the .env file:
  WA_TOKEN         permanent access token (System User token) of your Meta app
  WA_PHONE_ID      "Phone number ID" of the WhatsApp number (not the phone number itself)
  WA_VERIFY_TOKEN  any secret string you also type in Meta's webhook settings
  WA_APP_SECRET    the app secret (Meta dashboard > App settings > Basic), used to check every incoming call
  WA_OWNER         your own phone number(s), digits only, country code first, comma separated (e.g. 33612345678)
Optional: WA_PORT (default 8088, bound to 127.0.0.1 only), WA_API_VERSION (default v23.0).

Meta calls a public HTTPS address, so expose the local port with a tunnel (for example `tailscale funnel 8088`).
Every incoming call is rejected unless its X-Hub-Signature-256 matches the app secret.
Business-initiated messages only work inside the 24 h window that follows your last message to the bot.
"""
import hashlib
import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

log = logging.getLogger("whatsapp")

TOKEN = os.environ.get("WA_TOKEN", "")
PHONE_ID = os.environ.get("WA_PHONE_ID", "")
VERIFY = os.environ.get("WA_VERIFY_TOKEN", "")
SECRET = os.environ.get("WA_APP_SECRET", "")
OWNERS = {"".join(c for c in n if c.isdigit()) for n in os.environ.get("WA_OWNER", "").split(",")} - {""}
PORT = int(os.environ.get("WA_PORT", "8088") or 8088)
API = f"https://graph.facebook.com/{os.environ.get('WA_API_VERSION', 'v23.0')}"
MAX_MEDIA = 20 * 2**20

_http = requests.Session()


def configured():
    return bool(TOKEN and PHONE_ID and VERIFY and SECRET and OWNERS)


def allowed(number):
    return "".join(c for c in str(number) if c.isdigit()) in OWNERS


def _clean(e):
    s = str(e)
    for secret in (TOKEN, SECRET, VERIFY):
        if secret:
            s = s.replace(secret, "***")
    return s[:300]


def valid_signature(body, header):
    """True only if the header 'sha256=<hmac>' matches the body signed with the app secret."""
    if not SECRET or not header or not header.startswith("sha256="):
        return False
    good = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, header[7:])


def parse(payload):
    """Meta webhook JSON -> list of simple dicts: id, from, type, text, button, media, mime, name, caption."""
    out = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            for m in (change.get("value") or {}).get("messages", []) or []:
                t = m.get("type")
                item = {"id": m.get("id", ""), "from": m.get("from", ""), "type": t, "text": "", "button": "",
                        "media": "", "mime": "", "name": "", "caption": ""}
                if t == "text":
                    item["text"] = (m.get("text") or {}).get("body", "")
                elif t == "interactive":
                    it = m.get("interactive") or {}
                    rep = it.get("button_reply") or it.get("list_reply") or {}
                    item["button"] = rep.get("id", "")
                elif t == "button":
                    item["button"] = (m.get("button") or {}).get("payload", "")
                elif t in ("audio", "image", "document", "video"):
                    media = m.get(t) or {}
                    item.update(media=media.get("id", ""), mime=media.get("mime_type", ""),
                                name=media.get("filename", ""), caption=media.get("caption", ""))
                out.append(item)
    return out


# ---------------------------------------------------------------- sending (never raises)
def _post(body):
    try:
        r = _http.post(f"{API}/{PHONE_ID}/messages", json={"messaging_product": "whatsapp", **body},
                       headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30)
        if r.status_code >= 300:
            log.warning("whatsapp send code %s: %s", r.status_code, _clean(r.text))
        return r.status_code < 300
    except Exception as e:
        log.warning("whatsapp send failed: %s", _clean(e))
        return False


def send_text(to, text):
    text = (text or "").strip() or "(empty reply)"
    ok = True
    for i in range(0, len(text), 4000):
        ok = _post({"to": to, "type": "text", "text": {"body": text[i:i + 4000], "preview_url": False}}) and ok
    return ok


def send_buttons(to, text, buttons):
    """Up to 3 reply buttons: [(id, title), ...]. Title max 20 characters, body max 1024."""
    if len(text) > 1000:
        send_text(to, text)
        text = "Confirm?"
    return _post({"to": to, "type": "interactive", "interactive": {
        "type": "button", "body": {"text": text},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i[:256], "title": t[:20]}} for i, t in buttons[:3]]}}})


def _upload(data, filename, mime):
    try:
        r = _http.post(f"{API}/{PHONE_ID}/media", headers={"Authorization": f"Bearer {TOKEN}"},
                       data={"messaging_product": "whatsapp", "type": mime},
                       files={"file": (filename, data, mime)}, timeout=120)
        return r.json().get("id") if r.status_code < 300 else None
    except Exception as e:
        log.warning("whatsapp upload failed: %s", _clean(e))
        return None


def send_document(to, data, filename, mime="application/octet-stream"):
    mid = _upload(data, filename, mime)
    return bool(mid) and _post({"to": to, "type": "document", "document": {"id": mid, "filename": filename}})


def send_image(to, data, caption=""):
    mid = _upload(data, "image.jpg", "image/jpeg")
    return bool(mid) and _post({"to": to, "type": "image", "image": {"id": mid, "caption": (caption or "")[:1000]}})


def send_audio(to, data):
    """OGG/Opus bytes -> shows up as a voice note."""
    mid = _upload(data, "reply.ogg", "audio/ogg")
    return bool(mid) and _post({"to": to, "type": "audio", "audio": {"id": mid}})


def download(media_id):
    """Media id -> (bytes, mime). (None, '') if missing or bigger than 20 MB."""
    try:
        head = {"Authorization": f"Bearer {TOKEN}"}
        info = _http.get(f"{API}/{media_id}", headers=head, timeout=30).json()
        if not info.get("url") or int(info.get("file_size") or 0) > MAX_MEDIA:
            return None, ""
        r = _http.get(info["url"], headers=head, timeout=90)
        if r.status_code != 200 or len(r.content) > MAX_MEDIA:
            return None, ""
        return r.content, info.get("mime_type", "")
    except Exception as e:
        log.warning("whatsapp download failed: %s", _clean(e))
        return None, ""


# ---------------------------------------------------------------- receiving
def serve(on_message, is_duplicate):
    """Start the webhook server in a thread. on_message(dict) runs in its own thread per message."""
    class Hook(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, code, body=b""):
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):                       # Meta's one-time verification
            q = parse_qs(urlparse(self.path).query)
            ok = q.get("hub.mode") == ["subscribe"] and hmac.compare_digest(
                (q.get("hub.verify_token") or [""])[0].encode(), VERIFY.encode())
            self._reply(200, (q.get("hub.challenge") or [""])[0].encode()) if ok else self._reply(403)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > 2**20:
                return self._reply(400)
            body = self.rfile.read(n)
            if not valid_signature(body, self.headers.get("X-Hub-Signature-256", "")):
                log.warning("whatsapp call rejected: bad signature")
                return self._reply(403)
            self._reply(200)                    # answer fast; Meta retries if we are slow
            try:
                for m in parse(json.loads(body)):
                    if not m["id"] or not allowed(m["from"]) or is_duplicate(m["id"]):
                        continue
                    threading.Thread(target=on_message, args=(m,), daemon=True).start()
            except Exception as e:
                log.warning("whatsapp webhook error: %s", _clean(e))

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("whatsapp webhook listening on 127.0.0.1:%s", PORT)
    return srv
