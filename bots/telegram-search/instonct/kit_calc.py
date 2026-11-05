"""Small exact tools: text helpers, loan and savings maths, bill splitting, random draws, a pomodoro timer.

The numbers are computed here, never by the model: a language model is wrong about compound interest.
"""

import base64
import hashlib
import json
import re
import secrets
import unicodedata
import uuid
from urllib.parse import quote, unquote

from .kit_base import num, spec, text, whole

SPECS = [
    spec("texte_outils", "Outils sur un texte : operation hash|base64|base64_decode|url|url_decode|uuid|mots|json|slug. Calcul exact.", operation="string!", texte="string"),
    spec("pret", "Mensualite, cout total et interets d'un pret (montant, taux annuel en %, duree en mois).", montant="number!", taux="number!", mois="integer!"),
    spec("interets", "Combien vaut une epargne apres N annees avec interets composes (capital, taux en %, annees, versement mensuel).",
         capital="number!", taux="number!", annees="integer!", versement_mensuel="number"),
    spec("partage_note", "Partage une addition entre personnes (total, nombre de personnes, pourboire en %).", total="number!", personnes="integer!", pourboire="number"),
    spec("tirage", "Tire au sort : mode pile_ou_face|de|choix|equipes|nombre. choix/equipes prennent une liste separee par des virgules.",
         mode="string!", liste="string", valeur="integer"),
    spec("pomodoro", "Lance des cycles de travail/pause avec un rappel a chaque fin (travail et pause en minutes, nombre de cycles).",
         travail="integer", pause="integer", cycles="integer"),
]
GROUPS = [
    (r"hash|sha|md5|base64|encode|decode|uuid|slug|compte les mots|nombre de mots|json", {"texte_outils"}),
    (r"pret|credit|mensualite|emprunt|taux d.interet|immobilier", {"pret"}),
    (r"epargne|interets|placement|livret|capital|investir|compose", {"interets"}),
    (r"addition|partage|rembours.* entre|on divise|pourboire|chacun doit|diviser la note", {"partage_note"}),
    (r"tire au sort|tirage|pile ou face|lance un de|de \d+|au hasard|equipes|choisis pour moi|hasard", {"tirage"}),
    (r"pomodoro|focus|concentration|travail.*pause|session de travail", {"pomodoro"}),
]


