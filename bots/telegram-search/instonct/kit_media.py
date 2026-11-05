"""Media tools: download a video or its sound, say something as a voice note, turn a recording into text, edit a picture, work on PDFs.

Everything is done on the Mac mini with free tools (yt-dlp, ffmpeg, Pillow, pypdf). Files go back in the chat when they are under 50 MB.
Files are only read from the work folders (~/work, ~/recus, ~/exports), never from key or secret paths.
"""

import glob
import os
import re
import subprocess
import time

from . import system_tools, web
from .kit_base import spec, text, whole

WORK = os.path.expanduser("~/work")
FOLDERS = (WORK, os.path.expanduser("~/recus"), os.path.expanduser("~/exports"))
MAX_MB = 45

SPECS = [
    spec("ytdl", "Telecharge le son (mp3) ou la video (mp4 petite taille) d'un lien YouTube ou autre et l'envoie dans le chat.", url="string!", mode="string"),
    spec("voice_note", "Envoie un message vocal (voix) avec ce texte dans le chat.", texte="string!"),
    spec("transcribe_file", "Transcrit en texte un fichier audio ou video recu (30 premieres minutes).", chemin="string!"),
    spec("image_edit", "Modifie une image : action resize|rotate|gris|compress|convert|carre. valeur = largeur, angle ou format (png/jpg/webp).",
         chemin="string!", action="string!", valeur="string"),
    spec("pdf_outils", "PDF : action info|texte|fusion|extrait. fusion prend plusieurs chemins separes par des virgules, extrait prend pages (ex 2-4).",
         chemin="string!", action="string!", pages="string"),
]
GROUPS = [
    (r"telecharge.*(?:video|musique|son|youtube)|ytdl|youtube.*(?:mp3|mp4)|en mp3|extrais le son|recupere.*video", {"ytdl"}),
    (r"message vocal|note vocale|dis.moi .* en vocal|envoie.moi .* en vocal|reponds.moi en vocal|en audio", {"voice_note"}),
    (r"transcri|ce qu.il dit dans|retranscris|mets en texte|audio.*texte|dictee", {"transcribe_file"}),
    (r"redimension|rogne|pivote|noir et blanc|compresse.*(?:image|photo)|convertis.*(?:png|jpg|webp)|image.*(?:plus petite|plus legere)|retourne l.image", {"image_edit"}),
    (r"pdf|fusionne|fusion de|coupe le pdf|extrais .* pages?|pages? \d+", {"pdf_outils"}),
]
TAINT = {"transcribe_file", "pdf_outils"}


def find_file(name):
    """A file the user gave by name: from the work folders only, never a secret."""
    for base in FOLDERS:
        path = system_tools._path(str(name), base)
        if os.path.isfile(path) and not system_tools.SECRET_PATH.search(path) and path.startswith(FOLDERS):
            return path
        path = os.path.join(base, os.path.basename(str(name)))
        if os.path.isfile(path) and not system_tools.SECRET_PATH.search(path):
            return path
    return ""


def _send(chat_id, path):
    from . import media
    return media.send_local_file(chat_id, path)


