"""Telecommande virtuelle de la tele Sony (protocole Android TV Remote v2, par le Wi-Fi).

Appairage une seule fois : la tele affiche un code de 6 caracteres, on le donne au bot (/code).
Ensuite la connexion reste ouverte : chaque touche part tout de suite (et on se reconnecte tout seul).
"""
import asyncio
import logging
import os
import socket
import threading
import time

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed

HOST = os.environ.get("CAST_HOST", "192.168.1.11")
_DIR = os.path.expanduser("~/bots")
CERT, KEY, FLAG = f"{_DIR}/tv_cert.pem", f"{_DIR}/tv_key.pem", f"{_DIR}/tv_paired"
log = logging.getLogger("bot")

_loop = asyncio.new_event_loop()                      # une boucle asyncio dediee, dans son propre thread
threading.Thread(target=_loop.run_forever, daemon=True).start()
_pair = {"remote": None}
_conn = {"r": None}
_lock = threading.Lock()                              # une touche a la fois

# nom simple -> touche Android TV
KEYS = {
    "power": "POWER", "home": "HOME", "back": "BACK", "up": "DPAD_UP", "down": "DPAD_DOWN", "left": "DPAD_LEFT",
    "right": "DPAD_RIGHT", "ok": "DPAD_CENTER", "mute": "VOLUME_MUTE", "volume_up": "VOLUME_UP",
    "volume_down": "VOLUME_DOWN", "play_pause": "MEDIA_PLAY_PAUSE", "stop": "MEDIA_STOP", "next": "MEDIA_NEXT",
    "previous": "MEDIA_PREVIOUS", "menu": "MENU", "input": "TV_INPUT", "settings": "SETTINGS",
    "tv": "TV", "guide": "GUIDE", "info": "INFO", "ch_up": "CHANNEL_UP", "ch_down": "CHANNEL_DOWN", "last": "LAST_CHANNEL",
    "captions": "CAPTIONS", "rewind": "MEDIA_REWIND", "forward": "MEDIA_FAST_FORWARD", "search": "SEARCH",
    "hdmi1": "TV_INPUT_HDMI_1", "hdmi2": "TV_INPUT_HDMI_2", "hdmi3": "TV_INPUT_HDMI_3",
    "red": "PROG_RED", "green": "PROG_GREEN", "yellow": "PROG_YELLOW", "blue": "PROG_BLUE",
}
APPS = {"youtube": "https://www.youtube.com", "netflix": "https://www.netflix.com/title",
        "prime": "https://app.primevideo.com", "disney": "https://www.disneyplus.com"}


def _run(coro, timeout=25):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


def _new():
    return AndroidTVRemote("Jessica", CERT, KEY, HOST, loop=_loop)


def pairing_pending():
    return _pair["remote"] is not None


def paired():
    return os.path.exists(CERT) and os.path.exists(KEY) and os.path.exists(FLAG)


# ------------------------------------------------------------------ appairage
async def _start_pairing():
    r = _new()
    await r.async_generate_cert_if_missing()
    await r.async_start_pairing()
    _pair["remote"] = r


def start_pairing():
    """Fait afficher un code sur la tele."""
    _run(_start_pairing())


async def _finish_pairing(code):
    r = _pair["remote"]
    if r is None:
        raise RuntimeError("aucun appairage en cours")
    await r.async_finish_pairing(code)
    _pair["remote"] = None
    open(FLAG, "w").close()


def finish_pairing(code):
    _run(_finish_pairing(code))


# ------------------------------------------------------------------ touches
async def _send(fn):
    for essai in (1, 2):
        try:
            r = _conn["r"]
            if r is None:
                r = _new()
                await r.async_generate_cert_if_missing()
                await asyncio.wait_for(r.async_connect(), 8)
                _conn["r"] = r
            fn(r)
            await asyncio.sleep(0.15)
            return
        except (ConnectionClosed, CannotConnect, OSError, asyncio.TimeoutError):
            old, _conn["r"] = _conn["r"], None
            if old is not None:
                old.disconnect()
            if essai == 2:
                raise


_down = {"until": 0.0}


def _do(fn):
    """Une touche a la fois. Si la tele ne repond pas, on abandonne vite (6 s de pause) au lieu d'empiler les essais."""
    if time.time() < _down["until"]:
        raise ConnectionClosed("tele injoignable (pause)")
    if not _lock.acquire(timeout=4):
        raise ConnectionClosed("telecommande occupee")
    try:
        _run(_send(fn), timeout=25)
    except Exception:
        _down["until"] = time.time() + 6
        raise
    finally:
        _lock.release()


def mac():
    """Adresse MAC de la tele (lue dans la table ARP du reseau local)."""
    try:
        for line in open("/proc/net/arp").read().splitlines()[1:]:
            p = line.split()
            if p[0] == HOST and p[3] != "00:00:00:00:00:00":
                return p[3]
    except OSError:
        pass
    return None


def wake():
    """Reveille la tele par le reseau (Wake-on-LAN). Renvoie True si le paquet est parti."""
    m = mac()
    if not m:
        return False
    pkt = bytes.fromhex("ff" * 6 + m.replace(":", "") * 16)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        for _ in range(3):
            s.sendto(pkt, ("255.255.255.255", 9))
    finally:
        s.close()
    return True


def key(name):
    """Envoie une touche ('home', 'up', 'volume_up'...). Pour 'power', reveille aussi par le reseau si besoin."""
    code = KEYS.get(name, name)
    try:
        _do(lambda r: r.send_key_command(code))
    except Exception:
        if name == "power" and wake():
            return
        raise


def launch(app):
    link = APPS.get(app.lower(), app)
    _do(lambda r: r.send_launch_app_command(link))


def text(txt):
    """Tape du texte dans la zone de recherche affichee sur la tele."""
    _do(lambda r: r.send_text(txt))


def is_on():
    """What the TV says about itself over the remote connection: True, False, or None when we are not connected."""
    r = _conn["r"]
    return getattr(r, "is_on", None) if r is not None else None


def warm():
    """Ouvre la connexion a l'avance pour que la premiere touche parte tout de suite."""
    _do(lambda r: None)
