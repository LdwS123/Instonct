"""Test setup: fake settings, and a throw-away Redis database (never the real one)."""
import os
import sys
import tempfile

os.environ.setdefault("TELEGRAM_TOKEN", "1:test")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM2_BASE_URL", "https://second.example/v1")
os.environ.setdefault("LLM2_API_KEY", "test-key-2")
os.environ.setdefault("LLM2_MODELS", "second-model")
_private = tempfile.mkdtemp(prefix="instonct-tests-")               # never the real mail index or conversation archive
os.environ["MAIL_INDEX_PATH"] = os.path.join(_private, "mail_index.sqlite")
os.environ["CHAT_ARCHIVE_PATH"] = os.path.join(_private, "chat_archive.sqlite")
os.environ["REDIS_DB"] = os.environ.get("TEST_REDIS_DB", "9")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def clean_redis():
    from instonct.core import db
    assert db.connection_pool.connection_kwargs["db"] == 9, "tests must never touch the real database"
    db.flushdb()
    yield
    db.flushdb()
