"""Google Calendar connection and the calendar tool."""

from .core import db, is_wa, scrub, send, tg

def google_prompt(chat_id, why):
    from . import gcal
    if is_wa(chat_id):
        send(chat_id, why + "\n\n1. Open this link, pick your account and accept:\n" + gcal.auth_url() +
             "\n2. An error page on 'localhost' shows up: that is normal.\n3. Copy that page's address and paste it here.")
        return
    tg("sendMessage", chat_id=chat_id, disable_web_page_preview=True,
       text=why + "\n\n1. Appuie sur le bouton, choisis ton compte et accepte.\n"
                  "2. Une page d'erreur 'localhost' s'affiche : c'est normal.\n"
                  "3. Copie l'adresse de cette page (barre du haut) et colle-la ici, dans la conversation.",
       reply_markup={"inline_keyboard": [[{"text": "\U0001F511 Autoriser l'agenda", "url": gcal.auth_url()}]]})


def google_finish(chat_id, url):
    from . import gcal
    try:
        gcal.exchange(url)
        db.delete("alert:google")
        send(chat_id, "C'est bon, ton agenda est reconnecte pour 7 jours.")
    except Exception as e:
        send(chat_id, "Ca n'a pas marche : " + scrub(e)[:150] + "\nEnvoie /google pour recommencer.")


def calendar_tool(name, args, links):
    from . import gcal
    if not gcal.connected():
        return {"erreur": "agenda Google pas encore connecte : dis a l'utilisateur d'envoyer /google"}
    try:
        if name == "calendar_list":
            return {"evenements": gcal.list_events(int(args.get("days", 1) or 1), args.get("start") or None) or "aucun evenement"}
        # actions visibles par d'autres ou irreversibles : refusees apres lecture d'un email (risque d'ordre cache),
        # et il faut un oui explicite de l'utilisateur (confirmed=true)
        invites = [str(x) for x in (args.get("invites") or [])]
        risky = name == "calendar_delete" or bool(invites)
        if risky and "(email lu)" in links:
            return {"erreur": "refuse : un email a ete lu dans cette conversation. Demande a l'utilisateur de le redire dans un nouveau message."}
        if risky and args.get("confirmed") is not True:
            return {"confirmation_requise": "demande a l'utilisateur de confirmer (oui) avant, puis rappelle l'outil avec confirmed=true"}
        if name == "calendar_delete":
            gcal.delete_event(str(args.get("id", "")))
            return {"resultat": "evenement supprime"}
        ev = gcal.create_event(str(args.get("title", "")), str(args.get("start", "")), int(args.get("duration_min", 60) or 60),
                               invites, args.get("meet") is True, str(args.get("description", "")), str(args.get("location", "")))
        return {"resultat": "evenement cree", "evenement": ev}
    except Exception as e:
        return {"erreur": scrub(e)[:200]}
