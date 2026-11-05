"""Facts about the world from free public sources (no key): air, sun and moon, earthquakes, the space station, the day in history,
a word, books, countries, public holidays abroad, a GitHub project, and RSS feeds followed with new-item alerts.

What comes from the outside is named in TAINT: the conversation is then treated as having read a stranger's text.
"""

import hashlib
import html
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from .core import db, log, scrub, send
from . import web
from .kit_base import AGENT, get_json, spec, text, whole

SPECS = [
    spec("air_quality", "La qualite de l'air (indice europeen, particules, ozone, UV) dans une ville.", ville="string!"),
    spec("sun_moon", "Lever et coucher du soleil, duree du jour, UV max et phase de la lune pour une ville.", ville="string!"),
    spec("earthquakes", "Les derniers seismes importants dans le monde (magnitude, lieu, heure).", magnitude="number"),
    spec("iss_position", "Ou se trouve la Station spatiale internationale en ce moment."),
    spec("onthisday", "Ce qui s'est passe un jour de l'histoire (aujourd'hui par defaut).", mois="integer", jour="integer"),
    spec("define_word", "La definition d'un mot (Wiktionnaire).", mot="string!"),
    spec("rss", "Flux RSS : action add|list|remove|read. add/remove/read prennent url ; read donne les derniers articles. Les nouveaux articles sont signales.",
         action="string!", url="string"),
    spec("book_search", "Cherche un livre (titre, auteur, annee, lien Open Library).", recherche="string!"),
    spec("country_info", "Fiche d'un pays : capitale, population, langues, monnaie, fuseaux.", pays="string!"),
    spec("holidays_world", "Les jours feries d'un autre pays (nom ou code, ex. Italie ou IT).", pays="string!", annee="integer"),
    spec("github_repo", "Infos sur un projet GitHub (owner/nom) : etoiles, licence, derniere version ; ou recherche de projets par mots.", repo="string!"),
]
GROUPS = [
    (r"qualite de l.air|pollution|\bair\b|pollen|uv\b|ozone", {"air_quality"}),
    (r"soleil|coucher|lever du|lune|lunaire|duree du jour|crepuscule|aube", {"sun_moon"}),
    (r"seisme|tremblement de terre|earthquake|secousse", {"earthquakes"}),
    (r"station spatiale|\biss\b|astronaute|satellite", {"iss_position"}),
    (r"ce jour|il y a .* ans|dans l.histoire|ephemeride|aujourd.hui dans|ce jour-la", {"onthisday"}),
    (r"definition|definis|ca veut dire|signifie|synonyme|c.est quoi le mot|que veut dire|sens du mot", {"define_word"}),
    (r"\brss\b|flux|abonne.moi|suis ce blog|nouveaux articles|podcast", {"rss"}),
    (r"livre|roman|auteur|bouquin|bibliotheque|isbn|a lire", {"book_search"}),
    (r"pays|capitale|population|drapeau|habitants|langue officielle|monnaie de", {"country_info"}),
    (r"ferie|jour off|vacances scolaires|bank holiday|holiday", {"holidays_world"}),
    (r"github|depot|repo\b|open.?source|etoiles|stars|release|projet libre", {"github_repo"}),
]
TAINT = {"onthisday", "define_word", "rss", "book_search", "github_repo", "earthquakes", "country_info"}


