"""Outils en plus du bot : lire et creer des documents, QR code, lieux, Wikipedia, devises, reveil du reseau, telechargements.

Aucune dependance vers bot.py : chaque fonction recoit ce qu'il lui faut et renvoie du texte ou un chemin.
Les bibliotheques lourdes (python-docx, openpyxl, reportlab, qrcode, pypdf) ne sont importees qu'au moment de s'en servir.
"""
import csv
import io
import json
import os
import re
import socket
import subprocess
import time
from urllib.parse import quote, urlparse

import requests

UA = {"User-Agent": "Instonct/1.0 (personal assistant)"}
MAX_DOWNLOAD = 200 * 2**20


def _safe_name(name, default):
    name = re.sub(r"[^\w.\- ]", "_", os.path.basename(str(name or "").strip())).strip(" .") or default
    return name[:80]


# ---------------------------------------------------------------- lire un document
def read_document(path, start=0, limit=6000):
    """PDF, Word, Excel, CSV, texte, page web enregistree, ou image (lecture du texte par OCR). Renvoie du texte."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=90)
        text = r.stdout
        if len(text.strip()) < 30:                       # PDF scanne : on lit les images
            text = _ocr_pdf(path)
    elif ext == ".docx":
        import docx
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            parts += [" | ".join(c.text for c in row.cells) for row in t.rows]
        text = "\n".join(parts)
    elif ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets[:5]:
            out.append(f"## {ws.title}")
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 500:
                    out.append("(...)")
                    break
                out.append(" | ".join("" if v is None else str(v) for v in row))
        text = "\n".join(out)
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"):
        r = subprocess.run(["tesseract", path, "-", "-l", "fra+eng"], capture_output=True, text=True, timeout=120)
        text = r.stdout or "(aucun texte lisible sur cette image)"
    elif ext in (".odt", ".rtf", ".epub", ".html", ".htm", ".md", ".tex"):
        r = subprocess.run(["pandoc", path, "-t", "plain", "--wrap=none"], capture_output=True, text=True, timeout=60)
        text = r.stdout or r.stderr
    else:
        with open(path, "rb") as f:
            raw = f.read(2 * 2**20)
        if b"\0" in raw[:4000]:
            return "(fichier binaire : je ne sais pas le lire. Essaie python_run ou run_command.)"
        text = raw.decode("utf-8", "replace")
    text = text.strip() or "(vide)"
    start = max(0, int(start or 0))
    chunk = text[start:start + limit]
    more = f"\n[...suite : relis avec start={start + limit}, {len(text)} caracteres au total]" if len(text) > start + limit else ""
    return chunk + more


def _ocr_pdf(path):
    tmp = f"/tmp/ocr_{os.getpid()}_{int(time.time())}"
    os.makedirs(tmp, exist_ok=True)
    try:
        subprocess.run(["pdftoppm", "-r", "150", "-l", "8", "-png", path, f"{tmp}/p"], capture_output=True, timeout=120)
        out = []
        for f in sorted(os.listdir(tmp)):
            r = subprocess.run(["tesseract", f"{tmp}/{f}", "-", "-l", "fra+eng"], capture_output=True, text=True, timeout=120)
            out.append(r.stdout)
        return "\n".join(out)
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)


# ---------------------------------------------------------------- creer un document
def _rows(content):
    """Tableau pour Excel / CSV : une liste JSON de listes (ou de dictionnaires), sinon du CSV ou des colonnes separees par | ou tabulation."""
    content = content.strip()
    try:
        data = json.loads(content)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            return [keys] + [[d.get(k, "") for k in keys] for d in data]
        if isinstance(data, list):
            return [r if isinstance(r, list) else [r] for r in data]
    except ValueError:
        pass
    sep = "\t" if "\t" in content else ("|" if content.count("|") > content.count(",") else ",")
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(content), delimiter=sep)]


def make_document(kind, content, out_dir, name="", title=""):
    """Cree le fichier dans out_dir et renvoie son chemin. kind : pdf, docx, xlsx, csv, txt, md, html, json.
    Dans le texte, '# ' = grand titre, '## ' = sous-titre, '- ' = puce, ligne vide = nouveau paragraphe."""
    kind = kind.lower().lstrip(".")
    if kind not in ("pdf", "docx", "xlsx", "csv", "txt", "md", "html", "json"):
        raise ValueError("types possibles : pdf, docx, xlsx, csv, txt, md, html, json")
    os.makedirs(out_dir, exist_ok=True)
    base = _safe_name(name, "document")
    if not base.lower().endswith("." + kind):
        base = os.path.splitext(base)[0] + "." + kind
    path = os.path.join(out_dir, base)
    if kind == "pdf":
        from xml.sax.saxutils import escape
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer
        st = getSampleStyleSheet()
        flow = [Paragraph(escape(title), st["Title"])] if title else []
        bullets = []

        def flush():
            if bullets:
                flow.append(ListFlowable([ListItem(Paragraph(escape(b), st["BodyText"])) for b in bullets], bulletType="bullet"))
                bullets.clear()
        for line in content.splitlines():
            s = line.strip()
            if s.startswith(("- ", "* ")):
                bullets.append(s[2:])
                continue
            flush()
            if s.startswith("## "):
                flow.append(Paragraph(escape(s[3:]), st["Heading2"]))
            elif s.startswith("# "):
                flow.append(Paragraph(escape(s[2:]), st["Heading1"]))
            elif s:
                flow.append(Paragraph(escape(s), st["BodyText"]))
            else:
                flow.append(Spacer(1, 8))
        flush()
        SimpleDocTemplate(path, pagesize=A4, title=title or base).build(flow or [Paragraph(" ", st["BodyText"])])
    elif kind == "docx":
        import docx
        d = docx.Document()
        if title:
            d.add_heading(title, 0)
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("## "):
                d.add_heading(s[3:], 2)
            elif s.startswith("# "):
                d.add_heading(s[2:], 1)
            elif s.startswith(("- ", "* ")):
                d.add_paragraph(s[2:], style="List Bullet")
            elif s:
                d.add_paragraph(s)
        d.save(path)
    elif kind == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in _rows(content):
            ws.append(row)
        wb.save(path)
    elif kind == "csv":
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(_rows(content))
    elif kind == "html" and "<" not in content[:200]:
        from html import escape as hesc
        body = "".join(f"<p>{hesc(p)}</p>" for p in content.split("\n\n"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!doctype html><meta charset=utf-8><title>{hesc(title or base)}</title>{body}")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return path


def make_qr(text, path):
    import qrcode
    qrcode.make(text).save(path)
    return path


# ---------------------------------------------------------------- lieux, savoirs, argent, reseau
def geocode(query):
    """Nom d'un lieu -> (latitude, longitude, nom complet) avec OpenStreetMap. None si introuvable."""
    r = requests.get("https://nominatim.openstreetmap.org/search", params={"q": query, "format": "json", "limit": 1}, headers=UA, timeout=20)
    data = r.json() if r.status_code == 200 else []
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", query)[:200]


