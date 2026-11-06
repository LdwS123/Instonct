"""Docker on the Mac mini: a short list of free open-source apps that the bot can install, start, stop and remove, by words.

Safety, in code and not in a prompt:
- only apps of the APPS list exist: the user's words never reach the docker command line (no free image name, no free option);
- every container gets a memory ceiling, one CPU at most, no new privileges, small logs, and a port bound to the Tailscale address only
  (never 0.0.0.0): the apps are reachable from the user's own devices, not from the home network or the internet;
- no app that needs the Docker socket or a fixed default password is in the list;
- the containers that were there before the bot (uptime-kuma, adguard, navidrome) can be listed and their logs read, never stopped or removed;
- starting, stopping and removing are guarded: the user must have asked for it in this very message (see guard.py).
"""

import os
import re
import shutil
import subprocess
import threading
import time

from .core import db, log, scrub, send
from . import guard
from .kit_base import spec, text, whole

PREFIX = "inst-"
FOREIGN = ("uptime-kuma", "adguard", "navidrome")              # installed by hand before the bot: visible, never touched
MAX_RUNNING = 6                                                  # the Mac mini has 4.6 GB of RAM
ROOM_MB = 400                                                    # memory that must stay free besides the app's own ceiling
EXPORTS = os.path.expanduser("~/exports")


def _app(host, image, port, mem, desc, words, vol=(), cmd=(), env=None, bind=None):
    return {"host": host, "image": image, "port": port, "mem": mem, "desc": desc, "words": words, "vol": tuple(vol), "cmd": tuple(cmd), "env": env or {}, "bind": bind}