def _where(city):
    g = get_json("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1, language="fr").get("results") or []
    if not g:
        raise LookupError(f"ville introuvable : {city}")
    return g[0]["latitude"], g[0]["longitude"], g[0]["name"], g[0].get("country", "")


def aqi_label(v):
    return next(name for limit, name in ((20, "tres bon"), (40, "bon"), (60, "moyen"), (80, "mediocre"), (100, "mauvais"), (10**9, "tres mauvais")) if v <= limit)


def air_quality(chat_id, a):
    lat, lon, name, country = _where(text(a, "ville"))
    cur = get_json("https://air-quality-api.open-meteo.com/v1/air-quality", latitude=lat, longitude=lon, timezone="auto",
                   current="european_aqi,pm10,pm2_5,ozone,nitrogen_dioxide,uv_index").get("current", {})
    aqi = cur.get("european_aqi")
    return {"ville": f"{name} ({country})", "indice_europeen": aqi, "niveau": aqi_label(aqi) if aqi is not None else "inconnu", "pm2_5": cur.get("pm2_5"),
            "pm10": cur.get("pm10"), "ozone": cur.get("ozone"), "uv": cur.get("uv_index"), "unites": "ug/m3"}


def moon_phase(when=None):
    """Age of the moon in days since the new moon (29.53-day cycle) and its name. Accurate to about a day."""
    when = when or datetime.now(timezone.utc)
    age = ((when - datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)).total_seconds() / 86400) % 29.530588853
    names = ("nouvelle lune", "premier croissant", "premier quartier", "gibbeuse croissante", "pleine lune", "gibbeuse decroissante", "dernier quartier", "dernier croissant")
    return round(age, 1), names[int((age + 1.845) // 3.691) % 8], round((1 - math.cos(2 * math.pi * age / 29.530588853)) / 2 * 100)


def sun_moon(chat_id, a):
    lat, lon, name, country = _where(text(a, "ville"))
    d = get_json("https://api.open-meteo.com/v1/forecast", latitude=lat, longitude=lon, timezone="auto", forecast_days=1,
                 daily="sunrise,sunset,daylight_duration,uv_index_max").get("daily", {})
    age, phase, lit = moon_phase()
    return {"ville": f"{name} ({country})", "lever": (d.get("sunrise") or [""])[0][-5:], "coucher": (d.get("sunset") or [""])[0][-5:],
            "duree_du_jour": f"{int((d.get('daylight_duration') or [0])[0] // 3600)} h {int((d.get('daylight_duration') or [0])[0] % 3600 // 60)} min",
            "uv_max": (d.get("uv_index_max") or [None])[0], "lune": phase, "lune_eclairee_pct": lit, "age_lune_jours": age}


def earthquakes(chat_id, a):
    low = max(2.5, float(a.get("magnitude") or 4.5))
    feed = "4.5" if low >= 4.5 else "2.5"
    rows = get_json(f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}_day.geojson", timeout=15).get("features", [])
    rows = sorted((r["properties"] for r in rows if (r["properties"].get("mag") or 0) >= low), key=lambda p: -p["mag"])
    return {"depuis": "24 h", "magnitude_min": low, "total": len(rows), "plus_forts": [
        {"magnitude": p["mag"], "lieu": p.get("place", ""), "heure_utc": datetime.fromtimestamp(p["time"] / 1000, timezone.utc).strftime("%d/%m %H:%M"), "lien": p.get("url", "")} for p in rows[:8]]}


def iss_position(chat_id, a):
    d = get_json("https://api.wheretheiss.at/v1/satellites/25544")
    return {"latitude": round(d["latitude"], 2), "longitude": round(d["longitude"], 2), "altitude_km": round(d["altitude"]),
            "vitesse_km_h": round(d["velocity"]), "au_dessus": "jour" if d.get("visibility") == "daylight" else "ombre de la Terre", "carte": f"https://www.google.com/maps?q={d['latitude']},{d['longitude']}"}


def onthisday(chat_id, a):
    now = datetime.now()
    month, day = whole(a, "mois", now.month, 1, 12), whole(a, "jour", now.day, 1, 31)
    events = get_json(f"https://api.wikimedia.org/feed/v1/wikipedia/fr/onthisday/events/{month:02d}/{day:02d}", timeout=15).get("events", [])
    picked = sorted(events, key=lambda e: -len(e.get("pages", [])))[:6]
    return {"date": f"{day:02d}/{month:02d}", "evenements": sorted(f"{e.get('year')} : {e.get('text', '')[:160]}" for e in picked), "source": "Wikipedia"}


def _wikitext(raw):
    """A line of Wiktionary markup -> plain words ([[a|b]] -> b, {{templates}} dropped)."""
    raw = re.sub(r"\{\{(?:lien|l)\|([^|}]+)[^}]*\}\}", r"\1", raw)
    for _ in range(3):
        raw = re.sub(r"\{\{[^{}]*\}\}", "", raw)
    raw = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", raw)
    return re.sub(r"\s+", " ", raw.replace("'" * 3, "").replace("'" * 2, "")).strip(" :;,")


def _french_entry(word):
    """(title, wikitext) of the first Wiktionary page that has a French section. A page without one often points to the right spelling
    with {{voir|...}} ("ephemere" -> "éphémère"); if nothing does, the site's own search suggests titles."""
    api = "https://fr.wiktionary.org/w/api.php"
    queue, tried, searched = [word], set(), False
    while queue and len(tried) < 8:
        title = queue.pop(0)
        if title in tried:
            continue
        tried.add(title)
        j = get_json(api, action="query", prop="revisions", rvprop="content", rvslots="main", titles=title, format="json", formatversion=2)
        page = ((j.get("query") or {}).get("pages") or [{}])[0]
        wiki = ((page.get("revisions") or [{}])[0].get("slots") or {}).get("main", {}).get("content", "")
        if "{{langue|fr}}" in wiki:
            return title, wiki
        for m in re.findall(r"\{\{voir\|([^}]*)\}\}", wiki):
            queue += [x for x in m.split("|") if x and "=" not in x]
        if not queue and not searched:
            searched = True
            found = get_json(api, action="query", list="search", srsearch=word, srlimit=4, srnamespace=0, format="json", formatversion=2)
            queue += [h["title"] for h in (found.get("query") or {}).get("search", [])]
    return word, ""


def define_word(chat_id, a):
    word, wiki = _french_entry(text(a, "mot", "", 60))
    if not wiki:
        return {"mot": word, "erreur": "mot introuvable dans le Wiktionnaire (en francais)"}
    start = wiki.find("{{langue|fr}}")
    french = re.split(r"\n==\s*\{\{langue\|(?!fr\}\})", wiki[start:])[0]
    out, nature = [], ""
    for line in french.splitlines():
        head = re.match(r"=+\s*\{\{S\|([^|}]+)\|fr", line)
        if head:
            nature = head.group(1)
        elif re.match(r"#(?![*:#])", line) and nature and nature not in ("étymologie", "prononciation"):
            sense = _wikitext(line[1:])
            if sense and len(out) < 8:
                out.append({"nature": nature, "sens": sense[:200]})
    return {"mot": word, "definitions": out} if out else {"mot": word, "erreur": "pas de definition en francais"}


# ---- RSS -------------------------------------------------------------------------------------------------------------------------
def parse_feed(xml, limit=8):
    """RSS 2.0 and Atom -> [{id, titre, lien}]. A feed that is not XML gives an empty list."""
    out = []
    for block in re.findall(r"<item\b.*?</item>|<entry\b.*?</entry>", xml, re.S)[:limit]:
        def tag(name):
            m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        link = tag("link") or (re.search(r'<link[^>]*href="([^"]+)"', block) or [0, ""])[1]
        out.append({"id": tag("guid") or tag("id") or link, "titre": tag("title")[:160], "lien": link})
    return [x for x in out if x["titre"]]


def _feed(url):
    r = web.safe_get(url, timeout=12, headers=AGENT)
    r.raise_for_status()
    return parse_feed(r.text)


def rss(chat_id, a):
    action, url, key = text(a, "action", "list", 10).lower(), text(a, "url", "", 300), f"rss:{chat_id}"
    if action == "list":
        return {"flux": sorted(x.decode() if isinstance(x, bytes) else x for x in db.smembers(key))}
    if not web.url_ok(url):
        return {"erreur": "donne l'adresse du flux (https://...)"}
    if action == "remove":
        return {"retire": bool(db.srem(key, url))}
    items = _feed(url)
    if not items:
        return {"erreur": "ce n'est pas un flux RSS ou Atom lisible"}
    if action == "add":
        db.sadd(key, url)
        db.sadd("rss:seen:" + hashlib.md5(url.encode()).hexdigest(), *[i["id"] for i in items])          # what exists now is not "new"
        return {"ajoute": url, "articles_actuels": len(items), "note": "je te previens des nouveaux articles"}
    return {"flux": url, "articles": [{"titre": i["titre"], "lien": i["lien"]} for i in items[:8]]}


def check_feeds(chat_id):
    """Monitor tick (once an hour): tells about new articles of the followed feeds, three at most per feed."""
    if not db.set("rss:tick", 1, nx=True, ex=3600):
        return
    for raw in db.smembers(f"rss:{chat_id}"):
        url = raw.decode() if isinstance(raw, bytes) else raw
        try:
            items, seen = _feed(url), "rss:seen:" + hashlib.md5(url.encode()).hexdigest()
            new = [i for i in items if not db.sismember(seen, i["id"])]
            if new:
                db.sadd(seen, *[i["id"] for i in new])
                send(chat_id, "Nouveau sur ton flux :\n" + "\n".join(f"- {i['titre']}\n  {i['lien']}" for i in new[:3]))
        except Exception as e:
            log.warning("rss %s : %s", url[:60], scrub(e))


# ---- books, countries, holidays, GitHub ------------------------------------------------------------------------------------------
def book_search(chat_id, a):
    docs = get_json("https://openlibrary.org/search.json", q=text(a, "recherche"), limit=5, fields="title,author_name,first_publish_year,key,language").get("docs", [])
    return {"livres": [{"titre": d.get("title", ""), "auteur": ", ".join(d.get("author_name", [])[:2]), "annee": d.get("first_publish_year"), "lien": "https://openlibrary.org" + d.get("key", "")} for d in docs]}


def country_info(chat_id, a):
    name = text(a, "pays", "", 60)
    found = get_json("https://geocoding-api.open-meteo.com/v1/search", name=name, count=5, language="fr").get("results") or []
    land = next((g for g in found if g.get("feature_code") == "PCLI"), None)          # a country, not a town with the same name
    if not land:
        return {"erreur": f"pays introuvable : {name}"}
    out = {"pays": land.get("name"), "code": land.get("country_code"), "population": land.get("population")}
    try:                                                                              # capital and region: nice to have, the source is slow at times
        info = get_json(f"https://api.worldbank.org/v2/country/{land['country_code']}", timeout=8, format="json")[1][0]
        out |= {"capitale": info.get("capitalCity"), "region": (info.get("region") or {}).get("value", "").strip(), "niveau_de_revenu": (info.get("incomeLevel") or {}).get("value")}
    except Exception:
        pass
    return out


def holidays_world(chat_id, a):
    code = text(a, "pays", "", 60)
    if not re.fullmatch(r"[A-Za-z]{2}", code):
        code = country_info(chat_id, {"pays": code}).get("code") or ""
    year = whole(a, "annee", datetime.now().year, 1990, 2100)
    if not code:
        return {"erreur": "pays introuvable"}
    r = requests.get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/{code.upper()}", headers=AGENT, timeout=12)
    if r.status_code != 200:
        return {"erreur": f"pas de calendrier pour {code.upper()} {year}"}
    today = f"{datetime.now():%Y-%m-%d}"
    days = [f"{h['date']} : {h.get('localName') or h['name']}" for h in r.json()]
    return {"pays": code.upper(), "annee": year, "jours": days, "prochain": next((d for d in days if d[:10] >= today), "")}


def github_repo(chat_id, a):
    repo = text(a, "repo", "", 120).replace("https://github.com/", "").strip("/")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        d = get_json("https://api.github.com/repos/" + repo)
        rel = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", headers=AGENT, timeout=10)
        return {"projet": d["full_name"], "description": (d.get("description") or "")[:200], "etoiles": d["stargazers_count"], "forks": d["forks_count"],
                "problemes_ouverts": d["open_issues_count"], "licence": (d.get("license") or {}).get("spdx_id"), "langage": d.get("language"),
                "dernier_commit": (d.get("pushed_at") or "")[:10], "derniere_version": rel.json().get("tag_name") if rel.status_code == 200 else None, "lien": d["html_url"]}
    found = get_json("https://api.github.com/search/repositories", q=repo, per_page=5, sort="stars").get("items", [])
    return {"resultats": [{"projet": d["full_name"], "etoiles": d["stargazers_count"], "description": (d.get("description") or "")[:120], "lien": d["html_url"]} for d in found]}


FUNCS = {"air_quality": air_quality, "sun_moon": sun_moon, "earthquakes": earthquakes, "iss_position": iss_position, "onthisday": onthisday,
         "define_word": define_word, "rss": rss, "book_search": book_search, "country_info": country_info, "holidays_world": holidays_world,
         "github_repo": github_repo}
