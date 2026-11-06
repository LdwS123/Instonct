"""Language models: web search, Gemini, the OpenAI-compatible providers (Groq, Cloudflare, Cerebras) and their fallback order."""

import copy
import json
import os
import re
from urllib.parse import unquote, urlsplit
import time
from datetime import datetime

import requests

from .config import ALL_MODELS, GEMINI_KEY, MODELS, MODEL_API
from .core import NET, db, log, norm, scrub
from . import catalog, perf

# ---------------------------------------------------------------- recherche + Gemini
_AD_LINK = re.compile(r"/aclick\?|duckduckgo\.com/y\.js|googleadservices\.")


SPARE_ENGINES = "brave,startpage,mojeek,yahoo"      # other engines of the same library: used only when the usual mix finds nothing
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888")     # our own search engine on this machine ("" = not installed)


def searxng(query, n, kind):
    """Our own SearXNG (it asks about twenty engines at once). [] if it is not installed or does not answer."""
    if not SEARXNG_URL:
        return []
    try:
        r = requests.get(SEARXNG_URL + "/search", params={"q": query, "format": "json", "language": "fr", "categories": "news" if kind == "news" else "general"}, timeout=12)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "body": x.get("content", ""), "href": x.get("url", ""), "date": (x.get("publishedDate") or "")[:10]}
                for x in r.json().get("results", []) if x.get("url") and not _AD_LINK.search(x["url"])][:n]
    except (requests.RequestException, ValueError) as e:
        log.warning("searxng indisponible : %s", scrub(e)[:100])
        return []


def web_search(query, n=5, kind="text"):
    """Recherche web gratuite, sans cle : DuckDuckGo (ddgs), puis notre SearXNG, puis d'autres moteurs. kind="news" pour l'actualite. Renvoie [] en cas d'echec."""
    try:
        from ddgs import DDGS
    except ImportError:
        return searxng(query, n, kind)
    for step in ("ddgs", "searxng", "spare"):
        if step == "searxng":
            found = searxng(query, n, kind)
        else:
            try:
                if kind == "news":
                    found = [{**r, "href": r.get("url", "")} for r in (DDGS(timeout=6).news(query, max_results=n, region="fr-fr") or [])] if step == "ddgs" else []
                else:
                    found = [r for r in (DDGS(timeout=8 if step == "spare" else 4).text(query, max_results=n, region="fr-fr", **({"backend": SPARE_ENGINES} if step == "spare" else {})) or [])
                             if not _AD_LINK.search(r.get("href", ""))]
            except Exception as e:
                log.warning("recherche web (%s) indisponible : %s", step, scrub(e))
                found = []
        if found:
            return found
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
            db.set(f"cool:{model}", 1, ex=300)
            continue
        log.info("modele %s : %.1f s (code %s)", model, time.time() - t0, resp.status_code)
        if resp.status_code == 200:
            return resp
        if resp.status_code == 429:
            # quota du jour epuise : repos long ; quota de la minute : on reessaie apres ~1 minute
            db.set(f"cool:{model}", 1, ex=3600 if "PerDay" in resp.text else 65)
        elif resp.status_code in (404, 500, 503):
            db.set(f"cool:{model}", 1, ex=300)              # modele sature : on l'evite 5 min (pas de 6 s perdues a chaque question)
    if resp is None:                                   # tous les modeles sont au repos : on reessaie le premier
        resp = _call_model(MODELS[0], body)
    return resp


# Some models end with a word from their own checklist, sometimes stuck to the last sentence.
_FILLER = re.compile(r"(?:(?<=[.!?])\s*(?:check|all set|done)\b[.!]?)+\s*$", re.I)
_GLUED_END = re.compile(r"(?:(?<=[.!?])(?:c.est note|bonne chance|voila)[.!]?)+\s*$", re.I)
_GLUED = re.compile(r"([a-zà-ÿ]{2})\.([A-ZÀ-Ý][a-zà-ÿ'’])")


