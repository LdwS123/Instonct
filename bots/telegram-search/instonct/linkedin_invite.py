"""Sends LinkedIn connection requests WITH a note, one by one, in the real Chromium the user logged into himself (/connexion linkedin).

What it does not do: it never sees or types a password, it never hides that it is a program, it never sends an invitation without the note the user asked for,
and it stops and tells the user as soon as LinkedIn pushes back (login wall, security check, weekly limit, no more notes for a free account).
Slow on purpose (a pause between invitations, a daily and a weekly cap): the account belongs to the user, and LinkedIn restricts accounts that go too fast.

start(chat_id, keywords, note, count) -> dict (the work runs in the background and reports on Telegram)   state() -> dict   stop() -> dict
"""

import json
import random
import re
import threading
import time
from datetime import datetime
from urllib.parse import quote

from . import linkedin, realbrowser, screen
from .core import db, log, norm, scrub, send

DAY_MAX = 30                    # invitations per day
WEEK_MAX = 100                  # LinkedIn's own weekly limit is about this
NOTE_MAX = 300                  # LinkedIn refuses longer notes
PAUSE = (35, 80)                # seconds between two invitations
MAX_PAGES = 6
JOB_KEY = "linkedin:invite:job"
STOP_KEY = "linkedin:invite:stop"
DONE_KEY = "linkedin:invite:done"           # profile addresses already invited: never twice
SKIP_KEY = "linkedin:invite:skip"
SEARCH = "https://www.linkedin.com/search/results/people/?keywords={kw}&network=%5B%22S%22%2C%22O%22%5D&origin=FACETED_SEARCH&page={page}"


class Stop(Exception):
    """The job must end here: the message goes back to the user as it is."""


# ------------------------------------------------------------------ what we run inside the page (each starts with a marker comment)
FIND_JS = """/*find*/(()=>{document.querySelectorAll('[data-lpi]').forEach(e=>e.removeAttribute('data-lpi'));
const re=/^(?:connect|se connecter|invite .+ to connect|inviter .+ [àa] rejoindre votre r[ée]seau)$/i;const out=[];let n=0;
for(const e of document.querySelectorAll('button,a,[role=button]')){
 const label=(e.getAttribute('aria-label')||e.innerText||'').trim();if(!re.test(label))continue;
 const r=e.getBoundingClientRect();if(!r.width||!r.height||e.disabled)continue;
 let card=e,link=null;for(let i=0;i<8&&card;i++){card=card.parentElement;link=card&&card.querySelector('a[href*="/in/"]');if(link)break;}
 const m=label.match(/^(?:invite|inviter)\\s+(.+?)\\s+(?:to connect|[àa] rejoindre)/i);
 n+=1;e.setAttribute('data-lpi',String(n));
 out.push({sel:'[data-lpi="'+n+'"]',name:m?m[1]:'',url:link?link.href.split('?')[0]:''});}
return JSON.stringify(out);})()"""
STATE_JS = "/*state*/JSON.stringify({url:location.href,title:document.title||'',body:(document.body?document.body.innerText:'').slice(0,1500)})"
DIALOG_JS = ("/*dialog*/(()=>{const d=document.querySelector('[role=dialog],.artdeco-modal');if(!d)return '';"
             "return JSON.stringify({text:d.innerText.slice(0,500),textarea:!!d.querySelector('textarea')});})()")
VALUE_JS = "/*value*/(()=>{const t=document.querySelector('[role=dialog] textarea,.artdeco-modal textarea');return t?t.value:'';})()"
SCROLL_JS = "/*scroll*/(()=>{window.scrollTo(0,document.body.scrollHeight);return 'ok';})()"
_BUTTONS = {"note": r"^(?:add a note|ajouter une note)$",
            "send": r"^(?:send|send invitation|send now|envoyer|envoyer l.invitation|envoyer maintenant)$"}


