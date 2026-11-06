"""Open-source tools from Docker's MCP catalogue, reachable by words (see mcp_host.py for how they are run and locked down).

Three tools: mcp_serveurs (what exists, what really works), mcp_outils (the tools of one server) and mcp_appeler (use one).
Honesty is built in: of the ~250 servers of the catalogue only those I started and called for real are `ok`; the others are listed
with the reason they cannot be used (they ask for an account or a key, which the bot never handles, nothing is paid; or they need local files).
The tool lists of the usable servers are stored, reviewed, in mcp_catalog.json: listing costs no container and no web text reaches the model.
What a server answers is web content: mcp_appeler is TAINT, and a server that is not read-only (`sur` false) is refused once the turn has read the web.
"""

import json
import re

from . import mcp_host
from .core import norm
from .kit_base import spec, text

TAINT = {"mcp_appeler"}
TAINT_ALWAYS = {"mcp_appeler"}          # even a failed call: error messages carry text written by the server (kits.tool)
MAX_FREE_TEXT = 300                     # after the turn read the web, the arguments together may not carry more than this (data could leave through them)
GROUPS = [
    (r"\bmcp\b|outils? open ?source|serveurs? mcp|wikipedia|youtube.*(?:transcri|sous.?titre)|(?:transcri|sous.?titre).*youtube|arxiv|pubmed|biorxiv|hacker ?news|airbnb|"
     r"google flights|\bvols?\b.*(?:prix|pas cher|google|aeroport)|minecraft|swagger|openapi|\bnpm\b|\bcve\b|\bnvd\b|terraform|sequentialthinking|"
     r"raisonne.*etape|etape par etape|duckduckgo",
     {"mcp_serveurs", "mcp_outils", "mcp_appeler"}),
]
SPECS = [
    spec("mcp_serveurs", "Catalogue d'outils open source (MCP) : Wikipedia, arXiv, Airbnb, vols, Hacker News, YouTube, npm, CVE... Cherche par mot.", recherche="string"),
    spec("mcp_outils", "Liste les outils d'un serveur MCP (nom, role, arguments). A faire avant mcp_appeler.", serveur="string!"),
    spec("mcp_appeler", "Utilise un outil d'un serveur MCP. arguments = objet JSON ecrit en texte, ex {\"query\":\"paris\"}.", serveur="string!", outil="string!", arguments="string"),
]
WHY = {"compte": "demande un compte, une cle ou un service que je n'ai pas (je ne gere jamais de mot de passe ni de cle, rien de payant)",
       "autre": "demande tes dossiers ou un service local : pas branche",
       "essai": "branche mais pas encore teste pour de vrai",
       "echec": "essaye pour de vrai : ne marche pas (Mac mini trop ancien ou trop lourd, ou le site refuse les robots)"}
MAX_ARGS = 6000
MAX_TEXT = 3500


def _words(value):
    return set(re.findall(r"[a-z0-9]{3,}", norm(str(value))))


def _score(entry, wanted):
    hay = _words(" ".join(str(entry.get(k, "")) for k in ("id", "nom", "desc", "sert_a", "mots")))
    return sum(1 for w in wanted if w in hay or any(h.startswith(w[:5]) for h in hay if len(w) >= 5))


def match(need, limit=3):
    """The usable servers that fit a need (used by chercher_outil to point at them)."""
    wanted = _words(need)
    scored = sorted(((_score(e, wanted), e["id"]) for e in mcp_host.entries().values() if e.get("etat") == "ok"), key=lambda x: (-x[0], x[1]))
    return [{"id": sid, "sert_a": mcp_host.entries()[sid].get("sert_a", "")} for sc, sid in scored[:limit] if sc > 0]


def mcp_serveurs(chat_id, a):
    every = mcp_host.entries()
    wanted = _words(text(a, "recherche", "", 120))
    ok = [e for e in every.values() if e.get("etat") == "ok"]
    counts = {k: sum(1 for e in every.values() if e.get("etat") == k) for k in ("compte", "autre", "essai", "echec")}
    if not wanted:
        return {"utilisables": [{"id": e["id"], "sert_a": e.get("sert_a", e["desc"])} for e in ok],
                "autres": f"{counts['compte']} demandent un compte ou une cle, {counts['autre']} demandent des dossiers ou un service local : cherche par mot pour les voir",
                "suite": "mcp_outils(serveur) puis mcp_appeler(serveur, outil, arguments)"}
    ranked = sorted(((_score(e, wanted), e["id"]) for e in every.values()), key=lambda x: (-x[0], x[1]))
    found = []
    for sc, sid in ranked[:8]:
        if sc <= 0:
            break
        e = every[sid]
        found.append({"id": sid, "sert_a": e.get("sert_a", e["desc"][:100]), **({} if e.get("etat") == "ok" else {"inutilisable": WHY[e["etat"]]})})
    if not found:
        return {"erreur": "aucun serveur MCP ne correspond : essaie web_search, fetch_url ou browser"}
    return {"serveurs": found, "suite": "mcp_outils(serveur) puis mcp_appeler"}


