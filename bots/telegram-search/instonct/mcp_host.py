"""Open-source MCP servers (Docker's catalogue) run in locked containers, spoken to over stdio.

Why containers: an MCP server is somebody else's program. It never runs on the Mac mini itself, only inside `docker run` with
- no capability, no new privileges, a read-only disk (+ a small /tmp), memory / CPU / process ceilings, removed on exit;
- its own network `mcpnet` where the firewall refuses the home network, Tailscale and the Mac mini itself (internet only),
  checked before every start (fail closed: no firewall rule = no server);
- only Docker's own signed `mcp/...` images that are listed in mcp_catalog.json: the user's words never reach the docker command line
  (they travel as JSON over stdin, never as arguments).
At most MAX_LIVE servers run at once and an idle one is stopped after IDLE_SECONDS: the Mac mini has 4.6 GB of RAM.
"""

import json
import queue
import re
import shutil
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path

from .core import log

NETWORK, BRIDGE, SUBNET = "mcpnet", "br-mcp", "172.29.0.0/24"
PRIVATE = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16")     # home network, Docker, Tailscale, link-local
MAX_LIVE = 2
IDLE_SECONDS = 150
START_SECONDS = 60
MAX_LINE = 4_000_000                       # one JSON message from a server
MAX_BYTES = 16_000_000                     # everything a server may send while one request waits
MIN_FREE_BYTES = 3 * 1024 ** 3             # no download below 3 GB of free disk
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9._-]+)?")
_VOLUME = re.compile(r"mcp-[a-z0-9-]+:/[A-Za-z0-9/_.-]+")

_live = {}
_lock = threading.RLock()
_pulls = {}
_pull_lock = threading.Lock()
_net = {"ok": False}


class McpError(Exception):
    """The server answered with a JSON-RPC error."""


@lru_cache(maxsize=1)
def entries():
    """The catalogue: id -> entry (see build_mcp_catalog.py). Values are checked here because they end up on a command line."""
    raw = json.loads((Path(__file__).with_name("mcp_catalog.json")).read_text(encoding="utf-8"))["servers"]
    out = {}
    for s in raw:
        assert re.fullmatch(r"[a-z0-9_-]+", s["id"]) and _IMAGE.fullmatch(s["image"]), s["id"]
        assert not s.get("digest") or re.fullmatch(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}", s["digest"]), s["id"]
        assert all(_VOLUME.fullmatch(v) for v in s.get("volumes", [])), s["id"]
        out[s["id"]] = s
    return out


def ref(entry):
    """The image to run: pinned by digest once verified (the 'latest' tag could change under us)."""
    return entry.get("digest") or entry["image"]


def usable(server_id):
    e = entries().get(server_id)
    return e if e and e.get("etat") == "ok" else None


# ---------------------------------------------------------------- docker and the firewall