def false_claim(answer, ran):
    """True if the answer says something was done by a tool that did not run."""
    said = norm(answer or "")
    return any(rx.search(said) and not (tools & ran) for rx, tools in CLAIMS)


_LINK = re.compile(r"https?://[^\s<>\"')\]]+")
_PRICE = re.compile(r"(\d[\d\s.,]*\d|\d)\s?(?:€|\$|euros?\b|dollars?\b)", re.I)


def _number(text):
    return re.sub(r"[\s.,]", "", text)


def invented(answer, known):
    """Deep links and prices in the answer that no tool result, nor the conversation, ever showed. A model writes these with full confidence, so plain code checks them."""
    answer = answer or ""
    seen = unquote(known)
    numbers = {_number(n) for n in re.findall(r"\d[\d\s.,]*\d|\d", seen)}
    links = [u.rstrip(".,;:!?*") for u in _LINK.findall(answer)]
    return ([u for u in links if urlsplit(u).path.strip("/") and unquote(u) not in seen] +
            [m.group(0).strip() for m in _PRICE.finditer(answer) if _number(m.group(1)) not in numbers])


_JSON_STUB = re.compile(r'\{\s*"\w+"\s*:[^{}]*\}')
_SENTENCE = re.compile(r'(?<=[.!?])\s*(?=[A-Z{"])')
_EN_WORDS = frozenset("the user wants want to need needs what else anything you your we should let is are with and for this that please confirm confirmation ask which "
                      "game games play delete memory answer respond reply i will can it of a an be do does not they them his her".split())
_FR_WORDS = frozenset("le la les un une des je tu il elle est pas de du que qui ne ce et en dans pour mais avec sur vous nous ton ta tes mon ma mes quel quelle veux peux "
                      "dis moi toi suis sont ai as a ete fait oui non voici voila donc ou ici deja bien tres plus moins".split())


def _english(sentence):
    words = re.findall(r"[a-z']+", sentence.lower())
    fr = sum(w in _FR_WORDS for w in words if w not in ("a", "i", "do", "is"))
    en = sum(w in _EN_WORDS for w in words)
    return fr == 0 and (en >= 2 or (en >= 1 and len(words) <= 2 and bool(re.match(r"(?:need|user|ok|so)\b", sentence.strip().lower()))))


def drop_english_notes(text):
    """The model sometimes leaves its English thinking ("User wants to play video games.") between French sentences, and tool stubs like {"text":"tout"}. Only a mixed text is touched: a fully English answer stays."""
    text = _JSON_STUB.sub("", text or "")
    parts = [p for p in _SENTENCE.split(text) if p.strip()]
    if len(parts) < 2:
        return text.strip()
    mine = [not _english(p) for p in parts]
    if all(mine) or not any(re.search(r"[éèêàçùôî]|\b(?:je|tu|le|la|les|des|est|pas|que|vous|nous)\b", p.lower()) for p, keep in zip(parts, mine) if keep):
        return text.strip()                          # nothing to remove, or no French around it: an English answer stays
    return " ".join(p.strip() for p, keep in zip(parts, mine) if keep)


def clean_answer(text):
    """Enleve les restes de reflexion du modele (<think>...</think>, ou texte avant un </think> orphelin)."""
    text = re.sub(r"<think>.*?</think>|【[^】]*】", "", text or "", flags=re.S)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    text = drop_english_notes(text.replace("<think>", "").strip())
    restart = text.find(text[:6], 6) if len(text) > 40 else -1      # some models write a draft, then start the same answer again right after its last full stop
    text = text[restart:] if restart > 0 and text[restart - 1] in ".!?" else text
    text = _FILLER.sub("", _GLUED_END.sub("", text)).rstrip()
    return " ".join(_GLUED.sub(r"\1. \2", w) if "://" not in w and "@" not in w else w for w in re.split(r"(?<=\S) (?=\S)", text)) if _GLUED.search(text) else text


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
    lines = []
    for i, m in enumerate(ALL_MODELS, 1):
        lines.append(f"{i}. {m} ({host(m)}){'  <- in use' if m == cur else ''}")
        lines += usage_detail(m)
    today = usage_today()
    return ("Models I can use:\n" + "\n".join(lines)
            + ("\n\nTotal today:\n" + "\n".join(today) if today else "")
            + "\n\n/model 2 : use number 2 first\n/model auto : default order. If one fails, I try the next automatically.")


