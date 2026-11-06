"""Tools for people who build things: package and vulnerability lookups, tech news, questions and papers, IP and domain facts,
and exact local helpers (regex, JSON, dates, colours, numbers, unit conversion, CSV, archives).

The first group asks free public sources and is named in TAINT. The local group computes the answer here: no model arithmetic.
"""

import colorsys
import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from ipaddress import ip_address
from urllib.parse import quote

import requests

from . import system_tools
from .kit_base import AGENT, clean, get_json, get_json_or_none, host_of, num, spec, text, whole
from .kit_media import FOLDERS, WORK, find_file

SPECS = [
    spec("package_info", "Derniere version, licence, description et telechargements d'un paquet npm, pypi ou crates (gestionnaire npm|pypi|crates).", nom="string!", gestionnaire="string"),
    spec("cve_search", "Faille de securite : fiche d'un CVE (ex. CVE-2021-44228) ou recherche par mots (gravite, resume, lien).", cve="string", mots="string"),
    spec("dev_news", "Les actus tech de Hacker News : type front|new|ask|show, ou recherche par mots.", type="string", recherche="string"),
    spec("stack_search", "Cherche une question de programmation sur Stack Overflow (ou un autre site Stack Exchange) : score, reponses, lien.", recherche="string!", site="string"),
    spec("github_tendances", "Les nouveaux projets GitHub qui montent (jours, langage).", jours="integer", langage="string", nombre="integer"),
    spec("arxiv_search", "Cherche des articles scientifiques recents sur arXiv (titre, auteurs, date, resume, lien).", recherche="string!", recents="boolean"),
    spec("ip_info", "Pays, ville, operateur et fuseau d'une adresse IP publique.", ip="string!"),
    spec("wayback", "Retrouve une ancienne copie d'un site sur archive.org (url, date AAAAMMJJ facultative).", url="string!", date="string"),
    spec("cert_subdomains", "Liste les sous-domaines connus d'un domaine grace aux certificats publics (crt.sh).", domaine="string!"),
    spec("regex_test", "Teste une expression reguliere sur un texte (correspondances, groupes, remplacement). Drapeaux i, m, s.", motif="string!", texte="string!", drapeaux="string", remplacer="string"),
    spec("json_outils", "JSON : operation valider|formater|minifier|chemin|cles. chemin prend ex. a.b[0].c.", operation="string!", json="string!", chemin="string"),
    spec("date_calc", "Calculs de dates exacts : operation diff|ajouter|semaine|age|jours_ouvres (dates AAAA-MM-JJ ou JJ/MM/AAAA).", operation="string!", date="string", date2="string", jours="integer"),
    spec("color_info", "Couleur : hex, rgb, hsl, luminosite et contraste (WCAG) ; donne une ou deux couleurs (#ff8800, rgb(1,2,3), rouge).", couleur="string!", couleur2="string"),
    spec("nombres", "Maths exactes : operation premier|facteurs|pgcd|ppcm|base|romain|factorielle|fibonacci|pourcentage|evolution.", operation="string!", nombre="string!", autre="string",
         base_depart="integer", base_arrivee="integer"),
    spec("unites", "Convertit une valeur entre unites (longueur, masse, volume, vitesse, surface, temps, donnees, energie, pression, puissance, angle, temperature).",
         valeur="number!", de="string!", vers="string!"),
    spec("csv_outils", "Analyse un CSV (texte ou fichier recu) : operation resume|colonne (stats, valeurs frequentes).", operation="string!", fichier="string", texte="string", colonne="string"),
    spec("archive_outils", "Archives zip/tar : action lister|extraire|creer (creer zippe un dossier de ~/work).", fichier="string!", action="string!"),
]
GROUPS = [
    (r"\bnpm\b|pypi|pip install|\bcrates?\b|cargo|paquet|package|derniere version de|bibliotheque python|librairie", {"package_info"}),
    (r"\bcve\b|faille|vulnerabilite|exploit|log4j|securite de", {"cve_search"}),
    (r"hacker news|actu(?:alite)?s? (?:tech|dev|informatique)|news tech|ycombinator", {"dev_news"}),
    (r"stack ?overflow|stack ?exchange|question de programmation|comment faire en (?:python|javascript|bash|sql|rust|go)", {"stack_search"}),
    (r"tendances? github|trending|nouveaux? projets? (?:open source|github)|projets? du moment|repos? populaires?", {"github_tendances"}),
    (r"arxiv|papier de recherche|article scientifique|publication scientifique|etat de l.art|preprint", {"arxiv_search"}),
    (r"adresse ip|geolocalise.*ip|d.ou vient (?:cette|l) ?ip|\bfai\b|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", {"ip_info"}),
    (r"wayback|archive\.org|ancienne version (?:du|de) site|internet archive|archive du site", {"wayback"}),
    (r"sous.?domaines?|subdomain|crt\.sh|certificats? emis", {"cert_subdomains"}),
    (r"regex|expression reguliere|teste ce motif", {"regex_test"}),
    (r"\bjson\b|\bjq\b|valide ce json|formate ce json|chemin dans le json", {"json_outils"}),
    (r"combien de jours (?:entre|avant|depuis|reste)|quel jour (?:etait|sera|tombe)|jour de la semaine|numero de semaine|jours ouvres|mon age|quel age|ajoute .* jours? a la date", {"date_calc"}),
    (r"couleur|#[0-9a-f]{6}\b|rgb\(|contraste|code hex|hexadecimal.*couleur|palette", {"color_info"}),
    (r"nombre premier|est.ce que \d+ est premier|factorise|facteurs premiers|pgcd|ppcm|en binaire|en hexadecimal|chiffres? romains?|en romain|factorielle|fibonacci|\d+ ?% de |pourcentage|augmentation de|baisse de|evolution de", {"nombres"}),
    (r"convertis|conversion|combien (?:de|d.) ?(?:km|kg|litres?|miles?|metres?|degres|celsius|fahrenheit|livres|pouces|pieds)|\d ?(?:km|kg|cm|mm|miles?|pouces|pieds|livres|onces|gallons?|celsius|fahrenheit|mph|psi)\b|en (?:miles|pouces|pieds|fahrenheit|celsius|onces)", {"unites"}),
    (r"\bcsv\b|tableur|moyenne de la colonne|statistiques? (?:du|de ce) fichier|colonnes? du fichier", {"csv_outils"}),
    (r"\bzip\b|archive|\btar\b|dezippe|decompresse|unzip|compresse (?:le|ce) dossier|\.tar|\.gz", {"archive_outils"}),
]
TAINT = {"package_info", "cve_search", "dev_news", "stack_search", "github_tendances", "arxiv_search", "ip_info", "wayback", "cert_subdomains"}
LOCAL_FILES = {"csv_outils", "archive_outils"}                       # these read a received file: a stranger may have written it
TAINT |= LOCAL_FILES


