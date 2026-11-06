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


_LOUD = {"aplay", "espeak-ng", "espeak", "paplay", "mpv", "play", "cvlc", "ffplay", "speaker-test", "pw-play"}


def _is_loud(args):
    argv = [str(a) for a in args] if isinstance(args, (list, tuple)) else str(args).split()
    if not argv:
        return False
    name = os.path.basename(argv[0])
    return name in _LOUD or (name in ("amixer", "pactl", "wpctl") and any(w in argv for w in ("sset", "set", "set-sink-volume", "set-volume", "set-sink-mute")))


@pytest.fixture(autouse=True)
def silence(monkeypatch):
    """Nothing in the suite may ever make the machine speak, play, beep or change the volume (people sleep next to the Mac mini)."""
    import subprocess
    real_run, real_popen = subprocess.run, subprocess.Popen

    class _Quiet:
        returncode, stdout, stderr, pid = 0, "", "", 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            pass

        kill = terminate

        def communicate(self, *a, **k):
            return "", ""

    def run(args, *a, **k):
        if _is_loud(args):
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, *a, **k)

    def popen(args, *a, **k):
        return _Quiet() if _is_loud(args) else real_popen(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
