"""Free commands that need no AI: status, weather."""

import glob
import shutil
import subprocess
from datetime import datetime

import redis
import requests

from .config import MAX_PER_DAY
from .texts import METEO_CODES
from .core import db

# ---------------------------------------------------------------- commandes gratuites
def cpu_temp():
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(f"{h}/name").read().strip() == "coretemp":
                return f"{int(open(f'{h}/temp2_input').read()) // 1000} C"
        except OSError:
            pass
    return "?"


def disk_info():
    u = shutil.disk_usage("/")
    return f"{u.free // 2**30} Go libres sur {u.total // 2**30} Go"


def status():
    up = float(open("/proc/uptime").read().split()[0])
    load = open("/proc/loadavg").read().split()[:3]
    mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
    svc = subprocess.run(
        "systemctl list-units 'bot-*' --no-legend --plain | awk '{print \"  \"$1\" \"$3}'",
        shell=True, capture_output=True, text=True).stdout.strip()
    try:
        rd = "ok" if db.ping() else "KO"
    except redis.RedisError:
        rd = "KO"
    return (f"Uptime : {int(up // 3600)} h {int(up % 3600 // 60)} min\n"
            f"Charge : {' '.join(load)}\n"
            f"CPU    : {cpu_temp()}\n"
            f"RAM    : {mem['MemAvailable'] // 1024} Mo dispo / {mem['MemTotal'] // 1024} Mo\n"
            f"Disque : {disk_info()}\n"
            f"Redis  : {rd}\n"
            f"Questions IA aujourd'hui : {db.get(f'rl:day:{datetime.now():%Y-%m-%d}') or 0}/{MAX_PER_DAY}\n"
            f"Services :\n{svc}")


def screen_message(text):
    """Affiche un message sur le tableau de bord de l'ecran (lu par ecran-status via Redis)."""
    text = "".join(c for c in text if c.isprintable())[:120]
    db.set("ecran_msg", text, ex=60)


CITY_ALIASES = {"sf": "San Francisco", "nyc": "New York", "la": "Los Angeles", "lyon": "Lyon", "bx": "Bordeaux"}


def meteo(city):
    city = CITY_ALIASES.get(city.strip().lower(), city)
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1, "language": "fr"}, timeout=15).json()
    if not g.get("results"):
        return f"Ville introuvable : {city}"
    p = g["results"][0]
    w = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code"}, timeout=15).json()["current"]
    return (f"Meteo a {p['name']} ({p.get('country', '')}) :\n"
            f"{METEO_CODES.get(w['weather_code'], 'conditions variables')}, {w['temperature_2m']} C "
            f"(ressenti {w['apparent_temperature']} C), vent {w['wind_speed_10m']} km/h")