def tag_js(kind):
    """Marks one thing inside the open dialog and returns its selector ('' if it is not there or is disabled)."""
    pick = ("t=d.querySelector('textarea');if(t){t.setAttribute('data-lpi-x','1');return '[data-lpi-x=\"1\"]';}" if kind == "text" else
            f"const re=new RegExp({json.dumps(_BUTTONS.get(kind, ''))},'i');for(const e of d.querySelectorAll('button,a,[role=button]')){{"
            "const t=(e.getAttribute('aria-label')||e.innerText||'').trim();"
            "if(re.test(t)&&!e.disabled&&e.getAttribute('aria-disabled')!=='true'){e.setAttribute('data-lpi-x','1');return '[data-lpi-x=\"1\"]';}}")
    return (f"/*tag:{kind}*/(()=>{{const d=document.querySelector('[role=dialog],.artdeco-modal');if(!d)return '';let t;"
            "document.querySelectorAll('[data-lpi-x]').forEach(x=>x.removeAttribute('data-lpi-x'));" + pick + "return '';})()")


# ------------------------------------------------------------------ plain helpers (tested without any browser)
def first_name(full):
    word = re.sub(r"[^\w'-]", "", str(full or "").strip().split(" ")[0]) if str(full or "").strip() else ""
    if word.lower() in ("linkedin", "member", "membre", "utilisateur"):             # LinkedIn hides some names as « LinkedIn Member »
        return ""
    return word.capitalize() if word.isalpha() or "-" in word else ""


def make_note(template, name):
    """The note for one person. {prenom} becomes the first name (or disappears cleanly when LinkedIn gave no name)."""
    first = first_name(name)
    text = template.replace("{prenom}", first) if first else re.sub(r"\s*\{prenom\}", "", template)
    return re.sub(r"\s+([,.!])", r"\1", text).strip()


def blocker(state):
    """A reason to stop when the page is a login wall, a security check or a limit message. '' when all is well."""
    url = str(state.get("url", "")).lower()
    head = norm(str(state.get("title", "")))
    body = norm(str(state.get("body", "")))
    if "/checkpoint/challenge" in url or re.search(r"security verification|verification de securite|quick security check|captcha|verification rapide", head + " " + body):
        db.set(linkedin.STOP_KEY, 1, ex=3600)
        return "LinkedIn demande une verification de securite. Je ne la contourne pas : fais /connexion linkedin et valide-la toi-meme."
    if re.search(r"/(?:login|authwall|checkpoint|uas/)", url) or re.search(r"\b(?:sign in|s.identifier|se connecter)\b", head):
        return "ta session LinkedIn n'est plus valide. Fais /connexion linkedin et connecte-toi toi-meme, puis redis-moi de continuer."
    if re.search(r"weekly invitation limit|limite hebdomadaire|reached the weekly|atteint la limite", body):
        return "LinkedIn dit que la limite d'invitations de la semaine est atteinte. Je m'arrete : reessaie la semaine prochaine."
    return ""


def counted_today():
    return int(db.get(f"linkedin:invite:day:{datetime.now():%Y%m%d}") or 0)


def counted_week():
    return int(db.get(f"linkedin:invite:week:{datetime.now():%G%V}") or 0)


def budget():
    """How many invitations may still go out today."""
    return max(0, min(DAY_MAX - counted_today(), WEEK_MAX - counted_week()))


def _count_one():
    for key, ttl in ((f"linkedin:invite:day:{datetime.now():%Y%m%d}", 90000), (f"linkedin:invite:week:{datetime.now():%G%V}", 700000)):
        db.incr(key)
        db.expire(key, ttl)


def state():
    raw = db.get(JOB_KEY)
    job = json.loads(raw) if raw else {}
    return {"en_cours": bool(job), **({"envoyees": job.get("sent", 0), "voulues": job.get("want", 0), "recherche": job.get("kw", "")} if job else {}),
            "aujourdhui": counted_today(), "limite_jour": DAY_MAX, "cette_semaine": counted_week(), "limite_semaine": WEEK_MAX,
            "pause_linkedin": bool(db.exists(linkedin.STOP_KEY))}


def stop():
    if not db.exists(JOB_KEY):
        return {"resultat": "aucune invitation en cours"}
    db.set(STOP_KEY, 1, ex=600)
    return {"resultat": "j'arrete apres l'invitation en cours"}


# ------------------------------------------------------------------ the work
def _driver():
    return realbrowser.DRIVER