# name -> app. The host ports never change once chosen (the user bookmarks the addresses): add new apps at the end, with the next port.
APPS = {
    "whoami": _app(9101, "traefik/whoami:latest", 80, "32m", "Tout petit serveur de test : montre ce qu'il recoit.", "test reseau"),
    "it-tools": _app(9102, "corentinth/it-tools:latest", 80, "64m", "80 outils de developpeur dans le navigateur (hash, JWT, couleurs, cron, regex...).", "outils developpeur convertisseur hash"),
    "cyberchef": _app(9103, "ghcr.io/gchq/cyberchef:latest", 80, "128m", "Le couteau suisse des donnees : encoder, decoder, chiffrer, analyser.", "encodage decodage donnees"),
    "excalidraw": _app(9104, "excalidraw/excalidraw:latest", 80, "128m", "Tableau blanc pour dessiner des schemas a la main.", "dessin schema tableau blanc"),
    "mermaid": _app(9105, "ghcr.io/mermaid-js/mermaid-live-editor:latest", 8080, "128m", "Fait des diagrammes a partir de texte (flux, sequences, Gantt).", "diagramme schema texte"),
    "drawio": _app(9106, "jgraph/drawio:latest", 8080, "512m", "Editeur de diagrammes complet (type Visio).", "diagramme organigramme visio"),
    "homepage": _app(9107, "ghcr.io/gethomepage/homepage:latest", 3000, "128m", "Page d'accueil avec les liens de tous tes services.", "tableau de bord accueil", vol=("/app/config",), env={"HOMEPAGE_ALLOWED_HOSTS": "{ip}:{host}"}),
    "memos": _app(9108, "neosmemo/memos:stable", 5230, "128m", "Notes rapides facon micro-blog, privees.", "notes memo bloc-notes", vol=("/var/opt/memos",)),
    "freshrss": _app(9109, "freshrss/freshrss:latest", 80, "192m", "Lecteur de flux RSS : toutes tes sources d'actualite au meme endroit.", "rss actualite lecteur", vol=("/var/www/FreshRSS/data", "/var/www/FreshRSS/extensions")),
    "ntfy": _app(9110, "binwiederhier/ntfy:latest", 80, "64m", "Notifications par simple HTTP vers le telephone.", "notification push alerte", cmd=("serve",), vol=("/var/cache/ntfy",)),
    "changedetection": _app(9111, "ghcr.io/dgtlmoon/changedetection.io:latest", 5000, "256m", "Surveille des pages web et previent quand elles changent.", "surveiller page changement prix", vol=("/datastore",)),
    "jellyfin": _app(9112, "jellyfin/jellyfin:latest", 8096, "1g", "Serveur de films et series (lourd pour ce Mac mini).", "films series video mediatheque", vol=("/config", "/cache")),
    "audiobookshelf": _app(9113, "ghcr.io/advplyr/audiobookshelf:latest", 80, "256m", "Bibliotheque de livres audio et de podcasts.", "livres audio podcast", vol=("/config", "/metadata", "/audiobooks")),
    "trilium": _app(9114, "triliumnext/notes:latest", 8080, "256m", "Prise de notes en arbre, tres complete.", "notes wiki base de connaissances", vol=("/home/node/trilium-data",)),
    "gitea": _app(9115, "gitea/gitea:latest", 3000, "384m", "Ton propre GitHub : depots git, tickets, revues.", "git depot code github", vol=("/data",)),
    "dashy": _app(9116, "lissy93/dashy:latest", 8080, "256m", "Tableau de bord personnalisable pour tes services.", "tableau de bord accueil", vol=("/app/user-data",)),
    "heimdall": _app(9117, "lscr.io/linuxserver/heimdall:latest", 80, "128m", "Lanceur d'applications : une page de raccourcis.", "raccourcis lanceur accueil", vol=("/config",)),
    "privatebin": _app(9118, "privatebin/nginx-fpm-alpine:latest", 8080, "128m", "Pastebin chiffre : partager un texte qui s'autodetruit.", "pastebin partage texte secret", vol=("/srv/data",)),
    "etherpad": _app(9119, "etherpad/etherpad:latest", 9001, "384m", "Edition de texte a plusieurs en direct.", "texte collaboratif pad", vol=("/opt/etherpad-lite/var",)),
    "node-red": _app(9120, "nodered/node-red:latest", 1880, "384m", "Automatisations par blocs a relier (domotique, API, alertes).", "automatisation flux domotique", vol=("/data",)),
    "adminer": _app(9121, "adminer:latest", 8080, "64m", "Interface web pour gerer une base de donnees.", "base de donnees sql", env={}),
    "web-exports": _app(9122, "nginx:alpine", 80, "32m", "Partage le dossier ~/exports du Mac mini en lecture seule.", "partager dossier fichiers web", bind=(EXPORTS, "/usr/share/nginx/html")),
    "openspeedtest": _app(9123, "openspeedtest/latest:latest", 3000, "128m", "Test de debit entre ton appareil et le Mac mini.", "debit vitesse wifi"),
    "librespeed": _app(9124, "lscr.io/linuxserver/librespeed:latest", 80, "128m", "Autre test de debit (telechargement, envoi, latence).", "debit vitesse wifi", vol=("/config",)),
    "actual": _app(9125, "actualbudget/actual-server:latest", 5006, "256m", "Budget personnel : suivre ses depenses par categorie.", "budget argent depenses finance", vol=("/data",)),
    "metube": _app(9126, "ghcr.io/alexta69/metube:latest", 8081, "384m", "Telecharge des videos et du son (YouTube et autres) depuis une page web.", "telecharger video youtube mp3", vol=("/downloads",)),
    "silverbullet": _app(9127, "ghcr.io/silverbulletmd/silverbullet:latest", 3000, "192m", "Notes en markdown, programmables.", "notes markdown wiki", vol=("/space",)),
    "mailpit": _app(9128, "axllent/mailpit:latest", 8025, "64m", "Boite mail de test qui attrape les mails sans les envoyer.", "mail test smtp", vol=("/data",)),
    "wallos": _app(9129, "bellamy/wallos:latest", 80, "128m", "Suivi des abonnements et de leur cout.", "abonnements depenses budget", vol=("/var/www/html/db", "/var/www/html/images/uploads/logos")),
    "smokeping": _app(9130, "lscr.io/linuxserver/smokeping:latest", 80, "192m", "Graphiques de la qualite de la connexion internet dans le temps.", "latence ping connexion reseau", vol=("/config", "/data")),
    "rsshub": _app(9131, "diygod/rsshub:latest", 1200, "384m", "Fabrique des flux RSS pour des sites qui n'en ont pas.", "rss flux sites reseaux sociaux"),
    "whoogle": _app(9132, "benbusby/whoogle-search:latest", 5000, "128m", "Recherche Google sans pisteurs ni publicites.", "recherche google prive"),
    "homebox": _app(9133, "ghcr.io/sysadminsmedia/homebox:latest", 7745, "128m", "Inventaire de la maison : objets, garanties, rangement.", "inventaire maison objets garantie", vol=("/data",)),
    "kavita": _app(9134, "jvmilazz0/kavita:latest", 5000, "384m", "Lecteur de BD, mangas et livres.", "bd manga livres lecture", vol=("/kavita/config",)),
    "komga": _app(9135, "gotson/komga:latest", 25600, "512m", "Serveur de BD et de mangas.", "bd manga comics", vol=("/config",)),
}

