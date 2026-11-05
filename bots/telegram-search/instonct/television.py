"""Virtual TV remote: keyboards, pairing, power, apps, channels."""

import re
import threading
import time

from .optional import tvremote
from .core import is_wa, log, norm, scrub, send, tg
from . import cast

# telecommande : "allume la tele", "eteins la tele", "ouvre youtube sur la tele", "telecommande"...
RE_TV_POWER = re.compile(r"(?:jessica )?(?:(?:peux tu|tu peux|pourrais tu|est ce que tu peux|veux tu|il faut que tu|je veux que tu|vas y|va)\s+)?"
                         r"(allume|allumer|eteins|eteint|eteindre|rallume|rallumer|reveille|reveiller)(?: moi)?(?: la| le)? ?(?:tele|television|tv)(?: maintenant| tout de suite| la)?")
RE_TV_APP = re.compile(r"(?:jessica )?(?:ouvre|lance|mets|met|va sur)(?: moi)?(?: l| la| le)? ?(youtube|netflix|prime(?: video)?|disney(?: plus)?)"
                       r"(?: sur| dans| de)?(?: la| le| l)? ?(?:tele|television|tv)")
RE_TV_CHANNEL = re.compile(r"(?:jessica )?(?:mets|met|va sur|passe sur|mets moi)(?: la)? ?(?:chaine|tele|tv) (?:numero |n )?(\d{1,3})")
RE_TV_REMOTE = re.compile(r"(?:jessica |steve )?(?:ou est |donne[ -]moi |donne |affiche[ -]moi |affiche |ouvre |montre[ -]moi |montre |sors[ -]moi |sors |mets[ -]moi |mets )?(?:la |ma |le )?(?:tele ?commande|remote)(?: virtuelle)?(?: ici| dans le chat| sur telegram)*")


RE_REMOTE_WORD = re.compile(r"\b(?:tele ?commande|remote)\b")
RE_NOT_REMOTE = re.compile(r"musique|chanson|son\b|volume|joue|playlist|explique|histoire|pourquoi|comment|prix|acheter|pile|marche pas|casse")


def wants_remote(text):
    """Vrai si la personne veut la telecommande (phrase courte qui la nomme), ex. 'passe moi la telecommande', 'non la telecommande pour la tele'."""
    t = norm(text)
    return bool(RE_TV_REMOTE.fullmatch(t) or (len(t.split()) <= 12 and RE_REMOTE_WORD.search(t) and not RE_NOT_REMOTE.search(t)))

APP_NAMES = {"youtube": "YouTube", "netflix": "Netflix", "prime": "Prime Video", "disney": "Disney+"}
_N = "tv:noop"
TV_KEYBOARD = [
    [("⏻ Marche/Arret", "tv:power"), ("🔀 Source", "tv:input"), ("🏠 Accueil", "tv:home")],
    [("·", _N), ("▲", "tv:up"), ("·", _N)],
    [("◀", "tv:left"), ("OK", "tv:ok"), ("▶", "tv:right")],
    [("↩ Retour", "tv:back"), ("▼", "tv:down"), ("☰ Menu", "tv:menu")],
    [("🔉 -", "tv:volume_down"), ("🔇 Muet", "tv:mute"), ("🔊 +", "tv:volume_up")],
    [("⏮", "tv:previous"), ("⏯", "tv:play_pause"), ("⏭", "tv:next")],
    [("YouTube", "tv:app:youtube"), ("Netflix", "tv:app:netflix"), ("Prime", "tv:app:prime"), ("Disney+", "tv:app:disney")],
    [("📺 Chaines, guide, plus...", "tv:page:2")],
]
TV_KEYBOARD2 = [
    [("1", "tv:1"), ("2", "tv:2"), ("3", "tv:3")],
    [("4", "tv:4"), ("5", "tv:5"), ("6", "tv:6")],
    [("7", "tv:7"), ("8", "tv:8"), ("9", "tv:9")],
    [("↺ Derniere", "tv:last"), ("0", "tv:0"), ("📺 TV", "tv:tv")],
    [("Chaine -", "tv:ch_down"), ("Chaine +", "tv:ch_up")],
    [("📋 Guide", "tv:guide"), ("ℹ️ Infos", "tv:info"), ("💬 Sous-titres", "tv:captions")],
    [("⏪", "tv:rewind"), ("⏯", "tv:play_pause"), ("⏩", "tv:forward")],
    [("HDMI 1", "tv:hdmi1"), ("HDMI 2", "tv:hdmi2"), ("HDMI 3", "tv:hdmi3")],
    [("🔍 Recherche", "tv:search"), ("⚙ Reglages", "tv:settings")],
    [("↩ Telecommande", "tv:page:1")],
]


