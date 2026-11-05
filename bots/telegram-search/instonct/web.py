"""Browser automation: forms, logins, extraction (Lightpanda / Chromium via webagent)."""

import json
import os
import re
import socket
import subprocess

import requests

from .core import db, log, norm, scrub, send
from . import callbacks

LIGHTPANDA = os.path.expanduser("~/lightpanda/lightpanda")


def url_ok(url):
    """Seulement des sites publics en http(s) : pas le reseau de la maison, ni le Mac mini lui-meme."""
    import ipaddress
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        return all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(u.hostname, None))
    except (OSError, ValueError):
        return False


def browse(url):
    """Lit une page avec le navigateur leger Lightpanda (comprend le JavaScript, ~25 Mo de memoire, lance a la demande)."""
    if os.path.exists(LIGHTPANDA):
        try:
            r = subprocess.run([LIGHTPANDA, "fetch", "--dump", "markdown", "--dump-max-bytes", "60000", url],
                               capture_output=True, text=True, timeout=45)
            if r.stdout.strip():
                return r.stdout.strip()
        except subprocess.TimeoutExpired:
            log.info("lightpanda trop long sur une page")
    html = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).text          # secours : lecture simple
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- navigateur : formulaires, connexions, extraction
SITES_FILE = os.path.expanduser("~/bots/sites.json")
EXPORTS = os.path.expanduser("~/exports")
SENSITIVE_BTN = re.compile(r"acheter|payer|paiement|commander|valider|confirmer|envoyer|supprimer|reserver|souscrire|publier|"
                           r"buy|pay|order|submit|delete|remove|send|confirm|checkout|purchase|book|subscribe|post|sign", re.I)
_web = {"main": None, "watch": None}


def web_browser(watch=False):
    from . import webagent
    k = "watch" if watch else "main"
    if _web[k] is None:
        _web[k] = webagent.Browser(cookies=not watch)
    return _web[k]


def sites_load():
    try:
        return json.load(open(SITES_FILE))
    except (OSError, ValueError):
        return {}


def sites_save(d):
    tmp = SITES_FILE + ".new"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)          # lisible par moi seul des la creation
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SITES_FILE)


def web_here(b, strict=True):
    """Adresse de la page ouverte ; si on a ete redirige vers le reseau de la maison, on quitte la page."""
    url = b.call("getUrl").strip()
    if strict and url and url != "about:blank" and not url_ok(url):
        b.call("goto", url="about:blank")
        raise RuntimeError("redirection vers une adresse interdite (reseau prive)")
    return url


def web_page(b, start=0, n=3000, strict=True):
    url = web_here(b, strict)
    md = b.call("markdown", maxBytes=60000)
    try:
        forms = int(b.js("document.forms.length"))
    except Exception:
        forms = 0
    out = {"adresse": url, "texte": md[start:start + n], "longueur_totale": len(md), "formulaires": forms}
    if len(md) > start + n:
        out["suite"] = f"relance read avec start={start + n}"
    return out


def web_elements(b):
    """Champs et boutons de la page, en lignes courtes : selecteur | type | nom | genre | valeur."""
    out, nlinks = [], 0
    for e in json.loads(b.call("interactiveElements")):
        tag, role, itype = e.get("tagName"), e.get("role"), e.get("inputType") or ""
        if tag == "html":
            continue
        if role == "link":
            nlinks += 1
            continue
        if e.get("id"):
            sel = '[id="%s"]' % e["id"]
        elif e.get("elementName") and tag in ("input", "select", "textarea"):
            sel = '%s[name="%s"]' % (tag, e["elementName"]) + ('[value="%s"]' % e["value"] if itype in ("radio", "checkbox") else "")
        else:
            sel = json.loads(b.call("nodeDetails", backendNodeId=e["backendNodeId"])).get("selector", "?")
        val = "" if itype == "password" else str(e.get("value") or "")[:30]
        out.append(f"{sel} | {role or tag} | {str(e.get('name') or '')[:40]} | {itype} | {val}")
    return {"elements": out[:40], "liens_sur_la_page": nlinks}


def web_probe(b, selector):
    """Que se passe-t-il si on clique ici ? lien simple, bouton, ou envoi de formulaire (avec ce qui partirait)."""
    raw = b.js("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");if(!e)return JSON.stringify({kind:'none'});"
               "const a=e.closest('a[href]');const f=e.closest('form');"
               "const t=(e.innerText||e.textContent||e.value||e.getAttribute('aria-label')||e.title||'').trim().slice(0,60);"
               "const fields=f?[...f.elements].filter(x=>x.name&&x.value&&!['password','hidden','submit','button'].includes(x.type)"
               "&&(!['radio','checkbox'].includes(x.type)||x.checked)).map(x=>x.name+'='+x.value.slice(0,50)).slice(0,10):[];"
               "const pw=!!(f&&f.querySelector('input[type=password]'));"
               "return JSON.stringify({kind:(a&&!f)?'link':(f?'form':'btn'),text:t,fields:fields,pw:pw,action:f?(f.action||''):''});})()")
    return json.loads(raw)