def _entry(a):
    sid = text(a, "serveur", "", 60).lower()
    entry = mcp_host.entries().get(sid)
    if not entry:
        return None, {"erreur": f"serveur MCP inconnu : {sid or '?'}. Appelle mcp_serveurs pour voir la liste."}
    if entry.get("etat") != "ok":
        return None, {"erreur": f"{sid} n'est pas utilisable : {WHY.get(entry.get('etat'), 'pas branche')}"}
    return entry, None


def mcp_outils(chat_id, a):
    entry, bad = _entry(a)
    if bad:
        return bad
    return {"serveur": entry["id"], "outils": entry.get("outils", []), "suite": "mcp_appeler(serveur, outil, arguments en JSON)"}


def read_only(args):
    """True for a server that only reads public information (kits.tool refuses the others once the turn has read the web)."""
    entry = mcp_host.entries().get(text(args if isinstance(args, dict) else {}, "serveur", "", 60).lower())
    return bool(entry and entry.get("sur"))


def leaky(args):
    """True when, after the web was read, the arguments could carry stolen data out (too long altogether)."""
    entry = mcp_host.entries().get(text(args if isinstance(args, dict) else {}, "serveur", "", 60).lower()) or {}
    if entry.get("hors_ligne"):
        return False
    value, bad = _arguments(args if isinstance(args, dict) else {})
    if bad:
        return True

    return len(json.dumps(value, ensure_ascii=False)) > MAX_FREE_TEXT                 # the whole payload, keys included, not each string



def _arguments(a):
    raw = a.get("arguments")
    if raw in (None, ""):
        return {}, None
    if isinstance(raw, dict):
        value = raw
    else:
        try:
            value = json.loads(str(raw))
        except ValueError:
            return None, {"erreur": 'arguments : ecris un objet JSON valide, ex {"query":"paris"}'}
    if not isinstance(value, dict) or len(json.dumps(value)) > MAX_ARGS:
        return None, {"erreur": "arguments : un objet JSON de moins de 6000 caracteres"}
    return value, None


def _answer(result):
    parts = []
    for c in result.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(str(c.get("text", "")))
        elif isinstance(c, dict):
            parts.append(f"[{c.get('type', 'contenu')} non affiche]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    return "\n".join(parts).strip()


def mcp_appeler(chat_id, a):
    entry, bad = _entry(a)
    if bad:
        return bad
    tool = text(a, "outil", "", 80)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", tool):
        return {"erreur": "outil : le nom exact donne par mcp_outils"}
    known = {t["nom"] for t in entry.get("outils", [])}
    if known and tool not in known:
        return {"erreur": f"{entry['id']} n'a pas d'outil {tool}. Il a : {', '.join(sorted(known))}"}
    arguments, bad = _arguments(a)
    if bad:
        return bad
    try:
        result = mcp_host.request(entry["id"], "tools/call", {"name": tool, "arguments": arguments}, timeout=90)
    except mcp_host.McpError as e:
        return {"erreur": f"{entry['id']} refuse : {e}"}
    except TimeoutError:
        return {"erreur": f"{entry['id']} met trop de temps (90 s) : reessaie plus simple, ou autrement"}
    except RuntimeError as e:
        return {"erreur": str(e)[:200]}
    except (ConnectionError, OSError, ValueError):
        return {"erreur": f"{entry['id']} s'est arrete : reessaie"}
    answer = _answer(result)
    if result.get("isError"):
        return {"erreur": f"{entry['id']} : {answer[:300] or 'erreur'}"}
    if not answer:
        return {"erreur": f"{entry['id']} n'a rien repondu"}
    return {"resultat": answer[:MAX_TEXT], **({"coupe": True} if len(answer) > MAX_TEXT else {})}


FUNCS = {"mcp_serveurs": mcp_serveurs, "mcp_outils": mcp_outils, "mcp_appeler": mcp_appeler}
