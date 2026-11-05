"""The agent loop: asks the models, runs the tools they request, keeps the short-term memory."""

import base64
import json
import re

from .config import ALL_MODELS, GEMINI_KEY, HISTORY_TTL, HISTORY_TURNS, STT_API_KEY
from .texts import SILENT
from .core import db
from . import catalog, chatlog, dispatch, guard, llm, perf, recall, sound

HISTORY_CHARS = 6000           # what is older is still found with chat_search
LOOP_CHARS = 20000             # above this, one call eats most of the free tier's minute
OLD_TOOL_CHARS = 600


def _recent_history(chat_id):
    """The last exchanges, newest first until the budget is spent, always keeping the last one."""
    out, left = [], HISTORY_CHARS
    for x in reversed(db.lrange(f"hist:{chat_id}", 0, -1)):
        m = json.loads(x)
        text = m["parts"][0].get("text", "")[:1500]
        if left - len(text) < 0 and len(out) >= 2:
            break
        left -= len(text)
        out.append({"role": "assistant" if m["role"] == "model" else "user", "content": text})
    return out[::-1]


def _squeeze(messages):
    """Long tasks resend every tool result at each step: the oldest results are cut first, the last two stay whole."""
    total = sum(len(m.get("content") or "") for m in messages)
    if total <= LOOP_CHARS:
        return
    for m in [m for m in messages if m["role"] == "tool"][:-2]:
        size = len(m["content"])
        if size > OLD_TOOL_CHARS:
            m["content"] = m["content"][:OLD_TOOL_CHARS] + "...[coupe : refais l'appel si tu en as besoin]"
            total -= size - len(m["content"])
            if total <= LOOP_CHARS:
                return


def agent_groq(chat_id, question, oral=False, taint=False):
    """Agent loop on the main provider (OpenAI-compatible API, Groq by default). Returns (text, links) ; text = None if it is unavailable."""
    history = _recent_history(chat_id)
    links = ["(fichier recu)"] if taint else []
    used_tools, nudged, checked, seen, ran = False, False, False, {}, set()
    context = " ".join([question] + [h["content"] for h in history[-2:]])
    toolset = [] if catalog.is_small_talk(question) and not taint else catalog.select_tools(context)
    said_before = "" if not toolset or taint else recall.past(chat_id, question, [h["content"] for h in history])
    messages = [{"role": "system", "content": catalog.build_system(oral, toolset, context) + said_before}] + history + [{"role": "user", "content": question}]
    for _ in range(llm.MAX_STEPS):
        _squeeze(messages)
        resp = llm.llm_call(messages, question, oral, toolset=toolset)
        if resp is None:
            return None, links
        msg = resp.json()["choices"][0]["message"]
        calls = msg.get("tool_calls")
        if not calls:
            answer = llm.clean_answer(msg.get("content"))
            if not used_tools and not nudged and not oral and llm.REFUSAL.search(answer or ""):
                nudged, toolset = True, catalog.GROQ_TOOLS    # il refuse sans avoir essaye : tous les outils, et on le renvoie chercher une voie (une fois)
                messages[0]["content"] = catalog.build_system(oral) + said_before
                messages += [{"role": "assistant", "content": answer}, {"role": "user", "content": llm.NUDGE}]
                continue
            if not checked and llm.false_claim(answer, ran):
                checked = True
                messages += [{"role": "assistant", "content": answer}, {"role": "user", "content": llm.FALSE_CLAIM}]
                continue
            return answer, links
        used_tools = True
        ran.update(c["function"]["name"] for c in calls)
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        drafted = False
        for c in calls:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            key = c["function"]["name"] + json.dumps(args, sort_keys=True)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 2:                         # meme appel pour la 3e fois : il tourne en rond
                out = {"erreur": "deja essaye plusieurs fois avec les memes parametres : change d'approche ou explique le blocage"}
            else:
                out = dispatch.run_tool(chat_id, c["function"]["name"], args, links)
            drafted = drafted or (c["function"]["name"] == "mail_send" and "statut" in out)
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out, ensure_ascii=False)[:4000]})
        if drafted:
            return SILENT, links
    messages.append({"role": "user", "content": "[Systeme] Limite d'etapes atteinte. En deux ou trois phrases : ce qui est fait, ce qui reste, et ce que tu proposes."})
    resp = llm.llm_call(messages, question, oral, tools=False, toolset=toolset)
    return (llm.clean_answer(resp.json()["choices"][0]["message"].get("content")) if resp is not None else ""), links


