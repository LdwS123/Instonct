"""Reads LinkedIn, and only reads. Public job offers need no account; other pages use the session the user opened himself with /connexion linkedin.

The bot never sees a password, never clicks, never hides that it is a bot, and it stops as soon as LinkedIn pushes back (limit, login wall, CAPTCHA):
getting past those is the user's decision, not a thing to work around.
"""

import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import quote, urlsplit

import requests

from . import screen
from .core import db

GUEST = "https://www.linkedin.com/jobs-guest/jobs/api"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
HOURLY = 20                 # pages per hour: slow on purpose, the account belongs to the user
STOP_KEY = "linkedin:stop"
PAGE_CHARS = 6000
_browser = threading.Lock()
_SEARCH = {"personnes": "people", "people": "people", "entreprises": "companies", "companies": "companies", "posts": "content", "content": "content"}
_LINKS = re.compile(r"/(?:in|company|jobs/view|posts|feed/update|school)/")


class Stop(Exception):
    """LinkedIn said no, or our own limit is reached: the message goes back to the user as it is."""


def _spend():
    wait = db.ttl(STOP_KEY)
    if db.exists(STOP_KEY):
        raise Stop(f"LinkedIn a demande de ralentir : je reessaie dans {max(1, wait // 60)} minutes, pas avant.")
    key = f"linkedin:count:{datetime.now():%Y%m%d%H}"
    used = db.incr(key)
    db.expire(key, 3700)
    if used > HOURLY:
        raise Stop(f"limite de {HOURLY} pages LinkedIn par heure atteinte, pour ne pas mettre ton compte en danger. Reessaie dans l'heure.")


def _get(url, params=None):
    _spend()
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=20)
    if r.status_code in (403, 429, 999):
        db.set(STOP_KEY, 1, ex=3600)
        raise Stop(f"LinkedIn refuse pour l'instant (code {r.status_code}) : j'arrete pendant une heure.")
    if r.status_code == 404:
        raise Stop("cette page n'existe pas sur LinkedIn.")
    r.raise_for_status()
    return r.text


def _soup(text):
    from bs4 import BeautifulSoup
    return BeautifulSoup(text, "html.parser")


def _text(node):
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def parse_job_cards(page):
    out = []
    for li in _soup(page).select("li"):
        title = _text(li.select_one(".base-search-card__title"))
        if not title:
            continue
        urn = li.select_one("[data-entity-urn]")
        link = li.select_one("a.base-card__full-link")
        when = li.select_one("time")
        out.append({"id": (urn.get("data-entity-urn", "") if urn else "").rpartition(":")[2], "titre": title,
                    "entreprise": _text(li.select_one(".base-search-card__subtitle")), "lieu": _text(li.select_one(".job-search-card__location")),
                    "date": when.get("datetime", "") if when else "", "lien": (link.get("href", "") if link else "").split("?")[0]})
    return out


def jobs(keywords, location="", days=0, limit=10):
    """Public job offers, ten per page: no account needed."""
    if not str(keywords or "").strip():
        return {"erreur": "dis-moi quel poste chercher"}
    limit = max(1, min(int(limit or 10), 30))
    found = []
    params = {"keywords": str(keywords), "location": str(location or "")}
    if days:
        params["f_TPR"] = f"r{int(days) * 86400}"
    for start in range(0, limit, 10):
        if start:
            time.sleep(1.5)
        cards = parse_job_cards(_get(f"{GUEST}/seeMoreJobPostings/search", {**params, "start": start}))
        found += cards
        if len(cards) < 10:
            break
    return {"offres": found[:limit], "nb": len(found[:limit])}


def job(job_id):
    """Full text of one offer."""
    job_id = re.sub(r"\D", "", str(job_id or "").rstrip("/").rpartition("-")[2])
    if not job_id:
        return {"erreur": "donne l'id de l'offre (champ id de la recherche)"}
    s = _soup(_get(f"{GUEST}/jobPosting/{job_id}"))
    criteria = {_text(i.select_one(".description__job-criteria-subheader")): _text(i.select_one(".description__job-criteria-text"))
                for i in s.select(".description__job-criteria-item")}
    return {"id": job_id, "titre": _text(s.select_one(".top-card-layout__title")), "entreprise": _text(s.select_one(".topcard__org-name-link")),
            "lieu": _text(s.select_one(".topcard__flavor--bullet")), "criteres": criteria, "texte": _text(s.select_one(".show-more-less-html__markup"))[:PAGE_CHARS],
            "lien": f"https://www.linkedin.com/jobs/view/{job_id}"}


