"""Language models: web search, Gemini, the OpenAI-compatible providers (Groq, Cloudflare, Cerebras) and their fallback order."""

import copy
import re
import time

import requests

from .config import ALL_MODELS, GEMINI_KEY, MODELS, MODEL_API
from .core import NET, db, log, norm, scrub
from . import catalog

# ---------------------------------------------------------------- recherche + Gemini
def web_search(query, n=5, kind="text"):
    """Recherche DuckDuckGo (gratuite, sans cle). kind="news" pour l'actualite. Renvoie [] en cas d'echec."""
    try:
        from ddgs import DDGS
        if kind == "news":
            return [{**r, "href": r.get("url", "")} for r in (DDGS(timeout=6).news(query, max_results=n, region="fr-fr") or [])]
        return DDGS(timeout=4).text(query, max_results=n, region="fr-fr") or []
    except Exception as e:
        log.warning("recherche web indisponible : %s", scrub(e))
        return []


def _call_model(model, body):
    """Un appel a un modele precis. Gemma n'a pas de 'systemInstruction' : on la colle devant la question."""
    b = copy.deepcopy(body)
    if model.startswith("gemma"):
        b.pop("tools", None)                            # Gemma n'a pas d'outils
        system = b.pop("systemInstruction", None)
        first = b["contents"][0]["parts"][0]
        if system and "text" in first:
            first["text"] = system["parts"][0]["text"] + "\n\n" + first["text"]
    else:
        # "thinkingLevel: low" : le modele reflechit moins longtemps -> reponse nettement plus rapide
        b["generationConfig"] = {"thinkingConfig": {"thinkingLevel": "low"}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(url, json=b, headers={"x-goog-api-key": GEMINI_KEY}, timeout=15)
    if resp.status_code == 400 and "generationConfig" in b:   # reglage non accepte : on s'en passe
        del b["generationConfig"]
        resp = requests.post(url, json=b, headers={"x-goog-api-key": GEMINI_KEY}, timeout=15)
    return resp


def call_gemini(body):
    """Essaie les modeles gratuits l'un apres l'autre : chacun a son propre quota.
    Un modele sature (429/503) ou indisponible est mis de cote quelques minutes."""
    # Gemma ne comprend ni l'audio ni les appels d'outils
    has_audio = any(k in p for c in body["contents"] for p in c["parts"] for k in ("inline_data", "functionCall", "functionResponse"))
    resp = None
    for model in MODELS:
        if has_audio and model.startswith("gemma"):
            continue                                   # Gemma ne comprend pas l'audio
        if db.get(f"cool:{model}"):
            continue
        t0 = time.time()
        try:
            resp = _call_model(model, body)
        except requests.RequestException as e:
            log.warning("modele %s injoignable : %s", model, scrub(e))
            db.setex(f"cool:{model}", 300, 1)
            continue
        log.info("modele %s : %.1f s (code %s)", model, time.time() - t0, resp.status_code)
        if resp.status_code == 200:
            return resp
        if resp.status_code == 429:
            # quota du jour epuise : repos long ; quota de la minute : on reessaie apres ~1 minute
            db.setex(f"cool:{model}", 3600 if "PerDay" in resp.text else 65, 1)
        elif resp.status_code in (404, 500, 503):
            db.setex(f"cool:{model}", 300, 1)              # modele sature : on l'evite 5 min (pas de 6 s perdues a chaque question)
    if resp is None:                                   # tous les modeles sont au repos : on reessaie le premier
        resp = _call_model(MODELS[0], body)
    return resp


def clean_answer(text):
    """Enleve les restes de reflexion du modele (<think>...</think>, ou texte avant un </think> orphelin)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.replace("<think>", "").strip()


HARD = re.compile(r"\b(analys|compar|strateg|plan|expliqu|pourquoi|comment faire|conseil|decid|choisir|choix|resum|redige|ecris|code|script|probleme|bug|organis|budget|idee)", re.I)


ACTION = re.compile(r"\b(cherche|trouve|fais|fait|installe|cree|ecris|envoie|telecharge|lis|ouvre|sauvegarde|supprime|deplace|compare|calcule|"
                    r"convertis|traduis|resume|analyse|surveille|programme|organise|prepare|reserve|configure|repare|corrige|ameliore|genere)", re.I)
DEEP = re.compile(r"\b(strateg|analys|compar|architecture|debug|bug|code|script|optimis|etape par etape|raisonn|calcul|demonstr|probleme)", re.I)


def effort(question, oral):
    """Courte conversation : reponse eclair. Action ou question de fond : il reflechit plus. Gros sujet : a fond."""
    q = norm(question)
    if oral:
        return "low"
    if len(q) > 400 or DEEP.search(q):
        return "high"
    return "medium" if (len(q) > 60 or HARD.search(q) or ACTION.search(q)) else "low"


def llm_models():
    """Model list in the order to try: the one picked with /model first, then the others as fallback."""
    ms = list(ALL_MODELS)
    pref = db.get("model_pref")
    if pref in ms:
        ms.remove(pref)
        ms.insert(0, pref)
    return ms


def model_command(chat_id, arg):
    """/model : show the models, /model 2 or /model <name> : use that one first, /model auto : back to the default order."""
    arg = arg.strip()
    if arg.lower() in ("auto", "default", "reset"):
        db.delete("model_pref")
        return "Back to automatic: " + ALL_MODELS[0] + " first, the others as backup."
    if arg:
        pick = ALL_MODELS[int(arg) - 1] if arg.isdigit() and 1 <= int(arg) <= len(ALL_MODELS) else (arg if arg in ALL_MODELS else None)
        if pick is None:
            return "Unknown model. Send /model to see the list."
        db.set("model_pref", pick)
        db.delete(f"cool:{pick}")
        return f"OK, I will use {pick} first."
    cur = llm_models()[0]
    host = lambda m: MODEL_API[m][0].split("//")[-1].split("/")[0]
    lines = [f"{i}. {m} ({host(m)}){'  <- in use' if m == cur else ''}" for i, m in enumerate(ALL_MODELS, 1)]
    return ("Models I can use:\n" + "\n".join(lines)
            + "\n\n/model 2 : use number 2 first\n/model auto : default order. If one fails, I try the next automatically.")


REFUSAL = re.compile(r"\b(je ne peux pas|je n.?ai pas (la possibilit|acc[eè]s|les moyens)|je suis (incapable|dans l.impossibilit)|impossible de|"
                     r"je ne suis pas (capable|en mesure)|i can.?t|i cannot|i am unable|i.m unable|not able to)", re.I)
NUDGE = ("[Systeme] Avant de dire que tu ne peux pas : cherche une voie avec tes outils (run_command, python_run, browser, fetch_url, http_request, "
         "write_file) et essaie vraiment. Si c'est reellement impossible (materiel absent, ou ca demande la validation de l'utilisateur), "
         "explique precisement pourquoi en une phrase et propose la meilleure alternative. Les validations Oui/Non restent obligatoires.")
MAX_STEPS = 16


_LEAK = re.compile(r"<\|(?:channel|call|start|end|message|return)\|>")


def leaked_field(r):
    """Which part of the answer shows raw model markers. Only what would reach the user or run as a tool counts: a hidden 'reasoning' field is allowed to contain them."""
    try:
        msg = r.json()["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return "reponse" if _LEAK.search(r.text.replace("\\u003c", "<").replace("\\u003e", ">")) else ""
    if _LEAK.search(str(msg.get("content") or "")):
        return "content"
    for c in msg.get("tool_calls") or []:
        fn = (c or {}).get("function") or {}
        if _LEAK.search(str(fn.get("name") or "") + str(fn.get("arguments") or "")):
            return "tool_calls"
    return ""


def llm_call(messages, question, oral, tools=True, toolset=None, plain=False, _retry=True):
    """Un appel au premier modele disponible (les suivants en secours). Renvoie la reponse HTTP, ou None si tous sont indisponibles."""
    for model in llm_models():
        if db.get(f"cool:{model}"):
            continue
        t0 = time.time()
        try:
            base, key = MODEL_API[model]
            body = ({"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 500,
                     **({"reasoning_effort": "low"} if "gpt-oss" in model else {})} if plain else
                    {"model": model, "messages": messages, "tools": toolset or catalog.GROQ_TOOLS, "tool_choice": "auto" if tools else "none",
                     "temperature": 0.4, "max_tokens": 2000,
                     **({"reasoning_effort": effort(question, oral)} if "gpt-oss" in model else {})})
            r = NET.post(f"{base}/chat/completions", timeout=45, headers={"Authorization": f"Bearer {key}"}, json=body)
        except requests.RequestException as e:
            log.warning("llm %s injoignable : %s", model, scrub(e))
            db.setex(f"cool:{model}", 60, 1)
            continue
        log.info("llm %s : %.1f s (code %s)", model, time.time() - t0, r.status_code)
        if r.status_code == 200:
            field = leaked_field(r)
            if field:                                  # le modele a recopie son brouillon interne (format gpt-oss brut) : on ne l'envoie JAMAIS a l'utilisateur
                log.warning("llm %s : brouillon interne dans %s, on passe au suivant", model, field)
                db.setex(f"cool:{model}", 60, 1)
                continue
            try:
                m0 = r.json()["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError):
                m0 = None
            if m0 is not None and not m0.get("tool_calls") and not (m0.get("content") or "").strip():       # reponse vide (le modele a tout depense en reflexion) : on essaie le suivant
                log.warning("llm %s : reponse vide, on passe au suivant", model)
                db.setex(f"cool:{model}", 30, 1)
                continue
            return r
        if r.status_code == 429:
            m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", r.text)       # Groq dit lui-meme quand ca remarche a nouveau
            wait = int(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3))) + 2 if m else (3600 if "per day" in r.text.lower() else 20)
            db.setex(f"cool:{model}", max(5, min(wait, 3600)), 1)
        elif r.status_code not in (400, 413):          # 400 = appel d'outil rate, 413 = requete trop grosse pour CE modele : on tente le suivant, sans le bloquer
            db.setex(f"cool:{model}", 120, 1)
    if _retry:                                         # Groq dit souvent "reessaie dans 5 a 20 s" : on attend un peu plutot que de passer tout de suite a Gemini (souvent sature)
        ttls = [db.ttl(f"cool:{m}") for m in llm_models()]
        ttls = [t for t in ttls if t and t > 0]
        if ttls and min(ttls) <= 25:
            time.sleep(min(ttls) + 1)
            return llm_call(messages, question, oral, tools, toolset, plain, _retry=False)
    return None
