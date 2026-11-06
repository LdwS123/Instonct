"""Shared helpers of the kit_* modules (small tools the model can call). Leaf module: it imports neither llm nor catalog."""

import html
import re

import requests

AGENT = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Instonct"}
TYPES = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean"}


def spec(name, description, **props):
    """One tool declaration. props: argument="string" ; add "!" (string!) when the argument is required."""
    required = [k for k, v in props.items() if v.endswith("!")]
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": {k: {"type": TYPES[v.rstrip("!")]} for k, v in props.items()}, **({"required": required} if required else {})}}


def get_json(url, timeout=12, **params):
    r = requests.get(url, params=params or None, headers=AGENT, timeout=timeout)
    r.raise_for_status()
    return r.json()


def text(a, key, default="", limit=300):
    return str(a.get(key) if a.get(key) is not None else default).strip()[:limit]


def num(a, key, default=0.0, low=-1e12, high=1e12):
    try:
        return max(low, min(high, float(str(a.get(key, default)).replace(",", ".").replace(" ", ""))))
    except ValueError:
        return default


def whole(a, key, default=0, low=-10**9, high=10**9):
    return int(num(a, key, default, low, high))


def host_of(value):
    """'https://www.exemple.fr/page' or 'exemple.fr' -> 'www.exemple.fr' (empty if it does not look like a host)."""
    h = re.sub(r"^[a-z]+://", "", str(value).strip().lower()).split("/")[0].split("?")[0].split(":")[0]
    return h if re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", h) and "." in h else ""


def get_json_or_none(url, timeout=12, **params):
    """Like get_json, but a plain "404 not found" gives None (so the tool can say "nothing found" instead of a technical error)."""
    r = requests.get(url, params=params or None, headers=AGENT, timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def clean(value, limit=400):
    """Text from a web service: tags removed, entities decoded, spaces collapsed, cut to a length."""
    plain = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", plain).strip()[:limit]


def locate(city):
    """City name -> (latitude, longitude, name, country) with the free Open-Meteo geocoder; LookupError when it does not exist."""
    found = get_json("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1, language="fr").get("results") or []
    if not found:
        raise LookupError(f"ville introuvable : {city}")
    return found[0]["latitude"], found[0]["longitude"], found[0]["name"], found[0].get("country", "")