def wikipedia(query, lang="fr"):
    lang = re.sub(r"[^a-z]", "", lang.lower())[:3] or "fr"
    s = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
                     headers=UA, timeout=20).json()
    if not s[1]:
        return None
    title = s[1][0]
    r = requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}", headers=UA, timeout=20)
    j = r.json()
    return {"titre": j.get("title", title), "resume": (j.get("extract") or "")[:2500], "lien": (j.get("content_urls") or {}).get("desktop", {}).get("page", "")}


def money(amount, a, b):
    """Convertit des devises (Banque centrale europeenne) ou des cryptos (CoinGecko). Renvoie une phrase."""
    a, b = a.strip(), b.strip()
    ua, ub = a.upper(), b.upper()
    r = requests.get("https://api.frankfurter.app/latest", params={"amount": amount, "from": ua, "to": ub}, headers=UA, timeout=20)
    if r.status_code == 200 and ub in r.json().get("rates", {}):
        j = r.json()
        return f"{amount} {ua} = {j['rates'][ub]} {ub} (cours du {j.get('date', '')})"

    def coin_id(sym):
        j = requests.get("https://api.coingecko.com/api/v3/search", params={"query": sym}, headers=UA, timeout=20).json()
        coins = j.get("coins") or []
        exact = [c for c in coins if c.get("symbol", "").lower() == sym.lower() or c.get("id", "").lower() == sym.lower()]
        return (exact or coins or [{}])[0].get("id")
    ida = coin_id(a)
    if not ida:
        return f"Je ne connais pas la monnaie '{a}'."
    j = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ida, "vs_currencies": b.lower()}, headers=UA, timeout=20).json()
    px = (j.get(ida) or {}).get(b.lower())
    if px is None:
        return f"Je ne trouve pas le cours de {a} en {b}."
    return f"{amount} {a} = {round(float(amount) * px, 6)} {ub} (cours actuel)"


def wake_on_lan(mac):
    """Reveille un appareil du reseau local (il doit accepter le Wake-on-LAN)."""
    m = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(m) != 12:
        raise ValueError("adresse MAC invalide (12 chiffres/lettres, ex. AA:BB:CC:DD:EE:FF)")
    packet = bytes.fromhex("FF" * 6 + m * 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            s.sendto(packet, ("255.255.255.255", port))
    return f"Paquet de reveil envoye a {m.upper()}"


def download(url, dest_dir, name, url_ok, max_bytes=MAX_DOWNLOAD):
    """Telecharge un fichier public (redirections verifiees une a une). Renvoie (chemin, octets)."""
    os.makedirs(dest_dir, exist_ok=True)
    cur = url
    for _ in range(5):
        if not url_ok(cur):
            raise ValueError("adresse refusee (seulement des sites publics en http/https)")
        r = requests.get(cur, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            from urllib.parse import urljoin
            cur = urljoin(cur, r.headers["Location"])
            continue
        break
    else:
        raise ValueError("trop de redirections")
    if r.status_code != 200:
        raise ValueError(f"le site repond {r.status_code}")
    fname = _safe_name(name or os.path.basename(urlparse(cur).path), "fichier")
    path = os.path.join(dest_dir, fname)
    n = 0
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            n += len(chunk)
            if n > max_bytes:
                f.close()
                os.remove(path)
                raise ValueError(f"fichier trop gros (plus de {max_bytes // 2**20} Mo)")
            f.write(chunk)
    return path, n