# ------------------------------------------------------------------ free public sources

def package_info(chat_id, a):
    name, tool = text(a, "nom", "", 100), text(a, "gestionnaire", "npm", 10).lower()
    if tool.startswith("py") or tool == "pip":
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            return {"erreur": "nom de paquet invalide"}
        d = get_json_or_none(f"https://pypi.org/pypi/{name}/json")
        if not d:
            return {"erreur": f"{name} n'existe pas sur pypi"}
        i = d["info"]
        return {"gestionnaire": "pypi", "nom": i["name"], "version": i["version"], "resume": clean(i.get("summary"), 200), "licence": clean(i.get("license"), 60) or None,
                "python_requis": i.get("requires_python"), "liens": {k: v for k, v in list((i.get("project_urls") or {}).items())[:4]}, "versions_publiees": len(d.get("releases") or {})}
    if tool.startswith("crate") or tool == "cargo":
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            return {"erreur": "nom de crate invalide"}
        d = get_json_or_none(f"https://crates.io/api/v1/crates/{name}")
        if not d:
            return {"erreur": f"{name} n'existe pas sur crates.io"}
        c = d["crate"]
        return {"gestionnaire": "crates", "nom": c["name"], "version": c.get("max_stable_version") or c.get("max_version"), "resume": clean(c.get("description"), 200),
                "telechargements": c.get("downloads"), "depot": c.get("repository"), "maj": (c.get("updated_at") or "")[:10]}
    if not re.fullmatch(r"(@[a-z0-9~-][a-z0-9._~-]*/)?[a-z0-9~-][a-z0-9._~-]*", name):
        return {"erreur": "nom de paquet npm invalide"}
    d = get_json_or_none(f"https://registry.npmjs.org/{quote(name, safe='@')}/latest")
    if not d:
        return {"erreur": f"{name} n'existe pas sur npm"}
    week = None
    try:
        week = get_json(f"https://api.npmjs.org/downloads/point/last-week/{quote(name, safe='@/')}", timeout=8).get("downloads")
    except Exception:                                                  # the version is still a good answer
        pass
    return {"gestionnaire": "npm", "nom": d["name"], "version": d["version"], "resume": clean(d.get("description"), 200), "licence": d.get("license"),
            "site": d.get("homepage"), "telechargements_semaine": week, "dependances": len(d.get("dependencies") or {})}


def _cvss(cve):
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        rows = (cve.get("metrics") or {}).get(key) or []
        if rows:
            d = rows[0]["cvssData"]
            return {"score": d.get("baseScore"), "gravite": d.get("baseSeverity") or rows[0].get("baseSeverity")}
    return {}


def cve_search(chat_id, a):
    ident, words = text(a, "cve", "", 30).upper(), text(a, "mots", "", 80)
    if ident and not re.fullmatch(r"CVE-\d{4}-\d{4,7}", ident):
        return {"erreur": "format attendu : CVE-AAAA-NNNN"}
    if not ident and not words:
        return {"erreur": "donne un numero CVE ou des mots (ex. apache log4j)"}
    data = get_json("https://services.nvd.nist.gov/rest/json/cves/2.0", timeout=20, **({"cveId": ident} if ident else {"keywordSearch": words, "resultsPerPage": 5}))
    rows = [v["cve"] for v in data.get("vulnerabilities") or []]
    if not rows:
        return {"erreur": "aucune faille trouvee"}
    return {"total": data.get("totalResults"), "failles": [{"id": c["id"], "publiee": c["published"][:10], **_cvss(c),
                                                             "resume": clean(next((d["value"] for d in c["descriptions"] if d["lang"] == "en"), ""), 350),
                                                             "lien": f"https://nvd.nist.gov/vuln/detail/{c['id']}"} for c in rows]}


