"""Automatisations : scenes (plusieurs actions d'un coup), regles « quand ... alors ... », panneau de boutons, auto-reparation.

Tout repose sur UN petit vocabulaire d'actions (les « etapes »), le meme pour les scenes, les regles et le panneau :
    tele on|off · musique stop · volume 20|+|- · chaine 3 · status · briefing · sauvegarde
    scene <nom> · routine <nom> · silence on|off · message <texte>
Les regles vivent dans le hash Redis `auto:rules`, les scenes perso dans `scenes` : elles survivent a un redemarrage.
Rien ici n'appelle un modele : c'est du code simple, rapide et previsible.
"""

import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime

from .core import db, log, norm, scrub, send
from . import commands, kit_server, life, music, plus, quiet, sound, television

MAX_RULES = 30
MAX_STEPS = 8
LATE = 10 * 60                                  # une regle « chaque jour a 7h30 » part encore si le bot redemarre dans les 10 minutes
MIN_EVERY = 5                                   # « toutes les N minutes » : pas moins de 5
HEAL_SERVICES = ("searxng", "tailscaled")       # les seuls services que le bot relance tout seul
DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

PRESETS = {                                     # scenes toutes faites (on peut en creer d'autres avec /scene creer)
    "dodo": ["tele off", "musique stop", "silence on", "message Bonne nuit : télé et musique coupées, mode silence activé. 🌙"],
    "film": ["tele on", "musique stop", "volume 25", "message Bonne séance ! 🎬"],
    "depart": ["tele off", "musique stop", "message Maison en veille : télé et musique coupées. À tout à l'heure !"],
    "reveil": ["silence off", "briefing"],
}

QUICK = {                                       # boutons du /panneau et des pages du /menu : cle -> etape
    "tele_on": "tele on", "tele_off": "tele off", "musique_stop": "musique stop", "volume_moins": "volume -", "volume_plus": "volume +",
    "briefing": "briefing", "status": "status", "sauvegarde": "sauvegarde", "dodo": "scene dodo", "film": "scene film", "depart": "scene depart",
}
QUICK_LABELS = {
    "tele_on": "📺 Allume la télé", "tele_off": "📴 Éteins la télé", "musique_stop": "⏹ Stop musique", "volume_moins": "🔉 Volume −",
    "volume_plus": "🔊 Volume +", "briefing": "☀️ Résumé du jour", "status": "📊 État du Mac", "sauvegarde": "💾 Sauvegarde",
    "dodo": "😴 Dodo", "film": "🎬 Film", "depart": "🚪 Départ",
}

FORMATS = ("Exemples de moments : « chaque jour à 7h30 », « le lundi à 8h », « en semaine à 7h », « toutes les 30 minutes », "
           "« si le disque < 15 », « si la température > 80 », « si le site exemple.fr tombe ».")
STEPS_HELP = "Actions : tele on/off, musique stop, volume 20 (ou + / -), chaine 3, status, briefing, sauvegarde, scene <nom>, routine <nom>, silence on/off, message <texte>."


def _n(text):
    return re.sub(r"\s+", " ", norm(str(text or "")))


def _launch(fn, *args):
    """Lance en arriere-plan (les tests remplacent cette fonction pour tout faire sur place)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ les etapes
def parse_step(text):
    """'Allume la télé' -> ('tele', 'on'). None si ce n'est pas une action connue."""
    raw = str(text or "").strip()
    m = re.match(r"\s*(?:message|msg)\b\s*:?\s*(.+)", raw, re.I | re.S)
    if m:
        return "message", m.group(1).strip()[:300]
    n = _n(raw)
    if not n:
        return None
    if m := re.match(r"scene (\S+)$", n):
        return "scene", m.group(1)
    if m := re.match(r"routine (.+)$", n):
        return "routine", m.group(1)
    if m := re.match(r"silence(?: nuit)? (on|off)$", n):
        return "silence", m.group(1)
    if m := re.match(r"chaine (\d{1,3})$", n):
        return "chaine", m.group(1)
    if re.match(r"(?:musique|son) (?:stop|off|arret)$|(?:stop|stoppe|arrete|coupe) (?:la )?musique$", n):
        return "musique", "stop"
    if m := re.match(r"volume (?:a )?(\d{1,3}) ?%?$", n):
        return "volume", str(min(100, int(m.group(1))))
    if re.match(r"volume (?:\+|plus|monte)$|monte (?:le )?(?:son|volume)$", n):
        return "volume", "+"
    if re.match(r"volume (?:-|moins|baisse)$|baisse (?:le )?(?:son|volume)$", n):
        return "volume", "-"
    if re.match(r"(?:tele|tv|television) (on|allume)$|(?:allume|allumer|rallume) (?:la )?(?:tele|tv|television)$", n):
        return "tele", "on"
    if re.match(r"(?:tele|tv|television) (off|eteins?|eteint)$|(?:eteins?|eteindre|eteint|coupe) (?:la )?(?:tele|tv|television)$", n):
        return "tele", "off"
    if re.match(r"(?:status|statut|etat)(?: du mac| du serveur)?$", n):
        return "status", ""
    if re.match(r"(?:briefing|resume|resume du jour|bulletin|point du matin)$", n):
        return "briefing", ""
    if re.match(r"(?:sauvegarde|backup)$", n):
        return "sauvegarde", ""
    return None