_NAME_WORDS = "|".join(re.escape(n).replace(r"\-", ".?") for n in APPS if n not in ("homepage", "memos", "whoami", "adminer", "actual", "mermaid"))
GROUPS = [
    (r"docker|conteneur|container|auto.?heberg|self.?host|catalogue d.?app|(?:quelles|quels) (?:apps?|applications?|outils) (?:peux|puis|sais)|installe(?:r)? (?:une |l.)?(?:app|application)|" + _NAME_WORDS
     + r"|(?:install|lance|mets|met|deploie|demarre|arrete|supprime|desinstalle)\w*\s+(?:l.|le |la |un |une )?(?:app\w* )?(?:memos|homepage|whoami|adminer|actual|mermaid)",
     {"docker_apps", "docker_app", "docker_logs"}),
]
SPECS = [
    spec("docker_apps", "Liste les applications gratuites installables avec Docker sur le Mac mini, leur etat, leur adresse, et les conteneurs deja la.", filtre="string"),
    spec("docker_app", "Installe, demarre, arrete, redemarre ou supprime une application Docker de la liste (action : install, start, stop, restart, remove).",
         app="string!", action="string!", avec_donnees="boolean"),
    spec("docker_logs", "Montre les dernieres lignes de journal d'un conteneur (pour comprendre pourquoi une app ne marche pas).", app="string!", lignes="integer"),
]
TAINT = {"docker_logs"}                                          # what a program prints is not the user's words


