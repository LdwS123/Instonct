"""Everything said to the bot, searchable for good. The Redis history only keeps the last turns, this is what lets it remember older conversations."""

import os
import re
import json
import time
from contextlib import closing
from datetime import datetime

from . import localdb
from .core import db, log, scrub

PATH = os.environ.get("CHAT_ARCHIVE_PATH") or os.path.join(os.path.expanduser("~"), "bots", "chat_archive.sqlite")
SCHEMA = """
CREATE TABLE IF NOT EXISTS msgs(id INTEGER PRIMARY KEY, chat INTEGER, at INTEGER, role TEXT, text TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS msgs_fts USING fts5(text, content='msgs', content_rowid='id', tokenize="unicode61 remove_diacritics 2");
CREATE TRIGGER IF NOT EXISTS msgs_ai AFTER INSERT ON msgs BEGIN INSERT INTO msgs_fts(rowid, text) VALUES (new.id, new.text); END;
"""
_STOP = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "a", "on", "je", "tu", "que", "qui", "quoi", "pour", "sur", "dans"}


def _db():
    return closing(localdb.connect(PATH, SCHEMA))


def record(chat_id, question, answer, from_file=False):
    """Called after each exchange. The archive must never get in the way of the answer, so a failure is only logged."""
    try:
        now = int(time.time())
        with _db() as con:
            con.executemany("INSERT INTO msgs(chat, at, role, text) VALUES (?,?,?,?)",
                            [(chat_id, now, role, scrub(text)) for role, text in (("fichier" if from_file else "utilisateur", question), ("bot", answer)) if text])
            con.commit()
    except Exception as e:
        log.warning("archive des conversations : %s", scrub(e)[:150])


def import_history():
    """First start only: what Redis still remembers becomes the beginning of the archive."""
    try:
        with _db() as con:
            if con.execute("SELECT 1 FROM msgs LIMIT 1").fetchone():
                return
            now = int(time.time())
            for key in db.scan_iter("hist:*"):
                for raw in db.lrange(key, 0, -1):
                    turn = json.loads(raw)
                    con.execute("INSERT INTO msgs(chat, at, role, text) VALUES (?,?,?,?)",
                                (int(key.split(":")[1]), now, "utilisateur" if turn["role"] == "user" else "bot", scrub(turn["parts"][0].get("text", ""))))
            con.commit()
    except Exception as e:
        log.warning("reprise de l'historique : %s", scrub(e)[:150])


def user_messages(chat_id, after_id, limit):
    """[(id, text)] written by the user, oldest first. Files they sent do not count: anyone could have written them."""
    with _db() as con:
        return [(r["id"], r["text"]) for r in con.execute("SELECT id, text FROM msgs WHERE chat=? AND role='utilisateur' AND id>? ORDER BY id LIMIT ?", (chat_id, after_id, limit))]


def search(chat_id, query, limit=8):
    limit = max(1, min(int(limit or 8), 20))
    with _db() as con:
        rows = []
        for any_word in (False, True):
            q = localdb.match_query(query, _STOP, any_word=any_word)
            if not q:
                return {"erreur": "donne au moins un mot a chercher"}
            rows = con.execute("SELECT m.at, m.role, snippet(msgs_fts, 0, '[', ']', '...', 40) AS extrait FROM msgs_fts JOIN msgs m ON m.id=msgs_fts.rowid "
                               "WHERE msgs_fts MATCH ? AND m.chat=? ORDER BY bm25(msgs_fts) - m.at / 15768000.0 LIMIT ?", (q, chat_id, limit)).fetchall()
            if rows:
                break
    return {"resultats": [{"date": f"{datetime.fromtimestamp(r['at']):%Y-%m-%d %H:%M}", "qui": r["role"], "extrait": re.sub(r"\s+", " ", r["extrait"])[:320]} for r in rows]}