def _json(raw, default):
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def _wait(fn, seconds, step=0.4):
    end = time.time() + seconds
    while True:
        got = fn()
        if got:
            return got
        if time.time() >= end:
            return got
        time.sleep(step)


def _stopped():
    return bool(db.exists(STOP_KEY))


def _pause(seconds):
    end = time.time() + seconds
    while time.time() < end and not _stopped():
        time.sleep(min(2.0, max(0.0, end - time.time())))


def _dialog(b):
    return _json(b.js(DIALOG_JS), {})


def _dismiss(b):
    """Closes whatever dialog is open (Escape), twice because LinkedIn may ask « discard ? »."""
    for _ in range(2):
        if not _dialog(b):
            return
        b.call("press", key="Escape")
        time.sleep(0.6)


def invite_one(b, cand, note):
    """One person: Connect, Add a note, write it, Send. Returns 'ok', or a short reason when it did not go through. Raises Stop when the job must end."""
    if _dialog(b):
        _dismiss(b)
    b.call("click", selector=cand["sel"])
    dialog = _wait(lambda: _dialog(b), 6)
    if not dialog:
        raise Stop(f"LinkedIn n'a pas ouvert la fenetre de note pour {cand.get('name') or 'cette personne'} : je m'arrete pour ne pas envoyer d'invitation sans note. "
                   "Regarde sur /connexion si l'invitation est partie.")
    if not dialog.get("textarea"):
        add = b.js(tag_js("note"))
        if not add:
            if re.search(r"limit|premium|limite|abonnement", norm(dialog.get("text", ""))):
                raise Stop("LinkedIn ne laisse plus ecrire de note avec ce compte (les comptes gratuits n'en ont que quelques-unes par mois). "
                           "Je m'arrete. Tu veux que j'envoie les invitations sans note ? Dis-le moi.")
            _dismiss(b)
            return "pas de bouton note"
        b.call("click", selector=add)
        if not _wait(lambda: _dialog(b).get("textarea"), 5):
            _dismiss(b)
            return "la zone de note n'est pas apparue"
    area = b.js(tag_js("text"))
    if not area:
        _dismiss(b)
        return "zone de note introuvable"
    b.call("fill", selector=area, value=note)
    if b.js(VALUE_JS).strip() != note.strip():
        _dismiss(b)
        return "la note ne s'est pas ecrite correctement"
    send_btn = _wait(lambda: b.js(tag_js("send")), 4)
    if not send_btn:
        _dismiss(b)
        return "bouton envoyer introuvable"
    b.call("click", selector=send_btn)
    if _wait(lambda: not _dialog(b), 8):
        return "ok"
    _dismiss(b)
    return "LinkedIn n'a pas valide l'envoi"


def _candidates(b):
    b.js(SCROLL_JS)
    time.sleep(1.2)
    return _json(b.js(FIND_JS), [])