def logged_in():
    """Is there a LinkedIn session in the browser profile? Only the cookie's NAME is read, never its value."""
    path = os.path.join(screen.PROFILE, "Default", "Cookies")
    if not os.path.exists(path):
        return False
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=5)
    try:
        return con.execute("SELECT 1 FROM cookies WHERE host_key LIKE '%linkedin.com' AND name='li_at' LIMIT 1").fetchone() is not None
    finally:
        con.close()


def _dump_dom(url):
    """The page as rendered by the same Chromium the user logged in with, without opening any window."""
    chrome = screen._chrome()
    if not chrome:
        raise Stop("Chromium n'est pas installe sur le Mac mini.")
    p = subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", f"--user-data-dir={screen.PROFILE}",
                          "--virtual-time-budget=8000", "--dump-dom", url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)         # Chromium has child processes: leaving one behind would keep the profile locked
        p.communicate()
        raise Stop("la page LinkedIn met trop de temps a s'ouvrir.") from None
    return out.decode("utf-8", "replace")


def read_rendered(dom):
    """Text and useful links of a rendered page. Raises Stop on a login wall or a security check."""
    s = _soup(dom)
    title = _text(s.title)
    if s.select_one("input[name=session_key]") or s.select_one('form[action*="login"]') or re.search(r"\b(?:sign in|s.identifier|connexion)\b", title, re.I):
        raise Stop("ta session LinkedIn n'est plus valide. Fais /connexion linkedin et connecte-toi toi-meme.")
    if s.select_one('form[action*="checkpoint"]') or s.select_one('iframe[src*="captcha"]') or re.search(r"security verification|verification de securite|v.rification de s.curit", title, re.I):
        db.set(STOP_KEY, 1, ex=3600)
        raise Stop("LinkedIn demande une verification de securite. Je ne la contourne pas : fais /connexion linkedin et valide-la toi-meme.")
    links = []
    for a in s.select("a[href]"):
        href = a["href"].split("?")[0]
        if _LINKS.search(href) and href not in links:
            links.append(href)
    for junk in s(["script", "style", "noscript", "svg", "template"]):
        junk.decompose()
    return {"titre": title, "texte": _text(s.body or s)[:PAGE_CHARS], "liens": links[:40]}


def page(url):
    """Reads any linkedin.com page with the user's session."""
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return {"erreur": "je ne lis ici que des pages https de linkedin.com"}
    if not logged_in():
        return {"erreur": "LinkedIn n'est pas connecte. Dis a l'utilisateur de faire /connexion linkedin et de se connecter lui-meme. Les offres publiques marchent sans compte (action jobs)."}
    if screen.active():
        return {"erreur": "l'ecran distant est ouvert et utilise le meme navigateur : ferme-le (/connexion fin) puis redemande."}
    if not _browser.acquire(blocking=False):
        return {"erreur": "une autre page LinkedIn est en cours de lecture, reessaie dans une minute."}
    try:
        _spend()
        return {"lien": url, **read_rendered(_dump_dom(url))}
    finally:
        _browser.release()


def tool(args):
    action = str(args.get("action") or "jobs").lower()
    try:
        if action == "status":
            used = int(db.get(f"linkedin:count:{datetime.now():%Y%m%d%H}") or 0)
            return {"connecte": logged_in(), "pages_cette_heure": used, "limite_par_heure": HOURLY, "en_pause": bool(db.exists(STOP_KEY))}
        if action == "job":
            return job(args.get("id"))
        if action == "page":
            return page(args.get("url"))
        if action == "search":
            kind = _SEARCH.get(str(args.get("kind") or "personnes").lower(), "people")
            return page(f"https://www.linkedin.com/search/results/{kind}/?keywords={quote(str(args.get('keywords') or ''))}")
        if action not in ("jobs", "emplois", "offres"):
            return {"erreur": f"action « {action} » inconnue ici (jobs, job, search, page, status). Pour envoyer des invitations LinkedIn : outil linkedin_inviter (action lancer)."}
        return jobs(args.get("keywords"), args.get("location"), args.get("days") or 0, args.get("limit") or 10)
    except Stop as e:
        return {"erreur": str(e)}