def _sudo(*args, timeout=30):
    r = subprocess.run(["sudo", "-n", *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def _rules():
    return [("DOCKER-USER", ["-i", BRIDGE, "-d", cidr, "-j", "DROP"]) for cidr in PRIVATE] + [("INPUT", ["-i", BRIDGE, "-j", "DROP"])]


def ensure_network():
    """The isolated network exists and every firewall rule is proven present (re-added if missing). Raises if a rule cannot be proven."""
    first = not _net["ok"]
    if first:
        rc, _ = _sudo("docker", "network", "inspect", NETWORK)
        if rc != 0:
            rc, out = _sudo("docker", "network", "create", "--driver", "bridge", "--subnet", SUBNET, "-o", f"com.docker.network.bridge.name={BRIDGE}",
                            "-o", "com.docker.network.bridge.enable_icc=false", NETWORK)
            if rc != 0:
                raise RuntimeError("reseau isole impossible : " + out[:120])
    for chain, rule in _rules():                                    # checked before EVERY container start (someone may have flushed iptables since)
        if _sudo("iptables", "-C", chain, *rule)[0] != 0:
            rc, out = _sudo("iptables", "-I", chain, "1", *rule)
            if rc != 0 or _sudo("iptables", "-C", chain, *rule)[0] != 0:
                raise RuntimeError("pare-feu impossible : " + out[:120])
    if first:
        _, stale = _sudo("docker", "ps", "-aq", "--filter", "label=instonct=mcp")      # leftovers of a previous run of the bot
        for cid in stale.split():
            _sudo("docker", "rm", "-f", cid)
        _net["ok"] = True


def argv(entry, name):
    """The docker command line of one server: everything comes from the checked catalogue, nothing from the user."""
    a = ["sudo", "-n", "docker", "run", "--rm", "-i", "--name", name, "--label", "instonct=mcp", "--network", NETWORK, "--dns", "1.1.1.1", "--dns", "9.9.9.9",
         "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "450m", "--memory-swap", "450m", "--cpus", "1.5"]
    if entry.get("ro", True):
        a += ["--read-only", "--tmpfs", "/tmp:rw,size=96m"]
    for key, value in sorted(entry.get("env", {}).items()):
        a += ["-e", f"{key}={value}"]
    for volume in entry.get("volumes", []):
        a += ["-v", volume]
    return a + [ref(entry), *entry.get("cmd", [])]


def image_ready(entry):
    return _sudo("docker", "image", "inspect", ref(entry))[0] == 0


def pull_status(server_id):
    return _pulls.get(server_id, "")


def start_pull(entry):
    """Downloads the image in the background (it can take minutes on this connection). Returns a short status."""
    sid = entry["id"]
    with _pull_lock:
        if _pulls.get(sid) == "en cours":
            return "en cours"
        if shutil.disk_usage("/").free < MIN_FREE_BYTES:
            return "disque presque plein"
        _pulls[sid] = "en cours"

    def work():
        try:
            rc, out = _sudo("docker", "pull", ref(entry), timeout=1500)
            _pulls[sid] = "fini" if rc == 0 else "echec"
            if rc != 0:
                log.warning("mcp pull %s : %s", sid, out[-200:])
        except Exception as e:
            _pulls[sid] = "echec"
            log.warning("mcp pull %s : %s", sid, type(e).__name__)
    threading.Thread(target=work, daemon=True).start()
    return "en cours"


# ---------------------------------------------------------------- one running server


class Proc:
    def __init__(self, entry, command, name):
        self.entry, self.name, self.last, self.n = entry, name, time.time(), 0
        self.lock = threading.Lock()
        self.q = queue.Queue(maxsize=256)
        self.busy = False                                                     # True only while one of OUR requests waits for its answer
        self.bytes = 0
        self.p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                line = self.p.stdout.readline(MAX_LINE)
                if not line:
                    break
                if len(line) >= MAX_LINE and not line.endswith("\n"):          # a message bigger than any sane answer: cut the server off
                    self.cut()
                    break
                try:
                    message = json.loads(line)
                except ValueError:
                    continue                                                  # a log line on stdout
                if not self.busy:
                    continue                                                  # nobody asked: unsolicited output is dropped, not stored
                self.bytes += len(line)
                try:
                    if self.bytes > MAX_BYTES:
                        raise queue.Full
                    self.q.put_nowait(message)
                except queue.Full:                                            # a server flooding us (messages or bytes): cut it off
                    self.cut()
                    break
        finally:
            try:
                self.q.put_nowait(None)
            except queue.Full:
                pass

    def cut(self):
        """Stops the server for good. The process we hold is `sudo`, owned by root, which we may not be allowed to signal: so the container itself is removed."""
        try:
            self.p.kill()
        except OSError:
            pass
        try:
            _sudo("docker", "rm", "-f", self.name, timeout=20)
        except Exception:
            pass

    def alive(self):
        return self.p.poll() is None

    def send(self, message):
        """Writes one line. A server that stops reading would block this forever, so a timer kills it if the write hangs."""
        timer = threading.Timer(15, self.cut)
        timer.start()
        try:
            self.p.stdin.write(json.dumps(message) + "\n")
            self.p.stdin.flush()
        finally:
            timer.cancel()

    def rpc(self, method, params, timeout):
        while not self.q.empty():                                            # notifications that nobody asked for
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.n += 1
        mid = self.n
        self.bytes = 0
        self.busy = True
        try:
            return self._rpc(mid, method, params, timeout)
        finally:
            self.busy = False

    def _rpc(self, mid, method, params, timeout):
        self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise TimeoutError(method)
            try:
                msg = self.q.get(timeout=left)
            except queue.Empty:
                raise TimeoutError(method) from None
            if msg is None:
                raise ConnectionError("le serveur s'est arrete")
            if not isinstance(msg, dict):
                continue
            if msg.get("id") == mid and ("result" in msg or "error" in msg):
                if "error" in msg:
                    raise McpError(str((msg["error"] or {}).get("message", "erreur"))[:200])
                return msg.get("result") or {}
            if "method" in msg and isinstance(msg.get("id"), (int, str)) and len(str(msg["id"])) <= 64:      # the server asks us something (sampling, roots): we offer nothing
                self.send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "non supporte"}})

    def handshake(self):
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "instonct", "version": "1"}}, START_SECONDS)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.terminate()
            self.p.wait(timeout=4)
        except (subprocess.TimeoutExpired, OSError):
            pass
        self.cut()


