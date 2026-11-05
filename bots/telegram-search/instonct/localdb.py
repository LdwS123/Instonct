"""Small private SQLite files kept on the Mac mini (mail index, conversation archive)."""

import os
import sqlite3

_ready = set()


def connect(path, schema):
    """A new connection, one per call: bot threads never share one. The file is readable by this user only, it holds private mail."""
    if path not in _ready:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        os.close(os.open(path, os.O_CREAT | os.O_RDWR, 0o600))
        os.chmod(path, 0o600)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    if path not in _ready:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(schema)
        _ready.add(path)
    return con


def match_query(text, stop=(), any_word=False):
    """Turns free text into a safe FTS5 query: every word is quoted, so nothing the model writes is read as FTS syntax."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in str(text or "").lower()).split() if w not in stop]
    terms = [f'"{w}"*' if len(w) >= 3 else f'"{w}"' for w in words[:10]]
    return (" OR " if any_word else " AND ").join(terms)
