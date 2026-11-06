"""The scraper kit: read public web pages as data, not as prose (scraper, crawler, sitemap_lire, capture_page).

Built from light open-source parts already on the Mac mini: requests + BeautifulSoup/lxml (parsing), trafilatura (main text), Lightpanda (~25 MB browser that runs JavaScript),
headless Chromium (screenshots only). Nothing stays running: each call starts a process or a request, works, and ends.

Rules: public http(s) sites only (web.safe_get checks every redirect); a multi-page job obeys robots.txt, waits between requests and has a page and time limit;
no login, no captcha, no forms (that is the `browser` tool, with the user's word). Everything a page says is TAINT: the model reads it as data and never obeys it.
Exports are CSV files in ~/work/scrapes, sent to the chat; a cell that starts with = + - @ gets a quote in front, so a hostile page cannot plant a spreadsheet formula.
"""

import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zlib
from collections import Counter
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import requests

from . import web
from .kit_base import AGENT, host_of, spec, text, whole
from .kit_media import WORK, _send

TAINT = {"scraper", "crawler", "sitemap_lire", "capture_page"}
PAGE_BYTES = 3_000_000
SITEMAP_BYTES = 10_000_000
LIGHTPANDA = web.LIGHTPANDA
CHROMIUM = "chromium-browser"
DELAY = 1.0                                                      # seconds between two requests to the same site
CRAWL_SECONDS = 150
PAGE_MODES = ("texte", "liens", "images", "tableaux", "meta", "contacts", "champs")
SKIP_EXT = re.compile(r"\.(?:jpe?g|png|gif|webp|svg|ico|pdf|zip|gz|rar|7z|mp[34]|avi|mov|css|js|json|xml|woff2?|ttf|exe|dmg|docx?|xlsx?|pptx?)(?:$|\?)", re.I)

SPECS = [
    spec("scraper", "Extrait les donnees d'une page publique. mode : texte, liens, images, tableaux, meta, contacts, champs (selecteur+champs CSS, suivant+pages). csv=nom.",
         url="string!", mode="string", selecteur="string", champs="string", suivant="string", pages="integer", js="boolean", csv="string"),
    spec("crawler", "Parcourt un site (meme domaine, robots.txt respecte) : titres, descriptions, liens casses, pages lentes. Export CSV.", url="string!", pages="integer", motif="string"),
    spec("sitemap_lire", "Lit le sitemap d'un site (robots.txt, sitemap.xml) : combien de pages, lesquelles, dates. Export CSV.", url="string!"),
    spec("capture_page", "Capture d'ecran (png) ou PDF d'une page publique, envoyee dans le chat. format=png|pdf, pleine_page=true pour une page longue.",
         url="string!", format="string", pleine_page="boolean"),
]
GROUPS = [
    (r"scrap|extrais? .*(?:donnees|tableau|liste|prix|emails?|contacts?|liens|images)|recupere .*(?:donnees|emails?|tableau|prix|liens|images|telephones?)|tableaux? (?:de|du|sur) (?:la |cette )?(?:page|site)|"
     r"emails? .*(?:du |de ce |sur le |sur ce )(?:site|page)|(?:telephone|contact)s? .*(?:du |de ce |sur le )(?:site|entreprise)|json-?ld|open ?graph|toutes les pages (?:de|du)|selecteur css|donnees structurees", {"scraper"}),
    (r"crawl|explore .*site|parcours .*site|tout le site|toutes les pages du site|liens? (?:casses?|morts?|brises?)|pages? en 404|audit .*(?:du )?site", {"crawler"}),
    (r"sitemap|plan du site", {"sitemap_lire"}),
    (r"capture d.?ecran|screenshot|photo de (?:la|cette) page|montre.* (?:la|cette) page|pdf de (?:la|cette) page|page en pdf|imprime .*page", {"capture_page"}),
]


# ---- fetching ---------------------------------------------------------------------------------------------------------------------------------

def _url(value):
    value = text({"u": value}, "u", "", 500)
    if re.match(r"https?://", value, re.I):
        return value
    return "https://" + value if "://" not in value and host_of(value) else ""          # ftp://, file://, javascript: ... are not web pages


