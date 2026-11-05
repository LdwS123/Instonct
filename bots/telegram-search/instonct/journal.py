"""What the bot really did, tool by tool, with the result: the answer to "he said it was done, but was it?".

Only the tool name, whether it worked and a short scrubbed result are kept, never the arguments (they can hold a mail or a link).
Spoken and written direct orders (TV, music) are kept with the user's own words.
"""

import json
import time
from datetime import datetime

from .core import db, log, scrub

KEY = "journal"
KEEP = 80
SHOWN = 15
QUIET = {"get_status", "dates", "heure_monde", "calcul", "chat_search", "list_todos", "list_reminders"}     # reads that would drown the actions


def _add(entry):
    try:
        db.rpush(KEY, json.dumps(entry, ensure_ascii=False))
        db.ltrim(KEY, -KEEP, -1)
    except Exception as e:
        log.warning("journal : %s", scrub(e)[:120])               # the journal must never get in the way of an action


def tool(name, out):
    """Called after each tool call. `out` is what the tool returned, or None if it crashed."""
    if name in QUIET:
        return
    ok = isinstance(out, dict) and "erreur" not in out
    detail = str(out.get("erreur") or out.get("resultat") or out.get("statut") or "") if isinstance(out, dict) else ("plantage" if out is None else "")
    _add({"t": int(time.time()), "what": name, "ok": ok, "detail": scrub(detail)[:90]})


def order(said, done):
    """A direct order (no model): the words heard and the answer given."""
    _add({"t": int(time.time()), "what": "ordre : " + scrub(said)[:60], "ok": True, "detail": scrub(str(done))[:90]})


def report(n=SHOWN):
    rows = [json.loads(x) for x in db.lrange(KEY, -n, -1)]
    if not rows:
        return "Je n'ai encore rien fait que je puisse te montrer."
    lines = [f"{'OK ' if r['ok'] else 'RATE'} {datetime.fromtimestamp(r['t']):%d/%m %H:%M} {r['what']}" + (f" : {r['detail']}" if r["detail"] else "") for r in reversed(rows)]
    return "Mes dernieres actions (la plus recente en haut) :\n" + "\n".join(lines) + "\n\nRATE = l'outil a repondu une erreur : dans ce cas je ne dois pas dire que c'est fait."
