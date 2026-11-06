"""LinkedIn invitations with a note, in the real Chromium where the user logged in himself (see linkedin_invite.py).

The tool starts a slow background job and returns at once. It is guarded: the user must have asked for it in this very message (or said a plain yes to our proposal),
so a web page or a mail can never make the bot contact people. Heavy modules are imported inside the function (no import cycle with the catalog).
"""

from . import guard
from .kit_base import spec, text, whole

GROUPS = [
    (r"(?:linkedin|linked in).*(?:ajout|invit|connect|relation|reseau|note|founder|fondateur|contact)|(?:ajout|invit|connect).*(?:linkedin|linked in)|"
     r"\byc founders?|\bfounders? yc\b|\bfondateurs? yc\b|\byc fondateurs?|demandes? de connexion|demandes? (?:de )?(?:contact|relation)|"
     r"\binvitations? linkedin|stop linkedin|arrete.*invitations",
     {"linkedin_inviter"}),
]
SPECS = [
    spec("linkedin_inviter",
         "Demandes de connexion LinkedIn, avec note ou SANS note (sans_note=true). action : lancer (montre le plan, attend le OUI), etat, stop. {prenom}=prenom.",
         action="string!", recherche="string", note="string", sans_note="boolean", nombre="integer"),
]


FREE_ACTIONS = ("etat", "voir", "statut", "stop", "arreter", "arrete")
LOCKED = {"linkedin_inviter"}          # kits.tool refuses these (except FREE_ACTIONS) once the turn has read a web page, a mail or a file


def linkedin_inviter(chat_id, a):
    from . import linkedin_invite
    action = text(a, "action", "", 20).lower()
    if action in ("etat", "voir", "statut"):
        return linkedin_invite.state()
    if action in ("stop", "arreter", "arrete"):
        return linkedin_invite.stop()
    if action not in ("lancer", "lance", "start", "envoyer"):
        return {"erreur": "action inconnue : lancer, etat ou stop."}
    if guard.plain_yes():                                         # the user said yes to the note and the audience we showed him: start exactly that
        started = linkedin_invite.confirm(chat_id)
        if started:
            return started
    denied = guard.refusal("linkedin_invite")
    if denied:
        return denied
    from . import linkedin, screen
    try:
        known = linkedin.logged_in() or screen.active()           # with the screen open the cookie may not be on disk yet: the job itself notices a login wall
    except Exception:
        known = screen.active()
    if not known:
        return {"erreur": "LinkedIn n'est pas connecte dans mon navigateur. Dis a l'utilisateur de faire /connexion linkedin et de se connecter LUI-MEME (jamais de mot de passe dans le chat), puis de te redemander."}
    plain = str(a.get("sans_note", "")).lower() in ("true", "1", "oui", "yes")
    note = "" if plain else text(a, "note", "", 400)
    if not plain and not note:
        return {"erreur": "il faut une note (ecris-la avec l'utilisateur) ; s'il veut juste la demande de connexion, sans note : relance avec sans_note=true"}
    return linkedin_invite.propose(chat_id, text(a, "recherche", "", 80), note, whole(a, "nombre", 30, 1, 100))


FUNCS = {"linkedin_inviter": linkedin_inviter}