def canon(kind, arg):
    return f"{kind} {arg}".strip()


def parse_steps(text):
    """'tele off, musique stop puis message bonne nuit' -> (['tele off', 'musique stop', 'message bonne nuit'], erreur ou None)."""
    raw = str(text or "").strip()
    tail = None
    m = re.search(r"\b(?:message|msg)\b\s*:?\s*", raw, re.I)
    if m:
        raw, tail = raw[:m.start()], raw[m.start():]
    pieces = [p.strip() for p in re.split(r"[,;+]|\bpuis\b|\bet puis\b|\bet\b", raw) if p.strip()]
    if tail:
        pieces.append(tail)
    if not pieces:
        return [], "Il manque les actions. " + STEPS_HELP
    out = []
    for p in pieces:
        step = parse_step(p)
        if step is None:
            return [], f"Je ne connais pas l'action « {p[:40]} ». " + STEPS_HELP
        out.append(canon(*step))
    if len(out) > MAX_STEPS:
        return [], f"Trop d'actions (maximum {MAX_STEPS})."
    return out, None


def _do(chat_id, kind, arg, depth):
    if kind == "tele":
        return television.tv_power(arg)
    if kind == "musique":
        music.stop_all()
        return "Musique arrêtée."
    if kind == "volume":
        if arg == "+":
            return sound.change_volume(10)
        if arg == "-":
            return sound.change_volume(-10)
        sound.set_volume(int(arg))
        return f"Volume réglé à {arg} %."
    if kind == "chaine":
        return television.tv_channel(int(arg))
    if kind == "status":
        return commands.status()
    if kind == "briefing":
        return life.briefing_text()
    if kind == "sauvegarde":
        res = kit_server.backup_now(chat_id, {})
        return "Sauvegarde faite : " + str(res.get("fichier", "ok"))
    if kind == "silence":
        return quiet.command(arg)
    if kind == "message":
        return arg
    if kind == "scene":
        return "\n".join(run_scene(chat_id, arg, depth + 1))
    if kind == "routine":
        from . import brain                                   # lazy : brain pulls half of the package
        r = db.hget("routines", arg)
        if not r:
            return f"Je ne connais pas la routine « {arg} »."
        return brain.ask(chat_id, life.routine_prompt(arg, json.loads(r)))
    return f"Action inconnue : {kind}"


def run_steps(chat_id, steps, depth=0):
    """Fait les actions une par une. Une qui rate n'arrête pas les autres. Renvoie une ligne par action."""
    lines = []
    for s in steps:
        step = parse_step(s)
        if step is None:
            lines.append(f"✗ {s} : action inconnue")
            continue
        try:
            res = str(_do(chat_id, step[0], step[1], depth)).strip()
            lines.append(res if step[0] in ("message", "scene", "status", "briefing") else f"✓ {res}")
        except Exception as e:
            log.warning("automatisation : %s a echoue (%s)", s[:40], scrub(e)[:100])
            lines.append(f"✗ {s} : ça n'a pas marché")
    return lines


# ------------------------------------------------------------------ scenes
def scenes():
    """Toutes les scenes : les toutes faites, puis les tiennes (les tiennes gagnent si le nom est le meme)."""
    out = {k: list(v) for k, v in PRESETS.items()}
    for k, v in db.hgetall("scenes").items():
        try:
            out[k] = json.loads(v)
        except ValueError:
            pass
    return out


def run_scene(chat_id, name, depth=0):
    steps = scenes().get(_n(name))
    if steps is None:
        return [f"Je ne connais pas la scène « {name} ». /scene pour voir la liste."]
    if depth > 2:
        return ["Trop de scènes dans des scènes."]
    return run_steps(chat_id, steps, depth)


