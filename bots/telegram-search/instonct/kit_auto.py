"""Automation tools for the model: rules (« chaque soir a 23h, eteins la tele »), scenes (« mode film ») and quiet hours (« silence la nuit »).

The real work is in automate.py and quiet.py (plain code, no model). Everything that creates, changes or runs something is guarded:
the user must have asked for it in this very message (see guard.py), so a mail or a web page can never plant a rule.
Heavy modules are imported inside the functions (kits.py is imported by the catalog: no cycle allowed at the top).
"""

from . import guard
from .kit_base import spec, text

GROUPS = [
    (r"automat|\bscenes?\b|\bambiance|\bsilence|\bchut\b|mode (?:film|dodo|depart|nuit|reveil)|\bregles? auto|ne parle pas la nuit|calme la nuit|"
     r"toutes les \d+ ?(?:min|h)|si le disque|si la temperature|quand le disque|quand le site|chaque (?:jour|matin|soir|semaine|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b.*"
     r"(?:eteins|allume|sauvegarde|briefing|volume|musique|scene)",
     {"automatisation", "scene", "silence_nuit"}),
]
SPECS = [
    spec("automatisation", "Regles automatiques sans modele : lister, ajouter (quand + quoi), supprimer, pause, reprise, lancer. quand='chaque jour a 7h30'.",
         action="string!", quand="string", quoi="string", id="string"),
    spec("scene", "Scenes = plusieurs actions d'un coup (dodo, film, depart, reveil + les tiennes). action : lancer, lister, creer, supprimer.",
         action="string!", nom="string", quoi="string"),
    spec("silence_nuit", "Mode silence : la nuit le Mac mini ne parle plus. etat : on, off ou rien (voir). Heures optionnelles : debut, fin.",
         etat="string", debut="string", fin="string"),
]


def automatisation(chat_id, a):
    from . import automate
    action = text(a, "action", "", 20).lower()
    if action in ("lister", "liste", "voir"):
        return {"regles": [automate.rule_line(r) for r in automate.rules()] or "aucune", "moments": automate.FORMATS, "actions": automate.STEPS_HELP}
    verbs = {"ajouter": "auto_add", "supprimer": "auto_remove", "pause": "auto_change", "reprise": "auto_change", "lancer": "auto_run"}
    if action not in verbs:
        return {"erreur": "action inconnue : lister, ajouter, supprimer, pause, reprise ou lancer."}
    denied = guard.refusal(verbs[action])
    if denied:
        return denied
    if action == "ajouter":
        rule, err = automate.add_rule(text(a, "quand", "", 120) + " : " + text(a, "quoi", "", 400))
        return {"erreur": err} if err else {"resultat": "regle enregistree", "regle": automate.rule_line(rule)}
    ident = text(a, "id", "", 20)
    if not automate._find(ident):
        return {"erreur": "regle introuvable : demande la liste d'abord."}
    word = {"supprimer": "suppr", "pause": "pause", "reprise": "reprise", "lancer": "lance"}[action]
    return {"resultat": automate.auto_command(chat_id, f"{word} {ident}")}


def scene(chat_id, a):
    from . import automate
    action = text(a, "action", "", 20).lower()
    if action in ("lister", "liste", "voir"):
        return {"scenes": {k: ", ".join(v) for k, v in automate.scenes().items()}}
    verbs = {"lancer": "scene_run", "creer": "auto_add", "supprimer": "auto_remove"}
    if action not in verbs:
        return {"erreur": "action inconnue : lancer, lister, creer ou supprimer."}
    denied = guard.refusal(verbs[action])
    if denied:
        return denied
    name = text(a, "nom", "", 30)
    if action == "lancer":
        return {"resultat": automate.run_scene(chat_id, name)}
    if action == "creer":
        return {"resultat": automate.scene_command(chat_id, f"creer {name} = {text(a, 'quoi', '', 400)}")}
    return {"resultat": automate.scene_command(chat_id, f"suppr {name}")}


def silence_nuit(chat_id, a):
    from . import quiet
    state = text(a, "etat", "", 10).lower()
    if not state and not a.get("debut"):
        return {"resultat": quiet.command("")}
    denied = guard.refusal("silence")
    if denied:
        return denied
    if a.get("debut") and a.get("fin"):
        return {"resultat": quiet.command(f"{text(a, 'debut', '', 12)} {text(a, 'fin', '', 12)}")}
    return {"resultat": quiet.command(state)}


FUNCS = {"automatisation": automatisation, "scene": scene, "silence_nuit": silence_nuit}