def _forget(proc):
    with _lock:
        if _live.get(proc.entry["id"]) is proc:
            del _live[proc.entry["id"]]
    proc.close()


def _session(entry):
    with _lock:
        proc = _live.get(entry["id"])
        if proc and proc.alive():
            return proc
        if proc:
            _live.pop(entry["id"], None)
        while len(_live) >= MAX_LIVE:
            idle = [p for p in _live.values() if not p.lock.locked()]
            if not idle:
                raise RuntimeError("deja deux serveurs MCP occupes : reessaie dans un instant")
            _forget(min(idle, key=lambda p: p.last))
        ensure_network()
        name = f"mcp_{entry['id']}"[:60]
        _sudo("docker", "rm", "-f", name)
        proc = Proc(entry, argv(entry, name), name)
        try:
            proc.handshake()
        except Exception:
            proc.close()
            raise
        _live[entry["id"]] = proc
        _reaper()
        return proc


def request(server_id, method, params, timeout=60):
    """One JSON-RPC request to a catalogue server (started on demand). Errors: McpError, TimeoutError, ConnectionError, RuntimeError, LookupError."""
    entry = usable(server_id)
    if not entry:
        raise LookupError("serveur MCP inconnu ou pas utilisable")
    if not image_ready(entry):
        status = start_pull(entry)
        raise RuntimeError(f"ce serveur n'est pas encore telecharge ({status}) : reessaie dans quelques minutes")
    for attempt in (1, 2):
        proc = _session(entry)
        with proc.lock:
            try:
                result = proc.rpc(method, params, timeout)
                proc.last = time.time()
                return result
            except (ConnectionError, BrokenPipeError, OSError, ValueError):
                _forget(proc)
                if attempt == 2:
                    raise
            except TimeoutError:
                _forget(proc)
                raise
    raise ConnectionError("serveur MCP injoignable")


_reaper_state = {"on": False}


def _reaper():
    if _reaper_state["on"]:
        return
    _reaper_state["on"] = True

    def loop():
        while True:
            time.sleep(30)
            with _lock:
                old = [p for p in _live.values() if time.time() - p.last > IDLE_SECONDS and not p.lock.locked()]
                for proc in old:
                    _forget(proc)
    threading.Thread(target=loop, daemon=True).start()


def stop_all():
    with _lock:
        for proc in list(_live.values()):
            _forget(proc)
