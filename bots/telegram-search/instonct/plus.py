"""Instonct extras: personal tracker, expenses, important dates, notebook, calculator/units, video transcripts, settings.

Everything is plain Redis counting and lookups: no AI call, no quota. The LLM only decides WHICH tool to call.
  tool(db, name, args) -> dict          (the 7 tools below)
  due(db, now)          -> [messages]   (follow-ups and date reminders that are due now; each is returned once)
Data keys: suivi (hash), depenses (list), dates (hash), carnet (hash), reglages (hash).
"""
import ast
import json
import math
import operator
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta

NAMES = {"suivi", "depenses", "dates", "carnet", "calcul", "video_texte", "reglage"}
CLOSED = ("termine", "fini", "refus", "accept", "annule", "abandon", "clos", "ferme", "recu", "livre", "signe", "paye", "obtenu")
SETTINGS = {                       # name -> (default on?, short description)
    "rappel_rdv": (True, "me prevenir 30 minutes avant un rendez-vous de l'agenda (avec le lien Meet)"),
    "relances": (True, "me proposer une relance quand une demande du suivi reste sans nouvelle"),
    "dates": (True, "me rappeler les anniversaires et dates importantes"),
    "mails_sans_reponse": (True, "me dire une fois par jour quels mails importants attendent peut-etre ma reponse"),
    "memoire_auto": (True, "retenir tout seul ce que je dis de durable sur moi, a partir de mes messages"),
    "menage_auto": (False, "mettre les pubs a la corbeille toutes les nuits"),
    "bilan_soir": (False, "m'envoyer un petit bilan chaque soir a 21 h"),
}


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def _id():
    return uuid.uuid4().hex[:5]


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v or "").replace(" ", ""))
    return float(m.group(0).replace(",", ".")) if m else None


# ------------------------------------------------------------------ settings
def setting(db, name):
    v = db.hget("reglages", name)
    return SETTINGS[name][0] if v is None else v == "1"


def t_reglage(db, a):
    name = norm(a.get("nom", "")).replace(" ", "_")
    alias = {"menage": "menage_auto", "nettoyage": "menage_auto", "bilan": "bilan_soir", "soir": "bilan_soir", "rdv": "rappel_rdv",
             "rendez_vous": "rappel_rdv", "relance": "relances", "anniversaires": "dates", "mails": "mails_sans_reponse", "relance_mails": "mails_sans_reponse", "memoire": "memoire_auto"}
    name = alias.get(name, name)
    if name not in SETTINGS:
        return {"reglages": {k: ("oui" if setting(db, k) else "non") + " : " + v[1] for k, v in SETTINGS.items()}}
    if a.get("actif") is None:
        return {name: "oui" if setting(db, name) else "non", "sert_a": SETTINGS[name][1]}
    on = a.get("actif") is True or norm(a.get("actif")) in ("true", "oui", "on", "1")
    db.hset("reglages", name, "1" if on else "0")
    return {"resultat": f"{name} : {'active' if on else 'coupe'}", "sert_a": SETTINGS[name][1]}


# ------------------------------------------------------------------ tracker
def _suivi_all(db):
    return sorted((json.loads(v) for v in db.hvals("suivi")), key=lambda x: x["maj"], reverse=True)


def _suivi_find(db, ref):
    ref = norm(ref)
    if not ref:
        return None
    items = _suivi_all(db)
    for it in items:
        if it["id"] == ref:
            return it
    hits = [it for it in items if ref in norm(it["titre"])]
    return hits[0] if hits else None


def _is_closed(it):
    return any(k in norm(it["statut"]) for k in CLOSED)


