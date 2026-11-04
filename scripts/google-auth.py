#!/usr/bin/env python3
"""Autorise le bot a utiliser ton Google Agenda (une seule fois).

Etape 1 : python3 google-auth.py url      -> affiche un lien a ouvrir dans le navigateur, puis cliquer "Autoriser"
Etape 2 : python3 google-auth.py echange 'http://localhost:8085/?code=...'   (l'adresse de la page ou le navigateur arrive,
          meme si elle affiche une erreur : on a juste besoin de l'adresse)

Il faut avant ~/bots/google_client.json : {"client_id": "...", "client_secret": "..."} (identifiant "application de bureau").
"""
import json
import os
import stat
import sys
import urllib.parse

import requests

CLIENT = os.path.expanduser("~/bots/google_client.json")
TOKEN = os.path.expanduser("~/bots/google_token.json")
REDIRECT = "http://localhost:8085"
SCOPE = "https://www.googleapis.com/auth/calendar.events"

cfg = json.load(open(CLIENT))
if len(sys.argv) >= 2 and sys.argv[1] == "url":
    print("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cfg["client_id"], "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"}))
elif len(sys.argv) >= 3 and sys.argv[1] == "echange":
    code = urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[2]).query).get("code", [""])[0]
    if not code:
        sys.exit("Pas de code dans cette adresse.")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}, timeout=20)
    d = r.json()
    if "refresh_token" not in d:
        sys.exit("Echec : " + json.dumps(d)[:300])
    with open(TOKEN, "w") as f:
        json.dump({"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                   "refresh_token": d["refresh_token"]}, f)
    os.chmod(TOKEN, stat.S_IRUSR | stat.S_IWUSR)
    print("OK : le bot peut maintenant utiliser ton agenda.")
else:
    sys.exit(__doc__)