REFUSAL = re.compile(r"\b(je ne peux pas|je n.?ai pas (la possibilit|acc[eè]s|les moyens)|je suis (incapable|dans l.impossibilit)|impossible de|"
                     r"je ne suis pas (capable|en mesure)|i can.?t|i cannot|i am unable|i.m unable|not able to)", re.I)
NUDGE = ("[Systeme] Avant de dire que tu ne peux pas : appelle chercher_outil(besoin), puis cherche une voie avec tes outils (run_command, python_run, browser, fetch_url, http_request, "
         "write_file) et essaie vraiment. Si c'est reellement impossible (materiel absent, ou ca demande la validation de l'utilisateur), "
         "explique precisement pourquoi en une phrase et propose la meilleure alternative. Les validations Oui/Non restent obligatoires.")
MAX_STEPS = 16
# An answer that announces an action needs that action to have run in this turn.
CLAIMS = ((re.compile(r"rappel (est |a ete |bien )?(programm|prevu|cree|enregistr)|voici le rappel|je te rappellerai", re.I), {"set_reminder", "schedule_task", "todo_add", "routine_save"}),
          (re.compile(r"(mis|mise|mises) a la corbeille|j.ai (supprime|efface|archive)|(ont|a) ete (supprime|efface|archive)", re.I), {"mail_manage", "mail_clean", "calendar_delete", "run_command", "todo_done"}),
          (re.compile(r"j.ai envoye|(mail|message) (est |a ete |bien )?envoye", re.I), {"mail_send", "mail_reply", "run_command", "http_request"}),
          (re.compile(r"j.ai (bien )?(appele|telephone)|je viens (d.appeler|de telephoner)", re.I), set()),                       # no phone line is plugged in: this is never true
          (re.compile(r"j.ai (bien )?(paye|achete|commande)|je viens (de payer|d.acheter|de commander)|commande (est |a ete )?passee|paiement (est |a ete )?effectue", re.I), set()),   # paying is always the user's hand
          (re.compile(r"(?:j.ai|je t.ai) (?:bien )?(?:ajoute|mis)\b.{0,80}\bpanier|(?:ajoute|mis) (?:a|dans) ton panier|(?:j.ai|je t.ai) (?:bien )?ouvert (?:la |le |une |un )?(?:page|site|lien)", re.I), {"browser"}),
          (re.compile(r"(?:j.eteins|j.allume|j.arrete|je coupe|j.ai (?:bien )?(?:eteint|allume|coupe|arrete|mis))\b.{0,25}\b(?:tele|television|televiseur)\b"
                      r"|\b(?:tele|television|televiseur)\b.{0,12}\b(?:est|s.est) (?:maintenant |bien |bien en train d.etre )?(?:eteinte|allumee|arretee|coupee)", re.I), {"tv_remote", "show_remote"}),
          (re.compile(r"musique (?:est )?(?:bien )?(?:arretee|coupee|en pause|lancee|reprise|stoppee)|j.(?:arrete|ai (?:bien )?(?:arrete|coupe|lance|mis en pause))\b.{0,25}\b(?:musique|chanson|morceau|video|titre)", re.I),
           {"play_music", "music_control", "tv_remote"}),
          (re.compile(r"(?:volume|le son) (?:de la tele )?(?:est )?(?:bien )?(?:monte|baisse|regle|coupe|mis)\b|j.ai (?:bien )?(?:monte|baisse|coupe|regle)\b.{0,15}\b(?:son|volume)", re.I),
           {"change_volume", "set_volume", "tv_remote"}),
          (re.compile(r"j.ai reserve|je viens de reserver|c.est (bien |tout )?reserve\b(?! aux?\b)|billet (est |a ete )?reserve|reservation (est |a ete )?confirmee", re.I), {"calendar_create"}))
