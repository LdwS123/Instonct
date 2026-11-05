"""Agent tools that touch the machine: shell, files, Python, HTTP requests."""

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import uuid
from datetime import datetime

import requests

from .core import db, log, scrub, send
from . import callbacks, web

# ---------------------------------------------------------------- agent (Gemini + outils)
SAFE_CMDS = {"ls", "df", "free", "uptime", "ps", "date", "whoami", "hostname", "uname", "du", "lsblk",
             "sensors", "pwd", "nproc", "lscpu", "who"}


def run_shell(cmd, timeout=120):
    try:
        env = {**os.environ, "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")}   # yt-dlp & co. du venv
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout, cwd=os.path.expanduser("~"), env=env)
    except subprocess.TimeoutExpired:
        return f"(arrete apres {timeout} s : trop long. Relance avec background=true pour une tache longue.)"
    return ((r.stdout + r.stderr).strip() or "(aucune sortie)")[-3000:] + ("" if r.returncode == 0 else f"\n(code {r.returncode})")


DANGEROUS = re.compile(
    r"\brm\s+-\w*[rf]|\bmkfs|\bdd\s+if=|\b(shutdown|reboot|poweroff|halt)\b|\bpasswd\b|chpasswd|\buserdel\b|\bvisudo\b|"
    r"/etc/sudoers|\bufw\b|sshd_config|authorized_keys|id_rsa|\.env\b|\b(curl|wget)\b.*\|\s*(sudo\s+)?(ba|z)?sh\b|:\(\)\s*\{|"
    r">\s*/dev/sd|chmod\s+-R\s+777|tailscale\s+(down|logout)|sites\.json|google_token|browser_cookies|\bsystemctl\s+(stop|disable|mask)\s+(ssh|sshd|tailscaled|fail2ban|bot-telegram)")


def tool_run_command(chat_id, command, tainted, force_confirm=False, background=False):
    """Execute la commande directement. Confirmation (/oui) seulement si elle est destructrice/sensible, ou si
    la conversation vient de lire du contenu web (une page piegee pourrait avoir glisse un ordre)."""
    if DANGEROUS.search(command) or tainted or force_confirm:
        db.setex(f"pending_cmd:{chat_id}", 300, command)
        callbacks.send_confirm(chat_id, f"Je vais lancer :\n{command[:3500]}\n\nC'est bon ?", callbacks.cmd_id(command), "Lancer")
        return {"statut": "en attente : l'utilisateur doit appuyer sur le bouton Oui. Dis-lui que tu attends sa confirmation."}
    if background:
        return start_job(chat_id, command)
    return {"sortie": run_shell(command)}


JOBS = os.path.expanduser("~/work/jobs")


def start_job(chat_id, command):
    """Tache longue : tourne en arriere-plan (1 h max), le bot envoie la fin du journal quand c'est fini."""
    os.makedirs(JOBS, exist_ok=True)
    jid = uuid.uuid4().hex[:6]
    path = f"{JOBS}/{jid}.log"

    def _run():
        try:
            with open(path, "w") as f:
                code = subprocess.run(["bash", "-c", command], stdout=f, stderr=subprocess.STDOUT,
                                      cwd=os.path.expanduser("~"), timeout=3600).returncode
        except subprocess.TimeoutExpired:
            code = "trop long, arrete apres 1 h"
        except Exception as e:
            code = scrub(e)[:100]
        try:
            tail = open(path, errors="replace").read()[-1500:].strip()
            send(chat_id, f"Tache longue terminee (code {code}) :\n{tail or '(aucune sortie)'}")
        except Exception as e:
            log.warning("fin de tache : %s", scrub(e))
    threading.Thread(target=_run, daemon=True).start()
    return {"resultat": f"lance en arriere-plan (tache {jid}), je previens des que c'est fini", "journal": path}


WORK = os.path.expanduser("~/work")
HOME = os.path.expanduser("~")
SAFE_DIRS = (WORK, os.path.expanduser("~/recus"), os.path.expanduser("~/exports"))
SECRET_PATH = re.compile(r"\.env\b|id_rsa|id_ed25519|/shadow|\.ssh/|sites\.json|google_token|browser_cookies|\.pem$|/etc/sudoers", re.I)
PY_DANGEROUS = re.compile(r"shutil\.rmtree|os\.(remove|unlink|rmdir|removedirs)\b|\.unlink\(|\.rmdir\(|os\.system\(\s*f?[\"'][^\"']*(rm|mkfs|dd|shutdown|reboot)\b")


def _path(p, base=HOME):
    p = os.path.expanduser(str(p).strip() or "~")
    return os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))


