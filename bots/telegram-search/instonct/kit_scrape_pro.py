"""The heavy scraping kit (crawl_gros, aspirer_js, selecteur_adaptatif): three well-known open-source engines, each used for what it does best.

- Scrapy      : big polite crawls of one site (hundreds of pages), items out as CSV.
- Crawl4AI    : pages built by JavaScript (a real headless Chromium), scrolling, clean Markdown for reading or for an AI.
- Scrapling   : ONLY its parser. It remembers an element by its shape and finds it again after the site was redesigned. Its fetchers and "stealth" modes are NOT used:
                the bot downloads the page itself (public addresses only) and hands the HTML over, so no anti-bot protection is ever bypassed.

The engines live in their own virtualenv (~/scrape-venv) and run as short child processes (instonct/runners/*.py): nothing stays resident, only one heavy job at a time
(the Mac mini has 4.6 GB), the child gets no secrets from the bot (minimal environment), a time limit kills the whole process group.
Rules, as in kit_scrape: public http(s) only (checked again inside the child for every link, redirect and browser request), robots.txt obeyed, no login, no captcha, no forms.
Whatever a page says is TAINT. Exports are CSV/Markdown files in ~/work/scrapes, sent to the chat; a cell starting with = + - @ gets a quote in front.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlparse

from . import kit_scrape, web
from .kit_base import spec, text, whole
from .kit_media import WORK, _send

TAINT = {"crawl_gros", "aspirer_js", "selecteur_adaptatif"}
VENV_PYTHON = os.path.expanduser("~/scrape-venv/bin/python")
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runners")
BUSY = threading.Lock()                                          # one heavy job at a time: RAM
MAX_ROWS = 20000
SAFE_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": os.path.expanduser("~"), "LANG": "C.UTF-8"}   # nothing of the bot's own environment (tokens, keys) is passed on

SPECS = [
    spec("crawl_gros", "Gros crawl d'un site (Scrapy, 300 pages max, robots.txt). item=bloc repete + champs={nom:css ou css@attr} pour extraire. CSV.",
         url="string!", pages="integer", profondeur="integer", motif="string", item="string", champs="string", csv="string"),
    spec("aspirer_js", "Lit un site JavaScript (Crawl4AI, vrai Chromium, 20 pages max) en Markdown. attendre=selecteur, defiler=nb de scrolls, item+champs=extraction.",
         url="string!", pages="integer", profondeur="integer", motif="string", attendre="string", defiler="integer", item="string", champs="string"),
    spec("selecteur_adaptatif", "Scrapling : memorise=true retient un element (CSS) sous un nom, puis le retrouve meme apres une refonte. attribut=href lit un attribut.",
         url="string!", selecteur="string!", nom="string!", memorise="boolean", attribut="string", js="boolean"),
]
GROUPS = [
    (r"scrapy|gros (?:crawl|scraping|scrap)|crawl\w* .*(?:centaines|300|enorme|gros|massif|puissant)|scrape\w* .*(?:centaines|milliers|tout le catalogue|toutes les fiches)|aspire\w* tout le site|"
     r"toutes les fiches|tout le catalogue|(?:centaines|milliers) de pages", {"crawl_gros"}),
    (r"crawl4ai|(?:site|page)s? (?:en |fait en |construit en )?(?:javascript|js|react|vue|angular|dynamiques?)|scroll infini|defile\w* (?:la |cette )?page|en markdown|markdown (?:du|de|des) (?:ce |cette )?(?:site|page)|"
     r"pour (?:une? )?(?:ia|llm|rag)\b", {"aspirer_js"}),
    (r"scrapling|selecteur adaptatif|apres (?:une |la )?refonte|(?:site|page) (?:a|qui a) (?:change|ete refait)|memorise .*(?:element|selecteur|prix|bloc)|retrouve .*meme si .*(?:change|refait)", {"selecteur_adaptatif"}),
]


# ---- running an engine --------------------------------------------------------------------------------------------------------------------------

def _start(a):
    """The start address of a job, or an error text."""
    start = kit_scrape._url(a.get("url"))
    if not start or not web.url_ok(start):
        return "", "il faut l'adresse d'un site public (https://...)"
    return start, ""


def _ready(script):
    if not os.path.exists(VENV_PYTHON) or not os.path.exists(os.path.join(SCRIPTS, script)):
        return "cet outil n'est pas installe sur le serveur (~/scrape-venv manquant)"
    return ""


def _child(script, cfg, seconds):
    """Runs runners/<script> in the scrape virtualenv with `cfg` on stdin. Returns (stdout, stderr, timed_out). The whole process group dies at the limit."""
    cmd = ["nice", "-n", "10", VENV_PYTHON, os.path.join(SCRIPTS, script)]
    child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=SAFE_ENV, cwd=WORK, start_new_session=True)
    try:
        stdout, stderr = child.communicate(json.dumps(cfg) + "\n", timeout=seconds)
        return stdout, stderr, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except OSError:
            pass
        stdout, stderr = child.communicate()
        return stdout or "", stderr or "", True


def _rows(path):
    """The JSON lines the engine wrote (a broken line is skipped; the file may be partial after a time-out)."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                if len(rows) >= MAX_ROWS:
                    break
    except OSError:
        pass
    return rows


