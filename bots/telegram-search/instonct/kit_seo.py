"""Free SEO tools: audit one page, find keyword ideas, check where a site ranks. No paid service, no key.

Honest limits: Google's suggestions give ideas but no search volume; the ranking comes from our own search engine, so it is close to Google, not Google.
Everything read from outside is named in TAINT. Heavy modules (llm) are imported inside the function (no import cycle with the catalog).
"""

import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from . import web
from .kit_base import AGENT, clean, host_of, spec, text, whole

SPECS = [
    spec("seo_audit", "Audit SEO gratuit d'une page : titre, description, h1, images, liens, vitesse, robots.txt, sitemap, avec la liste des problemes.", url="string!"),
    spec("seo_idees", "Idees de mots-cles et de questions que les gens tapent sur Google pour un sujet (suggestions gratuites, sans volume).", mot="string!", langue="string"),
    spec("seo_position", "Ou se classe un site dans les resultats pour un mot-cle (10 premiers), et qui est devant lui.", domaine="string!", mot="string!"),
]
GROUPS = [
    (r"\bseo\b|referencement|audit (?:de |du )?(?:mon |ton |le )?(?:site|page)|balise|meta description|\bh1\b|sitemap", {"seo_audit"}),
    (r"mots? ?cles?|keywords?|idees? (?:de|d.)(?:mots|article|contenu|sujet)|que cherchent|requetes|\bseo\b", {"seo_idees"}),
    (r"\bseo\b|(?:position|classe|rang).*(?:google|recherche|resultats)|(?:google|resultats).*(?:position|classe)|premiere page", {"seo_position"}),
]
TAINT = {s["name"] for s in SPECS}
MAX_BYTES, READ_SECONDS = 600_000, 15


class _Page(HTMLParser):
    """Collects what an SEO audit looks at; nothing is executed."""

    def __init__(self, host):
        super().__init__(convert_charrefs=True)
        self.host, self.title, self.og, self.meta, self.canonical, self.lang = host, "", 0, "", "", ""
        self.h1, self.h2, self.words, self.no_alt, self.images = [], 0, 0, 0, 0
        self.inner, self.outer, self.jsonld, self.viewport = 0, 0, False, False
        self._open, self._skip = None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            self.jsonld = self.jsonld or (tag == "script" and "ld+json" in (a.get("type") or ""))
        elif tag == "html":
            self.lang = a.get("lang") or ""
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            if name == "description":
                self.meta = clean(a.get("content"), 400)
            elif name == "viewport":
                self.viewport = True
            elif (a.get("property") or "").startswith("og:"):
                self.og += 1
        elif tag == "link" and "canonical" in (a.get("rel") or ""):
            self.canonical = a.get("href") or ""
        elif tag == "img":
            self.images += 1
            self.no_alt += not (a.get("alt") or "").strip()
        elif tag == "a" and a.get("href"):
            h = host_of(a["href"]) if re.match(r"https?://", a["href"]) else ""
            self.outer += bool(h) and not h.endswith(self.host)
            self.inner += not h or h.endswith(self.host)
        if tag in ("title", "h1", "h2"):
            self._open = tag
            if tag == "h1":
                self.h1.append("")
            self.h2 += tag == "h2"

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == self._open:
            self._open = None

    def handle_data(self, data):
        if self._skip:
            return
        self.words += len(data.split())
        if self._open == "title":
            self.title += data
        elif self._open == "h1" and self.h1:
            self.h1[-1] += data


def _status(url):
    """The status code of a public URL, without reading its body (0 when it cannot be reached or is not public)."""
    try:
        r = web.safe_get(url, timeout=8, stream=True, headers=AGENT)
        r.close()
        return r.status_code
    except (ValueError, requests.RequestException):
        return 0


def _cut(r):
    """Ends a read that is blocked on a slow server. close() alone does not wake a thread waiting in recv (checked against a real dripping socket): shutdown does."""
    for path in (("_connection", "sock"), ("_fp", "fp", "raw", "_sock")):
        try:
            sock = r.raw
            for name in path:
                sock = getattr(sock, name)
            sock.shutdown(socket.SHUT_RDWR)
            break
        except (AttributeError, OSError):
            continue
    r.close()


def _read(url):
    """(response, body, ms) of a public page. Every redirect is checked (web.safe_get), the body is read as it comes with a size and time limit, never decompressed."""
    t0 = time.time()
    r = web.safe_get(url, timeout=15, stream=True, headers={**AGENT, "Accept-Encoding": "identity"})
    cutter = threading.Timer(READ_SECONDS, _cut, (r,))       # a server that drips one byte at a time: closing the connection from outside ends the blocked read
    cutter.start()
    try:
        if (r.headers.get("Content-Encoding") or "identity").lower() != "identity":
            raise ValueError("page compressee refusee")
        body = b""
        for chunk in r.iter_content(8192):
            body += chunk
            if len(body) >= MAX_BYTES or time.time() - t0 > READ_SECONDS:
                break
    finally:
        cutter.cancel()
        r.close()
    return r, body[:MAX_BYTES], int((time.time() - t0) * 1000)