def scene_command(chat_id, arg):
    """/scene : liste · /scene <nom> : la lance · /scene creer <nom> = actions · /scene suppr <nom>."""
    raw = (arg or "").strip()
    n = _n(raw)
    if not n:
        lines = ["Scènes (lance-les avec /scene <nom>, ou dis « mode film ») :"]
        for k, v in scenes().items():
            lines.append(f"• {k}{' (à toi)' if k in db.hgetall('scenes') else ''} : " + ", ".join(v)[:120])
        lines.append("\nCréer : /scene creer soiree = tele on, volume 30, message Bonne soirée\nEffacer : /scene suppr soiree")
        return "\n".join(lines)
    m = re.match(r"(?:creer|cree|ajoute|nouvelle)\s+(\S+)\s*(?:=|:)\s*(.+)$", raw, re.I | re.S)
    if m:
        name = _n(m.group(1))
        if not re.fullmatch(r"[a-z0-9_-]{2,20}", name):
            return "Le nom doit faire 2 à 20 lettres ou chiffres, sans espace."
        steps, err = parse_steps(m.group(2))
        if err:
            return err
        if len(db.hkeys("scenes")) >= 30 and name not in db.hkeys("scenes"):
            return "Déjà 30 scènes : efface-en une avant (/scene suppr nom)."
        db.hset("scenes", name, json.dumps(steps))
        return f"Scène « {name} » enregistrée : " + ", ".join(steps) + f"\nPour la lancer : /scene {name}"
    m = re.match(r"(?:suppr\w*|efface\w*|supprime|delete)\s+(\S+)$", n)
    if m:
        if db.hdel("scenes", m.group(1)):
            return f"Scène « {m.group(1)} » effacée."
        return "Je ne trouve pas cette scène à toi (les scènes toutes faites ne s'effacent pas)."
    n = re.sub(r"^(?:lance |active |mode )", "", n)
    return "\n".join(run_scene(chat_id, n))


def quick(chat_id, text):
    """« mode film », « scène dodo », « lance le mode départ » : ordre direct, sans modèle. None si ce n'est pas ça."""
    n = _n(text)
    m = re.match(r"(?:(?:lance|active|mets|mets le|mets la|fais|fait)\s+)?(?:le |la )?(?:mode|scene|ambiance)\s+(\S+)$", n)
    if not m or m.group(1) not in scenes():
        return None
    return "\n".join(run_scene(chat_id, m.group(1)))


# ------------------------------------------------------------------ regles
def parse_when(text):
    """'chaque jour a 7h30' -> {'type': 'daily', ...}. Renvoie (dict, None) ou (None, message d'erreur)."""
    n = _n(text)
    if m := re.search(r"site (\S+) (?:tombe|est down|plante|ne repond plus|hors ligne)", n):
        host = m.group(1).strip(".,;")
        return {"type": "site", "host": host}, None
    if "disque" in n:
        m = re.search(r"(\d{1,2})", n)
        if not m or not 1 <= int(m.group(1)) <= 90:
            return None, "Dis-moi le seuil : « si le disque < 15 » (moins de 15 % de libre)."
        return {"type": "disk", "pct": int(m.group(1))}, None
    if "temp" in n:
        m = re.search(r"(\d{2,3})", n)
        if not m or not 40 <= int(m.group(1)) <= 110:
            return None, "Dis-moi le seuil en degrés (entre 40 et 110) : « si la température > 80 »."
        return {"type": "temp", "deg": int(m.group(1))}, None
    if m := re.search(r"(?:toutes les|tous les|chaque)\s*(\d+)?\s*(minutes?|min|heures?|h)\b", n):
        count = int(m.group(1) or 1)
        minutes = count if m.group(2).startswith("m") else count * 60
        if minutes < MIN_EVERY:
            return None, f"Pas plus souvent que toutes les {MIN_EVERY} minutes."
        if minutes > 24 * 60:
            return None, "Maximum : toutes les 24 heures (pour plus long, dis « chaque jour à … »)."
        return {"type": "every", "min": minutes}, None
    hhmm = quiet.parse_time(text)
    if hhmm:
        days = [i for i, d in enumerate(DAYS) if d in n or d + "s" in n]
        if "semaine" in n and "week" not in n:
            days = [0, 1, 2, 3, 4]
        elif "weekend" in n or "week-end" in n or "week end" in n:
            days = [5, 6]
        return {"type": "daily", "time": hhmm, "days": days or None}, None
    return None, "Je n'ai pas compris le moment. " + FORMATS