def t_suivi(db, a):
    act = norm(a.get("action", "list"))
    now = int(time.time())
    if act in ("add", "ajoute"):
        titre = str(a.get("titre", "")).strip()[:120]
        if not titre:
            return {"erreur": "titre manquant"}
        old = _suivi_find(db, titre)
        if old and norm(old["titre"]) == norm(titre):
            act, a["ref"] = "update", old["id"]
        else:
            it = {"id": _id(), "titre": titre, "cat": norm(a.get("categorie", "")) or "autre", "statut": str(a.get("statut", "") or "en cours")[:40],
                  "note": str(a.get("note", ""))[:300], "cree": now, "maj": now,
                  "relance": max(0, min(60, int(_num(a.get("relance_jours")) or (7 if "candid" in norm(a.get("categorie", "")) else 0))))}
            db.hset("suivi", it["id"], json.dumps(it))
            return {"resultat": "ajoute au suivi", "id": it["id"], "relance_dans_jours": it["relance"] or "pas de relance"}
    if act in ("update", "maj", "statut"):
        it = _suivi_find(db, a.get("ref") or a.get("titre"))
        if not it:
            return {"erreur": "introuvable dans le suivi"}
        if a.get("statut"):
            it["statut"] = str(a["statut"])[:40]
        if a.get("note"):
            it["note"] = (it["note"] + " | " if it["note"] else "") + str(a["note"])[:200]
            it["note"] = it["note"][-400:]
        if a.get("relance_jours") is not None:
            it["relance"] = max(0, min(60, int(_num(a.get("relance_jours")) or 0)))
        it["maj"] = now
        db.hset("suivi", it["id"], json.dumps(it))
        return {"resultat": "mis a jour", "titre": it["titre"], "statut": it["statut"]}
    if act in ("remove", "supprime", "delete"):
        it = _suivi_find(db, a.get("ref") or a.get("titre"))
        if not it:
            return {"erreur": "introuvable dans le suivi"}
        db.hdel("suivi", it["id"])
        return {"resultat": "retire du suivi", "titre": it["titre"]}
    items = _suivi_all(db)
    cat, st = norm(a.get("categorie", "")), norm(a.get("statut", ""))
    if cat:
        items = [i for i in items if cat in i["cat"]]
    if st:
        items = [i for i in items if st in norm(i["statut"])]
    if not items:
        return {"suivi": "rien dans le suivi"}
    out = []
    for i in items[:30]:
        days = (int(time.time()) - i["maj"]) // 86400
        out.append(f"{i['id']} | {i['titre']} | {i['cat']} | {i['statut']} | il y a {days} j" + (f" | {i['note'][:80]}" if i["note"] else ""))
    return {"suivi": out, "total": len(items)}


# ------------------------------------------------------------------ expenses
def _expenses(db):
    out = []
    for raw in db.lrange("depenses", 0, -1):
        try:
            out.append(json.loads(raw))
        except ValueError:
            pass
    return out