def ytdl(chat_id, a):
    url, video = text(a, "url", "", 500), text(a, "mode", "audio", 10).lower() in ("video", "mp4")
    if not web.url_ok(url):
        return {"erreur": "lien public attendu (https://...)"}
    folder = os.path.join(WORK, "ytdl")
    os.makedirs(folder, exist_ok=True)
    stamp = f"{int(time.time())}"
    fmt = ["-f", "best[height<=480][ext=mp4]/best[height<=480]/worst", "--merge-output-format", "mp4"] if video else ["-x", "--audio-format", "mp3", "--audio-quality", "5"]
    cmd = [os.path.expanduser("~/bots/venv/bin/yt-dlp"), "--no-playlist", "--max-filesize", f"{MAX_MB}M", "--no-progress", *fmt,
           "--print", "after_move:filepath", "-o", os.path.join(folder, stamp + "-%(title).60B.%(ext)s"), url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
    files = glob.glob(os.path.join(folder, stamp + "-*"))
    if r.returncode != 0 or not files:
        return {"erreur": "telechargement impossible (lien prive, trop gros ou bloque) : " + (r.stderr.strip().splitlines() or [""])[-1][:150]}
    path = files[0]
    sent = _send(chat_id, path)
    return {"fichier": os.path.basename(path), "taille_mo": round(os.path.getsize(path) / 2**20, 1), "envoye": sent,
            **({} if sent else {"note": "trop gros pour Telegram (50 Mo) : le fichier reste sur le Mac mini"})}


def voice_note(chat_id, a):
    from . import sound
    spoken = text(a, "texte", "", 900)
    if not spoken:
        return {"erreur": "il faut un texte"}
    return {"envoye": bool(sound.send_voice(chat_id, spoken))}


def _chunks(path, folder):
    """The sound cut in 10-minute pieces of small mono mp3 (Whisper accepts 25 MB), three pieces at most."""
    pieces = []
    for i in range(3):
        out = os.path.join(folder, f"part{i}.mp3")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(i * 600), "-t", "600", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", out],
                           capture_output=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 2000:
            break
        pieces.append(out)
    return pieces


def transcribe_file(chat_id, a):
    from . import sound
    path = find_file(text(a, "chemin", "", 200))
    if not path:
        return {"erreur": "fichier introuvable dans ~/work, ~/recus ou ~/exports"}
    folder = os.path.join(WORK, f"stt-{int(time.time())}")
    os.makedirs(folder)
    pieces, parts = _chunks(path, folder), []
    for p in pieces:
        with open(p, "rb") as f:
            heard = sound.transcribe(f.read())
        parts.append(heard or "[passage non compris]")
        os.remove(p)
    os.rmdir(folder)
    if not parts:
        return {"erreur": "pas de son lisible dans ce fichier"}
    return {"texte": " ".join(parts)[:6000], "minutes_lues": len(parts) * 10, "note": "30 premieres minutes au maximum"}


def image_edit(chat_id, a):
    from PIL import Image, ImageOps
    path = find_file(text(a, "chemin", "", 200))
    action, value = text(a, "action", "", 12).lower(), text(a, "valeur", "", 12).lower()
    if not path:
        return {"erreur": "image introuvable dans ~/work, ~/recus ou ~/exports"}
    img, ext = ImageOps.exif_transpose(Image.open(path)), "png"
    if action == "resize":
        width = whole({"v": value}, "v", 800, 16, 8000)
        img = img.resize((width, max(1, round(img.height * width / img.width))))
    elif action == "rotate":
        img = img.rotate(-whole({"v": value}, "v", 90, -360, 360), expand=True)
    elif action in ("gris", "grayscale"):
        img = ImageOps.grayscale(img)
    elif action == "carre":
        img = ImageOps.fit(img, (min(img.size), min(img.size)))
    elif action in ("compress", "convert"):
        ext = {"jpg": "jpg", "jpeg": "jpg", "webp": "webp", "png": "png"}.get(value, "jpg" if action == "compress" else "png")
    else:
        return {"erreur": "action : resize, rotate, gris, compress, convert ou carre"}
    out = os.path.join(WORK, f"{os.path.splitext(os.path.basename(path))[0]}-{action}.{ext}")
    os.makedirs(WORK, exist_ok=True)
    if ext == "jpg":
        img = img.convert("RGB")
    img.save(out, **({"quality": 70, "optimize": True} if ext in ("jpg", "webp") else {}))
    return {"fichier": os.path.basename(out), "taille": f"{img.width}x{img.height}", "ko": os.path.getsize(out) // 1024, "envoye": _send(chat_id, out)}


def _page_range(spec_text, count):
    """'2-4' -> [1, 2, 3]  (0-based, within the document); '3' -> [2]; nothing -> every page."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", spec_text or "")
    if not m:
        return list(range(count))
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    return [i for i in range(first - 1, min(last, count)) if i >= 0]


def pdf_outils(chat_id, a):
    from pypdf import PdfReader, PdfWriter
    action, names = text(a, "action", "", 10).lower(), [n.strip() for n in str(a.get("chemin") or "").split(",") if n.strip()]
    paths = [find_file(n) for n in names]
    if not paths or not all(paths):
        return {"erreur": "pdf introuvable dans ~/work, ~/recus ou ~/exports"}
    os.makedirs(WORK, exist_ok=True)
    if action == "fusion":
        w = PdfWriter()
        for p in paths:
            for page in PdfReader(p).pages:
                w.add_page(page)
        out = os.path.join(WORK, f"fusion-{int(time.time())}.pdf")
        with open(out, "wb") as f:
            w.write(f)
        return {"fichier": os.path.basename(out), "pages": len(w.pages), "envoye": _send(chat_id, out)}
    reader = PdfReader(paths[0])
    if reader.is_encrypted:
        return {"erreur": "ce pdf est protege par un mot de passe : je ne peux pas l'ouvrir"}
    if action == "info":
        meta = reader.metadata or {}
        return {"pages": len(reader.pages), "titre": str(meta.get("/Title") or "")[:100], "auteur": str(meta.get("/Author") or "")[:100]}
    chosen = _page_range(text(a, "pages", "", 20), len(reader.pages))
    if action == "texte":
        return {"pages_lues": len(chosen[:15]), "texte": "\n".join((reader.pages[i].extract_text() or "") for i in chosen[:15])[:6000]}
    if action == "extrait":
        w = PdfWriter()
        for i in chosen:
            w.add_page(reader.pages[i])
        if not len(w.pages):
            return {"erreur": "ces pages n'existent pas"}
        out = os.path.join(WORK, f"extrait-{int(time.time())}.pdf")
        with open(out, "wb") as f:
            w.write(f)
        return {"fichier": os.path.basename(out), "pages": len(w.pages), "envoye": _send(chat_id, out)}
    return {"erreur": "action : info, texte, fusion ou extrait"}


FUNCS = {"ytdl": ytdl, "voice_note": voice_note, "transcribe_file": transcribe_file, "image_edit": image_edit, "pdf_outils": pdf_outils}
