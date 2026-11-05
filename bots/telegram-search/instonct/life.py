"""Habits, routines, lists, notes and the morning briefing."""

import json
import re
import threading
import time
import uuid
from datetime import datetime
from datetime import timedelta

import requests

from .optional import habits
from .texts import METEO_CODES
from .core import db, is_wa, log, norm, scrub, send, tg
from . import brain, cast, commands, mail, monitor, music, sound, television

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def note(kind, key=""):
    """Compte une habitude (aucun appel IA). Ne casse jamais le reste."""
    try:
        if habits:
            habits.track(db, kind, key)
    except Exception as e:
        log.info("habitude : %s", scrub(e)[:100])


HABIT_TOOLS = {"weather": ("weather", "city"), "calendar_list": ("agenda", ""), "mail_list": ("mail", ""), "mail_search": ("mail", ""), "todo_list": ("todo", ""),
               "get_status": ("status", ""), "tv_remote": ("tv", "action"), "list_show": ("list", "list"), "routine_run": ("routine", "name")}


def note_tool(name, args):
    if name in HABIT_TOOLS:
        kind, field = HABIT_TOOLS[name]
        note(kind, str(args.get(field, "")) if field else "")
    elif name == "web_search" and str(args.get("kind", "")) == "news":
        note("news")


def habit_desc(c):
    k = c.get("kind")
    if k == "music":
        return f"mets « {c.get('key', '')} »"
    if k == "weather":
        return "te donne la meteo" + (f" de {c['key']}" if c.get("key") else "")
    return {"agenda": "te montre ton agenda du jour", "mail": "resume tes nouveaux emails", "news": "te donne les infos du jour",
            "todo": "te rappelle ce qu'il te reste a faire"}.get(k, "fais ca")


def parse_hhmm(s):
    m = re.search(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?", str(s or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        return None
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


def forecast_today(city):
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "fr"}, timeout=15).json()
    if not g.get("results"):
        return ""
    p = g["results"][0]
    d = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "forecast_days": 1,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"}, timeout=15).json()["daily"]
    rain = d["precipitation_probability_max"][0]
    return (f"{METEO_CODES.get(d['weather_code'][0], 'conditions variables')}, de {round(d['temperature_2m_min'][0])} a "
            f"{round(d['temperature_2m_max'][0])} C" + (f", pluie {rain} %" if rain is not None else ""))


def agenda_text():
    from . import gcal
    if not gcal.connected():
        return ""
    ev = gcal.list_events(1)
    return "\n".join(f"- {e['debut'][11:16]} {e['titre']}" + (f" ({e['lieu']})" if e.get("lieu") else "") for e in ev)


def briefing_text():
    cfg = db.hgetall("briefing")
    city = cfg.get("city") or "Paris"
    now = datetime.now()
    out = [f"Bonjour ! On est {JOURS[now.weekday()]} {now:%d/%m}."]
    for title, fn in (("Meteo a " + city, lambda: forecast_today(city)), ("Agenda du jour", agenda_text)):
        try:
            txt = fn()
            if txt:
                out.append(f"{title} : {txt}" if "\n" not in txt else f"{title} :\n{txt}")
            elif title == "Agenda du jour":
                out.append("Agenda du jour : rien de prevu.")
        except Exception as e:
            log.info("resume du matin (%s) : %s", title, scrub(e)[:100])
    todo = monitor.todo_texts()
    if todo:
        out.append("A faire :\n- " + "\n- ".join(todo[:10]))
    try:
        mails = mail.mail_list("", True, 15).get("emails")
        if isinstance(mails, list) and mails:
            imp = [m for m in mails if m.get("tri") != "PUB"]
            pubs = len(mails) - len(imp)
            if imp:
                out.append(f"{len(imp)} email(s) important(s) non lu(s) :\n"
                           + "\n".join(f"- {m['de']} : {m['sujet']}" + (f" ({m['tri']})" if m.get("tri") else "") for m in imp[:4])
                           + (f"\n({pubs} pub(s) ignoree(s))" if pubs else ""))
            else:
                out.append(f"Aucun email important ({pubs} pub(s) ignoree(s)).")
    except Exception as e:
        log.info("resume du matin (mails) : %s", scrub(e)[:100])
    return "\n\n".join(out)