def seo_audit(chat_id, a):
    url = text(a, "url")
    url = url if "://" in url else "https://" + url
    parts = urlparse(url)
    if not parts.hostname or parts.username or parts.password or not web.url_ok(url):
        return {"erreur": "seulement les sites publics"}
    try:
        r, body, ms = _read(url)
    except (ValueError, requests.RequestException) as e:
        return {"erreur": "page illisible (" + type(e).__name__ + ")"}   # never the server's own words: they would reach the model untainted
    final = urlparse(r.final_url)
    host, root = final.hostname, f"{final.scheme}://{final.hostname}"
    page = _Page(host)
    page.feed(body.decode(r.encoding or "utf-8", "replace"))
    title = clean(page.title, 200)
    robots, sitemap = _status(root + "/robots.txt"), _status(root + "/sitemap.xml")
    problems = []
    if not title:
        problems.append("pas de balise title")
    elif not 30 <= len(title) <= 60:
        problems.append(f"title de {len(title)} caracteres (ideal 30 a 60)")
    if not page.meta:
        problems.append("pas de meta description")
    elif not 70 <= len(page.meta) <= 160:
        problems.append(f"meta description de {len(page.meta)} caracteres (ideal 70 a 160)")
    if len(page.h1) != 1:
        problems.append("aucun h1" if not page.h1 else f"{len(page.h1)} h1 (il en faut un seul)")
    if not page.canonical:
        problems.append("pas de lien canonical")
    if page.no_alt:
        problems.append(f"{page.no_alt} image(s) sur {page.images} sans texte alternatif")
    if page.words < 300:
        problems.append(f"seulement {page.words} mots lisibles dans le HTML (page vide pour Google si tout est charge par JavaScript)")
    if not page.viewport:
        problems.append("pas de balise viewport (mobile)")
    if not page.lang:
        problems.append("pas de langue sur la balise html")
    if not page.jsonld:
        problems.append("pas de donnees structurees (JSON-LD)")
    if robots != 200:
        problems.append(f"robots.txt : code {robots}")
    if sitemap != 200:
        problems.append(f"sitemap.xml : code {sitemap}")
    if ms > 1500:
        problems.append(f"page lente depuis le Mac mini ({ms} ms)")
    return {"url": url, "code": r.status_code, "ms": ms, "ko": len(body) // 1000, "title": title, "description": page.meta, "canonical": page.canonical,
            "h1": [clean(x, 100) for x in page.h1[:3]], "nb_h2": page.h2, "mots": page.words, "images": page.images, "liens_internes": page.inner,
            "liens_externes": page.outer, "balises_og": page.og, "robots_txt": robots, "sitemap": sitemap, "problemes": problems or ["rien de grave trouve"]}


def _suggest(query, lang):
    try:
        r = requests.get("https://suggestqueries.google.com/complete/search", params={"client": "firefox", "q": query, "hl": lang}, headers=AGENT, timeout=8)
        data = r.json() if r.status_code == 200 else []
        return [str(x) for x in data[1]] if len(data) > 1 else []
    except (requests.RequestException, ValueError):
        return []


def seo_idees(chat_id, a):
    word = text(a, "mot", "", 80)
    lang = re.sub(r"[^a-z]", "", text(a, "langue", "fr", 5).lower())[:2] or "fr"
    if not word:
        return {"erreur": "il faut un sujet"}
    asks = ("how", "why", "what", "best", "is") if lang == "en" else ("comment", "pourquoi", "quel", "meilleur", "avis")
    queries = [word] + [f"{word} {c}" for c in "abcdefghijklmnoprst"] + [f"{q} {word}" for q in asks]
    with ThreadPoolExecutor(6) as pool:
        batches = list(pool.map(lambda q: _suggest(q, lang), queries))
    seen, ideas = set(), []
    for batch in batches:
        for s in batch:
            if s.lower() not in seen:
                seen.add(s.lower())
                ideas.append(clean(s, 100))
    if not ideas:
        return {"erreur": "Google n'a rien propose (ou ne repond pas), reessaie plus tard"}
    return {"sujet": word, "idees": ideas[:40], "questions": [i for i in ideas if re.match(r"(?:comment|pourquoi|quel|quelle|quels|est.ce|que|qu.est|how|why|what|which|is|can|does|should|where|when|who)\b", i, re.I)][:12],
            "note": "ce sont des idees, sans volume de recherche : l'ordre montre ce que les gens tapent le plus"}


def seo_position(chat_id, a):
    from . import llm                                           # imported here: llm reaches modules that import this one
    host, word = host_of(text(a, "domaine")), text(a, "mot", "", 120)
    if not host or not word:
        return {"erreur": "il faut un domaine (exemple.fr) et un mot-cle"}
    results = llm.web_search(word, n=whole(a, "profondeur", 10, 1, 10), kind="text")
    hosts = [host_of(x.get("href", "")) for x in results]
    place = next((i + 1 for i, h in enumerate(hosts) if h and (h == host or h.endswith("." + host))), None)
    return {"domaine": host, "mot": word, "position": place or "pas dans les 10 premiers", "devant_lui": [h for h in hosts[:(place or 11) - 1] if h][:5],
            "note": "classement de notre moteur de recherche, proche de Google mais pas identique (pas de personnalisation, pas de pays)"}


FUNCS = {"seo_audit": seo_audit, "seo_idees": seo_idees, "seo_position": seo_position}