def _job(script, cfg, seconds):
    """(rows, summary, note, error) of one heavy job. Only one at a time; the working folder is removed at the end."""
    missing = _ready(script)
    if missing:
        return [], "", "", missing
    if not BUSY.acquire(blocking=False):
        return [], "", "", "un gros travail est deja en cours, reessaie quand il est fini"
    folder = tempfile.mkdtemp(prefix="pro-", dir=WORK)
    try:
        cfg = dict(cfg, out=os.path.join(folder, "out.jsonl"))
        stdout, stderr, timed_out = _child(script, cfg, seconds)
        rows = _rows(cfg["out"])
        summary = (stdout.strip().splitlines() or [""])[-1][:300]
        if not rows and not timed_out:
            reason = (stderr.strip().splitlines() or ["aucun resultat"])[-1][:200]
            return [], summary, "", reason
        return rows, summary, f"arrete apres {seconds} secondes (resultat partiel)" if timed_out else "", ""
    finally:
        BUSY.release()
        shutil.rmtree(folder, ignore_errors=True)


def _flat(row):
    """One CSV line from an engine row: lists and dicts become short JSON text."""
    return {str(k): (json.dumps(v, ensure_ascii=False)[:500] if isinstance(v, (list, dict)) else v) for k, v in row.items()}


def _items(rows):
    """Rows of an `item` extraction (Crawl4AI nests them in row["items"]) as flat lines with the page address."""
    out = []
    for row in rows:
        for item in row.get("items") or []:
            if isinstance(item, dict):
                out.append({"page": row.get("url", ""), **item})
    return out


def _preview(rows, count=3):
    return [{k: (str(v)[:80] if not isinstance(v, (int, float)) else v) for k, v in list(_flat(row).items())[:6]} for row in rows[:count]]


# ---- crawl_gros (Scrapy) ------------------------------------------------------------------------------------------------------------------------

def crawl_gros(chat_id, a):
    start, error = _start(a)
    if error:
        return {"erreur": error}
    fields = kit_scrape._fields(text(a, "champs", "", 1500))
    item = text(a, "item", "", 200)
    if fields is None or bool(fields) != bool(item):
        return {"erreur": "pour extraire des donnees il faut item (le bloc repete) ET champs au format JSON {\"nom\": \"css\"} ou {\"lien\": \"a@href\"}"}
    pattern = text(a, "motif", "", 60)
    cfg = {"url": start, "pages": whole(a, "pages", 60, 1, 300), "depth": whole(a, "profondeur", 3, 0, 5), "follow": re.escape(pattern) if pattern else "", "item": item, "fields": fields, "delay": 0.5}
    rows, summary, note, error = _job("scrapy_run.py", cfg, 270)
    if error:
        return {"erreur": error}
    host = urlparse(start).netloc
    out = {"site": host, "lignes": len(rows), "apercu": _preview(rows)}
    if note:
        out["note"] = note
    out.update(kit_scrape._ship(chat_id, kit_scrape._export(text(a, "csv", "", 50) or "scrapy-" + host, [_flat(r) for r in rows])))
    return out


# ---- aspirer_js (Crawl4AI) ----------------------------------------------------------------------------------------------------------------------