INVENTED = ("[Systeme] Ces liens ou prix de ta reponse ne viennent d'aucun resultat d'outil : %s. Tu les as probablement inventes. Va les chercher avec un outil, "
            "ou reecris ta reponse sans eux en disant ce que tu n'as pas pu verifier. Si tu as calcule un montant, dis-le.")
NOT_DONE = ("Je n'ai pas reussi a le faire : l'action n'est pas partie, donc ne compte pas dessus. "
            "Redis-le plus simplement (ex. « eteins la tele »), ou utilise la telecommande : dis « telecommande ».")
UNVERIFIED = "\n\n(Attention : je n'ai pas pu verifier ces liens ou ces prix : %s.)"
FALSE_CLAIM = ("[Systeme] Tu viens d'annoncer une action alors que l'outil n'a pas ete appele dans ce tour. Appelle l'outil maintenant, "
               "ou corrige ta reponse et dis franchement que ce n'est pas fait.")


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


def _usage_key(day=None):
    return f"usage:{day or datetime.now():%Y-%m-%d}"


def _meter(model, r, seconds=0.0):
    """Counts calls, tokens and time per model and per day: this is how we see if the good model really answers."""
    try:
        tokens = int((r.json().get("usage") or {}).get("total_tokens") or 0)
    except (ValueError, TypeError, AttributeError):
        tokens = 0
    key = _usage_key()
    db.hincrby(key, f"{model}|calls", 1)
    db.hincrby(key, f"{model}|tokens", tokens)
    db.hincrby(key, f"{model}|ms", int(seconds * 1000))
    db.expire(key, 8 * 86400)


def _seen(model, r):
    """What the provider says about its own limits (x-ratelimit-* headers), and how often it said "too many requests"."""
    try:
        if r.status_code == 429:
            db.hincrby(_usage_key(), f"{model}|limited", 1)
        found = {k.lower(): str(v) for k, v in r.headers.items() if k.lower().startswith("x-ratelimit-") and ("remaining" in k.lower() or "limit" in k.lower())}
        if found:
            db.hset("limits", model, json.dumps(found))
    except (AttributeError, TypeError, ValueError):
        pass


def _left(model):
    """"requests 14,350/14,400 · tokens 7,900/8,000" from the last answer of this model, or ''."""
    try:
        h = json.loads(db.hget("limits", model) or "{}")
    except ValueError:
        return ""
    out = []
    for k, rem in sorted(h.items()):
        if not k.startswith("x-ratelimit-remaining-"):
            continue
        name = k[len("x-ratelimit-remaining-"):]
        lim = h.get("x-ratelimit-limit-" + name)
        try:
            out.append(f"{name.replace('-', ' ')} {int(float(rem)):,}" + (f"/{int(float(lim)):,}" if lim else ""))
        except ValueError:
            continue
    return " · ".join(out)


def usage_detail(model):
    """Today's figures for one model: calls, tokens, average speed, refusals for 'too many requests', pause, and what is left."""
    u = db.hgetall(_usage_key())
    calls, tokens = int(u.get(f"{model}|calls", 0)), int(u.get(f"{model}|tokens", 0))
    lines = []
    if calls or u.get(f"{model}|limited"):
        bits = [f"{calls} calls", f"{tokens:,} tokens"]
        if calls and int(u.get(f"{model}|ms", 0)):
            bits.append(f"{int(u.get(f'{model}|ms', 0)) / calls / 1000:.1f} s on average")
        if int(u.get(f"{model}|limited", 0)):
            bits.append(f"{u.get(f'{model}|limited')}x \"too many requests\"")
        lines.append("   today: " + ", ".join(bits))
    wait = db.ttl(f"cool:{model}")
    if wait and wait > 0:
        lines.append(f"   resting for {wait} s")
    left = _left(model)
    if left:
        lines.append("   left: " + left)
    return lines


