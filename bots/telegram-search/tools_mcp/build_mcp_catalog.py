"""Builds instonct/mcp_catalog.json from the Docker MCP registry dump (reg2.json) + my hand-vetted list + the real test results (verified.json)."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REG = json.load(open(os.path.join(HERE, "reg2.json")))
VERIFIED = json.load(open(os.path.join(HERE, "verified.json"))) if os.path.exists(os.path.join(HERE, "verified.json")) else {}
OUT = sys.argv[1]

# Vetted candidates: keyless, no local folder needed, nothing to configure. sur=True: only reads public information.
# fr = what it is for (French, short); kw = words a user would say (French, no accents).
V = {
    "fetch": dict(sur=True, fr="Lit une page web et la rend en texte propre (markdown)", kw="page web url lire site article contenu markdown"),
    "time": dict(sur=True, fr="Heure exacte dans n'importe quel fuseau horaire, conversions", kw="heure fuseau horaire decalage timezone"),
    "duckduckgo": dict(sur=True, fr="Recherche web avec DuckDuckGo", kw="duckduckgo recherche web internet"),
    "wikipedia-mcp": dict(sur=True, fr="Wikipedia : chercher et lire des articles", kw="wikipedia encyclopedie article definition"),
    "youtube-transcript": dict(sur=True, fr="Texte (sous-titres) d'une video YouTube", kw="youtube transcription sous-titres video texte"),
    "sequentialthinking": dict(sur=True, fr="Reflechir a un probleme complexe etape par etape", kw="raisonner reflechir etape probleme complexe planifier"),
    "paper-search": dict(sur=True, fr="Articles scientifiques (arXiv, PubMed, bioRxiv...)", kw="article scientifique papier recherche publication etude arxiv pubmed biorxiv"),
    "arxiv-mcp-server": dict(sur=True, fr="Chercher et lire des articles arXiv", kw="arxiv article scientifique preprint", env={"ARXIV_STORAGE_PATH": "/app/papers"}, volumes=["mcp-arxiv:/app/papers"]),
    "hackernews-mcp": dict(sur=True, fr="Hacker News : histoires, commentaires, utilisateurs", kw="hacker news hackernews actu tech startup"),
    "markitdown": dict(sur=True, fr="Convertit un lien ou un document (pdf, word, excel...) en texte", kw="convertir document pdf word excel markdown texte"),
    "openapi": dict(sur=True, fr="Lire et comprendre n'importe quelle API (OpenAPI/Swagger)", kw="openapi swagger api specification documentation"),
    "npm-sentinel": dict(sur=True, fr="Analyse de paquets npm : versions, securite, popularite", kw="npm paquet package javascript dependances securite"),
    "vuln-nist-mcp-server": dict(sur=True, fr="Failles de securite (base NVD / CVE)", kw="cve faille vulnerabilite securite nvd nist"),
    "google-flights": dict(sur=True, fr="Vols Google Flights : aller simple, aller-retour, dates", kw="vol vols avion billet google flights prix aeroport"),
    "openbnb-airbnb": dict(sur=True, fr="Chercher des logements Airbnb et voir une annonce", kw="airbnb logement location hebergement sejour"),
    "minecraft-wiki": dict(sur=True, fr="Wiki Minecraft : recettes, objets, creatures", kw="minecraft craft recette objet wiki"),
    "gemini-api-docs-mcp": dict(sur=True, fr="Documentation de l'API Gemini de Google", kw="gemini api documentation google ia"),
    "aws-documentation": dict(sur=True, fr="Documentation officielle d'Amazon AWS", kw="aws amazon cloud documentation"),
    "terraform-mcp-server": dict(sur=True, fr="Terraform : chercher fournisseurs et modules du registre", kw="terraform infrastructure registre module fournisseur"),
    "osp_marketing_tools": dict(sur=True, fr="Guides de redaction marketing (positionnement, contenu)", kw="marketing redaction contenu positionnement"),
    "effect-mcp": dict(sur=True, fr="Documentation de la bibliotheque TypeScript Effect", kw="effect typescript documentation bibliotheque"),
    # They write into their own private volume: allowed, but refused once the turn has read the web (see kits.tool).
    "memory": dict(sur=False, fr="Memoire en graphe : retenir des faits et leurs liens", kw="memoire graphe retenir entites relations connaissances", volumes=["mcp-memory:/app/dist"]),
    "sqlite": dict(sur=False, fr="Base de donnees SQLite privee : creer, remplir, interroger", kw="sqlite base de donnees sql table requete", cmd=["--db-path", "/mcp/db.sqlite"], volumes=["mcp-sqlite:/mcp"]),
}

# Started fine, but the real call fails (tested 2026-11-06 through kit_mcp.mcp_appeler): Google blocks it / Airbnb robots.txt refuses bots.
REAL_CALL_FAILED = {"google-flights", "openbnb-airbnb"}

SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|AWS_|USER_ID|CREDENTIAL|DATABASE_URL|_URL$|_HOST$|_PORT$|PROFILE", re.I)


def slug(image):
    tail = image.split("/")[-1].split(":")[0]
    return re.sub(r"[^a-z0-9_-]", "-", tail.lower())


def clean(s, n=150):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[: n - 1] + "…" if len(s) > n else s


INJECT = re.compile(r"ignor|previous instruction|system prompt|you must|always call|never tell|do not tell|secret|password|<\s*/?\s*(?:system|instruction|important)|tu dois", re.I)
screened = []


def kind(schema):
    if not isinstance(schema, dict):
        return "any"
    if schema.get("enum"):
        return "|".join(str(v) for v in schema["enum"][:8])
    t = schema.get("type")
    if t is None and schema.get("anyOf"):
        t = next((o.get("type") for o in schema["anyOf"] if o.get("type") not in (None, "null")), "any")
    if t == "array":
        return "liste de " + str(kind(schema.get("items", {})))
    return str(t or "any")


# Only these tools are offered (and callable) for servers with too many, duplicated or unwanted ones (no downloads, no Sci-Hub).
KEEP = {
    "paper-search": "search_papers search_arxiv search_pubmed search_biorxiv search_medrxiv search_semantic search_crossref search_openalex search_europepmc get_crossref_paper_by_doi",
    "wikipedia-mcp": "search_wikipedia get_article get_summary get_sections get_related_topics extract_key_facts get_coordinates get_links",
    "npm-sentinel": "npmVersions npmLatest npmDeps npmSize npmVulnerabilities npmCompare npmScore npmPackageReadme npmSearch npmRepoStats npmDeprecated npmQuality",
    "osp_marketing_tools": "get_editing_codes get_writing_guide get_meta_guide get_value_map_positioning_guide get_on_page_seo_guide",
}


# My own wording where the server's text sounds like orders to the model ("You must call...").
OVERRIDE = {
    ("terraform-mcp-server", "get_module_details"): "Documentation d'un module Terraform (son id vient de search_modules)",
    ("terraform-mcp-server", "get_policy_details"): "Details d'une politique Terraform (son id vient de search_policies)",
    ("terraform-mcp-server", "get_provider_details"): "Documentation d'un service d'un fournisseur Terraform (id de search_provider_docs)",
    ("terraform-mcp-server", "search_modules"): "Cherche un module Terraform par nom et donne son id",
    ("terraform-mcp-server", "search_policies"): "Cherche des politiques Terraform par mot",
    ("terraform-mcp-server", "search_provider_docs"): "Cherche dans la doc d'un fournisseur Terraform (service_slug, provider_name...)",
    ("sequentialthinking", "sequentialthinking"): "Reflechir etape par etape a un probleme complexe (une pensee a la fois)",
}


def review(sid, tools):
    """Static, reviewed tool list: short description (first sentence), argument names and types, nothing else from the server."""
    out = []
    if sid in KEEP:
        tools = [t for t in tools if t["nom"] in KEEP[sid].split()]
    for t in tools[:12]:
        desc = re.sub(r"\s+", " ", t.get("desc", "")).strip()
        first = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0]
        if (sid, t["nom"]) in OVERRIDE:
            first = OVERRIDE[(sid, t["nom"])]
        elif INJECT.search(desc):
            screened.append((sid, t["nom"], desc[:80]))
            first = f"outil {t['nom']}"
        props = (t.get("args") or {}).get("properties", {}) or {}
        out.append({"nom": t["nom"], "sert_a": clean(first or f"outil {t['nom']}", 140),
                    "args": {k: kind(v) for k, v in list(props.items())[:8]},
                    "requis": [k for k in (t.get("args") or {}).get("required", []) if k in props][:12]})
    return out


servers, seen = [], set()
for x in REG:
    if not x["image"] or x["remote"]:
        continue
    sid = slug(x["image"])
    if sid in seen:
        continue
    seen.add(sid)
    cur = V.get(sid)
    if cur:
        etat = "echec" if sid in REAL_CALL_FAILED else "ok" if VERIFIED.get(sid, {}).get("ok") else ("echec" if sid in VERIFIED else "essai")
    elif x["secret"] or any(SECRET_ENV.search(e) for e in x["env"]):
        etat = "compte"
    else:
        etat = "autre"
    desc = clean(x["desc"])
    if INJECT.search(desc) or INJECT.search(str(x["name"])):
        screened.append((sid, "(registry)", desc[:80]))
        desc = "serveur " + sid
    e = {"id": sid, "nom": clean(x["name"], 60), "image": x["image"], "etat": etat, "desc": desc}
    if cur:
        e.update({"sert_a": cur["fr"], "mots": cur["kw"], "sur": cur["sur"]})
        for k in ("env", "volumes", "cmd"):
            if cur.get(k):
                e[k] = cur[k]
        if sid in VERIFIED:
            e["verifie"] = {k: VERIFIED[sid][k] for k in ("ok", "outils") if k in VERIFIED[sid]}
            for k in ("ro", "cmd", "env", "volumes"):
                if k in VERIFIED[sid] and VERIFIED[sid][k] is not None:
                    e[k] = VERIFIED[sid][k]
            if etat == "ok":
                e["digest"] = VERIFIED[sid]["digest"]
                e["outils"] = review(sid, VERIFIED[sid]["tools"])
                if e.get("ro") is True:
                    del e["ro"]                                    # read-only disk is the default
    servers.append(e)

servers.sort(key=lambda s: ({"ok": 0, "essai": 1, "echec": 2, "compte": 3, "autre": 4}[s["etat"]], s["id"]))
json.dump({"source": "github.com/docker/mcp-registry (2026-11-06)", "servers": servers}, open(OUT, "w"), ensure_ascii=False, indent=0)
from collections import Counter
print(len(servers), Counter(s["etat"] for s in servers))
missing = [k for k in V if k not in seen]
print("curated missing from registry:", missing)
print("screened descriptions:", screened)