def aspirer_js(chat_id, a):
    start, error = _start(a)
    if error:
        return {"erreur": error}
    fields = kit_scrape._fields(text(a, "champs", "", 1500))
    item = text(a, "item", "", 200)
    if fields is None or bool(fields) != bool(item):
        return {"erreur": "pour extraire des donnees il faut item (le bloc repete) ET champs au format JSON {\"nom\": \"css\"}"}
    pattern = text(a, "motif", "", 60)
    cfg = {"url": start, "pages": whole(a, "pages", 1, 1, 20), "depth": whole(a, "profondeur", 1, 0, 3), "motif": pattern, "wait_for": text(a, "attendre", "", 120),
           "scroll": whole(a, "defiler", 0, 0, 12), "item": item, "fields": fields}
    rows, summary, note, error = _job("crawl4ai_run.py", cfg, 280)
    if error:
        return {"erreur": error}
    host = urlparse(start).netloc
    good = [r for r in rows if r.get("ok")]
    out = {"site": host, "pages_lues": len(good), "pages_en_echec": len(rows) - len(good), "titres": [str(r.get("titre", ""))[:80] for r in good[:5]]}
    if note:
        out["note"] = note
    if item:
        lines = _items(good)
        out["lignes"] = len(lines)
        out["apercu"] = _preview(lines)
        if lines:
            out.update(kit_scrape._ship(chat_id, kit_scrape._export("crawl4ai-" + host, lines)))
        return out
    if not good:
        out["erreur"] = (str(rows[0].get("erreur", "")) if rows else "") or "aucune page lisible"
        return out
    out["apercu"] = " ".join(str(good[0].get("markdown", "")).split())[:1200]
    folder = os.path.join(WORK, "scrapes")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{re.sub(r'[^A-Za-z0-9.-]', '_', host)[:40] or 'site'}-{int(time.time())}.md")
    with open(path, "w", encoding="utf-8") as f:
        for r in good:
            f.write(f"# {r.get('url', '')}\n\n{r.get('markdown', '')}\n\n---\n\n")
    out["fichier"] = os.path.basename(path)
    out["envoye"] = bool(_send(chat_id, path))
    return out


# ---- selecteur_adaptatif (Scrapling parser) -----------------------------------------------------------------------------------------------------

def selecteur_adaptatif(chat_id, a):
    start, error = _start(a)
    if error:
        return {"erreur": error}
    selector, name = text(a, "selecteur", "", 200), re.sub(r"[^\w.-]", "_", text(a, "nom", "", 40))
    if not selector or not name:
        return {"erreur": "il faut selecteur (CSS) et nom (pour le retrouver plus tard)"}
    final, html = kit_scrape._html_page(start, bool(a.get("js")))
    if final is None:
        return {"erreur": str(html)[:150]}
    folder = os.path.join(WORK, "scrapes")
    os.makedirs(folder, exist_ok=True)
    save = bool(a.get("memorise"))
    cfg = {"html": html.decode("utf-8", "ignore"), "url": final, "selector": selector, "name": name, "db": os.path.join(folder, "adaptive.db"), "save": save,
           "attribute": re.sub(r"[^\w:-]", "", text(a, "attribut", "", 30))}
    missing = _ready("scrapling_run.py")
    if missing:
        return {"erreur": missing}
    if not BUSY.acquire(blocking=False):
        return {"erreur": "un gros travail est deja en cours, reessaie quand il est fini"}
    try:
        stdout, stderr, timed_out = _child("scrapling_run.py", cfg, 60)
    finally:
        BUSY.release()
    try:
        data = json.loads((stdout.strip().splitlines() or [""])[-1])
    except ValueError:
        data = None
    if timed_out or not isinstance(data, dict):
        return {"erreur": (stderr.strip().splitlines() or ["Scrapling n'a pas repondu"])[-1][:200]}
    found = [str(x)[:300] for x in data.get("found", [])][:50]
    out = {"page": final, "trouve": found}
    if save:
        out["memorise"] = bool(data.get("saved"))
        if not data.get("saved"):
            out["note"] = "rien trouve avec ce selecteur : rien n'a ete memorise"
    elif found:
        out["retrouve_par_la_forme"] = bool(data.get("adaptive"))
    else:
        out["note"] = "rien trouve, meme avec la memoire (as-tu memorise ce nom sur cette page avant ?)"
    return out


FUNCS = {"crawl_gros": crawl_gros, "aspirer_js": aspirer_js, "selecteur_adaptatif": selecteur_adaptatif}