def _docker(*args, timeout=30):
    r = subprocess.run(["sudo", "-n", "docker", *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def _bind_ip():
    """The Tailscale address of the Mac mini, or 127.0.0.1 (only the mini itself) when Tailscale is not there."""
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split()
        if out and re.fullmatch(r"100\.\d+\.\d+\.\d+", out[0]):
            return out[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return "127.0.0.1"


def _ram_free_mb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return 0


def _mb(value):
    n = int(re.match(r"\d+", value).group())
    return n * 1024 if value.endswith("g") else n


def _containers():
    """name -> {state, image, ports} of every container, running or not."""
    rc, out = _docker("ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Image}}\t{{.Ports}}")
    if rc:
        raise RuntimeError("Docker ne repond pas : " + out[:120])
    rows = {}
    for line in out.splitlines():
        name, _, rest = line.partition("\t")
        state, _, rest = rest.partition("\t")
        image, _, ports = rest.partition("\t")
        rows[name] = {"state": state, "image": image, "ports": ports}
    return rows


def _address(app, ip):
    return f"http://{ip}:{APPS[app]['host']}"


def _pick(name):
    """'IT Tools' / 'it-tools' / 'node red' -> 'it-tools' (None if the list has no such app)."""
    key = re.sub(r"[^a-z0-9]+", "-", str(name).lower().strip()).strip("-")
    key = key.removeprefix(PREFIX)
    if key in APPS:
        return key
    flat = key.replace("-", "")
    return next((n for n in APPS if n.replace("-", "") == flat), None)


def docker_apps(chat_id, a):
    word = text(a, "filtre", "", 40).lower()
    rows = _containers()
    ip = _bind_ip()
    apps = []
    for name, app in APPS.items():
        if word and word not in f"{name} {app['desc']} {app['words']}".lower():
            continue
        have = rows.get(PREFIX + name)
        apps.append(f"{name} : {app['desc']} [{have['state'] if have else 'pas installee'}, max {app['mem']} de RAM]" + (f" {_address(name, ip)}" if have else ""))
    others = [f"{n} ({r['state']})" for n, r in rows.items() if not n.startswith(PREFIX)]
    running = sum(1 for n, r in rows.items() if n.startswith(PREFIX) and r["state"] == "running")
    return {"applications": apps, "deja_la_avant_moi": others, "mes_apps_en_marche": f"{running} sur {MAX_RUNNING} possibles",
            "ram_libre_mo": _ram_free_mb(), "acces": "Tailscale seulement" if ip != "127.0.0.1" else "uniquement depuis le Mac mini (Tailscale absent)"}


def _run_args(name, app, ip):
    args = ["run", "-d", "--name", PREFIX + name, "--label", "instonct=1", "--restart", "unless-stopped",
            "--memory", app["mem"], "--memory-swap", app["mem"], "--cpus", "1", "--pids-limit", "512", "--security-opt", "no-new-privileges",
            "--log-opt", "max-size=5m", "--log-opt", "max-file=2", "-p", f"{ip}:{app['host']}:{app['port']}"]
    for i, path in enumerate(app["vol"]):
        args += ["-v", f"{PREFIX}{name}-{i}:{path}"]
    if app["bind"]:
        args += ["-v", f"{app['bind'][0]}:{app['bind'][1]}:ro"]
    for key, value in app["env"].items():
        args += ["-e", f"{key}={value.format(ip=ip, host=app['host'])}"]
    return args + [app["image"], *app["cmd"]]


def _install_job(chat_id, name, ip):
    """Runs in the background: downloading an image takes minutes, the chat must not wait on it."""
    app = APPS[name]
    try:
        rc, out = _docker("pull", app["image"], timeout=1500)
        if rc:
            send(chat_id, f"Je n'ai pas pu telecharger {name} : {scrub(out)[-150:]}")
            return
        if app["bind"]:
            os.makedirs(app["bind"][0], exist_ok=True)
        rc, out = _docker(*_run_args(name, app, ip), timeout=120)
        if rc:
            send(chat_id, f"{name} n'a pas demarre : {scrub(out)[-150:]}")
            return
        time.sleep(6)
        rc, state = _docker("inspect", "-f", "{{.State.Running}}", PREFIX + name)
        if rc or state != "true":
            _, logs = _docker("logs", "--tail", "8", PREFIX + name)
            _docker("rm", "-f", PREFIX + name)
            send(chat_id, f"{name} s'est arrete juste apres le demarrage et je l'ai retire. Derniere sortie : {scrub(logs)[-200:]}")
            return
        send(chat_id, f"{name} est pret : {_address(name, ip)}" + ("" if ip != "127.0.0.1" else " (seulement depuis le Mac mini, Tailscale n'est pas actif)")
             + ". La premiere page te demandera de creer ton compte, c'est toi qui le fais.")
    except Exception as e:                                       # a thread must say what happened, not die silently
        log.warning("docker install %s : %s", name, scrub(e))
        send(chat_id, f"Installation de {name} interrompue : {scrub(e)[:150]}")
    finally:
        db.delete(f"docker:busy:{name}")


def _background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _port_taken(host, rows):
    return any(f":{host}->" in r["ports"] for r in rows.values())


def _install(chat_id, name, rows):
    app = APPS[name]
    ip = _bind_ip()
    running = sum(1 for n, r in rows.items() if n.startswith(PREFIX) and r["state"] == "running")
    if PREFIX + name in rows:
        return {"erreur": f"{name} est deja installee (etat : {rows[PREFIX + name]['state']}). Utilise start pour la demarrer."}
    if running >= MAX_RUNNING:
        return {"erreur": f"Il y a deja {running} applications en marche, c'est le maximum pour ce Mac mini. Arrete-en une d'abord."}
    need = _mb(app["mem"]) + ROOM_MB
    if _ram_free_mb() < need:
        return {"erreur": f"Pas assez de memoire libre pour {name} : il faut environ {need} Mo, il y en a {_ram_free_mb()}. Arrete une application d'abord."}
    if shutil.disk_usage("/").free < 5 * 2**30:
        return {"erreur": "Moins de 5 Go libres sur le disque : je n'installe rien."}
    if _port_taken(app["host"], rows):
        return {"erreur": f"Le port {app['host']} est deja pris."}
    if not db.set(f"docker:busy:{name}", 1, nx=True, ex=1800):
        return {"erreur": f"L'installation de {name} est deja en cours."}
    _background(_install_job, chat_id, name, ip)
    return {"app": name, "lancee": True, "adresse_prevue": _address(name, ip),
            "note": "PAS ENCORE PRETE : le telechargement prend quelques minutes. Dis seulement que l'installation est lancee et qu'un message arrivera quand c'est pret."}


def _control(name, action, rows, wipe):
    have = rows.get(PREFIX + name)
    if not have:
        return {"erreur": f"{name} n'est pas installee."}
    if action == "remove":
        rc, out = _docker("rm", "-f", PREFIX + name)
        if rc:
            return {"erreur": f"{name} n'a pas pu etre supprimee : {scrub(out)[:120]}"}
        if wipe:
            for i in range(len(APPS[name]["vol"])):
                _docker("volume", "rm", f"{PREFIX}{name}-{i}")
        return {"app": name, "supprimee": True, "donnees": "effacees" if wipe else "gardees (on peut reinstaller et tout retrouver)"}
    rc, out = _docker(action, PREFIX + name, timeout=90)
    if rc:
        return {"erreur": f"{name} : {action} a echoue : {scrub(out)[:120]}"}
    _, state = _docker("inspect", "-f", "{{.State.Status}}", PREFIX + name)
    wanted = "exited" if action == "stop" else "running"
    if state != wanted:
        return {"erreur": f"{action} envoye mais {name} est dans l'etat '{state}' (attendu : {wanted})."}
    return {"app": name, "etat": state, "adresse": _address(name, _bind_ip())}


def docker_app(chat_id, a):
    action = text(a, "action", "", 20).lower()
    names = {"install": "docker_start", "installer": "docker_start", "start": "docker_start", "restart": "docker_start", "stop": "docker_stop", "remove": "docker_remove"}
    if action == "installer":
        action = "install"
    if action not in names:
        return {"erreur": "action inconnue : choisis install, start, stop, restart ou remove."}
    asked = text(a, "app", "", 60)
    if asked.lower().removeprefix(PREFIX) in FOREIGN:
        return {"erreur": f"{asked} etait installe avant moi : je peux lire ses logs mais je ne l'arrete pas et je ne le supprime pas (adguard fait le DNS de la maison)."}
    name = _pick(asked)
    if not name:
        return {"erreur": f"application inconnue : {asked}. Voici la liste : {', '.join(APPS)}"}
    wipe = a.get("avec_donnees") is True
    denied = guard.refusal(names[action], extra_word="donnee" if wipe and action == "remove" else None)
    if denied:
        return denied
    rows = _containers()
    return _install(chat_id, name, rows) if action == "install" else _control(name, action, rows, wipe)


def docker_logs(chat_id, a):
    asked = text(a, "app", "", 60)
    name = asked.lower().removeprefix(PREFIX)
    if name in FOREIGN:
        container = name
    elif _pick(asked):
        container = PREFIX + _pick(asked)
    else:
        return {"erreur": f"conteneur inconnu : {asked}"}
    rc, out = _docker("logs", "--tail", str(whole(a, "lignes", 25, 1, 60)), container, timeout=20)
    if rc:
        return {"erreur": f"pas de journal pour {container} : {scrub(out)[:120]}"}
    return {"conteneur": container, "lignes": [scrub(line)[:200] for line in out.splitlines()[-60:]]}


FUNCS = {"docker_apps": docker_apps, "docker_app": docker_app, "docker_logs": docker_logs}
