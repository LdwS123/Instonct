"""Inline-button callbacks and the Yes/No confirmation flow for risky actions."""

import hashlib
import json
import time

from .optional import whatsapp
from .core import db, is_wa, log, scrub, send, tg, wa_to
from . import automate, life, mail, rubriques, system_tools, television, web

def cmd_id(command):
    return hashlib.md5(command.encode()).hexdigest()[:6]


def send_confirm(chat_id, text, pid, yes_label):
    """Message avec deux boutons : valider / annuler (le bouton ne marche que pour CE brouillon)."""
    if is_wa(chat_id):
        whatsapp.send_buttons(wa_to(chat_id), text, [(f"ok:yes:{pid}", "\u2705 Oui"), (f"ok:no:{pid}", "\u274c Non")])
        return
    tg("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True,
       reply_markup=television._markup([[("\u2705 Oui", f"ok:yes:{pid}"), ("\u274c Non", f"ok:no:{pid}")]]))


def confirm_yes(chat_id, pid=None):
    """Valide ce qui attend : mail ou commande. pid = identifiant du bouton (rien ne part s'il ne correspond pas)."""
    pmail = db.get(f"pending_mail:{chat_id}")
    pending = db.get(f"pending_cmd:{chat_id}")
    pweb = db.get(f"pending_web:{chat_id}")
    phttp = db.get(f"pending_http:{chat_id}")
    if pmail and (pid is None or json.loads(pmail).get("id") == pid):
        db.delete(f"pending_mail:{chat_id}")
        try:
            p = json.loads(pmail)
            mail.mail_send_now(p)
            send(chat_id, "Email envoye a " + ", ".join(p["to"]) + ".")
        except Exception as e:
            send(chat_id, "L'envoi a echoue : " + scrub(e)[:200])
    elif pending and (pid is None or cmd_id(pending) == pid):
        db.delete(f"pending_cmd:{chat_id}")
        send(chat_id, "Execution...")
        send(chat_id, system_tools.run_shell(pending))
    elif pweb and (pid is None or cmd_id(pweb) == pid):
        db.delete(f"pending_web:{chat_id}")
        send(chat_id, "Je valide...")
        web.web_run_pending(chat_id, json.loads(pweb))
    elif phttp and (pid is None or cmd_id(phttp) == pid):
        db.delete(f"pending_http:{chat_id}")
        p = json.loads(phttp)
        try:
            out = system_tools.http_do(p["method"], p["url"], {str(k): str(v) for k, v in p["headers"].items()}, p["body"])
            send(chat_id, f"Reponse {out.get('code_http', '')} : {out.get('texte') or out.get('erreur', '')}"[:800])
        except Exception as e:
            send(chat_id, "La requete a echoue : " + scrub(e)[:200])
    else:
        send(chat_id, "Rien a valider (c'est trop ancien ou deja fait).")


def confirm_no(chat_id):
    db.delete(f"pending_cmd:{chat_id}")
    db.delete(f"pending_mail:{chat_id}")
    db.delete(f"pending_web:{chat_id}")
    db.delete(f"pending_http:{chat_id}")
    send(chat_id, "Annule.")


def handle_callback(cq):
    """Appui sur un bouton de la telecommande."""
    data = cq.get("data") or ""
    try:
        tg("answerCallbackQuery", callback_query_id=cq["id"])          # tout de suite : le bouton ne reste pas "charge"
    except Exception as e:
        log.info("reponse au bouton : %s", scrub(e)[:100])
    if str((cq.get("from") or {}).get("id")) != db.get("owner_id"):
        return
    msg = cq.get("message") or {}
    if data.startswith("ok:"):
        try:
            tg("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"], reply_markup={"inline_keyboard": []})
        except Exception as e:
            log.info("boutons : %s", scrub(e)[:100])
        _, yn, pid = (data.split(":") + ["", ""])[:3]
        chat_id = msg["chat"]["id"]
        if yn == "yes":
            confirm_yes(chat_id, pid)
        else:
            confirm_no(chat_id)
        return
    if data.startswith("habit:"):
        try:
            tg("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"], reply_markup={"inline_keyboard": []})
        except Exception as e:
            log.info("boutons : %s", scrub(e)[:100])
        _, yn, sid = (data.split(":") + ["", ""])[:3]
        life.habit_answer(msg["chat"]["id"], yn, sid)
        return
    if data.startswith("menu:"):                                         # a category page replaces the menu in place
        text, rows = rubriques.page(data[5:])
        try:
            tg("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"], text=text[:4000], reply_markup=television._markup(rows))
        except Exception as e:
            log.info("menu : %s", scrub(e)[:100])
        return
    if data.startswith("go:"):
        automate.press(msg["chat"]["id"], data[3:])
        return
    if not data.startswith("tv:") or data == television._N:
        return
    if data.startswith("tv:page:"):                                      # change de page du clavier sur place
        rows = television.TV_KEYBOARD2 if data.endswith("2") else television.TV_KEYBOARD
        try:
            tg("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"], reply_markup=television._markup(rows))
        except Exception as e:
            log.info("changement de page : %s", scrub(e)[:100])
        return
    res = television.tv_do(data[3:])
    if res != "OK" and msg and time.time() - television._tv_err["t"] > 10:        # un seul message d'erreur, pas dix
        television._tv_err["t"] = time.time()
        send(msg["chat"]["id"], res)