def describe_when(w):
    t = w["type"]
    if t == "daily":
        days = w.get("days")
        which = "chaque jour" if not days else "le " + "/".join(DAYS[d] for d in days) if len(days) < 5 else "en semaine" if days == [0, 1, 2, 3, 4] else "chaque jour"
        return f"{which} à {w['time']}"
    if t == "every":
        return f"toutes les {w['min']} min" if w["min"] < 120 else f"toutes les {w['min'] // 60} h"
    if t == "disk":
        return f"si le disque a moins de {w['pct']} % de libre"
    if t == "temp":
        return f"si le processeur dépasse {w['deg']} °C"
    return f"si le site {w['host']} tombe"


def rules():
    out = []
    for raw in db.hvals("auto:rules"):
        try:
            out.append(json.loads(raw))
        except ValueError:
            pass
    return sorted(out, key=lambda r: r.get("made", 0))


def add_rule(text):
    """'chaque jour a 7h30 : briefing' -> (regle, None) ou (None, erreur)."""
    parts = re.split(r"(?::\s+|\s+alors\s+|\s*->\s*|\s*=>\s*)", text.strip(), maxsplit=1)
    if len(parts) != 2:
        return None, "Il me faut le moment ET les actions, séparés par « : ». Exemple : /auto ajoute chaque jour à 7h30 : briefing"
    when, err = parse_when(parts[0])
    if err:
        return None, err
    steps, err = parse_steps(parts[1])
    if err:
        return None, err
    if len(db.hkeys("auto:rules")) >= MAX_RULES:
        return None, f"Déjà {MAX_RULES} règles : efface-en une (/auto suppr <numéro>)."
    rid = uuid.uuid4().hex[:4]
    rule = {"id": rid, "when": when, "steps": steps, "on": True, "made": time.time()}
    db.hset("auto:rules", rid, json.dumps(rule))
    return rule, None


def _save(rule):
    db.hset("auto:rules", rule["id"], json.dumps(rule))


def _find(token):
    token = _n(token)
    for r in rules():
        if r["id"] == token:
            return r
    return None


def rule_line(r):
    return f"{'▶' if r['on'] else '⏸'} {r['id']} · {describe_when(r['when'])} → {', '.join(r['steps'])}"[:300]


def auto_command(chat_id, arg):
    """/auto : liste · ajoute <quand> : <actions> · pause|reprise|suppr <numéro> · lance <numéro>."""
    raw = (arg or "").strip()
    n = _n(raw)
    if n in ("", "liste", "list", "etat"):
        rs = rules()
        if not rs:
            return ("Aucune règle pour l'instant. Exemples :\n/auto ajoute chaque jour à 7h30 : briefing\n"
                    "/auto ajoute en semaine à 22h30 : scene dodo\n/auto ajoute si le disque < 15 : message Le disque se remplit\n"
                    "/auto ajoute toutes les 2 heures : sauvegarde\n\n" + FORMATS + "\n" + STEPS_HELP)
        return "Mes règles :\n" + "\n".join(rule_line(r) for r in rs) + "\n\n/auto pause|reprise|suppr|lance <numéro> · /auto ajoute <quand> : <actions>"
    m = re.match(r"(?:ajoute\w*|nouvelle|cree\w*|add)\s+(.+)$", raw, re.I | re.S)
    if m:
        rule, err = add_rule(m.group(1))
        return err or "Règle enregistrée.\n" + rule_line(rule)
    m = re.match(r"(pause|reprise|reprend|suppr\w*|efface\w*|supprime|lance|teste?|test)\s+(\S+)$", n)
    if m:
        act, rule = m.group(1), _find(m.group(2))
        if rule is None:
            return "Je ne trouve pas cette règle. /auto pour voir la liste."
        if act.startswith(("suppr", "efface")):
            db.hdel("auto:rules", rule["id"])
            return f"Règle {rule['id']} effacée."
        if act in ("pause", "reprise", "reprend"):
            rule["on"] = act != "pause"
            _save(rule)
            return ("Règle en pause : " if act == "pause" else "Règle reprise : ") + rule_line(rule)
        return "Je la lance maintenant :\n" + "\n".join(run_steps(chat_id, rule["steps"]))
    return "Je n'ai pas compris. /auto pour la liste et des exemples."


def _fire(rule, chat_id):
    try:
        lines = run_steps(chat_id, rule["steps"])
        send(chat_id, f"🤖 Règle {rule['id']} ({describe_when(rule['when'])})\n" + "\n".join(lines))
    except Exception as e:
        log.error("regle %s : %s", rule.get("id"), scrub(e)[:150])