def texte_outils(chat_id, a):
    op, s = text(a, "operation", "", 20).lower(), str(a.get("texte") or "")[:20000]
    if op == "uuid":
        return {"uuid": str(uuid.uuid4())}
    if not s:
        return {"erreur": "donne le texte"}
    if op == "hash":
        return {algo: hashlib.new(algo, s.encode()).hexdigest() for algo in ("md5", "sha1", "sha256")}
    if op == "base64":
        return {"resultat": base64.b64encode(s.encode()).decode()}
    if op == "base64_decode":
        try:
            return {"resultat": base64.b64decode(s, validate=True).decode("utf-8", "replace")}
        except ValueError:
            return {"erreur": "ce n'est pas du base64 valide"}
    if op == "url":
        return {"resultat": quote(s, safe="")}
    if op == "url_decode":
        return {"resultat": unquote(s)}
    if op == "mots":
        words = len(re.findall(r"\w+", s))
        return {"mots": words, "caracteres": len(s), "lecture_minutes": round(words / 230, 1)}
    if op == "json":
        try:
            return {"valide": True, "formate": json.dumps(json.loads(s), ensure_ascii=False, indent=2)[:3000]}
        except ValueError as e:
            return {"valide": False, "erreur": str(e)[:120]}
    if op == "slug":
        plain = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        return {"resultat": re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")}
    return {"erreur": "operation inconnue : hash, base64, base64_decode, url, url_decode, uuid, mots, json ou slug"}


def pret(chat_id, a):
    amount, rate, months = num(a, "montant", 0, 0), num(a, "taux", 0, 0, 100), whole(a, "mois", 0, 1, 600)
    if amount <= 0 or not months:
        return {"erreur": "il faut un montant et une duree en mois"}
    r = rate / 100 / 12
    monthly = amount / months if r == 0 else amount * r / (1 - (1 + r) ** -months)
    return {"mensualite": round(monthly, 2), "cout_total": round(monthly * months, 2), "interets": round(monthly * months - amount, 2), "montant": amount, "taux_annuel_pct": rate, "mois": months,
            "note": "hors assurance et frais"}


def interets(chat_id, a):
    capital, rate, years, add = num(a, "capital", 0, 0), num(a, "taux", 0, -50, 100), whole(a, "annees", 0, 1, 80), num(a, "versement_mensuel", 0, 0)
    r, value = rate / 100 / 12, capital
    for _ in range(years * 12):
        value = value * (1 + r) + add
    put = capital + add * years * 12
    return {"valeur_finale": round(value, 2), "verse_au_total": round(put, 2), "interets_gagnes": round(value - put, 2), "taux_annuel_pct": rate, "annees": years,
            "note": "taux fixe suppose, avant impots et inflation"}


def partage_note(chat_id, a):
    total, people, tip = num(a, "total", 0, 0), whole(a, "personnes", 0, 0, 500), num(a, "pourboire", 0, 0, 100)
    if total <= 0 or people < 1:
        return {"erreur": "il faut le total et le nombre de personnes"}
    full = total * (1 + tip / 100)
    return {"total_avec_pourboire": round(full, 2), "par_personne": round(full / people, 2), "pourboire_pct": tip}


def tirage(chat_id, a):
    mode, items = text(a, "mode", "", 20).lower(), [x.strip() for x in str(a.get("liste") or "").split(",") if x.strip()]
    if mode == "pile_ou_face":
        return {"resultat": secrets.choice(["pile", "face"])}
    if mode == "de":
        sides = whole(a, "valeur", 6, 2, 1000)
        return {"resultat": secrets.randbelow(sides) + 1, "faces": sides}
    if mode == "nombre":
        top = whole(a, "valeur", 100, 1, 10**9)
        return {"resultat": secrets.randbelow(top) + 1, "entre": f"1 et {top}"}
    if mode == "choix":
        return {"resultat": secrets.choice(items), "parmi": len(items)} if items else {"erreur": "donne une liste separee par des virgules"}
    if mode == "equipes":
        n = whole(a, "valeur", 2, 2, 20)
        if len(items) < n:
            return {"erreur": "il faut au moins autant de noms que d'equipes"}
        pool = items[:]
        secrets.SystemRandom().shuffle(pool)
        return {"equipes": {f"equipe {i + 1}": pool[i::n] for i in range(n)}}
    return {"erreur": "mode : pile_ou_face, de, nombre, choix ou equipes"}


def pomodoro(chat_id, a):
    from . import reminders                                 # reminders imports brain, which imports the catalog that imports this file
    work, rest, cycles = whole(a, "travail", 25, 5, 120), whole(a, "pause", 5, 1, 60), whole(a, "cycles", 4, 1, 8)
    clock = 0
    for i in range(1, cycles + 1):
        clock += work
        reminders.add_reminder(chat_id, f"{clock} Fin du travail {i}/{cycles} : pause de {rest} min." if i < cycles else f"{clock} Dernier cycle fini, bravo ! Longue pause.")
        if i < cycles:
            clock += rest
            reminders.add_reminder(chat_id, f"{clock} Fin de la pause : au travail ({i + 1}/{cycles}), {work} min.")
    return {"lance": True, "cycles": cycles, "travail_min": work, "pause_min": rest, "fini_dans_min": clock, "premier_rappel_dans_min": work}


FUNCS = {"texte_outils": texte_outils, "pret": pret, "interets": interets, "partage_note": partage_note, "tirage": tirage, "pomodoro": pomodoro}