def set_briefing(args, chat_id):
    if args.get("off") is True:
        db.hset("briefing", "on", "0")
        return "Resume du matin arrete."
    if args.get("now") is True:
        send(chat_id, briefing_text())
        return "Envoye."
    cfg = db.hgetall("briefing")
    t = parse_hhmm(args.get("time")) or cfg.get("time")
    if not t:
        wake = habits.wake_hour(db) if habits else None
        t = f"{wake if wake is not None and 5 <= wake <= 11 else 8:02d}:00"
    city = str(args.get("city") or cfg.get("city") or "Paris")[:60]
    db.hset("briefing", mapping={"on": "1", "time": t, "city": city})
    return f"Resume du matin active : chaque jour a {t.replace(':', ' h ')} (meteo de {city}, agenda, taches, emails)."


def check_briefing():
    cfg = db.hgetall("briefing")
    owner = db.get("owner_id")
    if cfg.get("on") != "1" or not owner:
        return
    now = datetime.now()
    try:
        hh, mm = (int(x) for x in cfg.get("time", "08:00").split(":"))
    except ValueError:
        return
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now <= target + timedelta(hours=3) and db.set(f"briefing_sent:{now:%Y-%m-%d}", 1, nx=True, ex=86400):
        threading.Thread(target=lambda: send(int(owner), briefing_text()), daemon=True).start()


def match_routine(text):
    n = norm(text)
    n = re.sub(r"^(?:lance |fais |execute |demarre )?(?:la |ma |mon )?(?:routine )", "", n).strip() or n
    names = db.hkeys("routines")
    if n in names:
        return n, json.loads(db.hget("routines", n))
    return None


def routine_prompt(name, r):
    return f"[Routine « {name} »] Execute maintenant, une par une avec tes outils, ces etapes : {r['steps']}. Puis confirme en une phrase."


def habits_report():
    out = (habits.summary(db) if habits else "") or "Je n'ai pas encore assez vu tes habitudes : il me faut quelques jours."
    auto = [json.loads(v) for v in db.hvals("hab:auto")]
    if auto:
        out += "\n\nCe que je fais deja tout seul, chaque jour :\n- " + "\n- ".join(f"a {a['hour']} h : {habit_desc(a)}" for a in auto)
    return out + "\n\nPour tout effacer : /habitudes effacer"


def habits_reset():
    n = 0
    for raw in db.zrange("tasks", 0, -1):
        if json.loads(raw).get("habit"):
            n += db.zrem("tasks", raw)
    if habits:
        habits.forget(db)
    return f"J'ai tout oublie de tes habitudes et arrete {n} action(s) automatique(s)."


def habit_answer(chat_id, yn, sid):
    raw = db.get(f"hab:pend:{sid}")
    if not raw:
        send(chat_id, "C'est trop ancien : je te le reproposerai si ca se repete.")
        return
    c = json.loads(raw)
    db.delete(f"hab:pend:{sid}")
    if yn != "yes":
        habits.mark(db, sid, "no")
        send(chat_id, "D'accord, je ne te le proposerai plus pendant deux mois.")
        return
    now = datetime.now()
    first = now.replace(hour=c["hour"], minute=0, second=0, microsecond=0)
    if first <= now:
        first += timedelta(days=1)
    item = json.dumps({"chat": chat_id, "prompt": f"[Habitude] {habit_desc(c)}", "repeat": 1440, "id": uuid.uuid4().hex,
                       "habit": sid, "action": c["kind"], "arg": c.get("key", "")}, ensure_ascii=False)
    db.zadd("tasks", {item: first.timestamp()})
    db.hset("hab:auto", sid, json.dumps(c, ensure_ascii=False))
    habits.mark(db, sid, "yes")
    send(chat_id, f"C'est fait : chaque jour a {c['hour']} h, je {habit_desc(c)}. /habitudes pour voir ou arreter.")


def check_habits(chat_id):
    """Propose (avec boutons Oui/Non) de faire tout seul une chose sure qu'il fait a la meme heure plusieurs jours."""
    now = datetime.now()
    if not habits or is_wa(chat_id) or not 9 <= now.hour < 21 or db.exists("hab:ping"):
        return
    if not db.set("hab:scan", 1, nx=True, ex=7200):
        return
    c = habits.detect(db)
    if not c:
        return
    habits.mark(db, c["id"], "asked")
    db.set(f"hab:pend:{c['id']}", json.dumps(c, ensure_ascii=False), ex=3 * 86400)
    db.set("hab:ping", 1, ex=20 * 3600)               # une seule proposition par jour
    tg("sendMessage", chat_id=chat_id, text=(f"J'ai remarque que vers {c['hour']} h tu me demandes souvent ca ({c['days']} jours sur les 14 derniers) : "
                                              f"je {habit_desc(c)}.\nTu veux que je le fasse tout seul chaque jour a {c['hour']} h ?"),
       reply_markup=television._markup([[("✅ Oui, fais-le", f"habit:yes:{c['id']}"), ("❌ Non merci", f"habit:no:{c['id']}")]]))


