"""Remote screen for Instonct: lets the owner log in to LinkedIn & co. HIMSELF, from his phone, on the Mac mini's browser.

The bot never sees a password. It opens a temporary virtual screen (Xvfb + openbox + Chromium with a persistent profile),
shares it through noVNC, and ONLY on the Tailscale address (100.x.x.x): nobody outside the owner's Tailscale network can reach it.
The session closes by itself after a few minutes. Logins stay in the Chromium profile, so the bot can reuse them later.

start(minutes, url) -> dict   stop() -> dict   status() -> dict
"""
import glob
import json
import os
import secrets
import shutil
import signal
import subprocess
import time

HOME = os.path.expanduser("~")
PROFILE = os.path.join(HOME, "bots", "browser_profile")
STATE = os.path.join(HOME, "bots", "screen.json")
DISPLAY = ":99"
VNC_PORT = 5900
WEB_PORT = 6080
NOVNC_DIRS = ("/usr/share/novnc", "/usr/share/novnc/www")
MAX_MINUTES = 60


def _chrome():
    found = sorted(glob.glob(os.path.join(HOME, ".cache", "ms-playwright", "chromium-*", "chrome-linux*", "chrome")))
    return found[-1] if found else (shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome"))


def _tailscale_ip():
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split()
        return out[0] if out else ""
    except Exception:
        return ""


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def _kill_all(st):
    for pid in st.get("pids", []):
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except Exception:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    time.sleep(0.8)
    for pid in st.get("pids", []):
        if _alive(pid):
            try:
                os.killpg(int(pid), signal.SIGKILL)
            except Exception:
                pass


def status():
    st = _load()
    if st and any(_alive(p) for p in st.get("pids", [])) and st.get("until", 0) > time.time():
        return {"actif": True, "url": st["url"], "mot_de_passe": st["pw"], "reste_min": max(1, int((st["until"] - time.time()) / 60))}
    return {"actif": False}


def active():
    return status()["actif"]


def stop():
    st = _load()
    if st:
        _kill_all(st)
    try:
        os.remove(STATE)
    except OSError:
        pass
    # leftovers (a crashed session): only our own display/ports
    subprocess.run(["pkill", "-f", f"Xvfb {DISPLAY}"], capture_output=True)
    subprocess.run(["pkill", "-f", f"x11vnc.*-rfbport {VNC_PORT}"], capture_output=True)
    subprocess.run(["pkill", "-f", f"websockify.*:{WEB_PORT}"], capture_output=True)
    subprocess.run(["pkill", "-f", f"user-data-dir={PROFILE}"], capture_output=True)
    return {"ok": True, "message": "Ecran ferme."}


def expire():
    """Called by the bot every few minutes: closes the screen when its time is over. True if it closed something."""
    st = _load()
    if st and (st.get("until", 0) <= time.time() or not any(_alive(p) for p in st.get("pids", []))):
        stop()
        return True
    return False


def start(minutes=15, url="https://www.linkedin.com/login"):
    cur = status()
    if cur["actif"]:
        return {"ok": True, **cur}
    stop()                                                       # clean slate
    ip = _tailscale_ip()
    if not ip:
        return {"ok": False, "erreur": "Tailscale n'est pas actif sur le Mac mini"}
    chrome = _chrome()
    novnc = next((d for d in NOVNC_DIRS if os.path.exists(os.path.join(d, "vnc.html"))), None)
    if not chrome or not novnc or not all(shutil.which(b) for b in ("Xvfb", "openbox", "x11vnc", "websockify")):
        return {"ok": False, "erreur": "il manque des programmes (Xvfb, openbox, x11vnc, novnc ou chromium)"}
    minutes = max(2, min(int(minutes or 15), MAX_MINUTES))
    os.makedirs(PROFILE, exist_ok=True)
    pw = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")[:8]
    pwfile = os.path.join(HOME, "bots", ".vncpass")
    subprocess.run(["x11vnc", "-storepasswd", pw, pwfile], capture_output=True)
    os.chmod(pwfile, 0o600)
    env = dict(os.environ, DISPLAY=DISPLAY)
    pids = []

    def run(cmd, **kw):
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, **kw)
        pids.append(p.pid)
        return p

    try:
        run(["Xvfb", DISPLAY, "-screen", "0", "1280x800x24", "-nolisten", "tcp"])
        time.sleep(1.2)
        run(["openbox"])
        run([chrome, "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", f"--user-data-dir={PROFILE}", "--window-position=0,0",
             "--window-size=1280,800", "--no-first-run", "--no-default-browser-check", "--disable-features=Translate", url])
        run(["x11vnc", "-display", DISPLAY, "-localhost", "-rfbport", str(VNC_PORT), "-rfbauth", pwfile, "-forever", "-shared", "-noxdamage", "-quiet"])
        time.sleep(1.0)
        run(["websockify", "--web", novnc, f"{ip}:{WEB_PORT}", f"localhost:{VNC_PORT}"])
        time.sleep(1.5)
    except Exception as e:
        _kill_all({"pids": pids})
        return {"ok": False, "erreur": f"demarrage rate : {str(e)[:100]}"}
    link = f"http://{ip}:{WEB_PORT}/vnc.html?autoconnect=1&resize=scale"
    st = {"pids": pids, "pw": pw, "url": link, "until": time.time() + minutes * 60}
    with open(STATE, "w") as f:
        json.dump(st, f)
    os.chmod(STATE, 0o600)
    # safety net that does not depend on the bot: closes everything even if the bot is restarted
    subprocess.Popen(["setsid", "sh", "-c", f"sleep {minutes * 60 + 30}; " + " ".join(f"kill {p} 2>/dev/null;" for p in pids) + f" rm -f {STATE}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {"ok": True, "actif": True, "url": link, "mot_de_passe": pw, "reste_min": minutes}