def web_confirm(chat_id, b, p, info):
    from urllib.parse import urlparse
    host = urlparse(info.get("action") or web_here(b)).hostname or "la page"
    lines = [f"Je vais valider « {info.get('text') or p.get('key') or 'ce bouton'} » sur {host}."]
    if info.get("fields"):
        lines.append("Ce qui sera envoye : " + ", ".join(info["fields"]))
    if info.get("pw"):
        lines.append("(le formulaire contient un mot de passe)")
    db.setex(f"pending_web:{chat_id}", 300, json.dumps(p))
    callbacks.send_confirm(chat_id, "\n".join(lines) + "\n\nC'est bon ?", callbacks.cmd_id(json.dumps(p)), "Valider")


def web_run_pending(chat_id, p):
    """Appelee quand l'utilisateur appuie sur Oui : fait le clic (ou la touche) puis montre la page obtenue."""
    try:
        b = web_browser()
        if p["action"] == "press":
            b.call("press", key=p["key"], **({"selector": p["selector"]} if p.get("selector") else {}))
        else:
            b.call("click", selector=p["selector"])
        r = web_page(b, n=1500)
        send(chat_id, f"Fait. Page : {r['adresse']}\n\n{r['texte']}")
    except Exception as e:
        send(chat_id, "Ca n'a pas marche : " + scrub(e)[:200])


TAG_JS = ("(()=>{const pw=document.querySelector('input[type=password]');const root=(pw&&pw.form)||document;"
          "const cand=[...root.querySelectorAll('input')].filter(i=>!['password','hidden','submit','button','checkbox','radio','image','file']"
          ".includes((i.type||'text').toLowerCase())&&!i.disabled);let u=null;"
          "if(pw){for(const i of cand){if(i.compareDocumentPosition(pw)&4)u=i;}}else{u=cand[0]||null;}"
          "document.querySelectorAll('[data-lp]').forEach(x=>x.removeAttribute('data-lp'));"
          "if(pw)pw.setAttribute('data-lp','p');if(u)u.setAttribute('data-lp','u');return JSON.stringify({pw:!!pw,u:!!u});})()")


def web_login(b, site):
    """Connexion a un site enregistre avec /site. Le mot de passe ne passe JAMAIS par le modele : il va du fichier au formulaire."""
    sites = sites_load()
    q = norm(site)
    key = next((k for k in sites if norm(k) == q), None) or next((k for k in sites if q and (q in norm(k) or norm(k) in q)), None)
    if not key:
        return {"erreur": "site inconnu. Sites enregistres : " + (", ".join(sites) or "aucun (l'utilisateur doit envoyer /site pour en ajouter)")}
    cfg = sites[key]
    if not str(cfg.get("url", "")).startswith(("http://", "https://")):
        return {"erreur": "adresse du site invalide"}
    b.call("goto", url=cfg["url"])
    st = json.loads(b.js(TAG_JS))
    if not st["pw"]:                                             # connexion en deux temps : identifiant, puis mot de passe
        if not st["u"]:
            return {"erreur": "pas de formulaire de connexion trouve", **web_page(b, n=600, strict=False)}
        b.call("fill", selector='[data-lp="u"]', value=cfg["username"])
        b.call("press", key="Enter", selector='[data-lp="u"]')
        try:
            b.call("waitForSelector", selector="input[type=password]", timeout=8000)
        except Exception:
            return {"erreur": "pas de champ mot de passe apres l'identifiant", **web_page(b, n=600, strict=False)}
        st = json.loads(b.js(TAG_JS))
    elif st["u"]:
        b.call("fill", selector='[data-lp="u"]', value=cfg["username"])
    b.call("fill", selector='[data-lp="p"]', value=cfg["password"])
    b.call("press", key="Enter", selector='[data-lp="p"]')
    page = web_page(b, n=800, strict=False)
    page["connecte_probable"] = b.js("!!document.querySelector('input[type=password]')").strip() != "true"
    return page