def _markup(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def send_remote(chat_id):
    """Envoie la telecommande : des boutons sous le message."""
    if is_wa(chat_id):
        send(chat_id, "The TV remote buttons only exist on Telegram. Here you can still say 'volume up' or 'switch to channel 3'.")
        return
    if tvremote is None or not tvremote.paired():
        send(chat_id, "La telecommande n'est pas encore reliee a la tele. Allume la tele et envoie /pairer.")
        return
    tg("sendMessage", chat_id=chat_id, text="Telecommande de la tele", reply_markup=_markup(TV_KEYBOARD))
    threading.Thread(target=lambda: tv_do("warm"), daemon=True).start()     # connexion prete avant le premier appui


def tv_do(action, times=1):
    """Appuie sur une touche de la tele ('home', 'volume_up'...) ou ouvre une appli ('app:youtube'). Renvoie une phrase."""
    if tvremote is None:
        return "La telecommande n'est pas installee."
    if not tvremote.paired():
        return "La telecommande n'est pas encore reliee a la tele. Envoie /pairer."
    try:
        if action.startswith("app:") or action in APP_NAMES:
            app = action.removeprefix("app:")
            tvremote.launch(app)
            return f"J'ouvre {APP_NAMES.get(app, app)} sur la tele."
        if action == "warm":
            tvremote.warm()
            return "OK"
        for _ in range(max(1, min(20, times))):
            tvremote.key(action)
            if times > 1:
                time.sleep(0.25)
    except Exception as e:
        log.warning("telecommande : %s %s", type(e).__name__, scrub(e)[:100])
        return "La tele ne repond pas. Est-elle branchee et allumee ?"
    cast._tv_cache["t"] = 0.0
    return "OK"


def tv_channel(num):
    """Tape le numero d'une chaine avec les chiffres de la telecommande."""
    res = "OK"
    for d in str(int(num)):
        res = tv_do(d)
        if res != "OK":
            return res
        time.sleep(0.3)
    return f"Je mets la chaine {int(num)}."


def tv_power(want):
    """Allume ('on') ou eteint ('off') la tele, en verifiant d'abord dans quel etat elle est."""
    on = cast.tv_on()
    if want == "on" and on:
        return "La tele est deja allumee."
    if want == "off" and not on:
        return "La tele est deja eteinte."
    res = tv_do("power")
    if res != "OK":
        return res
    for _ in range(8):                                  # on verifie pour de vrai (jusqu'a ~12 s) au lieu de dire "fait" a l'aveugle
        time.sleep(1.5)
        cast._tv_cache["t"] = 0.0
        now_on = cast.tv_on()
        if now_on == (want == "on"):
            return "La tele est allumee." if want == "on" else "La tele est eteinte."
    if want == "on":
        return ("J'ai envoye l'ordre mais la tele ne s'est PAS allumee. Elle est peut-etre completement eteinte (plus de Wi-Fi) : "
                "il faut l'allumer une fois a la main, ou activer dans ses reglages l'option qui la laisse joignable par le reseau en veille.")
    return "J'ai envoye l'ordre mais la tele est toujours allumee."


def start_pairing(chat_id):
    if tvremote is None:
        send(chat_id, "La telecommande n'est pas installee.")
        return
    try:
        tvremote.start_pairing()
    except Exception as e:
        log.warning("appairage : %s %s", type(e).__name__, scrub(e)[:100])
        send(chat_id, "Je n'arrive pas a joindre la tele. Allume-la, attends 10 secondes et reessaie /pairer.")
        return
    send(chat_id, "Regarde la tele : un code de 6 caracteres s'affiche. Envoie-le moi comme ca : /code A1B2C3")


def finish_pairing(chat_id, code):
    code = re.sub(r"\W", "", code).upper()
    if len(code) != 6:
        send(chat_id, "Le code a 6 caracteres. Exemple : /code A1B2C3")
        return
    try:
        tvremote.finish_pairing(code)
    except Exception as e:
        log.warning("appairage : %s %s", type(e).__name__, scrub(e)[:100])
        send(chat_id, "Ca n'a pas marche (mauvais code ?). Envoie /pairer pour recommencer.")
        return
    send(chat_id, "C'est relie ! Voici ta telecommande :")
    send_remote(chat_id)


_tv_err = {"t": 0.0}
