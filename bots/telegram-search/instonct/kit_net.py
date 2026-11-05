"""Network tools: is a site up, certificate end date, DNS, my IP, devices at home, speed, an open port, who owns a domain.

Only public hosts can be reached from the outside checks (web.url_ok). The home network is only read by lan_devices.
"""

import re
import socket
import ssl
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from . import web
from .kit_base import AGENT, get_json, host_of, spec, text, whole

SPECS = [
    spec("site_up", "Dit si un site repond (code, temps de reponse).", url="string!"),
    spec("ssl_expiry", "Date de fin du certificat HTTPS d'un site et jours restants.", domaine="string!"),
    spec("dns_lookup", "Les enregistrements DNS d'un domaine (A, AAAA, MX, TXT, NS).", domaine="string!", type="string"),
    spec("my_ip", "L'adresse IP publique du Mac mini et son adresse sur le reseau de la maison."),
    spec("lan_devices", "Les appareils branches sur le reseau de la maison (adresse IP et MAC)."),
    spec("speed_test", "Mesure la vitesse de telechargement d'internet du Mac mini."),
    spec("port_check", "Dit si un port est ouvert sur un serveur public.", hote="string!", port="integer!"),
    spec("whois_domain", "A qui est un nom de domaine : registrar, dates de creation et d'expiration.", domaine="string!"),
]
GROUPS = [
    (r"site (?:est|marche)|en panne|down\b|ne repond|repond plus|is it up", {"site_up"}),
    (r"certificat|ssl|https|tls", {"ssl_expiry"}),
    (r"\bdns\b|enregistrement|\bmx\b|nom de domaine", {"dns_lookup", "whois_domain"}),
    (r"adresse ip|mon ip|ip publique|\bip\b", {"my_ip"}),
    (r"appareils|reseau|wifi|box\b|qui est connecte|branche", {"lan_devices"}),
    (r"debit|vitesse|speedtest|speed test|fibre|connexion lente|internet lent", {"speed_test"}),
    (r"port\b|ouvert sur", {"port_check"}),
    (r"whois|proprietaire du domaine|registrar|expire le domaine|domaine .*(?:expire|appartient)", {"whois_domain"}),
]


def _public_host(value):
    h = host_of(value)
    if not h or not web.url_ok("https://" + h):
        return ""
    return h


def site_up(chat_id, a):
    url = text(a, "url")
    url = url if "://" in url else "https://" + url
    if not web.url_ok(url):
        return {"erreur": "seulement les sites publics"}
    t0 = time.time()
    try:
        r = requests.get(url, headers=AGENT, timeout=10, allow_redirects=True, stream=True)
        r.close()
    except requests.RequestException as e:
        return {"site": url, "en_ligne": False, "raison": type(e).__name__}
    return {"site": url, "en_ligne": r.status_code < 500, "code": r.status_code, "ms": int((time.time() - t0) * 1000)}


def ssl_expiry(chat_id, a):
    host = _public_host(a.get("domaine", ""))
    if not host:
        return {"erreur": "domaine public attendu (exemple.fr)"}
    try:
        with socket.create_connection((host, 443), timeout=8) as raw, ssl.create_default_context().wrap_socket(raw, server_hostname=host) as s:
            cert = s.getpeercert()
    except (OSError, ssl.SSLError) as e:
        return {"domaine": host, "erreur": f"connexion HTTPS impossible ({type(e).__name__})"}
    end = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
    return {"domaine": host, "expire_le": end.strftime("%Y-%m-%d"), "jours_restants": (end - datetime.now(timezone.utc)).days,
            "emis_par": dict(x[0] for x in cert.get("issuer", ())).get("organizationName", "")}


def dns_lookup(chat_id, a):
    host = _public_host(a.get("domaine", ""))
    kind = text(a, "type", "A", 5).upper()
    if not host or kind not in ("A", "AAAA", "MX", "TXT", "NS", "CNAME"):
        return {"erreur": "domaine public et type A, AAAA, MX, TXT, NS ou CNAME"}
    r = requests.get("https://cloudflare-dns.com/dns-query", params={"name": host, "type": kind}, headers={**AGENT, "accept": "application/dns-json"}, timeout=10)
    r.raise_for_status()
    answers = [x["data"].strip('"') for x in r.json().get("Answer", []) if "data" in x]
    return {"domaine": host, "type": kind, "reponses": answers[:12]} if answers else {"domaine": host, "type": kind, "reponses": [], "note": "aucun enregistrement"}


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))             # nothing is sent: this only picks the interface
            return s.getsockname()[0]
    except OSError:
        return ""


