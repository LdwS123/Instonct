"""Remote screen (/connexion) and the Siri endpoint (/siri)."""

import json
import re
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

from . import screen
from .texts import SILENT
from .core import db, log, norm, scrub, send
from . import brain, handlers, music, sound

SCREEN_SITES = {"linkedin": "https://www.linkedin.com/login", "indeed": "https://secure.indeed.com/auth", "gmail": "https://mail.google.com/",
                "google": "https://accounts.google.com/", "welcome": "https://www.welcometothejungle.com/fr/signin", "france travail": "https://candidat.francetravail.fr/",
                "facebook": "https://www.facebook.com/login", "instagram": "https://www.instagram.com/accounts/login/", "x": "https://x.com/login",
                "twitter": "https://x.com/login", "amazon": "https://www.amazon.fr/ap/signin", "github": "https://github.com/login"}


def connexion_command(chat_id, arg):
    """/connexion [site] : ouvre un ecran temporaire (noVNC via Tailscale) pour que l'humain se connecte LUI-MEME. /connexion stop : ferme."""
    a = norm(arg)
    if a in ("stop", "fin", "ferme", "fermer", "off"):
        screen.stop()
        return "Ecran ferme. Tes connexions restent gardees sur le Mac mini."
    url = next((u for k, u in SCREEN_SITES.items() if k in a), None) or (arg.strip() if re.match(r"https?://\S+$", arg.strip()) else "https://www.linkedin.com/login")
    return open_screen(chat_id, url)


def open_screen(chat_id, url):
    """Sends the link and the steps, and returns the line holding the screen's password (or why it could not open)."""
    r = screen.start(15, url)
    if not r.get("ok"):
        return "Je n'arrive pas a ouvrir l'ecran : " + str(r.get("erreur", "?"))
    send(chat_id, "Ecran ouvert pour " + str(r["reste_min"]) + " minutes. Il faut Tailscale allume sur ton telephone.\n\n"
                  f"1) Ouvre ce lien :\n{r['url']}\n\n2) Quand il demande un mot de passe, tape celui du message suivant.\n"
                  "3) Connecte-toi toi-meme au site. Je ne vois jamais tes mots de passe.\n4) Quand c'est fini : /connexion stop")
    return "Mot de passe de l'ecran : " + r["mot_de_passe"]


SIRI_PORT = 8765


def siri_token():
    t = db.get("siri_token")
    if not t:
        t = uuid.uuid4().hex
        db.set("siri_token", t)
    return t


def siri_url():
    ip = screen._tailscale_ip()
    return f"http://{ip}:{SIRI_PORT}/{siri_token()}" if ip else ""


def start_siri_server():
    """Petit serveur reserve a Tailscale : un Raccourci iPhone ('Dis Siri, Steve') lui envoie ce que tu as dit, meme telephone verrouille.
    Il repond par du texte que Siri lit a voix haute. Le jeton secret est dans l'adresse ; seul ton reseau Tailscale peut l'atteindre."""
    ip = screen._tailscale_ip()
    if not ip:
        log.info("serveur Siri non demarre : pas d'adresse Tailscale")
        return

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _out(self, code, txt):
            data = txt.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path.strip("/") != siri_token():
                return self._out(404, "non")
            owner = db.get("owner_id")
            if not owner:
                return self._out(403, "Parle d'abord au bot sur Telegram.")
            try:
                raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4000)).decode("utf-8", "ignore")
                try:
                    text = str(json.loads(raw).get("texte", ""))
                except ValueError:
                    text = urllib.parse.parse_qs(raw).get("texte", [raw])[0] if "=" in raw else raw
                text = re.sub(r"^\s*(?:hey |ok |eh )?steve\b[\s,:;.!-]*", "", text.strip(), flags=re.I).strip()
                if len(text) < 2:
                    return self._out(200, "Je t'ecoute, mais je n'ai rien entendu.")
                chat = int(owner)
                if handlers.quota_exceeded(chat):
                    return self._out(200, "Trop de questions pour le moment.")
                done = music.quick_music(text)
                if done:
                    return self._out(200, done)
                answer = brain.ask(chat, text, oral=True)
                if answer == SILENT:
                    return self._out(200, "Le brouillon t'attend sur Telegram.")
                send(chat, "Siri : " + text + "\n\n" + answer)               # une trace dans la conversation
                self._out(200, sound.clean_for_speech(answer, 700) or "C'est fait.")
            except Exception as e:
                log.warning("serveur Siri : %s", scrub(e))
                self._out(500, "Petit souci, reessaie.")

    try:
        srv = ThreadingHTTPServer((ip, SIRI_PORT), H)
    except OSError as e:
        log.warning("serveur Siri impossible : %s", scrub(e))
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("serveur Siri pret sur %s:%s", ip, SIRI_PORT)


def siri_command(chat_id):
    url = siri_url()
    if not url:
        return "Tailscale n'est pas actif sur le Mac mini."
    send(chat_id, "Pour que « Dis Siri, Steve » marche, meme telephone verrouille :\n\n"
                  "1) Ouvre l'app Raccourcis (Shortcuts) sur ton iPhone, touche + (nouveau raccourci).\n"
                  "2) Nomme-le : Steve\n"
                  "3) Ajoute l'action « Dicter du texte » (langue : francais).\n"
                  "4) Ajoute « Obtenir le contenu de l'URL » : colle l'adresse du message suivant, Methode = POST, "
                  "Corps de la requete = JSON, ajoute un champ Texte nomme texte = (Texte dicte).\n"
                  "5) Ajoute « Enoncer le texte » (Speak Text) avec (Contenu de l'URL).\n\n"
                  "Ensuite tu dis « Dis Siri, Steve », il t'ecoute, tu dis ta demande, et il te repond a voix haute. "
                  "Il faut Tailscale allume sur le telephone. Garde cette adresse secrete.")
    return url