def _fetch(url, cap=PAGE_BYTES, timeout=15):
    """(response, bytes) for a public page, or (None, error text). Every redirect is checked; the body is cut at `cap`."""
    try:
        r = web.safe_get(url, timeout=timeout, stream=True, headers=AGENT)
    except (ValueError, requests.RequestException) as e:
        return None, str(e)[:120] or "page illisible"
    try:
        chunks, size = [], 0
        for part in r.iter_content(65536):
            chunks.append(part)
            size += len(part)
            if size >= cap:
                break
        return r, b"".join(chunks)[:cap]
    except requests.RequestException as e:
        return None, str(e)[:120] or "lecture interrompue"
    finally:
        r.close()


def _html_page(url, js):
    """(final_url, html bytes) or (None, error). js=True renders the page with Lightpanda (the page's own scripts run)."""
    r, body = _fetch(url)
    if r is None:
        return None, body
    final = r.final_url
    kind = (r.headers.get("content-type") or "").lower()
    if r.status_code >= 400:
        return None, f"le site repond {r.status_code}"
    if kind and not re.search(r"html|xml|text/plain", kind):
        return None, "ce n'est pas une page web (" + kind.split(";")[0][:30] + ")"
    if not js and len(re.sub(r"<[^>]+>|\s+", "", body[:200000].decode("utf-8", "ignore"))) < 300:
        js = True                                                                  # an empty shell: the content is built by scripts
    if js and os.path.exists(LIGHTPANDA):
        try:
            run = subprocess.run(["nice", "-n", "10", LIGHTPANDA, "fetch", "--dump", "html", final], capture_output=True, timeout=45)
            if run.stdout.strip():
                return final, run.stdout[:PAGE_BYTES]
        except (subprocess.TimeoutExpired, OSError):
            pass
    return final, body


def _soup(raw):
    from bs4 import BeautifulSoup
    return BeautifulSoup(raw, "lxml")


def _robots(url):
    """A robots.txt parser for the site of `url`, or None when the site has none (no rule = allowed). A server error means: do not crawl."""
    parts = urlparse(url)
    r, body = _fetch(f"{parts.scheme}://{parts.netloc}/robots.txt", cap=300_000, timeout=8)
    parser = robotparser.RobotFileParser()
    if r is None:
        return None
    if r.status_code >= 500:
        parser.disallow_all = True
        return parser
    if r.status_code >= 400:
        return None
    parser.parse(body.decode("utf-8", "ignore").splitlines())
    return parser


def _allowed(parser, url):
    return parser is None or parser.can_fetch("Instonct", url)


def _same_site(a, b):
    strip = lambda u: (urlparse(u).hostname or "").lower().removeprefix("www.")
    return strip(a) == strip(b)


# ---- CSV --------------------------------------------------------------------------------------------------------------------------------------

def _cell(value):
    value = value if isinstance(value, (int, float)) else str(value if value is not None else "")
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _export(name, rows):
    """Write rows (list of dicts) to ~/work/scrapes/<name>-<time>.csv and send it. Returns the answer fields."""
    folder = os.path.join(WORK, "scrapes")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", name).removesuffix(".csv").strip("._")[:50] or "export"
    path = os.path.join(folder, f"{safe}-{int(time.time())}.csv")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: _cell(v) for k, v in row.items()} for row in rows)
    return {"fichier": os.path.basename(path), "lignes": len(rows), "envoye": False, "_path": path}


def _ship(chat_id, out):
    path = out.pop("_path", "")
    if path:
        out["envoye"] = bool(_send(chat_id, path))
    return out


# ---- scraper ----------------------------------------------------------------------------------------------------------------------------------

EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,60}@[A-Za-z0-9-]{1,60}(?:\.[A-Za-z0-9-]{1,60})*\.[A-Za-z]{2,10}")
PHONE = re.compile(r"(?<![\d.])(?:\+|00)\d[\d .()-]{7,16}\d|(?<![\d.+])0\d(?:[ .-]?\d{2}){4}(?![\d])")
SOCIALS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com", "github.com", "tiktok.com", "t.me", "wa.me")
FILE_LIKE = re.compile(r"\.(?:png|jpe?g|gif|webp|svg|css|js|woff2?)$|@\d?x\b", re.I)


def _links(soup, base):
    seen, out = set(), []
    for tag in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base, tag["href"].strip()))[0]
        if not re.match(r"https?://", href) or href in seen:
            continue
        seen.add(href)
        out.append({"lien": href[:200], "texte": tag.get_text(" ", strip=True)[:80], "interne": _same_site(href, base)})
    return out


