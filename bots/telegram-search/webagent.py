"""Navigateur leger Lightpanda garde ouvert (protocole MCP sur stdio) : ouvrir, lire, remplir, cliquer, extraire.

Le navigateur demarre a la premiere utilisation (~25 Mo de memoire), s'arrete tout seul apres 10 minutes sans
activite, et garde les cookies dans ~/bots/browser_cookies.json (donc les connexions survivent).
"""
import json
import os
import queue
import subprocess
import threading
import time

LIGHTPANDA = os.path.expanduser("~/lightpanda/lightpanda")
COOKIES = os.path.expanduser("~/bots/browser_cookies.json")
WORKDIR = os.path.expanduser("~/recus")          # les telechargements et captures atterrissent ici
IDLE = 600


class BrowserError(Exception):
    pass


class Browser:
    def __init__(self, cookies=True):
        self.cookies = cookies          # False : navigateur de veille, sans cookies (n'ecrase pas ceux du navigateur principal)
        self.lock = threading.RLock()
        self.p = None
        self.q = None
        self.n = 0
        self.last = 0.0
        threading.Thread(target=self._reaper, daemon=True).start()

    # ---- vie du processus
    def _start(self):
        os.makedirs(WORKDIR, exist_ok=True)
        cmd = [LIGHTPANDA, "mcp"]
        if self.cookies:
            if os.path.exists(COOKIES):
                cmd += ["--cookie", COOKIES]
            cmd += ["--cookie-jar", COOKIES]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, cwd=WORKDIR, preexec_fn=lambda: os.umask(0o077))
        self.q = queue.Queue()
        threading.Thread(target=self._read, args=(self.p, self.q), daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "bot-telegram", "version": "1"}}, 20)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    @staticmethod
    def _read(p, q):
        for line in p.stdout:
            q.put(line)
        q.put(None)

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def _rpc(self, method, params, timeout):
        self.n += 1
        rid = self.n
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + timeout
        while True:
            try:
                line = self.q.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                self.stop(kill=True)
                raise BrowserError("le navigateur ne repond plus (redemarre au prochain essai)")
            if line is None:
                self.p = None
                raise BrowserError("le navigateur s'est arrete")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == rid:
                return msg

    def stop(self, kill=False):
        with self.lock:
            p, self.p = self.p, None
            if not p:
                return
            try:
                if not kill:
                    p.stdin.close()              # fermeture propre : le navigateur enregistre les cookies
                    p.wait(timeout=8)
            except Exception:
                pass
            if p.poll() is None:
                p.kill()
            if self.cookies:
                try:
                    os.chmod(COOKIES, 0o600)
                except OSError:
                    pass

    def _reaper(self):
        while True:
            time.sleep(30)
            if self.p and time.time() - self.last > IDLE and self.lock.acquire(blocking=False):
                try:
                    self.stop()
                finally:
                    self.lock.release()

    # ---- appel d'un outil du navigateur
    def call(self, tool, timeout=60, **args):
        """Renvoie le texte de la reponse ; BrowserError si le navigateur signale une erreur."""
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self.p = None
                self._start()
            self.last = time.time()
            msg = self._rpc("tools/call", {"name": tool, "arguments": args}, timeout)
            self.last = time.time()
        if "error" in msg:
            raise BrowserError(str(msg["error"].get("message", msg["error"]))[:300])
        res = msg.get("result", {})
        text = "".join(c.get("text", "") for c in res.get("content", []))
        if res.get("isError"):
            raise BrowserError(text[:300])
        return text

    def js(self, script, **kw):
        """Execute du JavaScript dans la page et renvoie le resultat (texte)."""
        return self.call("evaluate", script=script, **kw)