def dev_news(chat_id, a):
    kind, words = text(a, "type", "front", 8).lower(), text(a, "recherche", "", 80)
    if words:
        data = get_json("https://hn.algolia.com/api/v1/search", query=words, tags="story", hitsPerPage=8)
    else:
        data = get_json("https://hn.algolia.com/api/v1/search_by_date" if kind == "new" else "https://hn.algolia.com/api/v1/search",
                        tags={"new": "story", "ask": "ask_hn", "show": "show_hn"}.get(kind, "front_page"), hitsPerPage=8)
    return {"articles": [{"titre": clean(h.get("title"), 150), "points": h.get("points"), "commentaires": h.get("num_comments"), "lien": h.get("url"),
                          "discussion": f"https://news.ycombinator.com/item?id={h['objectID']}"} for h in data.get("hits", [])]}


def stack_search(chat_id, a):
    site = text(a, "site", "stackoverflow", 40).lower()
    if not re.fullmatch(r"[a-z.]+", site):
        return {"erreur": "nom de site invalide"}
    data = get_json("https://api.stackexchange.com/2.3/search/advanced", q=text(a, "recherche", "", 120), site=site, sort="relevance", order="desc", pagesize=5)
    rows = data.get("items") or []
    if not rows:
        return {"erreur": "aucune question trouvee"}
    return {"questions": [{"titre": clean(r["title"], 160), "score": r["score"], "reponses": r["answer_count"], "repondue": r["is_answered"], "tags": r["tags"][:4],
                           "lien": r["link"]} for r in rows]}


def github_tendances(chat_id, a):
    since = (date.today() - timedelta(days=whole(a, "jours", 7, 1, 90))).isoformat()
    lang = text(a, "langage", "", 30)
    query = f"created:>{since}" + (f" language:{lang}" if re.fullmatch(r"[\w+#.-]+", lang) else "")
    try:
        rows = get_json("https://api.github.com/search/repositories", q=query, sort="stars", order="desc", per_page=whole(a, "nombre", 8, 1, 15)).get("items") or []
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 429):
            return {"erreur": "GitHub limite les recherches sans compte (10 par minute) : reessaie dans une minute"}
        raise
    return {"projets": [{"nom": r["full_name"], "etoiles": r["stargazers_count"], "langage": r.get("language"), "description": clean(r.get("description"), 140), "lien": r["html_url"]} for r in rows],
            "depuis": since}


def arxiv_search(chat_id, a):
    words = re.sub(r"[^\w ]", " ", text(a, "recherche", "", 100)).split()
    if not words:
        return {"erreur": "donne des mots a chercher"}
    r = requests.get("https://export.arxiv.org/api/query", headers=AGENT, timeout=20,
                     params={"search_query": "all:" + "+AND+".join(words), "max_results": 5, "sortBy": "submittedDate" if a.get("recents") is True else "relevance", "sortOrder": "descending"})
    r.raise_for_status()
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
        def tag(t, entry=entry):
            m = re.search(rf"<{t}[^>]*>(.*?)</{t}>", entry, re.S)
            return clean(m.group(1), 600) if m else ""
        out.append({"titre": tag("title"), "auteurs": [clean(x, 60) for x in re.findall(r"<name>(.*?)</name>", entry)[:4]], "date": tag("published")[:10], "resume": tag("summary")[:420], "lien": tag("id")})
    return {"articles": out} if out else {"erreur": "aucun article trouve"}


def ip_info(chat_id, a):
    raw = text(a, "ip", "", 45)
    try:
        ip = ip_address(raw)
    except ValueError:
        return {"erreur": "adresse IP invalide (pour la tienne, utilise my_ip)"}
    if not ip.is_global:
        return {"erreur": "c'est une adresse privee ou speciale : elle n'a pas de lieu sur internet"}
    d = get_json(f"https://ipwho.is/{ip}")
    if not d.get("success"):
        return {"erreur": f"adresse inconnue : {clean(d.get('message'), 80)}"}
    con = d.get("connection") or {}
    return {"ip": d["ip"], "pays": d.get("country"), "region": d.get("region"), "ville": d.get("city"), "operateur": con.get("isp"), "organisation": con.get("org"),
            "asn": con.get("asn"), "fuseau": (d.get("timezone") or {}).get("id"), "latitude": d.get("latitude"), "longitude": d.get("longitude")}


def wayback(chat_id, a):
    url, stamp = text(a, "url", "", 300), re.sub(r"\D", "", text(a, "date", "", 14))[:14]
    if not host_of(url):
        return {"erreur": "donne un site (ex. exemple.fr)"}
    r = requests.get("https://archive.org/wayback/available", params={"url": url, **({"timestamp": stamp} if stamp else {})}, headers=AGENT, timeout=15)
    r.raise_for_status()
    d = r.json()
    snap = (d.get("archived_snapshots") or {}).get("closest")
    if not snap:
        return {"erreur": "aucune copie archivee de ce site"}
    t = snap["timestamp"]
    return {"copie": snap["url"], "date": f"{t[:4]}-{t[4:6]}-{t[6:8]}", "statut_http": snap.get("status")}