def _mode_meta(soup, base):
    def meta(**attrs):
        tag = soup.find("meta", attrs=attrs)
        return (tag.get("content") or "").strip()[:200] if tag else ""
    canonical = soup.find("link", rel="canonical")
    out = {"titre": (soup.title.get_text(" ", strip=True) if soup.title else "")[:200], "description": meta(name="description"), "robots": meta(name="robots"),
           "langue": (soup.html.get("lang") or "")[:10] if soup.html else "", "canonique": (canonical.get("href") or "")[:200] if canonical else "",
           "h1": [h.get_text(" ", strip=True)[:120] for h in soup.find_all("h1")][:5], "nb_h2": len(soup.find_all("h2")),
           "open_graph": {t["property"][3:]: (t.get("content") or "")[:150] for t in soup.find_all("meta", property=re.compile(r"^og:")) if t.get("property")},
           "hreflang": len(soup.find_all("link", hreflang=True))}
    blocks = []
    for script in soup.find_all("script", type="application/ld+json")[:4]:
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else [])[:5]:
            if isinstance(item, dict):
                kept = {k: str(v)[:100] for k, v in item.items() if k in ("@type", "name", "headline", "description", "price", "priceCurrency", "ratingValue", "telephone", "email", "url") and not isinstance(v, (dict, list))}
                if item.get("@type") and "@type" not in kept:
                    kept["@type"] = str(item["@type"])[:60]
                if kept:
                    blocks.append(kept)
    out["donnees_structurees"] = blocks[:8]
    return {k: v for k, v in out.items() if v not in ("", [], {}, 0)}


def _contacts_in(soup, base):
    html_text = soup.get_text(" ", strip=True)
    emails = {m.lower() for m in EMAIL.findall(html_text) if not FILE_LIKE.search(m)}
    emails |= {a["href"][7:].split("?")[0].strip().lower() for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)) if EMAIL.fullmatch(a["href"][7:].split("?")[0].strip())}
    phones = {re.sub(r"\s+", " ", a["href"][4:]).strip() for a in soup.find_all("a", href=re.compile(r"^tel:", re.I))}
    phones |= {p.strip() for p in PHONE.findall(html_text) if 9 <= len(re.sub(r"\D", "", p)) <= 15}
    socials = sorted({link["lien"].split("?")[0] for link in _links(soup, base) if not link["interne"] and any(s in urlparse(link["lien"]).netloc for s in SOCIALS)})
    return sorted(emails)[:20], sorted(phones)[:10], socials[:12]


def _mode_contacts(soup, base, js):
    emails, phones, socials = _contacts_in(soup, base)
    asked = None
    if not emails:                                                              # often only the contact page has the address: look at one such page of the same site
        for link in _links(soup, base):
            if link["interne"] and re.search(r"contact|a-propos|about|mentions", link["lien"] + " " + link["texte"], re.I):
                final, raw = _html_page(link["lien"], js)
                if final and _same_site(final, base):
                    more = _contacts_in(_soup(raw), final)
                    emails, phones, socials, asked = sorted(set(emails) | set(more[0]))[:20], sorted(set(phones) | set(more[1]))[:10], sorted(set(socials) | set(more[2]))[:12], final
                break
    out = {"emails": emails, "telephones": phones, "reseaux": socials, "note": "seulement ce qui est affiche publiquement sur le site"}
    if asked:
        out["aussi_lu"] = asked
    if not (emails or phones or socials):
        out["resultat"] = "aucun contact trouve sur cette page"
    return out


def _tables(soup):
    out = []
    for table in soup.find_all("table")[:6]:
        rows = [[c.get_text(" ", strip=True)[:80] for c in tr.find_all(["th", "td"])] for tr in table.find_all("tr")[:300]]
        rows = [r for r in rows if any(r)]
        if len(rows) >= 2:
            out.append(rows)
    return out


