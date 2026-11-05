"""The Mac mini itself: disk, busiest programs, services, a local backup (kept 7 days), the bot's own errors, what it really did."""

import os
import re
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime

from .core import db, log, scrub, send
from . import journal
from .kit_base import num, spec, text, whole

BACKUPS = os.path.expanduser("~/backups")
KEEP = 7
SOURCE = os.path.expanduser("~/bots")
REDIS_DUMP = "/var/lib/redis/dump.rdb"
SERVICES = ("bot-telegram", "searxng", "redis-server", "tailscaled", "ssh")
NO_SECRETS = ("--exclude=__pycache__", "--exclude=.env", "--exclude=*.env", "--exclude=google_token*", "--exclude=sites.json",
              "--exclude=browser_cookies*", "--exclude=*.pem", "--exclude=id_*")

SPECS = [
    spec("disk_report", "L'espace disque du Mac mini et les dossiers les plus gros."),
    spec("top_processes", "Les programmes qui utilisent le plus le processeur ou la memoire.", tri="string"),
    spec("services_status", "L'etat des services du Mac mini (bot, recherche, redis, tailscale, ssh).", service="string"),
    spec("backup_now", "Fait tout de suite une sauvegarde locale du bot (sans les mots de passe) et garde les 7 dernieres."),
    spec("log_errors", "Resume des erreurs du bot sur les dernieres heures.", heures="integer"),
    spec("mes_actions", "Ce que le bot a VRAIMENT fait recemment (ok ou rate) : pour verifier avant de dire 'c'est fait'.", nombre="integer"),
]
GROUPS = [
    (r"disque|espace|stockage|place (?:libre|restante)|memoire pleine", {"disk_report"}),
    (r"processus|programme.*(?:lourd|consomme)|ca rame|lent|cpu|processeur|ram\b|charge", {"top_processes"}),
    (r"service|est.il (?:lance|actif)|tourne|redis|tailscale|searxng|en marche", {"services_status"}),
    (r"sauvegarde|backup|copie de securite", {"backup_now"}),
    (r"erreur|bug|plante|log\b|logs\b|journal|probleme du bot|ca marche pas", {"log_errors", "mes_actions"}),
    (r"qu.as.tu (?:vraiment )?fait|tu as vraiment|vraiment fait|c.est vrai que tu|verifie ce que tu", {"mes_actions"}),
]


def _run(cmd, timeout=20):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def disk_report(chat_id, a):
    total, used, free = shutil.disk_usage("/")
    big = []
    for line in _run(["du", "-x", "-d", "1", "-B", "1M", os.path.expanduser("~")], 30).splitlines():
        size, _, path = line.partition("\t")
        if size.isdigit() and path.rstrip("/") != os.path.expanduser("~"):
            big.append((int(size), os.path.basename(path.rstrip("/"))))
    big.sort(reverse=True)
    return {"total_go": round(total / 2**30), "libre_go": round(free / 2**30), "utilise_pct": round(used / total * 100),
            "gros_dossiers": [f"{n} : {s} Mo" for s, n in big[:8]]}


def top_processes(chat_id, a):
    key = "-pmem" if text(a, "tri", "cpu", 10).lower() in ("ram", "memoire", "mem") else "-pcpu"
    rows = _run(["ps", "-eo", "pid,comm,pcpu,pmem", f"--sort={key}"]).splitlines()[1:9]
    return {"tri": "memoire" if key == "-pmem" else "processeur",
            "programmes": [{"nom": p[1], "cpu_pct": float(p[2]), "ram_pct": float(p[3])} for p in (r.split(None, 3) for r in rows) if len(p) == 4]}


def services_status(chat_id, a):
    wanted = text(a, "service", "", 40)
    names = (wanted,) if re.fullmatch(r"[a-z0-9@._-]+", wanted) else SERVICES
    return {"services": {n: (_run(["systemctl", "is-active", n], 8).strip() or "inconnu") for n in names}}


def make_backup(source=SOURCE, folder=BACKUPS):
    """A tar.gz of the bot's code (never the key files) + a copy of the Redis dump when readable. Returns (path, details)."""
    os.makedirs(folder, mode=0o700, exist_ok=True)
    path = os.path.join(folder, f"instonct-{datetime.now():%Y%m%d-%H%M%S}.tar.gz")
    dump, extra = os.path.join(folder, "redis-dump.tmp"), []
    if subprocess.run(["sudo", "-n", "test", "-f", REDIS_DUMP], capture_output=True, timeout=10).returncode == 0:          # the folder is not readable by the bot itself
        try:
            db.bgsave()
        except Exception:
            pass
        if subprocess.run(["sudo", "-n", "cp", REDIS_DUMP, dump], capture_output=True, timeout=30).returncode == 0:
            subprocess.run(["sudo", "-n", "chown", str(os.getuid()), dump], capture_output=True, timeout=10)
            extra = ["-C", folder, "redis-dump.tmp", "--transform=s/redis-dump.tmp/redis-dump.rdb/"]
    r = subprocess.run(["tar", "-czf", path, *NO_SECRETS, "-C", source, "telegram-search", *extra], capture_output=True, text=True, timeout=240)
    if os.path.exists(dump):
        os.remove(dump)
    if r.returncode not in (0, 1) or not os.path.exists(path):          # tar exits 1 when a file changed while it was read: the archive is still good
        raise RuntimeError(r.stderr[-200:] or "tar a echoue")
    os.chmod(path, 0o600)
    for old in sorted(f for f in os.listdir(folder) if f.startswith("instonct-") and f.endswith(".tar.gz"))[:-KEEP]:
        os.remove(os.path.join(folder, old))
    return path, {"redis": bool(extra), "taille_mo": round(os.path.getsize(path) / 2**20, 1)}


def backup_now(chat_id, a):
    path, details = make_backup()
    return {"fichier": path, **details, "gardees": KEEP, "note": "copie locale seulement ; les cles et mots de passe ne sont pas dedans"}


def check_backup(chat_id):
    """Monitor tick: one silent backup a night (a message only if it fails)."""
    if not db.set("backup:nightly", 1, nx=True, ex=22 * 3600):
        return
    if not 2 <= datetime.now().hour < 6:
        db.delete("backup:nightly")
        return
    try:
        make_backup()
    except Exception as e:
        log.warning("sauvegarde de nuit : %s", scrub(e))
        send(chat_id, "La sauvegarde de cette nuit a echoue. Dis-moi 'sauvegarde maintenant' pour voir l'erreur.")


def log_errors(chat_id, a):
    hours = whole(a, "heures", 24, 1, 168)
    out = _run(["journalctl", "-u", "bot-telegram", "--since", f"{hours} hours ago", "--no-pager", "-o", "cat"], 30)
    seen = Counter()
    for line in out.splitlines():
        if re.search(r"error|erreur|traceback|exception|warning", line, re.I):
            seen[re.sub(r"\d+", "N", scrub(line))[:140]] += 1
    return {"heures": hours, "lignes_en_erreur": sum(seen.values()), "les_plus_frequentes": [f"{n}x {m}" for m, n in seen.most_common(8)]}


def mes_actions(chat_id, a):
    return {"journal": journal.report(whole(a, "nombre", journal.SHOWN, 1, journal.KEEP))}


FUNCS = {"disk_report": disk_report, "top_processes": top_processes, "services_status": services_status, "backup_now": backup_now,
         "log_errors": log_errors, "mes_actions": mes_actions}
