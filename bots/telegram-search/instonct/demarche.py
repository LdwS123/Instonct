"""Real procedures: one dossier per goal, direct links, the steps, and a clean hand-over when only the human can finish.

The bot does everything up to the last step. Logging in, paying and confirming stay with the user, on the same browser window, from their phone.
Phone calls: no line is plugged in (a real one needs a paid provider), so `appel` prepares the call and never pretends to have made it.
"""

import json
import re
import time
import uuid
from datetime import datetime
from urllib.parse import quote, urlencode

from .core import db, send
from . import remote_access

NAMES = {"demarche", "appel"}
KEY = "demarches"
KEEP = 50
MAX_NOTES = 30
STEPS = {
    "voyage": ["Ouvre les liens avec browser (moteur=chrome) et releve 2 ou 3 options : prix, horaires, duree", "Note-les avec action=note",
               "Donne une recommandation claire et les liens", "Pour reserver : ouvre la page choisie, remplis ce que tu sais, arrete-toi avant le paiement, puis action=main"],
    "courses": ["Lis sa liste (list_show) si les produits ne sont pas donnes", "Ouvre le site avec browser moteur=chrome et ajoute les produits au panier un par un",
                "Si le site bloque : donne les liens directs par produit", "Arrete-toi avant le paiement, dis le total du panier, puis action=main"],
    "facture": ["Retrouve la facture (mail_search, puis mail_read)", "Note le montant, la date, le numero et ce qui ne va pas", "Redige la reclamation (make_document si un fichier est utile)",
                "Montre-lui le texte. L'envoi passe par mail_send, avec son Oui", "Mets un rappel de relance dans 14 jours (set_reminder). Rappelle que ce n'est pas un conseil juridique"],
    "autre": ["Ecris le plan en une ligne par etape", "Fais les etapes une par une, note ce que tu trouves avec action=note", "Ce que seul lui peut faire (connexion, paiement, signature) : action=main"],
}


def _date(value):
    """The date as AAAA-MM-JJ, or raises: a wrong date in a booking link looks fine and shows the wrong trip."""
    value = str(value or "").strip()
    if value:
        datetime.strptime(value, "%Y-%m-%d")
    return value


def flight_link(depart, arrivee, date, retour=""):
    q = f"Flights to {arrivee} from {depart}" + (f" on {date}" if date else "") + (f" through {retour}" if retour else "")
    return "https://www.google.com/travel/flights?q=" + quote(q)


def hotel_link(ville, date="", retour="", personnes=1):
    params = {"ss": ville, "group_adults": personnes or 1}
    if date and retour:
        params |= {"checkin": date, "checkout": retour}
    return "https://www.booking.com/searchresults.fr.html?" + urlencode(params)


def route_link(depart, arrivee):
    return f"https://www.rome2rio.com/s/{quote(depart)}/{quote(arrivee)}"


def shop_links(produit):
    return {"carrefour": "https://www.carrefour.fr/s?q=" + quote(produit), "auchan": "https://www.auchan.fr/recherche?text=" + quote(produit)}


def _links(kind, args):
    depart, arrivee = str(args.get("depart") or "").strip(), str(args.get("arrivee") or "").strip()
    if kind == "voyage" and arrivee:
        date, retour = _date(args.get("date")), _date(args.get("retour"))
        out = {"hotel": hotel_link(arrivee, date, retour, int(args.get("personnes") or 1))}
        if depart:
            out |= {"vols": flight_link(depart, arrivee, date, retour), "trajets": route_link(depart, arrivee)}
        return out
    if kind == "courses":
        return {str(p): shop_links(str(p)) for p in (args.get("produits") or [])[:30]}
    return {}


def _load(ident):
    raw = db.hget(KEY, str(ident or ""))
    return json.loads(raw) if raw else None


def _save(item):
    db.hset(KEY, item["id"], json.dumps(item, ensure_ascii=False))
    every = sorted((json.loads(v) for v in db.hvals(KEY)), key=lambda x: (x["etat"] == "en cours", x["cree"]))
    for old in every[:max(0, len(every) - KEEP)]:                       # finished ones go first
        db.hdel(KEY, old["id"])