def cert_subdomains(chat_id, a):
    host = host_of(text(a, "domaine", "", 100))
    if not host:
        return {"erreur": "donne un domaine (ex. exemple.fr)"}
    r = requests.get("https://crt.sh/", params={"q": f"%.{host}", "output": "json"}, headers=AGENT, timeout=25)
    try:
        rows = r.json()
    except ValueError:
        return {"erreur": "crt.sh est surcharge en ce moment, reessaie dans une minute"}
    names = {n.strip().lstrip("*.").lower() for row in rows for n in str(row.get("name_value", "")).split("\n")}
    names = sorted(n for n in names if n.endswith(host))
    return {"domaine": host, "total": len(names), "sous_domaines": names[:80]}


# ------------------------------------------------------------------ local, exact

CHILD = """
import json, re, sys
d = json.load(sys.stdin)
flags = 0
for f in d["flags"]:
    flags |= {"i": re.I, "m": re.M, "s": re.S}.get(f, 0)
rx = re.compile(d["pattern"], flags)
if d["replace"] is not None:
    print(json.dumps({"remplace": rx.sub(d["replace"], d["text"])[:3000]}))
else:
    found = []
    for m in rx.finditer(d["text"]):
        found.append({"texte": m.group(0)[:200], "debut": m.start(), "groupes": [g[:100] if g else g for g in m.groups()], "nommes": {k: (v[:100] if v else v) for k, v in m.groupdict().items()}})
        if len(found) >= 30:
            break
    print(json.dumps({"correspondances": len(found), "resultats": found}))
"""


def regex_test(chat_id, a):
    """Runs in a child process with a 3-second limit: a pattern like (a+)+$ must not freeze the bot."""
    payload = {"pattern": str(a.get("motif") or "")[:500], "text": str(a.get("texte") or "")[:20000], "flags": [c for c in text(a, "drapeaux", "", 5).lower() if c in "ims"],
               "replace": None if a.get("remplacer") is None else str(a["remplacer"])[:500]}
    if not payload["pattern"]:
        return {"erreur": "donne un motif"}
    try:
        done = subprocess.run([sys.executable, "-I", "-c", CHILD], input=json.dumps(payload), capture_output=True, text=True, timeout=3)
    except subprocess.TimeoutExpired:
        return {"erreur": "motif trop lent (boucle presque infinie) : simplifie-le"}
    if done.returncode != 0:
        return {"erreur": "motif invalide : " + (done.stderr.strip().splitlines() or ["?"])[-1][:150]}
    return json.loads(done.stdout)


def _walk(data, path):
    for key, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
        data = data[int(index)] if index else (data[int(key)] if isinstance(data, list) else data[key])
    return data


def json_outils(chat_id, a):
    op, raw = text(a, "operation", "", 10).lower(), str(a.get("json") or "")[:100000]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"valide": False, "erreur": f"JSON invalide : {e.msg} (ligne {e.lineno}, colonne {e.colno})"}
    if op in ("valider", "validate"):
        return {"valide": True, "type": type(data).__name__, "taille": len(data) if isinstance(data, (list, dict)) else None}
    if op in ("formater", "format"):
        return {"json": json.dumps(data, indent=2, ensure_ascii=False)[:6000]}
    if op in ("minifier", "minify"):
        return {"json": json.dumps(data, separators=(",", ":"), ensure_ascii=False)[:6000]}
    if op == "cles":
        return {"cles": list(data)[:100] if isinstance(data, dict) else f"c'est une {type(data).__name__}"}
    if op == "chemin":
        try:
            return {"valeur": _walk(data, text(a, "chemin", "", 200))}
        except (KeyError, IndexError, ValueError, TypeError):
            return {"erreur": "ce chemin n'existe pas dans le JSON"}
    return {"erreur": "operations : valider, formater, minifier, cles, chemin"}


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _date(value):
    value = str(value or "").strip().lower()
    if value in ("", "aujourd'hui", "aujourdhui", "today"):
        return date.today()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"date illisible : {value[:20]} (ecris AAAA-MM-JJ)")


def _gap(start, end):
    """(years, months, days) between two dates, start <= end."""
    years, months = end.year - start.year, end.month - start.month
    days = end.day - start.day
    if days < 0:
        months -= 1
        days += (end.replace(day=1) - timedelta(days=1)).day
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


def _next_birthday(born, today):
    for year in (today.year, today.year + 1):
        try:
            nxt = born.replace(year=year)
        except ValueError:                                             # born on 29 February
            nxt = date(year, 3, 1)
        if nxt >= today:
            return nxt


