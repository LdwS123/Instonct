"""Page watching (prices, availability, changes) without any AI call."""

import hashlib
import json
import re
import time
import uuid

from .core import db, is_wa, log, norm, scrub, send, tg
from . import web

# ---------------------------------------------------------------- surveillance de pages (prix, disponibilite, changement) : sans IA, donc gratuite
def web_snapshot(url, selector=""):
    b = web.web_browser(watch=True)
    with b.lock:
        b.call("goto", url=url)
        web.web_here(b)
        if selector:
            txt = b.js("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");return e?(e.innerText||e.textContent||''):''})()")
        else:
            txt = b.call("markdown", maxBytes=40000)
    return re.sub(r"\s+", " ", txt).strip()


def watch_sig(w, txt):
    if w.get("contains"):
        return "present" if norm(w["contains"]) in norm(txt) else "absent"
    return hashlib.sha1(txt.encode()).hexdigest()[:12]


def tool_page_watch(args):
    act = str(args.get("action", "list")).lower()
    if act == "list":
        return {"surveillances": [{"id": k, **{x: json.loads(v).get(x) for x in ("url", "selector", "contains", "every", "note")}}
                                  for k, v in db.hgetall("pagewatch").items()] or "aucune"}
    if act == "remove":
        q = norm(str(args.get("text", "")))
        n = 0
        for k, v in db.hgetall("pagewatch").items():
            if not q or q in norm(v) or q == k:
                db.hdel("pagewatch", k)
                n += 1
        return {"resultat": f"{n} surveillance(s) supprimee(s)"}
    url = str(args.get("url", ""))
    if not web.url_ok(url):
        return {"erreur": "adresse refusee (il faut un site public en http ou https)"}
    if db.hlen("pagewatch") >= 10:
        return {"erreur": "10 surveillances maximum : supprime-en une d'abord"}
    w = {"url": url, "selector": str(args.get("selector", "") or ""), "contains": str(args.get("contains", "") or ""),
         "every": max(10, int(args.get("every_minutes", 60) or 60)), "note": str(args.get("note", ""))[:100], "err": 0}
    txt = web_snapshot(url, w["selector"])
    w.update(sig=watch_sig(w, txt), text=txt[:300], next=time.time() + w["every"] * 60)
    db.hset("pagewatch", uuid.uuid4().hex[:6], json.dumps(w, ensure_ascii=False))
    return {"resultat": f"surveillance creee (verification toutes les {w['every']} min, alerte seulement si ca change)",
            "valeur_actuelle": txt[:200] or "(vide : le selecteur ne correspond a rien ?)"}


def check_pages(chat_id):
    done = 0
    for k, raw in db.hgetall("pagewatch").items():
        w = json.loads(raw)
        if time.time() < w["next"]:
            continue
        w["next"] = time.time() + w["every"] * 60
        try:
            txt = web_snapshot(w["url"], w["selector"])
            sig = watch_sig(w, txt)
            w["err"] = 0
            if sig != w["sig"]:
                if w.get("contains"):
                    msg = f"« {w['contains']} » est maintenant {'present' if sig == 'present' else 'absent'} sur {w['url']}"
                else:
                    msg = f"La page a change : {w['url']}\nAvant : {w['text'][:250]}\nMaintenant : {txt[:250]}"
                send(chat_id, (w["note"] + "\n" if w["note"] else "") + msg)
                w.update(sig=sig, text=txt[:300])
        except Exception as e:
            w["err"] = w.get("err", 0) + 1
            log.warning("surveillance %s : %s", w["url"], scrub(e))
            if w["err"] == 3:
                send(chat_id, f"Je n'arrive plus a lire {w['url']} (3 essais rates). Dis-moi si je dois arreter de la surveiller.")
        db.hset("pagewatch", k, json.dumps(w, ensure_ascii=False))
        done += 1
        if done >= 3:                              # 3 pages par passage au maximum : on menage le petit processeur
            break


def site_command(chat_id, msg, arg):
    """/site ajouter nom adresse identifiant motdepasse | /site liste | /site suppr nom. Le mot de passe n'est jamais montre au modele."""
    parts = arg.split(None, 4)
    sub = parts[0].lower() if parts else ""
    sites = web.sites_load()
    if is_wa(chat_id) and sub in ("ajouter", "add"):
        send(chat_id, "For safety, save site passwords from Telegram: there the bot deletes your message right after. WhatsApp keeps it.")
        return
    if sub in ("ajouter", "add") and len(parts) == 5 and parts[2].startswith(("http://", "https://")):
        sites[parts[1]] = {"url": parts[2], "username": parts[3], "password": parts[4]}
        web.sites_save(sites)
        tg("deleteMessage", chat_id=chat_id, message_id=msg["message_id"])          # on efface le message qui contenait le mot de passe
        send(chat_id, f"Site '{parts[1]}' enregistre, et ton message avec le mot de passe est efface. Dis-moi 'connecte-toi a {parts[1]}'.\n"
                      "Conseil : evite les comptes tres sensibles (banque), et ca ne marche pas si le site demande un code SMS.")
    elif sub in ("liste", "list") or not parts:
        send(chat_id, ("Sites enregistres :\n" + "\n".join(f"- {k} : {v['url']} ({v['username']})" for k, v in sites.items())) if sites
             else "Aucun site. Ajoute-en un :\n/site ajouter nom https://adresse-de-connexion identifiant motdepasse")
    elif sub in ("suppr", "supprimer", "del") and len(parts) >= 2:
        send(chat_id, "Supprime." if sites.pop(parts[1], None) else "Je ne connais pas ce site.")
        web.sites_save(sites)
    else:
        send(chat_id, "Utilisation :\n/site ajouter nom https://adresse-de-connexion identifiant motdepasse\n/site liste\n/site suppr nom")