def run_habit(t):
    """Action automatique acceptee par l'utilisateur. Sans appel IA quand c'est possible."""
    chat, kind, arg = t["chat"], t["action"], t.get("arg", "")
    if kind == "music":
        if cast.tv_up():
            send(chat, f"J'allais mettre « {arg} », mais la tele est allumee : je ne touche a rien.")
        else:
            send(chat, music.music_play(arg, track=False))
    elif kind == "weather":
        send(chat, commands.meteo(arg or db.hget("briefing", "city") or "Paris"))
    elif kind == "todo":
        todo = monitor.todo_texts()
        send(chat, ("Il te reste :\n- " + "\n- ".join(todo[:15])) if todo else "Rien a faire pour l'instant, bravo.")
    elif kind == "agenda":
        send(chat, ("Ton agenda :\n" + agenda_text()) if agenda_text() else "Rien de prevu aujourd'hui.")
    else:
        sound.reply(chat, brain.ask(chat, "[Habitude automatique] " + t["prompt"].replace("[Habitude] ", "")))


def tool_life(chat_id, name, args, links):
    if name == "routine_save":
        if links:
            return {"erreur": "refuse : du contenu externe (web, email, document) a ete lu dans cette conversation. Demande a l'utilisateur de le redire dans un nouveau message."}
        n, steps = norm(str(args.get("name", ""))), str(args.get("steps", "")).strip()[:600]
        if not n or not steps:
            return {"erreur": "il faut un nom et des etapes"}
        if db.hlen("routines") >= 30 and not db.hexists("routines", n):
            return {"erreur": "30 routines maximum"}
        db.hset("routines", n, json.dumps({"steps": steps, "at": time.time()}, ensure_ascii=False))
        return {"resultat": f"routine « {n} » enregistree : il suffit de dire « {n} » pour la lancer"}
    if name == "routine_run":
        n = norm(str(args.get("name", "")))
        names = db.hkeys("routines")
        n = n if n in names else next((x for x in names if n and (n in x or x in n)), "")
        if not n:
            return {"erreur": "routine inconnue", "routines": names or "aucune"}
        return {"etapes": json.loads(db.hget("routines", n))["steps"], "consigne": "execute maintenant ces etapes avec tes outils"}
    if name == "routine_list":
        return {"routines": {k: json.loads(v)["steps"] for k, v in db.hgetall("routines").items()} or "aucune"}
    if name == "routine_delete":
        return {"resultat": f"{db.hdel('routines', norm(str(args.get('name', ''))))} routine supprimee"}
    if name in ("list_add", "list_show", "list_remove"):
        lst = norm(str(args.get("list") or "")) or ("courses" if name != "list_show" else "")
        if name == "list_show" and not lst:
            return {"listes": {k: db.lrange(f"list:{k}", 0, -1) for k in sorted(db.smembers("lists"))} or "aucune liste"}
        key = f"list:{lst}"
        if name == "list_add":
            items = [str(x).strip()[:100] for x in (args.get("items") or []) if str(x).strip()][:30]
            if items:
                db.rpush(key, *items)
                db.sadd("lists", lst)
            return {"resultat": f"ajoute a {lst}", lst: db.lrange(key, 0, -1)}
        if name == "list_show":
            return {lst: db.lrange(key, 0, -1) or "vide"}
        if args.get("clear") is True:
            db.delete(key)
            db.srem("lists", lst)
            return {"resultat": f"liste {lst} videe"}
        q = norm(str(args.get("item", "")))
        left = [x for x in db.lrange(key, 0, -1) if not (q and q in norm(x))]
        db.delete(key)
        if left:
            db.rpush(key, *left)
        return {"resultat": "retire", lst: left or "vide"}
    if name == "morning_briefing":
        return {"resultat": set_briefing(args, chat_id)}
    if name == "habits":
        return {"resultat": habits_reset() if args.get("action") == "reset" else habits_report()}
    return {"erreur": "outil inconnu"}