def date_calc(chat_id, a):
    op = text(a, "operation", "", 12).lower()
    try:
        d1 = _date(a.get("date"))
        if op == "diff":
            d2 = _date(a.get("date2"))
            lo, hi = sorted((d1, d2))
            y, m, d = _gap(lo, hi)
            return {"jours": (d2 - d1).days, "semaines": f"{abs((d2 - d1).days) // 7} sem {abs((d2 - d1).days) % 7} j", "detail": f"{y} an(s), {m} mois, {d} jour(s)"}
        if op == "ajouter":
            out = d1 + timedelta(days=whole(a, "jours", 0, -100000, 100000))
            return {"date": out.isoformat(), "jour": JOURS[out.weekday()]}
        if op == "semaine":
            iso = d1.isocalendar()
            return {"date": d1.isoformat(), "jour": JOURS[d1.weekday()], "semaine_iso": iso[1], "jour_de_l_annee": d1.timetuple().tm_yday,
                    "jours_restants_annee": (date(d1.year, 12, 31) - d1).days}
        if op == "age":
            today = date.today()
            if d1 > today:
                return {"erreur": "cette date est dans le futur"}
            y, m, d = _gap(d1, today)
            return {"age": f"{y} an(s), {m} mois, {d} jour(s)", "prochain_anniversaire_dans_jours": (_next_birthday(d1, today) - today).days}
        if op == "jours_ouvres":
            d2 = _date(a.get("date2"))
            lo, hi = sorted((d1, d2))
            count = sum(1 for i in range((hi - lo).days) if (lo + timedelta(days=i)).weekday() < 5)
            return {"jours_ouvres": count, "note": "du lundi au vendredi, sans compter les jours feries"}
    except ValueError as e:
        return {"erreur": str(e)}
    return {"erreur": "operations : diff, ajouter, semaine, age, jours_ouvres"}


COLORS = {"rouge": "#ff0000", "vert": "#008000", "bleu": "#0000ff", "jaune": "#ffff00", "orange": "#ffa500", "violet": "#800080", "rose": "#ffc0cb", "noir": "#000000",
          "blanc": "#ffffff", "gris": "#808080", "marron": "#8b4513", "cyan": "#00ffff", "magenta": "#ff00ff", "turquoise": "#40e0d0", "beige": "#f5f5dc", "bordeaux": "#800020"}


def _rgb(value):
    v = str(value or "").strip().lower()
    v = COLORS.get(_ascii(v), v)
    m = re.fullmatch(r"#?([0-9a-f]{6})", v) or re.fullmatch(r"#?([0-9a-f]{3})", v)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", v)
    if m and all(int(x) <= 255 for x in m.groups()):
        return tuple(int(x) for x in m.groups())
    raise ValueError(f"couleur illisible : {v[:20]}")


