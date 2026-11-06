"""A searchable catalogue of free public APIs (the public-apis list on GitHub, about 2,250 entries in 51 themes).

It does not call those APIs itself: it tells the model WHICH free service exists for a need and where its documentation is,
and the model then uses http_request / fetch_url (which have their own guards). The list is downloaded once a week and kept in Redis.
Everything in it was written by strangers, so a hit marks the conversation as tainted like any other web text.
"""

import json
import re

import requests

from .core import db
from .kit_base import AGENT, spec, text, whole

SOURCE = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
CACHE = "apis:list"
DAYS = 7
ROW = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)\s]+)\)\s*\|\s*(.*?)\s*\|\s*(`[^`]*`|No|Yes)?\s*\|\s*(Yes|No)?\s*\|\s*([^|]*?)\s*\|\s*$")

SPECS = [
    spec("api_search", "Cherche une API gratuite publique (meteo, animaux, finance, musique, cartes...) dans un catalogue de 2250 services. Sans mot : liste les themes.",
         recherche="string", theme="string", sans_cle="boolean", nombre="integer"),
]
GROUPS = [(r"\bapi\b.*(?:gratuit|libre|publique|existe)|(?:gratuit|libre|publique).*\bapi\b|y a.t.il une api|quelle api|trouve.*\bapi\b|public.?apis|service gratuit pour", {"api_search"})]
TAINT = {"api_search"}


def parse(markdown):
    """README text -> [{nom, url, description, cle, theme}] ('cle' is '' when no key is needed)."""
    theme, out = "", []
    for line in markdown.splitlines():
        if line.startswith("### "):
            theme = line[4:].strip()
            continue
        m = ROW.match(line)
        if m and theme:
            key = (m.group(4) or "").strip("` ")
            out.append({"nom": m.group(1), "url": m.group(2), "description": m.group(3)[:140], "cle": "" if key in ("No", "") else key, "theme": theme})
    return out


def catalogue():
    cached = db.get(CACHE)
    if cached:
        return json.loads(cached)
    r = requests.get(SOURCE, headers=AGENT, timeout=20)
    r.raise_for_status()
    entries = parse(r.text)
    if len(entries) < 200:                                       # the page changed shape: better an honest error than an empty list
        raise RuntimeError("le catalogue d'API a change de format")
    db.set(CACHE, json.dumps(entries, ensure_ascii=False), ex=DAYS * 86400)
    return entries


def _flat(value):
    return re.sub(r"[^a-z0-9 ]+", " ", str(value).lower())


def api_search(chat_id, a):
    entries = catalogue()
    word, theme = _flat(text(a, "recherche", "", 80)).split(), _flat(text(a, "theme", "", 60)).strip()
    if not word and not theme:
        counts = {}
        for e in entries:
            counts[e["theme"]] = counts.get(e["theme"], 0) + 1
        return {"total": len(entries), "themes": [f"{t} ({n})" for t, n in sorted(counts.items())]}
    hits = []
    for e in entries:
        hay = _flat(f"{e['nom']} {e['description']} {e['theme']}")
        if theme and theme not in _flat(e["theme"]):
            continue
        if a.get("sans_cle") is True and e["cle"]:
            continue
        score = sum(hay.count(w) + (3 if w in _flat(e["nom"]) else 0) for w in word if w in hay)
        if (word and score and all(w in hay for w in word)) or (not word and theme):
            hits.append((score, e))
    hits.sort(key=lambda h: -h[0])
    top = [e for _, e in hits[:whole(a, "nombre", 8, 1, 15)]]
    if not top:
        return {"erreur": "aucune API trouvee avec ces mots (essaie un mot plus simple, en anglais si possible)", "total_catalogue": len(entries)}
    return {"trouvees": len(hits), "resultats": [{"nom": e["nom"], "sert_a": e["description"], "theme": e["theme"], "cle": e["cle"] or "aucune", "doc": e["url"]} for e in top],
            "suite": "Ouvre la doc avec fetch_url, puis appelle l'API avec http_request. Ne donne jamais de cle ou de mot de passe."}


FUNCS = {"api_search": api_search}
