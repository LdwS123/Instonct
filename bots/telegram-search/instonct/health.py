"""/sante and `python bot.py doctor`: what works and what does not, in plain words. Spends no model tokens and never prints a secret."""

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

import requests

from .config import GEMINI_KEY, MODEL_API, STT_API_KEY, STT_BASE_URL
from .core import db, scrub, tg

OK, BAD, OFF = "OK", "PANNE", "absent"
REQUIRED = ("Redis", "Telegram", "Modeles")


def _key_works(base, key):
    """Listing the models costs no tokens and proves the key is accepted."""
    host = urlparse(base).hostname or base
    try:
        code = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=8).status_code
    except requests.RequestException as e:
        return BAD, f"{host} : injoignable ({scrub(type(e).__name__)})"
    if code == 200:
        return OK, host
    return BAD, f"{host} : {'cle refusee' if code in (401, 403) else f'code {code}'}"


def _providers():
    keys = sorted(set(MODEL_API.values()))
    if not keys:
        return BAD, "aucune cle de modele (LLM_API_KEY)"
    seen = [_key_works(base, key) for base, key in keys]
    state = OK if any(s == OK for s, _ in seen) else BAD
    resting = [m for m in MODEL_API if db.exists(f"cool:{m}")]
    return state, " ; ".join(d for _, d in seen) + (f" ; en pause : {', '.join(resting)}" if resting else "")


def _gemini():
    if not GEMINI_KEY:
        return OFF, "pas de secours Gemini"
    try:
        code = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": GEMINI_KEY}, timeout=8).status_code
    except requests.RequestException:
        return BAD, "injoignable"
    return (OK, "secours pret") if code == 200 else (BAD, f"code {code}")


def _voice():
    if not STT_API_KEY:
        return OFF, "pas de cle pour ecouter les vocaux"
    return _key_works(STT_BASE_URL, STT_API_KEY)


def _google():
    from . import gcal
    if not gcal.connected():
        return OFF, "pas connecte : /google"
    return (OK, f"jeton de {gcal.token_age_days() or 0:.0f} jour(s)") if gcal.token_ok() else (BAD, "acces expire : /google")


def _mailbox():
    from . import mail, mailindex
    boxes = mail._mail_accounts()
    if not boxes:
        return OFF, "pas de MAIL_USER"
    return OK, f"{len(boxes)} boite(s), index : {mailindex.status()['mails_dans_l_index']} mails"


def _browsers():
    from . import screen, web
    light = os.path.exists(web.LIGHTPANDA)
    full = bool(screen._chrome())
    if light and full:
        return OK, "Lightpanda et Chromium"
    return (OK if light or full else OFF), ("Lightpanda" if light else "pas de Lightpanda") + ", " + ("Chromium" if full else "pas de Chromium")


def _tailscale():
    if not shutil.which("tailscale"):
        return OFF, "pas installe : pas d'ecran a distance"
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return BAD, "ne repond pas"
    return (OK, "actif") if out.returncode == 0 and out.stdout.strip() else (BAD, "installe mais eteint")


def _machine():
    disk = shutil.disk_usage(os.path.expanduser("~"))
    free_gb = disk.free / 1e9
    mem = ""
    try:
        with open("/proc/meminfo") as f:
            info = dict(line.split(":", 1) for line in f)
        mem = f", {int(info['MemAvailable'].split()[0]) // 1024} Mo de memoire libre"
    except (OSError, KeyError, ValueError):
        pass
    return (OK if free_gb > 2 else BAD), f"{free_gb:.0f} Go de disque libre{mem}"


CHECKS = (("Redis", lambda: (OK, "repond") if db.ping() else (BAD, "ne repond pas")),
          ("Telegram", lambda: (OK, "@" + tg("getMe")["result"]["username"])),
          ("Modeles", _providers), ("Secours", _gemini), ("Vocaux", _voice), ("Agenda", _google), ("Mail", _mailbox),
          ("Navigateurs", _browsers), ("Tailscale", _tailscale), ("Machine", _machine))


def run():
    """[(name, state, detail)]. A check that crashes is a failed check, never a crashed report."""
    rows = []
    for name, check in CHECKS:
        try:
            state, detail = check()
        except Exception as e:
            state, detail = BAD, scrub(e)[:120]
        rows.append((name, state, detail))
    return rows


def report(rows=None):
    rows = run() if rows is None else rows
    broken = [r for r in rows if r[1] == BAD]
    head = "Tout marche." if not broken else f"{len(broken)} chose(s) en panne."
    return head + "\n\n" + "\n".join(f"{state} {name} : {detail}" for name, state, detail in rows)


def main():
    rows = run()
    print(report(rows))
    return 1 if any(n in REQUIRED and s == BAD for n, s, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
