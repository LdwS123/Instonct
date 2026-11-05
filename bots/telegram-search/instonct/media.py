"""Images, favourites, files sent to the chat and the extra tools (documents, QR, places...)."""

import json
import os
import random
import re
import time
import uuid

import requests

from .optional import extras
from .optional import whatsapp
from .config import TG
from .core import db, is_wa, log, norm, scrub, send, tg, wa_to
from . import system_tools, web

# ---------------------------------------------------------------- images et favoris
MAX_IMAGE = 10 * 2**20


def send_image(chat_id, data, caption=""):
    """Envoie une image (octets) dans le chat, Telegram ou WhatsApp. Renvoie True si c'est parti."""
    caption = (caption or "")[:900]
    if is_wa(chat_id):
        return whatsapp.send_image(wa_to(chat_id), data, caption)
    r = requests.post(f"{TG}/sendPhoto", data={"chat_id": chat_id, "caption": caption}, files={"photo": ("image.jpg", data)}, timeout=120)
    if r.status_code == 200:
        return True
    r = requests.post(f"{TG}/sendDocument", data={"chat_id": chat_id, "caption": caption}, files={"document": ("image.jpg", data)}, timeout=120)
    return r.status_code == 200


def send_local_file(chat_id, path):
    """Envoie un fichier du Mac mini dans le chat (Telegram ou WhatsApp, 50 Mo max). True si c'est parti."""
    if os.path.getsize(path) > 50 * 2**20:
        return False
    with open(path, "rb") as f:
        if is_wa(chat_id):
            return bool(whatsapp.send_document(wa_to(chat_id), f.read(), os.path.basename(path)))
        r = requests.post(f"{TG}/sendDocument", data={"chat_id": chat_id}, files={"document": (os.path.basename(path), f)}, timeout=180)
        return r.status_code == 200


def tool_extra(chat_id, name, args, links):
    """Outils de extras.py : le calcul est la-bas, ici on gere les chemins sures, l'envoi dans le chat et la 'contamination'."""
    if extras is None:
        return {"erreur": "extras.py absent ou ses bibliotheques ne sont pas installees"}
    try:
        if name == "read_document":
            path = system_tools._path(args.get("path", ""), system_tools.WORK)
            if system_tools.SECRET_PATH.search(path) or not os.path.isfile(path):
                return {"erreur": "fichier introuvable ou sensible"}
            links.append("doc:" + path)                       # le contenu vient de l'exterieur : meme prudence qu'une page web
            return {"texte": extras.read_document(path, args.get("start", 0))}
        if name == "make_document":
            path = extras.make_document(str(args.get("kind", "pdf")), str(args.get("content", "")), os.path.expanduser("~/exports"),
                                        name=str(args.get("name", "")), title=str(args.get("title", "")))
            ok = send_local_file(chat_id, path)
            return {"resultat": "document cree" + (" et envoye dans le chat" if ok else " (envoi impossible)"), "chemin": path}
        if name == "qr_code":
            text = str(args.get("text", "")).strip()[:1500]
            if not text:
                return {"erreur": "text vide"}
            path = extras.make_qr(text, os.path.expanduser(f"~/exports/qr_{int(time.time())}.png"))
            with open(path, "rb") as f:
                ok = send_image(chat_id, f.read(), "QR code")
            return {"resultat": "QR code envoye" if ok else "envoi impossible", "chemin": path}
        if name == "download_file":
            url = str(args.get("url", ""))
            path, n = extras.download(url, os.path.expanduser("~/recus"), str(args.get("name", "")), web.url_ok)
            links.append(url)
            sent = bool(args.get("send")) and send_local_file(chat_id, path)
            return {"resultat": f"telecharge ({n // 1024} Ko)" + (", envoye dans le chat" if sent else ""), "chemin": path}
        if name == "send_location":
            lat, lon, label = args.get("latitude"), args.get("longitude"), str(args.get("title", ""))
            if lat is None or lon is None:
                found = extras.geocode(str(args.get("query", "")))
                if not found:
                    return {"erreur": "lieu introuvable"}
                lat, lon, label = found[0], found[1], label or found[2]
            lat, lon = float(lat), float(lon)
            if is_wa(chat_id):
                send(chat_id, f"{label or 'Lieu'} : https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}")
            elif label:
                tg("sendVenue", chat_id=chat_id, latitude=lat, longitude=lon, title=label[:100], address=str(args.get("address", ""))[:200] or label[:200])
            else:
                tg("sendLocation", chat_id=chat_id, latitude=lat, longitude=lon)
            return {"resultat": f"lieu envoye ({lat:.4f}, {lon:.4f})", "nom": label}
        if name == "send_poll":
            opts = [str(o)[:100] for o in (args.get("options") or []) if str(o).strip()][:10]
            q = str(args.get("question", "")).strip()[:300]
            if len(opts) < 2 or not q:
                return {"erreur": "il faut une question et au moins 2 options"}
            if is_wa(chat_id):
                send(chat_id, q + "\n" + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(opts)))
            else:
                tg("sendPoll", chat_id=chat_id, question=q, options=opts, is_anonymous=True)
            return {"resultat": "sondage envoye"}
        if name == "wikipedia":
            res = extras.wikipedia(str(args.get("query", "")), str(args.get("lang", "fr")))
            if not res:
                return {"erreur": "aucun article trouve"}
            links.append(res.get("lien") or "wikipedia")
            return res
        if name == "money":
            return {"resultat": extras.money(float(args.get("amount", 1) or 1), str(args.get("from", "")), str(args.get("to", "")))}
        if name == "wake_on_lan":
            return {"resultat": extras.wake_on_lan(str(args.get("mac", "")))}
    except Exception as e:
        return {"erreur": f"{type(e).__name__}: {scrub(e)[:200]}"}
    return {"erreur": "outil inconnu"}