def t_depenses(db, a):
    act = norm(a.get("action", "list"))
    if act in ("add", "ajoute"):
        amount = _num(a.get("montant"))
        if amount is None or amount <= 0:
            return {"erreur": "montant manquant"}
        try:
            d = datetime.strptime(str(a.get("date", ""))[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            d = date.today().strftime("%Y-%m-%d")
        e = {"id": _id(), "d": d, "m": round(amount, 2), "cat": norm(a.get("categorie", "")) or "divers", "note": str(a.get("note", ""))[:80]}
        db.rpush("depenses", json.dumps(e))
        month = [x for x in _expenses(db) if x["d"][:7] == d[:7]]
        return {"resultat": f"{e['m']:.2f} EUR ajoute ({e['cat']})", "total_du_mois": round(sum(x["m"] for x in month), 2), "id": e["id"]}
    if act in ("remove", "supprime", "delete"):
        ref = str(a.get("ref", "")).strip()
        allx = _expenses(db)
        target = next((x for x in reversed(allx) if x["id"] == ref), None) or (allx[-1] if allx and not ref else None)
        if not target:
            return {"erreur": "depense introuvable"}
        db.lrem("depenses", 1, json.dumps(target))
        return {"resultat": "retire", "depense": f"{target['m']:.2f} EUR {target['cat']} {target['note']}"}
    allx = _expenses(db)
    period = norm(a.get("periode", "mois"))
    today = date.today()
    if period in ("semaine", "week"):
        since = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        sel = [x for x in allx if x["d"] >= since]
    elif period in ("tout", "all", "total"):
        sel = allx
    elif re.fullmatch(r"\d{4}-\d{2}", period):
        sel = [x for x in allx if x["d"][:7] == period]
    else:
        sel = [x for x in allx if x["d"][:7] == today.strftime("%Y-%m")]
    cat = norm(a.get("categorie", ""))
    if cat:
        sel = [x for x in sel if cat in x["cat"]]
    if not sel:
        return {"depenses": "aucune depense sur cette periode"}
    by = {}
    for x in sel:
        by[x["cat"]] = round(by.get(x["cat"], 0) + x["m"], 2)
    res = {"total_EUR": round(sum(x["m"] for x in sel), 2), "nombre": len(sel),
           "par_categorie": dict(sorted(by.items(), key=lambda kv: -kv[1])),
           "dernieres": [f"{x['d']} {x['m']:.2f} EUR {x['cat']} {x['note']}".strip() for x in sel[-5:]]}
    budget = db.hget("reglages", "budget_mois")
    if budget and period not in ("tout", "all", "total", "semaine", "week"):
        res["budget_mois_EUR"] = float(budget)
        res["reste_EUR"] = round(float(budget) - res["total_EUR"], 2)
    return res


# ------------------------------------------------------------------ important dates
def _dates(db):
    out = []
    for v in db.hvals("dates"):
        try:
            out.append(json.loads(v))
        except ValueError:
            pass
    return out


def t_dates(db, a):
    act = norm(a.get("action", "list"))
    if act in ("add", "ajoute"):
        nom = str(a.get("nom", "")).strip()[:80]
        m = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", str(a.get("jour", "")))
        iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(a.get("jour", "")))
        if iso:
            y, mo, d = int(iso[1]), int(iso[2]), int(iso[3])
        elif m:
            d, mo, y = int(m[1]), int(m[2]), (int(m[3]) if m[3] else 0)
            y = y + 2000 if 0 < y < 100 else y
        else:
            return {"erreur": "jour non compris (ex : 14/07 ou 1998-07-14)"}
        if not nom or not (1 <= mo <= 12 and 1 <= d <= 31):
            return {"erreur": "nom ou date invalide"}
        e = {"id": _id(), "nom": nom, "j": d, "m": mo, "a": y, "type": norm(a.get("type", "")) or "date"}
        db.hset("dates", e["id"], json.dumps(e))
        return {"resultat": f"{nom} : {d:02d}/{mo:02d} enregistre, je te previens 3 jours avant et le jour meme"}
    if act in ("remove", "supprime", "delete"):
        ref = norm(a.get("nom") or a.get("ref"))
        hit = next((e for e in _dates(db) if e["id"] == ref or ref in norm(e["nom"])), None)
        if not hit:
            return {"erreur": "introuvable"}
        db.hdel("dates", hit["id"])
        return {"resultat": "retire", "nom": hit["nom"]}
    today = date.today()
    rows = []
    for e in _dates(db):
        try:
            nxt = date(today.year, e["m"], e["j"])
        except ValueError:
            continue
        if nxt < today:
            nxt = date(today.year + 1, e["m"], e["j"])
        age = f" ({nxt.year - e['a']} ans)" if e["a"] else ""
        rows.append(((nxt - today).days, f"{e['nom']} le {e['j']:02d}/{e['m']:02d}{age} : dans {(nxt - today).days} jour(s)"))
    return {"dates": [r[1] for r in sorted(rows)] or "aucune date enregistree"}


# ------------------------------------------------------------------ notebook
def t_carnet(db, a):
    act = norm(a.get("action", "search"))
    if act in ("add", "ajoute", "note"):
        text = str(a.get("texte", "")).strip()[:1500]
        if not text:
            return {"erreur": "texte vide"}
        e = {"id": _id(), "t": text, "tags": norm(a.get("tags", ""))[:60], "at": int(time.time())}
        db.hset("carnet", e["id"], json.dumps(e))
        return {"resultat": "note enregistree dans le carnet", "id": e["id"]}
    if act in ("remove", "supprime", "delete"):
        ref = str(a.get("ref", "")).strip()
        if ref and db.hdel("carnet", ref):
            return {"resultat": "note supprimee"}
        return {"erreur": "id de note introuvable (utilise search pour le voir)"}
    notes = []
    for v in db.hvals("carnet"):
        try:
            notes.append(json.loads(v))
        except ValueError:
            pass
    notes.sort(key=lambda x: x["at"], reverse=True)
    q = [w for w in norm(a.get("recherche", "")).split() if len(w) > 2]
    if q:
        scored = []
        for n in notes:
            hay = norm(n["t"] + " " + n["tags"])
            s = sum(1 for w in q if w in hay)
            if s:
                scored.append((s, n))
        notes = [n for _, n in sorted(scored, key=lambda x: (-x[0], -x[1]["at"]))]
    if not notes:
        return {"carnet": "aucune note" + (" avec ces mots" if q else "")}
    return {"carnet": [f"{n['id']} | {datetime.fromtimestamp(n['at']):%d/%m/%Y} | {n['t'][:300]}" for n in notes[:8]], "total": len(notes)}


# ------------------------------------------------------------------ calculator / units
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max, "log": math.log, "log10": math.log10, "sin": math.sin,
          "cos": math.cos, "tan": math.tan, "floor": math.floor, "ceil": math.ceil}
