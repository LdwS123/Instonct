"""The small tools added in bulk (kit_net, kit_server, kit_info, kit_calc, kit_media): one list of specs, one set of words, one entry point.

Each kit file defines SPECS (what the model sees), GROUPS (words that bring the tools in), FUNCS (name -> function(chat_id, args)).
Leaf-like on purpose: the catalog imports this file, so nothing here may import the catalog or llm at the top.
"""

from .core import log, scrub
from . import kit_apis, kit_auto, kit_calc, kit_dev, kit_docker, kit_fr, kit_fun, kit_info, kit_media, kit_net, kit_server

PARTS = (kit_auto, kit_net, kit_server, kit_info, kit_calc, kit_media, kit_docker, kit_apis, kit_fun, kit_dev, kit_fr)
SPECS = [s for part in PARTS for s in part.SPECS]
GROUPS = [g for part in PARTS for g in part.GROUPS]
FUNCS = {name: fn for part in PARTS for name, fn in part.FUNCS.items()}
TAINT = set().union(*(getattr(part, "TAINT", set()) for part in PARTS))
NAMES = set(FUNCS)


def tool(chat_id, name, args, links):
    """Runs one tool. A failure is an {"erreur": ...} (never an exception, never a made-up success)."""
    try:
        out = FUNCS[name](chat_id, args if isinstance(args, dict) else {})
    except Exception as e:
        log.warning("outil %s : %s", name, scrub(e))
        return {"erreur": f"{name} a echoue : {scrub(e)[:150]}"}
    if name in TAINT and "erreur" not in out:
        links.append("(page web)")                              # text written by strangers: the guarded tools stay locked for this conversation
    return out