def tool_files(name, args, tainted):
    """read_file : lit un fichier (ou liste un dossier). write_file : ecrit un fichier (dans le dossier perso, hors secrets)."""
    path = _path(args.get("path", ""), WORK if name == "write_file" else HOME)
    if SECRET_PATH.search(path):
        return {"erreur": "fichier secret : acces refuse"}
    if name == "read_file":
        if os.path.isdir(path):
            items = sorted(os.listdir(path))[:100]
            return {"dossier": path, "contenu": [i + ("/" if os.path.isdir(os.path.join(path, i)) else "") for i in items]}
        if not os.path.isfile(path):
            return {"erreur": "fichier introuvable : " + path}
        with open(path, "rb") as f:
            raw = f.read(300000)
        if b"\0" in raw[:2000]:
            return {"erreur": f"fichier binaire ({os.path.getsize(path)} octets) : utilise send_file pour l'envoyer, ou python_run pour l'ouvrir"}
        text = raw.decode("utf-8", errors="replace")
        start = max(0, int(args.get("start", 0) or 0))
        return {"texte": text[start:start + 6000], "longueur": len(text),
                "suite": f"relance avec start={start + 6000}" if len(text) > start + 6000 else "fin du fichier"}
    # write_file
    in_home = path == HOME or path.startswith(HOME + os.sep)
    rel = os.path.relpath(path, HOME) if in_home else ""
    in_safe = any(path.startswith(d + os.sep) for d in SAFE_DIRS)
    protected = (not in_home or any(part.startswith(".") for part in rel.split(os.sep)) or rel.split(os.sep)[0] in ("bots", "depot", "lightpanda"))
    if (protected or tainted) and not in_safe:
        return {"erreur": "ecriture refusee ici (dossier systeme, cache ou du bot). Ecris dans ~/work, ou utilise run_command avec validation."
                          + (" Cette conversation a lu du contenu externe : seuls ~/work, ~/recus et ~/exports sont permis." if tainted else "")}
    content = str(args.get("content", ""))
    if len(content) > 2_000_000:
        return {"erreur": "contenu trop gros"}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a" if args.get("append") is True else "w", encoding="utf-8") as f:
        f.write(content)
    return {"resultat": f"{len(content)} caracteres ecrits dans {path}"}


def tool_python(chat_id, code, tainted):
    """Execute du Python (celui du bot : requests, etc.) dans ~/work. Demande /oui si le code supprime des fichiers."""
    code = str(code)
    if not code.strip():
        return {"erreur": "code vide"}
    os.makedirs(WORK, exist_ok=True)
    end = "PYEND" + uuid.uuid4().hex[:6]
    cmd = f"cd ~/work && {shlex.quote(sys.executable)} - <<'{end}'\n{code}\n{end}"
    return tool_run_command(chat_id, cmd, tainted, force_confirm=bool(PY_DANGEROUS.search(code)))


def http_do(method, url, headers, body):
    from urllib.parse import urljoin
    for _ in range(4):                                     # redirections suivies a la main : chaque etape reste verifiee
        if not web.url_ok(url):
            return {"erreur": "adresse refusee (site public en http ou https seulement)"}
        r = requests.request(method, url, headers=headers, data=(body.encode() if body else None), timeout=30,
                             allow_redirects=False, stream=True)
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            r.close()
            continue
        break
    raw = b""
    for chunk in r.iter_content(8192):
        raw += chunk
        if len(raw) > 200000:
            break
    r.close()
    return {"code_http": r.status_code, "type": r.headers.get("content-type", ""), "texte": raw.decode("utf-8", errors="replace")[:5000]}


def tool_http(chat_id, args, links):
    method = str(args.get("method", "GET")).upper()
    url = str(args.get("url", ""))
    if method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
        return {"erreur": "methode inconnue"}
    if not web.url_ok(url):
        return {"erreur": "adresse refusee (site public en http ou https seulement)"}
    try:
        headers = json.loads(args.get("headers") or "{}")
        assert isinstance(headers, dict)
    except (ValueError, AssertionError):
        return {"erreur": "headers doit etre un objet JSON en texte"}
    body = str(args.get("body") or "")
    if method in ("GET", "HEAD"):
        links.append(url)                                  # contenu externe : la conversation devient "sensible"
        return http_do(method, url, {str(k): str(v) for k, v in headers.items()}, "")
    if links:                                              # envoi de donnees apres lecture de contenu externe : validation par bouton
        p = {"method": method, "url": url, "headers": headers, "body": body}
        db.setex(f"pending_http:{chat_id}", 300, json.dumps(p))
        callbacks.send_confirm(chat_id, f"J'envoie une requete {method} a {url}\n{body[:600]}\n\nC'est bon ?", callbacks.cmd_id(json.dumps(p)), "Envoyer")
        return {"statut": "en attente : l'utilisateur doit appuyer sur le bouton Oui. Dis-lui que tu attends sa confirmation."}
    return http_do(method, url, {str(k): str(v) for k, v in headers.items()}, body)


def minutes_until(args, key="minutes"):
    """Delai en minutes : soit 'when' (AAAA-MM-JJ HH:MM, heure du Mac mini), soit le nombre donne dans args[key]."""
    when = str(args.get("when", "") or "").strip()
    if not when:
        return int(args.get(key, 1) or 1)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(when, fmt)
            break
        except ValueError:
            dt = None
    if dt is None:
        raise ValueError("format de date attendu : AAAA-MM-JJ HH:MM")
    secs = (dt - datetime.now()).total_seconds()
    if secs < 0:
        raise ValueError("cette date est deja passee")
    return max(1, int(secs // 60) + 1)