def _run(chat_id, kw, template, want):
    sent, names, problems = [], [], []
    reason = ""
    seen = set()
    try:
        b = _driver()
        for page in range(1, MAX_PAGES + 1):
            if len(sent) >= want or reason:
                break
            b.call("goto", url=SEARCH.format(kw=quote(kw), page=page))
            time.sleep(2.5)
            bad = blocker(_json(b.js(STATE_JS), {}))
            if bad:
                raise Stop(bad)
            cands = _candidates(b)
            fresh = [c for c in cands if c.get("url") and c["url"] not in seen and not db.sismember(DONE_KEY, c["url"]) and not db.sismember(SKIP_KEY, c["url"])]
            seen.update(c["url"] for c in cands if c.get("url"))
            if not fresh:
                reason = "je n'ai plus trouve de personnes a inviter dans cette recherche"
                continue
            for cand in fresh:
                if len(sent) >= want:
                    break
                if _stopped():
                    raise Stop("arrete comme demande")
                if budget() <= 0:
                    raise Stop(f"limite atteinte ({DAY_MAX} par jour, {WEEK_MAX} par semaine) pour proteger ton compte")
                screen.extend(15)                                 # the screen must not close in the middle of the job
                bad = blocker(_json(b.js(STATE_JS), {}))
                if bad:
                    raise Stop(bad)
                result = invite_one(b, cand, make_note(template, cand.get("name")))
                if result == "ok":
                    db.sadd(DONE_KEY, cand["url"])
                    _count_one()
                    sent.append(cand["url"])
                    names.append(cand.get("name") or cand["url"].rstrip("/").rpartition("/")[2])
                    db.set(JOB_KEY, json.dumps({"kw": kw, "want": want, "sent": len(sent)}), ex=7200)
                    if len(sent) % 10 == 0 and len(sent) < want:
                        send(chat_id, f"LinkedIn : {len(sent)} invitations envoyees sur {want}.")
                else:
                    db.sadd(SKIP_KEY, cand["url"])
                    db.expire(SKIP_KEY, 7 * 86400)
                    problems.append(result)
                    if len(problems) >= 3 and len(problems) > len(sent):
                        raise Stop("trop d'echecs de suite (" + problems[-1] + ") : LinkedIn a sans doute change sa page. Je m'arrete, rien d'autre n'est parti.")
                if len(sent) < want:
                    _pause(random.uniform(*PAUSE))
    except (Stop, realbrowser.Stop, linkedin.Stop) as e:
        reason = str(e)
    except Exception as e:
        log.warning("invitations linkedin : %s", scrub(e))
        reason = "erreur inattendue : " + scrub(e)[:120]
    finally:
        db.delete(JOB_KEY)
        db.delete(STOP_KEY)
    lines = [f"LinkedIn : {len(sent)} invitation(s) envoyee(s) avec ta note" + (f" (sur {want} demandees)." if len(sent) < want else ".")]
    if names:
        lines.append("A : " + ", ".join(names[:40]))
    if reason:
        lines.append("Arret : " + reason)
    if problems and len(problems) < 3:
        lines.append(f"{len(problems)} personne(s) sautee(s) : " + "; ".join(dict.fromkeys(problems)))
    send(chat_id, "\n".join(lines))


def _spawn(*args):
    threading.Thread(target=_run, args=args, daemon=True).start()


def start(chat_id, keywords, note, count=30):
    """Checks everything that can be checked without the browser, then runs the job in the background."""
    kw = re.sub(r"\s+", " ", str(keywords or "")).strip()[:80]
    template = re.sub(r"[ \t]+", " ", str(note or "")).strip()
    if not kw:
        return {"erreur": "dis-moi qui chercher (par exemple : YC founder)"}
    if len(template) < 20:
        return {"erreur": "il faut une note d'au moins 20 caracteres : ecris-la avec l'utilisateur, puis relance"}
    if len(template.replace("{prenom}", "X" * 20)) > NOTE_MAX:
        return {"erreur": f"la note est trop longue : LinkedIn accepte {NOTE_MAX} caracteres au maximum"}
    if db.exists(JOB_KEY):
        return {"erreur": "des invitations sont deja en cours : dis stop pour les arreter"}
    if db.exists(linkedin.STOP_KEY):
        return {"erreur": "LinkedIn a demande de ralentir : je reessaie plus tard, pas avant une heure"}
    room = budget()
    if room <= 0:
        return {"erreur": f"limite atteinte ({DAY_MAX} par jour, {WEEK_MAX} par semaine) : je reprends demain"}
    want = max(1, min(int(count or 30), room))
    db.delete(STOP_KEY)
    db.set(JOB_KEY, json.dumps({"kw": kw, "want": want, "sent": 0}), ex=7200)
    _spawn(chat_id, kw, template, want)
    sample = make_note(template, "Alex")
    minutes = int(want * sum(PAUSE) / 2 / 60) + 1
    return {"statut": "lance en arriere-plan", "invitations_prevues": want, "duree_environ_minutes": minutes, "note_exemple": sample,
            "dis_a_l_utilisateur": f"C'est parti : {want} invitations avec ta note, environ {minutes} minutes, une toutes les minutes pour ne pas risquer ton compte. "
                                   "Je te previens a la fin. Dis « stop linkedin » pour arreter. LinkedIn n'aime pas les envois automatiques : c'est ton choix, et je m'arrete a la moindre alerte."}