def _hand_over(chat_id, args, links):
    """The user finishes on the screen. After reading a page, the address it might have dictated is not opened: a stranger must not choose what the user types into."""
    url = str(args.get("url") or "")
    if links or not re.match(r"https://\S+$", url):
        url = "about:blank"
    secret = remote_access.open_screen(chat_id, url)
    if not secret.startswith("Mot de passe"):
        return {"erreur": secret}
    send(chat_id, secret)                                               # goes to the user only: the model never sees this password
    return {"resultat": "ecran ouvert : l'utilisateur a recu le lien et le mot de passe. Dis-lui ce qu'il lui reste a faire, puis attends."}


def _demarche(chat_id, args, links):
    action = str(args.get("action") or "").lower()
    if action == "main":
        return _hand_over(chat_id, args, links)
    if action == "list":
        rows = [json.loads(v) for v in db.hvals(KEY)]
        return {"demarches": [{k: x[k] for k in ("id", "type", "objectif", "etat")} for x in sorted(rows, key=lambda x: x["cree"])[-15:]] or "aucune"}
    if action == "start":
        kind = str(args.get("type") or "autre").lower()
        kind = kind if kind in STEPS else "autre"
        goal = str(args.get("objectif") or "").strip()[:300]
        if not goal:
            return {"erreur": "dis l'objectif de la demarche"}
        try:
            found = _links(kind, args)
        except ValueError:
            return {"erreur": "date a donner au format AAAA-MM-JJ"}
        item = {"id": uuid.uuid4().hex[:6], "type": kind, "objectif": goal, "cree": time.time(), "etat": "en cours", "notes": [], "externe": bool(links)}
        _save(item)
        return {"id": item["id"], "liens": found, "etapes": STEPS[kind], "regle": "Tu ne paies jamais et ne valides jamais de commande. Page de cookies : refuse ce qui n'est pas essentiel. Le lien marche aussi sur son telephone."}
    item = _load(args.get("id"))
    if not item:
        return {"erreur": "demarche introuvable, regarde action=list"}
    if action == "note":
        item["notes"] = (item["notes"] + [{"quand": f"{datetime.now():%d/%m %H:%M}", "texte": str(args.get("texte") or "")[:500]}])[-MAX_NOTES:]
        item["externe"] = item["externe"] or bool(links)
        _save(item)
        return {"resultat": "note ajoutee"}
    if action == "finish":
        item["etat"] = "fini"
        item["fin"] = str(args.get("texte") or "")[:300]
        _save(item)
        return {"resultat": "demarche fermee"}
    if action == "resume":
        if item["externe"]:                                             # these notes may quote a page: same caution as the page itself
            links.append("(page web)")
        return {k: item[k] for k in ("id", "type", "objectif", "etat", "notes")} | {"etapes": STEPS[item["type"]]}
    return {"erreur": "action inconnue : start, note, list, resume, finish ou main"}


def phone_number(raw):
    """+33... from what people write: 01 23 45 67 89, 0033 1..., +1 (415) 555-0100. Empty if it cannot be a phone number."""
    text = str(raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if digits.startswith("00"):
        digits = digits[2:]
    elif text.startswith("0") and len(digits) == 10:
        digits = "33" + digits[1:]
    elif not text.startswith("+"):
        return ""
    return "+" + digits if 8 <= len(digits) <= 15 else ""


def _appel(args):
    goal = str(args.get("objet") or "").strip()
    who = str(args.get("qui") or "").strip()
    number = phone_number(args.get("numero"))
    script = str(args.get("script") or "").strip() or f"Bonjour, je vous appelle au sujet de : {goal}. Pouvez-vous m'aider ?"
    return {"numero": number or "pas de numero valable : cherche-le sur le site officiel (web_search)", "lien": f"tel:{number}" if number else "", "qui": who, "objet": goal, "a_lire": script,
            "attention": "C'est l'utilisateur qui appelle. Aucune ligne n'est branchee : dis-le clairement. Donne le numero tel quel, Telegram le rend cliquable."}


def tool(chat_id, name, args, links):
    return _appel(args) if name == "appel" else _demarche(chat_id, args, links)
