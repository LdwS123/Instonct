"""Knowing the world, not only the mailbox: news, deep research, world time, public holidays, interview preparation.

Everything here is free and needs no key. All that comes from a stranger (news titles, pages, mails) marks the conversation as tainted, as the other readers do.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .core import log, scrub
from . import llm, mailindex, meetings, web

NAMES = {"actu", "recherche_approfondie", "heure_monde", "feries", "prepare_entretien"}
AGENT = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Instonct"}
PAGES_READ = 3
PAGE_CHARS = 2500
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def _tag(block, name):
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.S)
    return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""


def parse_news(xml, limit):
    return [{"titre": _tag(b, "title"), "source": _tag(b, "source"), "date": _tag(b, "pubDate"), "lien": _tag(b, "link")} for b in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]]


def news(subject, limit=6):
    """Google News first: it needs no key and gives real dates. DuckDuckGo news if it does not answer."""
    url = f"https://news.google.com/rss/search?q={quote(subject)}&hl=fr&gl=FR&ceid=FR:fr"
    try:
        r = web.safe_get(url, timeout=10, headers=AGENT)
        found = parse_news(r.text, limit) if r.status_code == 200 else []
        if found:
            return found
    except Exception as e:
        log.info("google news : %s", scrub(e)[:100])
    return [{"titre": x.get("title", ""), "source": x.get("source", ""), "date": x.get("date", ""), "lien": x.get("href", "")} for x in llm.web_search(subject, n=limit, kind="news")]


def _actu(args, links):
    subject = str(args.get("sujet") or "").strip()
    if not subject:
        return {"erreur": "donne un sujet"}
    links.append("(page web)")
    found = news(subject, max(1, min(10, int(args.get("limit") or 6))))
    return {"nouvelles": found, "consigne": "Ne donne que ces titres, avec leur date. Ne brode pas sur ce qui n'y est pas."} if found else {"erreur": "aucune nouvelle trouvee, ou la recherche ne repond pas"}


def _read_page(hit):
    text = web.browse(hit.get("href", ""))
    readable = not text.startswith("Page illisible")
    return {"titre": hit.get("title", ""), "lien": hit.get("href", ""), "texte": (text if readable else hit.get("body", ""))[:PAGE_CHARS], "lue": readable}


def _research(args, links):
    question = str(args.get("question") or "").strip()
    if not question:
        return {"erreur": "donne la question"}
    hits = llm.web_search(question, n=6)
    if not hits:
        return {"erreur": "la recherche web ne repond pas"}
    links.append("(page web)")
    with ThreadPoolExecutor(PAGES_READ) as pool:
        pages = list(pool.map(_read_page, hits[:PAGES_READ]))
    return {"sources": pages, "autres_resultats": [{"titre": h.get("title", ""), "lien": h.get("href", "")} for h in hits[PAGES_READ:]],
            "consigne": "Reponds a partir de ces pages et cite le lien de chaque fait. Dis ce qui est sur, ce qui se contredit, et ce que tu n'as pas trouve."}


def _world_time(args):
    city = str(args.get("ville") or "").strip()
    if not city:
        return {"erreur": "donne une ville"}
    r = web.safe_get(f"https://geocoding-api.open-meteo.com/v1/search?name={quote(city)}&count=1&language=fr", timeout=8, headers=AGENT)
    places = (r.json() or {}).get("results") or []
    if not places:
        return {"erreur": f"ville introuvable : {city}"}
    place = places[0]
    now = datetime.now(ZoneInfo(place["timezone"]))
    return {"ville": place.get("name"), "pays": place.get("country"), "heure": f"{JOURS[now.weekday()]} {now:%d/%m %H:%M}", "fuseau": place["timezone"], "decalage_utc": now.strftime("%z")}


def _holidays(args):
    year = int(args.get("annee") or datetime.now().year)
    r = web.safe_get(f"https://calendrier.api.gouv.fr/jours-feries/metropole/{year}.json", timeout=8, headers=AGENT)
    if r.status_code != 200:
        return {"erreur": f"le calendrier officiel n'a pas repondu ({r.status_code})"}
    days = sorted(r.json().items())
    today = f"{datetime.now():%Y-%m-%d}"
    next_one = next((f"{d} : {n}" for d, n in days if d >= today), "")
    return {"annee": year, "jours": [f"{JOURS[datetime.strptime(d, '%Y-%m-%d').weekday()]} {d} : {n}" for d, n in days], "prochain": next_one, "source": "calendrier.api.gouv.fr (metropole)"}


def _prepare(args, links):
    """The four things one looks up before an interview, gathered in one call. A source that fails is said, never filled in."""
    company = str(args.get("entreprise") or "").strip()
    if not company:
        return {"erreur": "donne le nom de l'entreprise"}
    links.append("(email lu)")

    def attempt(fn):
        try:
            return fn()
        except Exception as e:
            return {"erreur": scrub(e)[:120]}
    return {"entreprise": company,
            "rendez_vous": attempt(lambda: meetings.tool({"entreprise": company, "days": 30})),
            "mails": attempt(lambda: mailindex.search(company, limit=6)),
            "presentation": attempt(lambda: [{"titre": h.get("title", ""), "extrait": h.get("body", "")[:300], "lien": h.get("href", "")} for h in llm.web_search(f"{company} entreprise produit clients", n=3)]),
            "actualite": attempt(lambda: news(company, 3)),
            "consigne": "Fais une fiche courte : le rendez-vous (heure et lien viennent du mail), qui il rencontre, ce que fait l'entreprise, 3 actus, 5 questions probables, 3 questions a poser. "
                        "Ne donne une heure ou un lien que s'ils sont ci-dessus. Propose un PDF avec make_document."}


def tool(name, args, links):
    if name == "actu":
        return _actu(args, links)
    if name == "recherche_approfondie":
        return _research(args, links)
    if name == "heure_monde":
        return _world_time(args)
    if name == "feries":
        return _holidays(args)
    return _prepare(args, links)