_CONST = {"pi": math.pi, "e": math.e}


def _ev(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        a, b = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e9):
            raise ValueError("puissance trop grande")
        return _OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_ev(n.operand))
    if isinstance(n, ast.Name) and n.id in _CONST:
        return _CONST[n.id]
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords and len(n.args) <= 3:
        return _FUNCS[n.func.id](*[_ev(x) for x in n.args])
    raise ValueError("expression non comprise")


_UNITS = {   # unit -> (family, factor to the base unit)
    "m": ("len", 1), "km": ("len", 1000), "cm": ("len", .01), "mm": ("len", .001), "mi": ("len", 1609.344), "mile": ("len", 1609.344), "miles": ("len", 1609.344),
    "ft": ("len", .3048), "pied": ("len", .3048), "pieds": ("len", .3048), "in": ("len", .0254), "pouce": ("len", .0254), "pouces": ("len", .0254), "yd": ("len", .9144),
    "kg": ("mas", 1), "g": ("mas", .001), "lb": ("mas", .45359237), "lbs": ("mas", .45359237), "livre": ("mas", .45359237), "livres": ("mas", .45359237), "oz": ("mas", .0283495),
    "l": ("vol", 1), "ml": ("vol", .001), "cl": ("vol", .01), "gal": ("vol", 3.78541), "gallon": ("vol", 3.78541), "gallons": ("vol", 3.78541),
    "km/h": ("vit", 1), "mph": ("vit", 1.609344), "m/s": ("vit", 3.6), "kmh": ("vit", 1),
    "h": ("tps", 3600), "min": ("tps", 60), "s": ("tps", 1), "j": ("tps", 86400), "jour": ("tps", 86400), "jours": ("tps", 86400),
    "go": ("oct", 1e9), "mo": ("oct", 1e6), "ko": ("oct", 1e3), "to": ("oct", 1e12), "gb": ("oct", 1e9), "mb": ("oct", 1e6), "tb": ("oct", 1e12),
}


def _convert(expr):
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*(?:°\s*)?([a-z/°]+)\s*(?:en|to|vers|->|=|in)\s*(?:°\s*)?([a-z/°]+)\s*", norm(expr))
    if not m:
        return None
    v, u1, u2 = float(m[1].replace(",", ".")), m[2].replace("°", ""), m[3].replace("°", "")
    temp = {"c", "f", "k", "celsius", "fahrenheit", "kelvin"}
    if u1 in temp and u2 in temp:
        c = {"c": v, "celsius": v, "f": (v - 32) / 1.8, "fahrenheit": (v - 32) / 1.8, "k": v - 273.15, "kelvin": v - 273.15}[u1]
        out = {"c": c, "celsius": c, "f": c * 1.8 + 32, "fahrenheit": c * 1.8 + 32, "k": c + 273.15, "kelvin": c + 273.15}[u2]
        return out
    if u1 in _UNITS and u2 in _UNITS and _UNITS[u1][0] == _UNITS[u2][0]:
        return v * _UNITS[u1][1] / _UNITS[u2][1]
    return None