def _condition_met(rule):
    w = rule["when"]
    if w["type"] == "disk":
        u = shutil.disk_usage("/")
        return u.free / u.total * 100 < w["pct"]
    if w["type"] == "temp":
        t = commands.cpu_temp().split()[0]
        return t.isdigit() and int(t) > w["deg"]
    if w["type"] == "site":
        from . import kit_net                                 # lazy : keeps the import graph light
        return kit_net.site_up(0, {"url": w["host"]}).get("en_ligne") is False
    return False


def _check_and_fire(rule, chat_id):
    try:
        if _condition_met(rule) and db.set(f"auto:cool:{rule['id']}", 1, nx=True, ex=6 * 3600):
            _fire(rule, chat_id)
    except Exception as e:
        log.warning("regle %s (condition) : %s", rule.get("id"), scrub(e)[:100])


def tick(now=None):
    """Appelé toutes les 5 secondes par reminder_loop : lance les règles dont c'est le moment."""
    owner = db.get("owner_id")
    if not owner or not db.hlen("auto:rules"):
        return
    now = now or datetime.now()
    stamp = now.timestamp()
    for r in rules():
        if not r.get("on"):
            continue
        w = r["when"]
        try:
            if w["type"] == "daily":
                if w.get("days") and now.weekday() not in w["days"]:
                    continue
                target = now.replace(hour=int(w["time"][:2]), minute=int(w["time"][3:]), second=0, microsecond=0)
                if 0 <= stamp - target.timestamp() <= LATE and db.set(f"auto:ran:{r['id']}:{now:%Y-%m-%d}", 1, nx=True, ex=86400):
                    _launch(_fire, r, int(owner))
            elif w["type"] == "every":
                due = db.hget("auto:next", r["id"])
                if due is None:
                    db.hset("auto:next", r["id"], stamp + w["min"] * 60)
                elif stamp >= float(due):
                    db.hset("auto:next", r["id"], stamp + w["min"] * 60)
                    _launch(_fire, r, int(owner))
            elif db.set(f"auto:chk:{r['id']}", 1, nx=True, ex=600):                  # conditions : on regarde toutes les 10 minutes
                _launch(_check_and_fire, r, int(owner))
        except Exception as e:
            log.warning("regle %s : %s", r.get("id"), scrub(e)[:100])


# ------------------------------------------------------------------ panneau
def panel_markup():
    keys = list(QUICK)
    buttons = [(QUICK_LABELS[k], f"go:{k}") for k in keys]
    return television._markup([buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def press(chat_id, key):
    """Bouton du panneau ou d'une page du menu. Répond tout de suite, fait le travail en arrière-plan."""
    step = QUICK.get(key)
    if step is None:
        return "Bouton inconnu."

    def work():
        try:
            send(chat_id, "\n".join(run_steps(chat_id, [step])))
        except Exception as e:
            log.warning("bouton %s : %s", key, scrub(e)[:100])
    _launch(work)
    return QUICK_LABELS[key]


# ------------------------------------------------------------------ auto-réparation
def check_selfheal(chat_id):
    """Relance un service en panne (liste blanche, 1 fois par heure) et fait de la place si le disque est presque plein."""
    if not plus.setting(db, "reparation_auto"):
        return
    try:
        failed = _run("systemctl --failed --no-legend --plain".split(), 20).stdout.split("\n")
    except Exception as e:
        log.info("auto-reparation : %s", scrub(e)[:100])
        failed = []
    for line in failed:
        svc = (line.split() or [""])[0].removesuffix(".service")
        if svc in HEAL_SERVICES and db.set(f"heal:{svc}", 1, nx=True, ex=3600):
            res = _run(["sudo", "-n", "systemctl", "restart", svc], 60)
            send(chat_id, f"🔧 Le service {svc} était en panne : je l'ai relancé" + ("." if res.returncode == 0 else ", mais ça n'a pas marché."))
    u = shutil.disk_usage("/")
    if u.free / u.total < 0.10 and db.set("heal:disk", 1, nx=True, ex=6 * 3600):
        try:
            _run(["sudo", "-n", "journalctl", "--vacuum-size=200M"], 120)
        except Exception as e:
            log.info("auto-reparation disque : %s", scrub(e)[:100])
        u = shutil.disk_usage("/")
        send(chat_id, f"🔧 Le disque était presque plein : j'ai réduit les vieux journaux. Il reste {u.free // 2**30} Go libres.")