def usage_today():
    u = db.hgetall(_usage_key())
    models = sorted({k.rsplit("|", 1)[0] for k in u}, key=lambda m: -int(u.get(f"{m}|calls", 0)))
    return [f"{m}: {u.get(f'{m}|calls', 0)} calls, {int(u.get(f'{m}|tokens', 0)):,} tokens" for m in models]


def llm_call(messages, question, oral, tools=True, toolset=None, plain=False, _retry=True):
    """Un appel au premier modele disponible (les suivants en secours). Renvoie la reponse HTTP, ou None si tous sont indisponibles."""
    for model in llm_models():
        if db.get(f"cool:{model}"):
            continue
        t0 = time.time()
        try:
            base, key = MODEL_API[model]
            offered = catalog.GROQ_TOOLS if toolset is None else toolset
            body = ({"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 500,
                     **({"reasoning_effort": "low"} if "gpt-oss" in model else {})} if plain else
                    {"model": model, "messages": messages, "temperature": 0.4, "max_tokens": 2000,
                     **({"tools": offered, "tool_choice": "auto" if tools else "none"} if offered else {}),
                     **({"reasoning_effort": effort(question, oral)} if "gpt-oss" in model else {})})
            r = NET.post(f"{base}/chat/completions", timeout=45, headers={"Authorization": f"Bearer {key}"}, json=body)
        except requests.RequestException as e:
            log.warning("llm %s injoignable : %s", model, scrub(e))
            db.set(f"cool:{model}", 1, ex=60)
            continue
        log.info("llm %s : %.1f s (code %s)", model, time.time() - t0, r.status_code)
        perf.add("modele", time.time() - t0)
        _seen(model, r)
        if r.status_code == 200:
            field = leaked_field(r)
            if field:                                  # le modele a recopie son brouillon interne (format gpt-oss brut) : on ne l'envoie JAMAIS a l'utilisateur
                log.warning("llm %s : brouillon interne dans %s, on passe au suivant", model, field)
                db.set(f"cool:{model}", 1, ex=60)
                continue
            try:
                m0 = r.json()["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError):
                m0 = None
            _meter(model, r, time.time() - t0)
            if m0 is not None and not m0.get("tool_calls") and not (m0.get("content") or "").strip():       # reponse vide (le modele a tout depense en reflexion) : on essaie le suivant
                log.warning("llm %s : reponse vide, on passe au suivant", model)
                db.set(f"cool:{model}", 1, ex=30)
                continue
            return r
        if r.status_code == 429:
            m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", r.text)       # Groq dit lui-meme quand ca remarche a nouveau
            wait = int(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3))) + 2 if m else (3600 if "per day" in r.text.lower() else 20)
            db.set(f"cool:{model}", 1, ex=max(5, min(wait, 3600)))
        elif r.status_code not in (400, 413):          # 400 = appel d'outil rate, 413 = requete trop grosse pour CE modele : on tente le suivant, sans le bloquer
            db.set(f"cool:{model}", 1, ex=120)
    if _retry:                                         # Groq dit souvent "reessaie dans 5 a 20 s" : on attend un peu plutot que de passer tout de suite a Gemini (souvent sature)
        ttls = [db.ttl(f"cool:{m}") for m in llm_models()]
        ttls = [t for t in ttls if t and t > 0]
        if ttls and min(ttls) <= 25:
            time.sleep(min(ttls) + 1)
            return llm_call(messages, question, oral, tools, toolset, plain, _retry=False)
    return None