def t_calcul(db, a):
    expr = str(a.get("expression", "")).strip()[:200]
    if not expr:
        return {"erreur": "expression vide"}
    c = _convert(expr)
    if c is not None:
        return {"resultat": round(c, 4)}
    e = norm(expr).replace(",", ".").replace("x", "*").replace("×", "*").replace("^", "**").replace("÷", "/")
    e = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", r"(\1/100*\2)", e)          # "15% de 80"
    e = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", e)
    try:
        r = _ev(ast.parse(e, mode="eval").body)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError) as ex:
        return {"erreur": "calcul impossible : " + str(ex)[:60]}
    return {"resultat": round(r, 8) if isinstance(r, float) else r}


# ------------------------------------------------------------------ video transcript
def _vtt_text(path):
    lines, last = [], ""
    for ln in open(path, encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if not ln or ln.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in ln:
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if ln and ln != last:
            lines.append(ln)
            last = ln
    return " ".join(lines)


def t_video_texte(db, a):
    url = str(a.get("url", "")).strip()
    if not re.match(r"https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", url):
        return {"erreur": "seulement les liens YouTube (youtube.com ou youtu.be)"}
    ytdlp = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    with tempfile.TemporaryDirectory() as tmp:
        title, limited = "", False
        for lang in ("fr", "en"):                      # ONE language per call: asking for many at once makes YouTube answer "429 too many requests"
            try:
                r = subprocess.run([ytdlp, "--no-playlist", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", lang,
                                    "--sub-format", "vtt", "--no-warnings", "--no-simulate", "--print", "%(title)s | %(channel)s | %(duration_string)s",
                                    "-o", os.path.join(tmp, "v.%(ext)s"), url], capture_output=True, text=True, timeout=90)
            except subprocess.TimeoutExpired:
                return {"erreur": "YouTube met trop de temps a repondre"}
            title = title or r.stdout.strip()[:150]
            limited = limited or "429" in r.stderr
            if any(f.endswith(".vtt") for f in os.listdir(tmp)):
                break
        files = sorted(f for f in os.listdir(tmp) if f.endswith(".vtt"))
        if not files:
            return {"erreur": "YouTube limite les demandes, reessaie dans quelques minutes" if limited else "pas de sous-titres pour cette video", "titre": title}
        text = _vtt_text(os.path.join(tmp, files[0]))
    start = max(0, int(_num(a.get("debut")) or 0))
    return {"video": title, "texte": text[start:start + 6000], "longueur_totale": len(text),
            **({"suite": f"relance avec debut={start + 6000}"} if len(text) > start + 6000 else {})}


# ------------------------------------------------------------------ dispatch + reminders
def tool(db, name, args):
    fn = {"suivi": t_suivi, "depenses": t_depenses, "dates": t_dates, "carnet": t_carnet, "calcul": t_calcul,
          "video_texte": t_video_texte, "reglage": t_reglage}[name]
    return fn(db, args if isinstance(args, dict) else {})


def due(db, now=None):
    """Messages to send now: follow-ups for stale tracker items, birthdays / dates. Each fires once (Redis guard keys)."""
    now = now or datetime.now()
    out = []
    if setting(db, "relances") and now.hour >= 9:
        for it in _suivi_all(db):
            n = it.get("relance", 0)
            if not n or _is_closed(it):
                continue
            idle = (time.time() - it["maj"]) / 86400
            if idle >= n and db.set(f"relance_ping:{it['id']}:{int(it['maj'])}", 1, nx=True, ex=int(n * 86400) + 86400):
                out.append(f"Pas de nouvelle depuis {int(idle)} jours pour : {it['titre']} ({it['statut']}). "
                           f"Je te prepare un message de relance ? Dis « oui relance {it['titre'][:30]} ».")
    if setting(db, "dates") and now.hour >= 9:
        for e in _dates(db):
            try:
                nxt = date(now.year, e["m"], e["j"])
            except ValueError:
                continue
            delta = (nxt - now.date()).days
            if delta in (0, 3) and db.set(f"date_ping:{e['id']}:{now.year}:{delta}", 1, nx=True, ex=40 * 86400):
                age = f" ({now.year - e['a']} ans)" if e["a"] else ""
                out.append(f"C'est aujourd'hui : {e['nom']}{age} !" if delta == 0 else f"Dans 3 jours : {e['nom']}{age} ({e['j']:02d}/{e['m']:02d}).")
    return out