def my_ip(chat_id, a):
    out = {"reseau_maison": local_ip()}
    try:
        out["publique"] = get_json("https://api.ipify.org?format=json", timeout=8)["ip"]
    except (requests.RequestException, KeyError, ValueError):
        out["publique"] = "inconnue (pas d'internet ?)"
    return out


def _ping(ip):
    return subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True, timeout=5).returncode == 0


def lan_devices(chat_id, a):
    me = local_ip()
    if not me:
        return {"erreur": "reseau local introuvable"}
    base = me.rsplit(".", 1)[0]
    with ThreadPoolExecutor(48) as pool:
        list(pool.map(_ping, [f"{base}.{i}" for i in range(1, 255)]))
    found = []
    for line in subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=10).stdout.splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+) dev \S+ lladdr ([0-9a-f:]{17}) (\S+)", line)
        if m and m.group(3) in ("REACHABLE", "STALE", "DELAY", "PROBE") and m.group(1).startswith(base + "."):
            found.append({"ip": m.group(1), "mac": m.group(2)})
    found.sort(key=lambda d: int(d["ip"].rsplit(".", 1)[1]))
    return {"nombre": len(found), "appareils": found, "note": "les noms ne sont pas connus : l'adresse MAC identifie l'appareil"}


def speed_test(chat_id, a):
    got, t0 = 0, time.time()
    try:
        with requests.get("https://speed.cloudflare.com/__down", params={"bytes": 12_000_000}, headers=AGENT, stream=True, timeout=(5, 20)) as r:
            r.raise_for_status()
            for chunk in r.iter_content(262144):
                got += len(chunk)
                if time.time() - t0 > 15:
                    break
    except requests.RequestException as e:
        return {"erreur": f"test impossible ({type(e).__name__})"}
    secs = max(time.time() - t0, 0.01)
    return {"telechargement_mbit_s": round(got * 8 / secs / 1e6, 1), "octets": got, "secondes": round(secs, 1)}


def port_check(chat_id, a):
    host, port = _public_host(a.get("hote", "")), whole(a, "port", 0, 0, 65535)
    if not host or not port:
        return {"erreur": "serveur public et port entre 1 et 65535"}
    try:
        with socket.create_connection((host, port), timeout=5):
            return {"hote": host, "port": port, "ouvert": True}
    except OSError:
        return {"hote": host, "port": port, "ouvert": False}


def _registrar(data):
    for ent in data.get("entities", []):
        if "registrar" in ent.get("roles", []):
            for field in (ent.get("vcardArray") or [0, []])[1]:
                if field[0] == "fn":
                    return field[3]
    return ""


def whois_domain(chat_id, a):
    host = _public_host(a.get("domaine", ""))
    if not host:
        return {"erreur": "domaine public attendu"}
    try:
        data = get_json("https://rdap.org/domain/" + ".".join(host.split(".")[-2:]), timeout=15)
    except (requests.RequestException, ValueError) as e:
        return {"domaine": host, "erreur": f"introuvable ({type(e).__name__})"}
    events = {e.get("eventAction"): (e.get("eventDate") or "")[:10] for e in data.get("events", [])}
    registrar = _registrar(data)
    return {"domaine": data.get("ldhName", host), "cree_le": events.get("registration", ""), "expire_le": events.get("expiration", ""),
            "registrar": registrar, "statut": data.get("status", [])[:4], "serveurs_dns": [n.get("ldhName", "") for n in data.get("nameservers", [])][:4]}


FUNCS = {"site_up": site_up, "ssl_expiry": ssl_expiry, "dns_lookup": dns_lookup, "my_ip": my_ip, "lan_devices": lan_devices,
         "speed_test": speed_test, "port_check": port_check, "whois_domain": whois_domain}