def _luminance(rgb):
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (x / 255 for x in rgb)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(c1, c2):
    hi, lo = sorted((_luminance(c1), _luminance(c2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def color_info(chat_id, a):
    try:
        rgb = _rgb(a.get("couleur"))
        hue, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        out = {"hex": "#%02x%02x%02x" % rgb, "rgb": f"rgb{rgb}", "hsl": f"hsl({round(hue * 360)}, {round(sat * 100)}%, {round(light * 100)}%)", "luminosite": round(_luminance(rgb), 4),
               "contraste_sur_blanc": round(_contrast(rgb, (255, 255, 255)), 2), "contraste_sur_noir": round(_contrast(rgb, (0, 0, 0)), 2)}
        if a.get("couleur2"):
            ratio = _contrast(rgb, _rgb(a.get("couleur2")))
            out["contraste_entre_les_deux"] = round(ratio, 2)
            out["wcag"] = "AAA" if ratio >= 7 else "AA" if ratio >= 4.5 else "AA (grand texte seulement)" if ratio >= 3 else "insuffisant"
        return out
    except ValueError as e:
        return {"erreur": str(e)}


def _prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d, r = d // 2, r + 1
    for base in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):         # deterministic below 3.3e24
        x = pow(base, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _rho(n):
    if n % 2 == 0:
        return 2
    for c in range(1, 40):
        x = y = 2
        d = 1
        for _ in range(200000):
            x, y = (x * x + c) % n, (((y * y + c) % n) ** 2 + c) % n
            d = math.gcd(abs(x - y), n)
            if d != 1:
                break
        if 1 < d < n:
            return d
    raise ValueError("trop grand a factoriser ici")


def _factors(n):
    out = {}
    for p in (2, 3, 5, 7, 11, 13):
        while n % p == 0:
            out[p], n = out.get(p, 0) + 1, n // p
    stack = [n] if n > 1 else []
    while stack:
        m = stack.pop()
        if _prime(m):
            out[m] = out.get(m, 0) + 1
        else:
            d = _rho(m)
            stack += [d, m // d]
    return dict(sorted(out.items()))


ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def _to_roman(n):
    out = ""
    for v, s in ROMAN:
        out, n = out + s * (n // v), n % v
    return out


def _from_roman(s):
    n, i = 0, 0
    for v, sym in ROMAN:
        while s[i:i + len(sym)] == sym:
            n, i = n + v, i + len(sym)
    if i != len(s) or _to_roman(n) != s:
        raise ValueError("chiffres romains invalides")
    return n


def _to_base(n, base):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    sign, n = ("-" if n < 0 else ""), abs(n)
    out = ""
    while True:
        n, r = divmod(n, base)
        out = digits[r] + out
        if n == 0:
            return sign + out


def _big(n):
    s = str(n)
    return s if len(s) <= 60 else f"{s[:25]}...{s[-25:]} ({len(s)} chiffres)"


def nombres(chat_id, a):
    op, raw, other = text(a, "operation", "", 14).lower(), text(a, "nombre", "", 40).replace(" ", ""), text(a, "autre", "", 40).replace(" ", "")
    try:
        if op == "romain":
            return {"resultat": _from_roman(raw.upper())} if raw.upper().isalpha() else ({"resultat": _to_roman(int(raw))} if 0 < int(raw) < 4000 else {"erreur": "entre 1 et 3999"})
        if op == "base":
            src, dst = whole(a, "base_depart", 10, 2, 36), whole(a, "base_arrivee", 2, 2, 36)
            return {"resultat": _to_base(int(raw, src), dst), "decimal": str(int(raw, src)), "de_base": src, "vers_base": dst}
        if op in ("pourcentage", "evolution"):
            x, y = num(a, "nombre"), num(a, "autre")
            if op == "pourcentage":
                return {"resultat": round(x * y / 100, 10), "calcul": f"{x:g} % de {y:g}"}
            return {"evolution_pct": round((y - x) / x * 100, 4)} if x else {"erreur": "le depart ne peut pas etre 0"}
        n = int(raw)
        if op == "premier":
            return {"premier": _prime(n)} if abs(n) < 10**24 else {"erreur": "nombre trop grand (max 10^24)"}
        if op == "facteurs":
            if not 1 < n < 10**24:
                return {"erreur": "entre 2 et 10^24"}
            f = _factors(n)
            return {"facteurs": {str(p): e for p, e in f.items()}, "ecriture": " x ".join(f"{p}^{e}" if e > 1 else str(p) for p, e in f.items())}
        if op in ("pgcd", "ppcm"):
            m = int(other)
            return {"resultat": math.gcd(n, m) if op == "pgcd" else abs(n * m) // math.gcd(n, m) if n and m else 0}
        if op == "factorielle":
            if not 0 <= n <= 2000:
                return {"erreur": "entre 0 et 2000"}
            f = math.factorial(n)
            return {"resultat": _big(f), "chiffres": len(str(f))}
        if op == "fibonacci":
            if not 0 <= n <= 10000:
                return {"erreur": "entre 0 et 10000"}
            x, y = 0, 1
            for _ in range(n):
                x, y = y, x + y
            return {"resultat": _big(x)}
    except (ValueError, ZeroDivisionError):
        return {"erreur": "valeur invalide pour cette operation"}
    return {"erreur": "operations : premier, facteurs, pgcd, ppcm, base, romain, factorielle, fibonacci, pourcentage, evolution"}


# category -> {symbol: (factor to the base unit, other names)}
UNITS = {
    "longueur": {"m": (1, "metre metres"), "km": (1000, "kilometre kilometres"), "cm": (0.01, "centimetre centimetres"), "mm": (0.001, "millimetre millimetres"),
                 "um": (1e-6, "micron microns micrometre"), "nm": (1e-9, "nanometre"), "mi": (1609.344, "mile miles"), "yd": (0.9144, "yard yards"),
                 "ft": (0.3048, "pied pieds foot feet"), "in": (0.0254, "pouce pouces inch inches"), "nmi": (1852, "millemarin"), "ly": (9460730472580800, "al anneelumiere"),
                 "ua": (149597870700, "au uniteastronomique"), "pc": (3.0856775814913673e16, "parsec parsecs")},
    "masse": {"kg": (1, "kilo kilos kilogramme kilogrammes"), "g": (0.001, "gramme grammes"), "mg": (1e-6, "milligramme milligrammes"), "t": (1000, "tonne tonnes"),
              "lb": (0.45359237, "livre livres pound pounds lbs"), "oz": (0.028349523125, "once onces ounce ounces"), "st": (6.35029318, "stone"), "ct": (0.0002, "carat carats")},
    "volume": {"l": (1, "litre litres liter liters"), "ml": (0.001, "millilitre millilitres"), "cl": (0.01, "centilitre centilitres"), "dl": (0.1, "decilitre decilitres"),
               "m3": (1000, "metrecube metrescubes"), "cm3": (0.001, "centimetrecube"), "gal": (3.785411784, "gallon gallons galus"), "qt": (0.946352946, "quart quarts"),
               "pt": (0.473176473, "pinte pintes pint pints"), "floz": (0.0295735295625, "onceliquide"), "cup": (0.2365882365, "tasse tasses"),
               "cuilleresoupe": (0.01478676478125, "tbsp cas"), "cuillerecafe": (0.00492892159375, "tsp cac"), "baril": (158.987294928, "barril barrel bbl")},
    "vitesse": {"m/s": (1, "mps metreseconde"), "km/h": (1 / 3.6, "kmh kph kilometreheure"), "mph": (0.44704, "milleheure"), "kn": (1852 / 3600, "noeud noeuds knot knots"),
                "mach": (340.29, ""), "lumiere": (299792458, "vitessedelalumiere")},
    "surface": {"m2": (1, "metrecarre metrescarres"), "km2": (1e6, "kilometrecarre"), "cm2": (1e-4, "centimetrecarre"), "ha": (1e4, "hectare hectares"), "are": (100, "ares"),
                "acre": (4046.8564224, "acres"), "ft2": (0.09290304, "piedcarre sqft"), "in2": (0.00064516, "poucecarre sqin"), "mi2": (2589988.110336, "milecarre sqmi")},
    "temps": {"s": (1, "seconde secondes sec"), "ms": (0.001, "milliseconde millisecondes"), "us": (1e-6, "microseconde"), "min": (60, "minute minutes"), "h": (3600, "heure heures"),
              "d": (86400, "jour jours day days"), "sem": (604800, "semaine semaines week weeks"), "mois": (2629800, "month months"), "an": (31557600, "ans annee annees year years")},
    "donnees": {"o": (1, "octet octets byte bytes b"), "ko": (1e3, "kb kilooctet"), "mo": (1e6, "mb megaoctet"), "go": (1e9, "gb gigaoctet"), "to": (1e12, "tb teraoctet"),
                "po": (1e15, "pb petaoctet"), "kio": (1024, "kib"), "mio": (1024**2, "mib"), "gio": (1024**3, "gib"), "tio": (1024**4, "tib"),
                "bit": (0.125, "bits"), "kbit": (125, "kbits"), "mbit": (125000, "mbits"), "gbit": (125000000, "gbits")},
    "energie": {"j": (1, "joule joules"), "kj": (1000, "kilojoule"), "cal": (4.184, "calorie calories"), "kcal": (4184, "kilocalorie kilocalories"), "wh": (3600, ""),
                "kwh": (3.6e6, "kilowattheure"), "mwh": (3.6e9, ""), "ev": (1.602176634e-19, "electronvolt"), "btu": (1055.05585262, "")},
    "pression": {"pa": (1, "pascal"), "kpa": (1000, "kilopascal"), "hpa": (100, "hectopascal mbar millibar"), "bar": (1e5, "bars"), "atm": (101325, "atmosphere"),
                 "psi": (6894.757293168, ""), "mmhg": (133.322387415, "torr")},
    "puissance": {"w": (1, "watt watts"), "kw": (1000, "kilowatt kilowatts"), "mw": (1e6, "megawatt megawatts"), "cv": (735.49875, "ch chevaux chevalvapeur"), "hp": (745.699872, "horsepower")},
    "angle": {"deg": (1, "degre degres degree degrees"), "rad": (180 / math.pi, "radian radians"), "grad": (0.9, "gradian"), "tour": (360, "tours turn")},
}
TEMPERATURE = {"c": "celsius degc degrecelsius degrescelsius", "f": "fahrenheit degf degrefahrenheit degresfahrenheit", "k": "kelvin"}


def _ascii(value):
    return "".join(ch for ch in unicodedata.normalize("NFD", str(value).lower()) if unicodedata.category(ch) != "Mn")


def _key(unit):
    return re.sub(r"[\s°.]", "", _ascii(unit).replace("²", "2").replace("³", "3").replace("µ", "u"))


def _build_index():
    index, clashes = {}, []
    for cat, units in UNITS.items():
        for sym, (_, names) in units.items():
            for n in [sym, *names.split()]:
                k = _key(n)
                if k in index and index[k] != (cat, sym):
                    clashes.append(k)
                index.setdefault(k, (cat, sym))
    for sym, names in TEMPERATURE.items():
        for n in [sym, *names.split()]:
            index.setdefault(_key(n), ("temperature", sym))
    return index, clashes


INDEX, CLASHES = _build_index()


def _unit(word):
    k = _key(word)
    for cand in (k, k.rstrip("s"), k[:-1] if k.endswith("x") else k):
        if cand in INDEX:
            return INDEX[cand]
    return None


def _kelvin(value, sym):
    return {"c": value + 273.15, "f": (value - 32) * 5 / 9 + 273.15, "k": value}[sym]


def unites(chat_id, a):
    value = num(a, "valeur")
    src, dst = _unit(text(a, "de", "", 30)), _unit(text(a, "vers", "", 30))
    if not src or not dst:
        return {"erreur": f"unite inconnue : {text(a, 'de' if not src else 'vers', '', 30)}", "familles": sorted(list(UNITS) + ["temperature"])}
    if src[0] != dst[0]:
        return {"erreur": f"on ne peut pas passer de {src[0]} a {dst[0]}"}
    if src[0] == "temperature":
        kel = _kelvin(value, src[1])
        out = {"c": kel - 273.15, "f": (kel - 273.15) * 9 / 5 + 32, "k": kel}[dst[1]]
    else:
        out = value * UNITS[src[0]][src[1]][0] / UNITS[dst[0]][dst[1]][0]
    return {"resultat": float(f"{out:.10g}"), "calcul": f"{value:g} {src[1]} = {out:.10g} {dst[1]}", "famille": src[0]}


def _table(a):
    """CSV text from the argument or from a received file; (rows, error)."""
    raw = str(a.get("texte") or "")
    if not raw and a.get("fichier"):
        path = find_file(text(a, "fichier", "", 200))
        if not path:
            return None, "fichier introuvable dans les dossiers de travail"
        if os.path.getsize(path) > 5_000_000:
            return None, "fichier trop gros (5 Mo maximum)"
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    if not raw.strip():
        return None, "donne le texte du CSV ou le nom d'un fichier"
    sample = raw[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(raw), dialect))[:200001]
    return (rows, "") if len(rows) >= 2 else (None, "il faut au moins une ligne d'en-tete et une ligne de donnees")


def _stats(values):
    nums = []
    for v in values:
        try:
            nums.append(float(str(v).replace(",", ".")))
        except ValueError:
            pass
    if values and len(nums) >= 0.8 * len([v for v in values if str(v).strip()]) and nums:
        nums.sort()
        mid = len(nums) // 2
        return {"type": "nombre", "min": nums[0], "max": nums[-1], "moyenne": round(sum(nums) / len(nums), 6), "mediane": nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2, "somme": round(sum(nums), 6)}
    freq = {}
    for v in values:
        if str(v).strip():
            freq[v] = freq.get(v, 0) + 1
    return {"type": "texte", "valeurs_differentes": len(freq), "plus_frequentes": [f"{k} ({n})" for k, n in sorted(freq.items(), key=lambda kv: -kv[1])[:5]]}


def csv_outils(chat_id, a):
    rows, err = _table(a)
    if err:
        return {"erreur": err}
    head, body = [h.strip() for h in rows[0]], rows[1:]
    if text(a, "operation", "resume", 10).lower() == "colonne":
        want = text(a, "colonne", "", 80).lower()
        idx = next((i for i, h in enumerate(head) if h.lower() == want), None)
        if idx is None:
            return {"erreur": "colonne introuvable", "colonnes": head}
        return {"colonne": head[idx], "lignes": len(body), **_stats([r[idx] if idx < len(r) else "" for r in body])}
    return {"lignes": len(body), "colonnes": {h: _stats([r[i] if i < len(r) else "" for r in body[:20000]]) for i, h in enumerate(head[:30])}}


MAX_FILES, MAX_BYTES = 5000, 500 * 1024 * 1024


def _safe_target(root, name):
    """The place an archive member would be written, or None when it would leave the folder (zip-slip), is absolute, or hides a secret."""
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or ".." in re.split(r"[\\/]", name):
        return None
    target = os.path.realpath(os.path.join(root, name))
    return target if target == root or target.startswith(root + os.sep) else None


def _copy(src, dst, budget):
    with open(dst, "wb") as out:
        while chunk := src.read(65536):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise ValueError("archive trop grosse une fois ouverte (500 Mo maximum)")
            out.write(chunk)


def _extract(path, root):
    os.makedirs(root, exist_ok=True)
    budget, files = [MAX_BYTES], 0
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                target = _safe_target(root, info.filename)
                if target is None:
                    raise ValueError(f"fichier refuse dans l'archive : {info.filename[:60]}")
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                files += 1
                if files > MAX_FILES:
                    raise ValueError("trop de fichiers dans l'archive (5000 maximum)")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src:
                    _copy(src, target, budget)
        return files
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            for m in tf:
                target = _safe_target(root, m.name)
                if target is None or m.issym() or m.islnk() or m.isdev():
                    raise ValueError(f"element refuse dans l'archive : {m.name[:60]}")
                if m.isdir():
                    os.makedirs(target, exist_ok=True)
                    continue
                files += 1
                if files > MAX_FILES:
                    raise ValueError("trop de fichiers dans l'archive (5000 maximum)")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tf.extractfile(m)
                if src:
                    _copy(src, target, budget)
        return files
    raise ValueError("ce n'est ni un zip ni un tar")


def archive_outils(chat_id, a):
    action, name = text(a, "action", "", 10).lower(), text(a, "fichier", "", 200)
    try:
        if action == "creer":
            folder = next((os.path.join(base, os.path.basename(name)) for base in FOLDERS if os.path.isdir(os.path.join(base, os.path.basename(name)))), "")
            if not folder or system_tools.SECRET_PATH.search(folder):
                return {"erreur": "dossier introuvable dans les dossiers de travail"}
            os.makedirs(WORK, exist_ok=True)
            out = shutil.make_archive(os.path.join(WORK, os.path.basename(folder.rstrip("/"))), "zip", folder)
            return {"archive": out, "taille_ko": os.path.getsize(out) // 1024}
        path = find_file(name)
        if not path:
            return {"erreur": "archive introuvable dans les dossiers de travail"}
        if action == "lister":
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as zf:
                    infos = zf.infolist()
                    names = [(i.filename, i.file_size) for i in infos]
            elif tarfile.is_tarfile(path):
                with tarfile.open(path) as tf:
                    names = [(m.name, m.size) for m in tf]
            else:
                return {"erreur": "ce n'est ni un zip ni un tar"}
            return {"elements": len(names), "liste": [f"{n} ({s // 1024} Ko)" for n, s in names[:60]]}
        if action == "extraire":
            root = os.path.realpath(os.path.join(WORK, "extrait-" + re.sub(r"[^\w.-]", "_", os.path.splitext(os.path.basename(path))[0])[:40]))
            return {"dossier": root, "fichiers": _extract(path, root)}
    except (ValueError, OSError, zipfile.BadZipFile, tarfile.TarError) as e:
        return {"erreur": str(e)[:150]}
    return {"erreur": "actions : lister, extraire, creer"}


FUNCS = {"package_info": package_info, "cve_search": cve_search, "dev_news": dev_news, "stack_search": stack_search, "github_tendances": github_tendances,
         "arxiv_search": arxiv_search, "ip_info": ip_info, "wayback": wayback, "cert_subdomains": cert_subdomains, "regex_test": regex_test, "json_outils": json_outils,
         "date_calc": date_calc, "color_info": color_info, "nombres": nombres, "unites": unites, "csv_outils": csv_outils, "archive_outils": archive_outils}