def _fields(raw):
    """The `champs` argument: {"nom": "css"} or {"nom": "css@attribut"}; None when it is not that."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not data or len(data) > 12 or not all(isinstance(v, str) for v in data.values()):
        return None
    return {str(k)[:40]: v[:200] for k, v in data.items()}


def _pick(node, rule, base):
    css, _, attr = rule.partition("@")
    target = node.select_one(css) if css.strip() else node
    if target is None:
        return ""
    if attr:
        value = target.get(attr, "")
        value = " ".join(value) if isinstance(value, list) else str(value)
        return urljoin(base, value)[:300] if attr in ("href", "src") else value[:300]
    return target.get_text(" ", strip=True)[:300]


def _mode_fields(soup, base, a, fields, js, chat_id):
    rule = text(a, "selecteur", "", 200)
    if not rule:
        return {"erreur": "mode champs : il faut selecteur (la repetition CSS, ex: .produit) et champs (ex: {\"titre\":\"h2\",\"prix\":\".prix\",\"lien\":\"a@href\"})"}
    pages = whole(a, "pages", 1, 1, 10)
    follow = text(a, "suivant", "", 200)
    parser, rows, visited, url = (_robots(base) if pages > 1 else None), [], set(), base
    for n in range(pages):
        if n:
            time.sleep(DELAY)
            final, raw = _html_page(url, js)
            if not final or not _same_site(final, base):
                break
            soup, base = _soup(raw), final
        visited.add(base)
        try:
            items = soup.select(rule)[:300]
        except Exception:                                                        # bs4/soupsieve raise several kinds of errors on a bad selector
            return {"erreur": "selecteur CSS invalide : " + rule}
        for item in items:
            if fields:
                try:
                    row = {name: _pick(item, css, base) for name, css in fields.items()}
                except Exception:
                    return {"erreur": "un selecteur de champs est invalide"}
            else:
                first = item if item.name == "a" else item.find("a", href=True)
                row = {"texte": item.get_text(" ", strip=True)[:300], "lien": urljoin(base, first["href"])[:300] if first and first.get("href") else ""}
            if any(row.values()):
                row["page"] = base
                rows.append(row)
        if len(rows) >= 500 or not follow:
            break
        try:
            nxt = soup.select_one(follow)
        except Exception:
            return {"erreur": "selecteur de page suivante invalide"}
        nxt_url = urldefrag(urljoin(base, nxt["href"]))[0] if nxt is not None and nxt.get("href") else ""
        if not nxt_url or nxt_url in visited or not _same_site(nxt_url, base) or not _allowed(parser, nxt_url):
            break
        url = nxt_url
    if not rows:
        return {"resultat": "rien trouve avec ce selecteur (la page est peut-etre construite par JavaScript : js=true)", "selecteur": rule}
    out = {"lignes": len(rows), "pages_lues": len(visited), "apercu": rows[:12]}
    if text(a, "csv", "", 50):
        out.update(_ship(chat_id, _export(a["csv"], rows)))
    return out


def scraper(chat_id, a):
    url = _url(a.get("url"))
    mode = text(a, "mode", "texte", 12).lower()
    if not url:
        return {"erreur": "il faut une adresse de site (https://...)"}
    if mode not in PAGE_MODES:
        return {"erreur": "mode : " + ", ".join(PAGE_MODES)}
    fields = _fields(text(a, "champs", "", 1500))
    if fields is None:
        return {"erreur": "champs doit etre un JSON : {\"nom\": \"selecteur css\", \"lien\": \"a@href\"}"}
    js = a.get("js") in (True, "true", "True", 1, "1")
    final, raw = _html_page(url, js)
    if not final:
        return {"erreur": raw}
    soup, ask_csv = _soup(raw), text(a, "csv", "", 50)
    if mode == "texte":
        try:
            import trafilatura
            body = trafilatura.extract(raw, include_tables=True, include_links=False) or ""
        except Exception:
            body = ""
        body = body or re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        return {"url": final, "caracteres": len(body), "texte": body[:6000], **({"suite": "texte coupe : demande un selecteur precis"} if len(body) > 6000 else {})}
    if mode == "meta":
        return {"url": final, **_mode_meta(soup, final)}
    if mode == "contacts":
        return {"url": final, **_mode_contacts(soup, final, js)}
    if mode == "champs":
        return {"url": final, **_mode_fields(soup, final, a, fields, js, chat_id)}
    if mode == "liens":
        links = _links(soup, final)
        out = {"url": final, "total": len(links), "internes": sum(1 for x in links if x["interne"]), "liens": links[:60]}
        rows = links
    elif mode == "images":
        rows = [{"image": urljoin(final, t["src"])[:300], "alt": (t.get("alt") or "")[:100]} for t in soup.find_all("img", src=True) if not t["src"].startswith("data:")][:300]
        out = {"url": final, "total": len(rows), "images": rows[:40]}
    else:
        tables = _tables(soup)
        if not tables:
            return {"url": final, "resultat": "aucun tableau sur cette page (essaie js=true, ou le mode champs)"}
        best = max(tables, key=len)
        header, body_rows = best[0], best[1:]
        rows = [dict(zip((h or f"col{i + 1}" for i, h in enumerate(header)), r)) if len(r) <= len(header) else {f"col{i + 1}": v for i, v in enumerate(r)} for r in body_rows]
        out = {"url": final, "nb_tableaux": len(tables), "colonnes": header[:15], "lignes": len(rows), "apercu": best[:12]}
    if ask_csv and rows:
        out.update(_ship(chat_id, _export(ask_csv, rows)))
    return out


# ---- crawler ----------------------------------------------------------------------------------------------------------------------------------

def _canon(url):
    url = urldefrag(url)[0]
    parts = urlparse(url)
    return parts._replace(netloc=parts.netloc.lower(), path=parts.path or "/").geturl()


def crawler(chat_id, a):
    start = _url(a.get("url"))
    if not start or not web.url_ok(start):
        return {"erreur": "il faut l'adresse d'un site public (https://...)"}
    limit, pattern = whole(a, "pages", 20, 1, 40), text(a, "motif", "", 60).lower()
    parser = _robots(start)
    queue, seen, rows, parent = [(_canon(start), 0)], {_canon(start)}, [], {}
    deadline = time.time() + CRAWL_SECONDS
    while queue and len(rows) < limit and time.time() < deadline:
        url, depth = queue.pop(0)
        if not _allowed(parser, url):
            rows.append({"url": url, "profondeur": depth, "statut": "interdit par robots.txt"})
            continue
        if rows:
            time.sleep(DELAY)
        began = time.time()
        r, body = _fetch(url, timeout=12)
        row = {"url": url, "profondeur": depth, "statut": "", "titre": "", "h1": "", "description": "", "mots": 0, "liens_internes": 0, "ms": int((time.time() - began) * 1000)}
        if r is None:
            row["statut"] = "erreur : " + str(body)[:60]
            rows.append(row)
            continue
        row["statut"] = r.status_code
        final, kind = r.final_url, (r.headers.get("content-type") or "").lower()
        if not _same_site(final, start):
            row["statut"] = f"{r.status_code} -> autre site"
        elif r.status_code < 400 and "html" in kind:
            soup = _soup(body)
            tag = soup.find("meta", attrs={"name": "description"})
            row.update(titre=(soup.title.get_text(" ", strip=True) if soup.title else "")[:150], h1=(soup.h1.get_text(" ", strip=True) if soup.h1 else "")[:120],
                       description=((tag.get("content") or "") if tag else "")[:200], mots=len(soup.get_text(" ", strip=True).split()))
            inner = [x["lien"] for x in _links(soup, final) if x["interne"] and not SKIP_EXT.search(x["lien"]) and (not pattern or pattern in x["lien"].lower())]
            row["liens_internes"] = len(inner)
            for link in inner:
                key = _canon(link)
                if key not in seen and len(seen) < 2000:
                    seen.add(key)
                    queue.append((key, depth + 1))
                    parent.setdefault(key, url)
        rows.append(row)
    done = [r for r in rows if isinstance(r["statut"], int)]
    broken = [{"url": r["url"], "statut": r["statut"], "trouve_sur": parent.get(r["url"], "")} for r in done if r["statut"] >= 400][:12]
    titles = Counter(r["titre"] for r in done if r.get("titre"))
    out = {"site": urlparse(start).netloc, "pages_lues": len(rows), "restent_a_lire": len(queue), "liens_casses": broken,
           "sans_titre": sum(1 for r in done if r["statut"] < 400 and "titre" in r and not r["titre"]), "sans_description": sum(1 for r in done if r["statut"] < 400 and "description" in r and not r["description"]),
           "titres_en_double": sum(1 for n in titles.values() if n > 1), "plus_lentes": [{"url": r["url"], "ms": r["ms"]} for r in sorted(done, key=lambda r: -r["ms"])[:3]],
           "interdit_par_robots": sum(1 for r in rows if r["statut"] == "interdit par robots.txt")}
    if time.time() >= deadline:
        out["note"] = f"arrete apres {CRAWL_SECONDS} secondes"
    out.update(_ship(chat_id, _export("crawl-" + urlparse(start).netloc, rows)))
    return {k: v for k, v in out.items() if v not in ([], 0, "")}


# ---- sitemap_lire -----------------------------------------------------------------------------------------------------------------------------

def _xml(raw):
    from lxml import etree
    if raw[:2] == b"\x1f\x8b":                                                   # .gz : unpack with a ceiling, so a "zip bomb" cannot fill the memory
        raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, 20_000_000)
    return etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False))


def _locs(root, tag):
    out = []
    for item in root.xpath(f"//*[local-name()='{tag}']"):
        loc = item.xpath("*[local-name()='loc']/text()")
        stamp = item.xpath("*[local-name()='lastmod']/text()")
        if loc:
            out.append({"url": loc[0].strip()[:300], "modifie": (stamp[0].strip() if stamp else "")[:25]})
    return out


def sitemap_lire(chat_id, a):
    start = _url(a.get("url"))
    if not start or not web.url_ok(start):
        return {"erreur": "il faut l'adresse d'un site public"}
    parts = urlparse(start)
    root_url = f"{parts.scheme}://{parts.netloc}"
    found = []
    if parts.path.lower().endswith((".xml", ".gz")):
        found = [start]
    else:
        r, body = _fetch(root_url + "/robots.txt", cap=300_000, timeout=8)
        if r is not None and r.status_code < 400:
            found = [m.strip() for m in re.findall(r"(?im)^\s*sitemap:\s*(\S+)", body.decode("utf-8", "ignore"))][:5]
        found = found or [root_url + "/sitemap.xml", root_url + "/sitemap_index.xml"]
    queue, done, urls, tried = list(found), set(), [], []
    while queue and len(done) < 8 and len(urls) < 5000:
        sm = queue.pop(0)
        if sm in done or not _same_site(sm, start):
            continue
        done.add(sm)
        r, body = _fetch(sm, cap=SITEMAP_BYTES, timeout=20)
        if r is None or r.status_code >= 400:
            tried.append(sm)
            continue
        try:
            root = _xml(body)
        except Exception:
            tried.append(sm)
            continue
        queue += [x["url"] for x in _locs(root, "sitemap")][:10]
        urls += [x for x in _locs(root, "url") if _same_site(x["url"], start)]
    if not urls:
        return {"resultat": "aucun sitemap lisible sur ce site", "essaye": (tried or found)[:4]}
    cut = len(urls) >= 5000
    urls = urls[:5000]
    by_part = Counter((urlparse(x["url"]).path.strip("/").split("/")[0] or "(accueil)")[:30] for x in urls)
    newest = sorted((x for x in urls if x["modifie"]), key=lambda x: x["modifie"], reverse=True)[:5]
    out = {"site": parts.netloc, "sitemaps_lus": len(done) - len(tried), "pages": len(urls), "rubriques": dict(by_part.most_common(8)), "dernieres_modifiees": newest,
           "exemples": [x["url"] for x in urls[:10]], **({"note": "liste coupee a 5000 pages"} if cut else {})}
    out.update(_ship(chat_id, _export("sitemap-" + parts.netloc, urls)))
    return out


# ---- capture_page -----------------------------------------------------------------------------------------------------------------------------

def capture_page(chat_id, a):
    url = _url(a.get("url"))
    kind = "pdf" if text(a, "format", "png", 5).lower() == "pdf" else "png"
    if not url:
        return {"erreur": "il faut une adresse de site (https://...)"}
    r, body = _fetch(url, cap=1024, timeout=15)                                 # checks the address and every redirect; Chromium then gets only the final public one
    if r is None:
        return {"erreur": "page inaccessible : " + str(body)[:100]}
    final = r.final_url
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, f"page-{re.sub(r'[^a-z0-9]+', '-', (urlparse(final).hostname or 'site'))[:40]}-{int(time.time())}.{kind}")
    profile = tempfile.mkdtemp(prefix="cap-", dir=WORK)                          # a throwaway profile: never the logged-in one of the real screen
    tall = a.get("pleine_page") in (True, "true", "True", 1, "1")
    cmd = ["nice", "-n", "10", CHROMIUM, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--disable-extensions",
           f"--user-data-dir={profile}", "--virtual-time-budget=6000", f"--window-size=1280,{3000 if tall else 900}"]
    cmd += ["--print-to-pdf=" + out, "--no-pdf-header-footer"] if kind == "pdf" else ["--screenshot=" + out]
    try:
        subprocess.run(cmd + [final], capture_output=True, timeout=90)
    except (subprocess.TimeoutExpired, OSError):
        pass
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not os.path.isfile(out) or not os.path.getsize(out):
        return {"erreur": "capture impossible (page trop lente ou bloquee)"}
    return {"fichier": os.path.basename(out), "ko": os.path.getsize(out) // 1024, "envoye": bool(_send(chat_id, out)), "page": final}


FUNCS = {"scraper": scraper, "crawler": crawler, "sitemap_lire": sitemap_lire, "capture_page": capture_page}
