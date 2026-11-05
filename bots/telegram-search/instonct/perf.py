"""Where the time of an answer goes: model, each tool, voice. Only durations are kept, never the text of a message.

Before this, "the bot feels slower" could not be checked: the logs only had the time of each model call.
"""

import json
import statistics
import threading
import time
from contextlib import contextmanager

from .core import db, log, scrub, send, tg

KEY = "perf:turns"
KEEP = 100
TYPING_EVERY = 4              # Telegram hides "typing..." after about 5 seconds
TYPING_FOR = 180
SLOW_NOTICE = 25
_local = threading.local()


def start(kind):
    _local.turn = {"kind": kind, "t0": time.time(), "stages": {}, "models": 0, "tools": 0}


def add(stage, seconds):
    """Adds time to a stage of the current answer. Does nothing outside an answer (reminders, watchers)."""
    turn = getattr(_local, "turn", None)
    if turn is not None:
        turn["stages"][stage] = round(turn["stages"].get(stage, 0) + seconds, 2)
        if stage == "modele":
            turn["models"] += 1
        elif stage.startswith("outil:"):
            turn["tools"] += 1


@contextmanager
def timed(stage):
    t0 = time.time()
    try:
        yield
    finally:
        add(stage, time.time() - t0)


def finish():
    """Closes the current answer and keeps its numbers. Answers with no model and no tool (plain commands) are not kept."""
    turn = getattr(_local, "turn", None)
    _local.turn = None
    if turn is None or not turn["stages"]:
        return None
    total = round(time.time() - turn["t0"], 2)
    entry = {"at": int(turn["t0"]), "kind": turn["kind"], "total": total, "models": turn["models"], "tools": turn["tools"], "stages": turn["stages"]}
    try:
        db.lpush(KEY, json.dumps(entry))
        db.ltrim(KEY, 0, KEEP - 1)
    except Exception as e:
        log.warning("mesure de vitesse : %s", scrub(e)[:100])
    log.info("reponse en %.1f s (%s) %s", total, turn["kind"], json.dumps(turn["stages"], ensure_ascii=False)[:200])
    return entry


def kind_of(msg):
    return "vocal" if msg.get("voice") else "fichier" if (msg.get("photo") or msg.get("document")) else "texte"


def keep_alive(chat_id):
    """Keeps "typing..." on during a long answer and says once that it is still working. Returns the function that stops it."""
    done = threading.Event()

    def run():
        t0 = time.time()
        told = False
        while not done.wait(TYPING_EVERY) and time.time() - t0 < TYPING_FOR:
            try:
                tg("sendChatAction", chat_id=chat_id, action="typing")
                if not told and time.time() - t0 >= SLOW_NOTICE:
                    told = True
                    send(chat_id, "Je continue, c'est un peu long...")
            except Exception:
                return
    threading.Thread(target=run, daemon=True).start()
    return done.set


def _median(values):
    return round(statistics.median(values), 1) if values else 0


def report():
    """What /vitesse shows: medians over the last answers, and what took the longest."""
    turns = [json.loads(x) for x in db.lrange(KEY, 0, -1)]
    if not turns:
        return "Pas encore de mesure : pose-moi quelques questions puis refais /vitesse."
    lines = [f"Vitesse sur tes {len(turns)} dernieres reponses (mediane) :"]
    for kind, label in (("texte", "ecrit"), ("vocal", "vocal"), ("fichier", "fichier")):
        some = [t["total"] for t in turns if t["kind"] == kind]
        if some:
            lines.append(f"- {label} : {_median(some)} s ({len(some)} reponses, la plus longue {max(some):.0f} s)")
    by_stage = {}
    for t in turns:
        for stage, seconds in t["stages"].items():
            by_stage.setdefault(stage, []).append(seconds)
    total = sum(sum(v) for v in by_stage.values()) or 1
    lines.append("\nOu part le temps :")
    for stage, values in sorted(by_stage.items(), key=lambda kv: -sum(kv[1]))[:8]:
        lines.append(f"- {stage.replace('outil:', 'outil ')} : {100 * sum(values) / total:.0f} % (mediane {_median(values)} s)")
    return "\n".join(lines)