def agent(chat_id, user_parts, oral=False, taint=False):
    """Boucle d'agent : Gemini repond, ou demande des outils (musique, recherche web, commandes...) puis conclut.
    Renvoie (texte, liens) ; texte = None si Gemini est indisponible (message deja pret dans liens[0])."""
    if not GEMINI_KEY:
        return None, ["No AI provider answered. Check LLM_API_KEY / LLM2_API_KEY (or add GEMINI_API_KEY as a backup) and try again."]
    history = [json.loads(x) for x in db.lrange(f"hist:{chat_id}", 0, -1)]
    contents = history + [{"role": "user", "parts": user_parts}]
    links = ["(fichier recu)"] if taint else []
    system = catalog.build_system(oral)
    for _ in range(llm.MAX_STEPS):
        resp = llm.call_gemini({"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "tools": catalog.TOOLS})
        if resp.status_code == 429:
            return None, ["Limite gratuite Gemini atteinte pour le moment, reessaie dans une minute."]
        if resp.status_code in (500, 503):
            return None, ["Gemini est sature en ce moment, reessaie dans un instant."]
        resp.raise_for_status()
        parts = resp.json()["candidates"][0].get("content", {}).get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
            return llm.clean_answer("".join(p.get("text", "") for p in parts)), links
        contents.append({"role": "model", "parts": parts})
        outs = [(c["name"], dispatch.run_tool(chat_id, c["name"], c.get("args", {}), links)) for c in calls]
        contents.append({"role": "user", "parts": [{"functionResponse": {"name": n, "response": o}} for n, o in outs]})
        if any(n == "mail_send" and "statut" in o for n, o in outs):
            return SILENT, links
    return "", links


def remember(chat_id, question, answer, from_file=False):
    if re.search(r"<\|(?:channel|call|start|end|message|return)\|>", answer or ""):          # jamais de brouillon interne dans la memoire
        return
    key = f"hist:{chat_id}"
    db.rpush(key, json.dumps({"role": "user", "parts": [{"text": question}]}),
             json.dumps({"role": "model", "parts": [{"text": answer}]}))
    db.ltrim(key, -2 * HISTORY_TURNS, -1)
    db.expire(key, HISTORY_TTL)
    chatlog.record(chat_id, question, answer, from_file)


def ask(chat_id, question, oral=False, taint=False):
    turn = guard.begin_turn(chat_id, question, taint)      # destructive tools check the user's own words against this
    try:
        answer, links = agent_groq(chat_id, question, oral, taint) if ALL_MODELS else (None, [])
        if answer is None:
            answer, links = agent(chat_id, [{"text": question}], oral, taint)
    finally:
        guard.end_turn(turn)
    if answer is None:
        return links[0]
    if answer == SILENT:
        p = json.loads(db.get(f"pending_mail:{chat_id}") or "{}")
        remember(chat_id, question, f"[Brouillon d'email montre, en attente de /oui] A : {', '.join(p.get('to', []))} | Sujet : "
                                    f"{p.get('subject', '')} | Texte : {p.get('body', '')}")
        return SILENT
    if not answer:
        return "Je n'ai pas pu formuler de reponse."
    remember(chat_id, question, answer, taint)
    urls = [x for x in links if x.startswith("http")]
    if urls:
        answer += "\n\nSources :\n" + "\n".join(dict.fromkeys(urls))[:600]
    return answer


def ask_voice(chat_id, audio, mime):
    """Message vocal : Gemini ecoute, comprend, agit si besoin et repond (un seul passage)."""
    if STT_API_KEY:
        with perf.timed("ecoute"):
            text = sound.transcribe(audio)
        if text:
            return text, ask(chat_id, text, oral=True)
    instruction = ("Voici un message vocal de l'utilisateur : fais ce qu'il demande, puis reponds-lui. Ta reponse finale suit ce "
                   "format strict : une ligne 'Q: ' avec la transcription exacte de ce qu'il a dit, puis une ligne 'R: ' avec ta reponse.")
    answer, links = agent(chat_id, [{"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
                                    {"text": instruction}], oral=True)
    if answer is None:
        return None, links[0]
    m = re.search(r"Q:\s*(.*?)\s*\n\s*R:\s*(.*)", answer, re.S)
    question, answer = (m.group(1), m.group(2).strip()) if m else ("(message vocal)", answer)
    if not answer:
        return None, "Je n'ai pas compris le message vocal."
    remember(chat_id, question, answer)
    return question, answer
