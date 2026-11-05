"""run_tool: routes a tool call from the model to the right implementation."""

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime

from . import plus
from .optional import tvremote
from .core import db, log, norm, scrub
from . import catalog, commands, google, guard, life, llm, mail, media, monitor, music, pagewatch, reminders, sound, system_tools, television, web

def run_tool(chat_id, name, args, links):
    log.info("outil %s %s", name, json.dumps(args, ensure_ascii=False)[:100])
    life.note_tool(name, args)
    try:
        if name in catalog.LIFE_TOOLS:
            return life.tool_life(chat_id, name, args, links)
        if name == "show_remote":
            television.send_remote(chat_id)
            return {"resultat": "telecommande affichee dans le chat"}
        if name in ("generate_image", "find_image", "send_photo"):
            return media.tool_image(chat_id, name, args)
        if name in ("favorite_add", "favorite_list", "favorite_remove"):
            return media.tool_favorite(name, args)
        if name == "web_search":
            res = llm.web_search(args.get("query", ""), n=max(1, min(10, int(args.get("limit", 4) or 4))), kind=str(args.get("kind", "text")))
            links.extend(r["href"] for r in res if r.get("href"))
            return {"resultats": [{"titre": r.get("title", ""), "texte": r.get("body", "")[:300], "lien": r.get("href", ""), "date": r.get("date", "")} for r in res]}
        if name in ("read_file", "write_file"):
            return system_tools.tool_files(name, args, tainted=bool(links))
        if name == "python_run":
            return system_tools.tool_python(chat_id, args.get("code", ""), tainted=bool(links))
        if name == "http_request":
            return system_tools.tool_http(chat_id, args, links)
        if name == "weather":
            return {"resultat": commands.meteo(str(args.get("city", "Paris")))}
        if name == "say_aloud":
            txt = sound.clean_for_speech(str(args.get("text", "")), 400)

            def _say():
                try:
                    sound.speak(txt, voice=sound.VOICE_FR, speed=150, limit=400)
                except Exception as e:
                    log.warning("say_aloud : %s", scrub(e))
            threading.Thread(target=_say, daemon=True).start()
            return {"resultat": "dit a voix haute"}
        if name in ("calendar_list", "calendar_create", "calendar_delete"):
            if name == "calendar_delete" and (no := guard.refusal("calendar_delete")):
                return no
            return google.calendar_tool(name, args, links)
        if name == "todo_add":
            txt = str(args.get("text", "")).strip()[:200]
            if not txt:
                return {"erreur": "tache vide"}
            if any(norm(json.loads(v)["text"]) == norm(txt) for v in db.hvals("todos")):
                return {"resultat": f"deja dans la liste : {txt}", "reste": monitor.todo_texts()}
            db.hset("todos", uuid.uuid4().hex[:8], json.dumps({"text": txt, "at": time.time()}, ensure_ascii=False))
            return {"resultat": f"note : {txt}", "reste": monitor.todo_texts()}
        if name == "todo_list":
            return {"reste_a_faire": monitor.todo_texts() or "rien, tout est fait"}
        if name == "todo_done":
            q = norm(str(args.get("text", "")))
            n = 0
            for k, v in db.hgetall("todos").items():
                if q and q in norm(json.loads(v)["text"]):
                    db.hdel("todos", k)
                    n += 1
                    if args.get("remove") is not True:
                        db.incr(f"todo_done:{datetime.now():%Y-%m-%d}")
            return {"resultat": f"{n} tache(s) " + ("supprimee(s)" if args.get("remove") is True else "terminee(s)"), "reste": monitor.todo_texts() or "rien, tout est fait"}
        if name in plus.NAMES:
            if name == "video_texte":
                links.append("(page web)")          # contenu externe : conversation "sensible"
            return plus.tool(db, name, args)
        if name == "mail_send":
            return mail.mail_send_request(chat_id, args)
        if name == "mail_reply":
            return mail.mail_reply_request(chat_id, args)
        if name == "mail_manage":
            ids = args.get("ids") or []
            ids = ids if isinstance(ids, list) else [ids]
            action = str(args.get("action", ""))
            if action in guard.MAIL_ACTIONS and (no := guard.refusal(action)):
                return no
            if action in ("delete", "spam"):
                risky = guard.unnamed_important(mail.important_among(ids), action)
                if risky:
                    return {"erreur": "refuse : ces mails sont importants et l'utilisateur ne les a pas designes. Montre-les-lui et demande s'il veut vraiment.", "mails_importants": risky[:10]}
            return mail.mail_manage(ids, action)
        if name == "mail_undo":
            return mail.mail_undo(str(args.get("query", "")), args.get("limit") or 10)
        if name == "mail_clean":
            refus = args.get("genre") == "refus" or "refus" in norm(str(args.get("genre", "")))
            if args.get("dry_run") is not True:
                no = guard.refusal("refus", extra_word="refus") if refus else guard.refusal("clean")
                if no:
                    return no
            if refus:
                return mail.mail_refus(args.get("days") or 365, args.get("limit") or 150, args.get("dry_run") is True)
            return mail.mail_clean(args.get("days", 30), args.get("limit", 100), args.get("dry_run") is True)
        if name in ("mail_list", "mail_read", "mail_search"):
            links.append("(email lu)")          # contenu externe : marque la conversation comme "sensible"
            if name == "mail_search":
                return mail.mail_search(str(args.get("query", "")), args.get("days", 365))
            if name == "mail_list":
                q = str(args.get("query", ""))
                return mail.mail_list(q, args.get("unread_only", not q) is not False, int(args.get("limit", 8) or 8), args.get("important_only") is True)
            return mail.mail_read(str(args.get("id", "")))
        if name == "play_music":
            return {"resultat": music.music_play(str(args.get("query", "")))}
        if name == "music_control":
            return {"resultat": music.music_control(args.get("action", "stop"))}
        if name == "set_output":
            return {"resultat": music.set_output(str(args.get("mode", "mac")))}
        if name == "tv_remote":
            act = str(args.get("action", "")).lower()
            if act in ("power_on", "power_off"):
                return {"resultat": television.tv_power(act[6:])}
            if act == "channel":
                return {"resultat": television.tv_channel(re.sub(r"\D", "", str(args.get("value", ""))) or 0)}
            if act == "type":
                try:
                    tvremote.text(str(args.get("value", "")))
                    return {"resultat": "texte tape"}
                except Exception as e:
                    return {"erreur": "la tele ne repond pas : " + type(e).__name__}
            if act in ("on", "off", "allume", "eteins", "eteindre", "allumer"):
                return {"resultat": television.tv_power("on" if act in ("on", "allume", "allumer") else "off")}
            res = television.tv_do(act, int(args.get("times", 1) or 1))
            return {"resultat": "touche envoyee (pas de verification)" if res == "OK" else res}
        if name == "change_volume":
            return {"resultat": sound.change_volume(int(args.get("delta", 15)))}
        if name == "set_volume":
            pct = max(0, min(100, int(args.get("percent", 80))))
            sound.set_volume(pct)
            return {"resultat": f"volume regle a {pct} %"}
        if name == "show_on_screen":
            commands.screen_message(str(args.get("text", "")))
            return {"resultat": "affiche"}
        if name == "set_reminder":
            try:
                mins = system_tools.minutes_until(args)
            except ValueError as e:
                return {"erreur": str(e)}
            return {"resultat": reminders.add_reminder(chat_id, f"{mins} {args.get('text', '')}")}
        if name == "get_status":
            return {"resultat": commands.status()}
        if name == "remember":
            if links:                                       # du contenu externe a ete lu : il pourrait avoir dicte ce "souvenir" (relu a chaque message)
                return {"erreur": "refuse : du contenu externe (web, mail, fichier) a ete lu dans cette conversation. Demande a l'utilisateur de le redire dans un nouveau message."}
            db.hset("memory", uuid.uuid4().hex[:8], str(args.get("fact", ""))[:300])
            return {"resultat": "retenu"}
        if name == "forget":
            if no := guard.refusal("forget"):
                return no
            n = 0
            for k, v in db.hgetall("memory").items():
                if str(args.get("text", "")).lower() in v.lower():
                    db.hdel("memory", k)
                    n += 1
            return {"resultat": f"{n} souvenir(s) oublie(s)"}
        if name == "send_file":
            path = system_tools._path(args.get("path", ""), system_tools.WORK)
            if system_tools.SECRET_PATH.search(path) or not os.path.isfile(path):
                return {"erreur": "fichier introuvable ou sensible"}
            return {"resultat": "envoye"} if media.send_local_file(chat_id, path) else {"erreur": "envoi refuse (fichier trop gros ? 50 Mo max)"}
        if name in catalog.EXTRA_TOOLS:
            return media.tool_extra(chat_id, name, args, links)
        if name == "schedule_task":
            rep_min = max(0, int(args.get("repeat_minutes", 0) or 0))
            if 0 < rep_min < 5:
                rep_min = 5
            try:
                delay = max(1, system_tools.minutes_until(args, "in_minutes"))
            except ValueError as e:
                return {"erreur": str(e)}
            db.zadd("tasks", {json.dumps({"chat": chat_id, "prompt": str(args.get("instruction", ""))[:300], "repeat": rep_min,
                                          "taint": bool(links), "id": uuid.uuid4().hex}): time.time() + delay * 60})
            return {"resultat": f"programmee dans {delay} min" + (f", puis toutes les {rep_min} min" if rep_min else "")}
        if name == "list_tasks":
            return {"taches": [f"{json.loads(r)['prompt']} (repete toutes les {json.loads(r)['repeat']} min)" if json.loads(r)["repeat"]
                               else json.loads(r)["prompt"] for r in db.zrange("tasks", 0, -1)] or "aucune"}
        if name == "cancel_tasks":
            if no := guard.refusal("cancel_tasks"):
                return no
            n = 0
            for r in db.zrange("tasks", 0, -1):
                if str(args.get("text", "")).lower() in json.loads(r)["prompt"].lower():
                    n += db.zrem("tasks", r)
            return {"resultat": f"{n} tache(s) annulee(s)"}
        if name == "fetch_url":
            url = str(args.get("url", ""))
            if not web.url_ok(url):
                return {"erreur": "adresse refusee (il faut un site public en http ou https)"}
            text = web.browse(url)
            links.append(url)
            start = max(0, int(args.get("start", 0) or 0))
            return {"texte": text[start:start + 5000], "longueur_totale": len(text),
                    "suite": f"relance avec start={start + 5000} pour lire la suite" if len(text) > start + 5000 else "fin de la page"}
        if name == "browser":
            return web.tool_browser(chat_id, args, links)
        if name == "page_watch":
            return pagewatch.tool_page_watch(args)
        if name == "run_command":
            return system_tools.tool_run_command(chat_id, str(args.get("command", "")), tainted=bool(links), background=args.get("background") is True)
    except Exception as e:
        log.warning("outil %s en erreur : %s", name, scrub(e))
        return {"erreur": scrub(e)[:200]}
    return {"erreur": "outil inconnu"}