def web_extract(b, schema, name, append):
    raw = b.call("extract", schema=schema if isinstance(schema, str) else json.dumps(schema))
    out = {"donnees": raw[:3500] + ("..." if len(raw) > 3500 else "")}
    if name:
        import csv
        data = json.loads(raw)
        if isinstance(data, dict):
            cols = {k: (v if isinstance(v, list) else [v]) for k, v in data.items()}
            rows = [{k: (v[i] if i < len(v) else "") for k, v in cols.items()} for i in range(max((len(v) for v in cols.values()), default=0))]
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            rows = data
        else:
            rows = [{"valeur": x} for x in (data if isinstance(data, list) else [data])]
        os.makedirs(EXPORTS, exist_ok=True)
        path = os.path.join(EXPORTS, re.sub(r"[^\w.-]", "_", name)[:60].removesuffix(".csv") + ".csv")
        fresh = not (append and os.path.exists(path))
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with open(path, "w" if fresh else "a", newline="", encoding="utf-8-sig" if fresh else "utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if fresh:
                w.writeheader()
            w.writerows({k: (v if isinstance(v, (str, int, float)) else json.dumps(v, ensure_ascii=False)) for k, v in r.items()} for r in rows)
        out.update(fichier=path, lignes=len(rows), conseil="envoie-le avec send_file")
    return out


def tool_browser(chat_id, args, links):
    act = str(args.get("action", "")).lower()
    sel = str(args.get("selector", "") or "")
    links.append("(page web)")                   # contenu externe : la conversation devient "sensible"
    b = web_browser()
    try:
        if act == "open":
            url = str(args.get("url", ""))
            if not url_ok(url):
                return {"erreur": "adresse refusee (il faut un site public en http ou https)"}
            b.call("goto", url=url)
            return web_page(b)
        if act == "read":
            return web_page(b, start=max(0, int(args.get("start", 0) or 0)), n=3500)
        if act == "forms":
            web_here(b)
            return web_elements(b)
        if act == "links":
            web_here(b)
            ls = json.loads(b.call("links", limit=min(int(args.get("limit", 30) or 30), 60)))
            return {"liens": [f"{str(x.get('text', ''))[:50]} | {x.get('href', '')}" for x in ls]}
        if act in ("fill", "choose"):
            if not sel:
                return {"erreur": "selector manquant (utilise forms pour les voir)"}
            kind = b.js("(()=>{const e=document.querySelector(" + json.dumps(sel) + ");return e?(e.tagName+':'+(e.type||'')).toLowerCase():'none'})()").strip()
            if kind == "none":
                return {"erreur": "element introuvable : utilise forms pour voir les champs"}
            val = str(args.get("value", ""))
            if kind.endswith("password"):
                return {"erreur": "ne remplis jamais un mot de passe toi-meme : utilise login avec le nom d'un site enregistre"}
            if kind.startswith("select"):
                b.call("selectOption", selector=sel, value=val)
            elif kind.endswith(("checkbox", "radio")):
                b.call("setChecked", selector=sel, checked=norm(val) not in ("false", "non", "0", "no"))
            else:
                b.call("fill", selector=sel, value=val)
            return {"resultat": "rempli"}
        if act in ("click", "press"):
            key = str(args.get("key", "Enter"))
            if act == "press" and key.lower() != "enter":
                b.call("press", key=key, **({"selector": sel} if sel else {}))
                return {"resultat": "touche appuyee"}
            if not sel:
                return {"erreur": "selector manquant"}
            info = web_probe(b, sel)
            if info["kind"] == "none":
                return {"erreur": "element introuvable : utilise forms pour voir les boutons"}
            p = {"action": act, "selector": sel, **({"key": key} if act == "press" else {})}
            if info["kind"] == "form" or (info["kind"] == "btn" and SENSITIVE_BTN.search(info.get("text", ""))):
                web_confirm(chat_id, b, p, info)
                return {"statut": "en attente : l'utilisateur doit appuyer sur Oui (le bot lui a envoye les boutons). Dis-lui que tu attends, ne rappelle pas cet outil."}
            b.call("click", selector=sel)
            return web_page(b)
        if act == "login":
            return web_login(b, str(args.get("site", "")))
        if act == "extract":
            web_here(b)
            return web_extract(b, args.get("schema", "{}"), str(args.get("name", "") or ""), args.get("append") is True)
        if act == "download":
            url = str(args.get("url", ""))
            if not url_ok(url):
                return {"erreur": "adresse refusee"}
            fname = re.sub(r"[^\w.-]", "_", str(args.get("name") or os.path.basename(url.split("?")[0]) or "telechargement"))[:80]
            return {"resultat": b.call("download", url=url, path=fname, timeout=120), "dossier": "~/recus"}
        if act == "close":
            b.stop()
            return {"resultat": "navigateur ferme"}
        return {"erreur": "action inconnue (open, read, forms, links, fill, choose, click, press, login, extract, download, close)"}
    except Exception as e:
        log.warning("navigateur %s : %s", act, scrub(e))
        return {"erreur": scrub(e)[:250]}
