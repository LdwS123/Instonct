"""Chromecast / TV helpers (catt): serve files, say text on the TV, wake the TV."""

import functools
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer

from .core import db, log

# ---------------------------------------------------------------- sortie son : Mac mini ou tele (Chromecast)
CAST_HOST = os.environ.get("CAST_HOST", "192.168.1.11")   # IP de la tele Sony (Chromecast integre)
CAST_PORT = int(os.environ.get("CAST_PORT", "8765"))
CAST_DIR = "/tmp/cast"
CATT = os.path.join(os.path.dirname(sys.executable), "catt")
_cast_srv = {"on": False}


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def cast_serve():
    """Petit serveur web local : la tele vient y chercher les fichiers de voix."""
    if _cast_srv["on"]:
        return
    os.makedirs(CAST_DIR, exist_ok=True)
    # Only the home network address: the Siri server holds the same port on the Tailscale address, and "every address" would collide with it.
    srv = ThreadingHTTPServer((my_ip(), CAST_PORT), functools.partial(_Quiet, directory=CAST_DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _cast_srv["on"] = True


def my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((CAST_HOST, 9))
        return s.getsockname()[0]
    finally:
        s.close()


def tv_up():
    try:
        socket.create_connection((CAST_HOST, 8009), timeout=1.5).close()
        return True
    except OSError:
        return False


_tv_cache = {"t": 0.0, "on": False}
_cc = {"c": None}
_cc_lock = threading.Lock()


def cast_dev():
    """Connexion Chromecast gardee ouverte (la rouvrir a chaque fois coute du temps)."""
    with _cc_lock:
        c = _cc["c"]
        if c is not None and c.socket_client.is_alive():
            return c
        if c is not None:
            try:
                c.disconnect()
            except Exception:
                pass
            _cc["c"] = None
        import pychromecast
        c = pychromecast.get_chromecast_from_host((CAST_HOST, 8009, None, None, None))
        c.wait(timeout=6)
        _cc["c"] = c
        return c


def cast_say(url, mime="audio/wav", max_s=40):
    """Joue un son sur la tele et attend la fin. Le recepteur reste ouvert : la 2e phrase part en moins d'une seconde."""
    mc = cast_dev().media_controller
    mc.play_media(url, mime)
    mc.block_until_active(timeout=20)
    t0 = time.time()
    while mc.status.player_state not in ("PLAYING", "BUFFERING") and time.time() - t0 < 15:
        time.sleep(0.05)
    while mc.status.player_state in ("PLAYING", "BUFFERING") and time.time() - t0 < max_s:
        time.sleep(0.1)


def tv_on():
    """True si la tele est branchee ET allumee (pas en veille). Reponse gardee 8 s pour ne pas la harceler."""
    now = time.time()
    if now - _tv_cache["t"] < 8:
        return _tv_cache["on"]
    on = False
    if tv_up():
        try:
            on = not cast_dev().status.is_stand_by
        except Exception as e:
            log.info("etat de la tele inconnu : %s", type(e).__name__)
    _tv_cache.update(t=now, on=on)
    return on


def use_tv():
    """Ou sort le son ? 'auto' (par defaut) : sur la tele si elle est allumee, sinon sur le Mac mini ;
    'tv' : sur la tele des qu'elle repond ; 'mac' : toujours sur le Mac mini."""
    mode = db.get("sortie") or "auto"
    if mode == "mac":
        return False
    return tv_up() if mode == "tv" else tv_on()


def catt(*args, timeout=60):
    try:
        r = subprocess.run([CATT, "-d", CAST_HOST, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.strip()


def catt_info():
    d = {}
    for line in catt("info", timeout=25).splitlines():
        k, _, v = line.partition(": ")
        d[k.strip()] = v.strip()
    return d