def _download_image(url):
    """Telecharge une image publique (10 Mo max). Renvoie les octets ou None."""
    if not web.url_ok(url):
        return None
    try:
        r = requests.get(url, timeout=60, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
            return None
        data = r.raw.read(MAX_IMAGE + 1, decode_content=True)
        return data if 0 < len(data) <= MAX_IMAGE else None
    except Exception as e:
        log.warning("image : %s", scrub(e)[:100])
        return None


def tool_image(chat_id, name, args):
    caption = str(args.get("caption", ""))
    if name == "generate_image":
        prompt = str(args.get("prompt", "")).strip()[:400]
        if not prompt:
            return {"erreur": "description vide"}
        data = _download_image("https://image.pollinations.ai/prompt/" + requests.utils.quote(prompt, safe="") +
                               f"?width=1024&height=1024&nologo=true&seed={random.randint(1, 10**6)}")
        if not data:
            return {"erreur": "le service d'images ne repond pas, reessaie dans une minute"}
        return {"resultat": "image envoyee"} if send_image(chat_id, data, caption or prompt[:200]) else {"erreur": "l'envoi a echoue"}
    if name == "find_image":
        try:
            from ddgs import DDGS
            found = DDGS(timeout=6).images(str(args.get("query", "")), max_results=8) or []
        except Exception as e:
            return {"erreur": "recherche d'images indisponible : " + scrub(e)[:100]}
        for item in found:
            data = _download_image(item.get("image", ""))
            if data and send_image(chat_id, data, str(item.get("title", ""))[:200]):
                return {"resultat": "image envoyee"}
        return {"erreur": "aucune image utilisable trouvee"}
    src = str(args.get("source", "")).strip()                      # send_photo
    if src.startswith(("http://", "https://")):
        data = _download_image(src)
    else:
        path = os.path.expanduser(src)
        if re.search(r"\.env\b|id_rsa|shadow", path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_IMAGE:
            return {"erreur": "fichier introuvable, trop gros ou sensible"}
        with open(path, "rb") as f:
            data = f.read()
    if not data:
        return {"erreur": "image introuvable"}
    return {"resultat": "image envoyee"} if send_image(chat_id, data, caption) else {"erreur": "l'envoi a echoue"}


def favorites():
    out = []
    for k, v in db.hgetall("favorites").items():
        try:
            out.append({"id": k, **json.loads(v)})
        except ValueError:
            continue
    return sorted(out, key=lambda f: f.get("at", 0))


def tool_favorite(name, args):
    if name == "favorite_add":
        text = str(args.get("text", "")).strip()[:200]
        if not text:
            return {"erreur": "rien a sauvegarder"}
        for f in favorites():
            if norm(f["text"]) == norm(text):
                return {"resultat": "deja dans les favoris"}
        db.hset("favorites", uuid.uuid4().hex[:8], json.dumps({"text": text, "kind": str(args.get("kind", ""))[:30], "at": time.time()}, ensure_ascii=False))
        return {"resultat": f"sauvegarde : {text}"}
    if name == "favorite_list":
        q = norm(str(args.get("filter", "")))
        items = [f"{f['text']} ({f['kind']})" if f.get("kind") else f["text"] for f in favorites() if not q or q in norm(f["text"] + " " + f.get("kind", ""))]
        return {"favoris": items or "aucun"}
    q = norm(str(args.get("text", "")))
    n = 0
    for f in favorites():
        if q and q in norm(f["text"]):
            db.hdel("favorites", f["id"])
            n += 1
    return {"resultat": f"{n} favori(s) retire(s)"}
