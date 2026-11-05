"""Settings read from the environment (.env): tokens, providers, models, limits."""

import os

TOKEN = os.environ["TELEGRAM_TOKEN"]
# Main brain: ANY OpenAI-compatible provider (Groq by default; also OpenRouter, Together, Mistral, OpenAI, Cerebras, DeepSeek,
# a local Ollama / LM Studio...). LLM_* names are the new ones; the old GROQ_* names still work.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY", "")
LLM_MODELS = [m.strip() for m in (os.environ.get("LLM_MODELS") or os.environ.get("GROQ_MODELS")
              or "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",") if m.strip()]
GROQ_KEY = LLM_API_KEY                                    # (old name, used in a few places below)
# Optional second provider (e.g. Cerebras: LLM2_BASE_URL=https://api.cerebras.ai/v1, LLM2_API_KEY=..., LLM2_MODELS=gpt-oss-120b). Its models come after the first
# provider's in the fallback order, so a daily quota running out at one provider just moves the work to the other.
LLM2_BASE_URL = os.environ.get("LLM2_BASE_URL", "").rstrip("/")
LLM2_API_KEY = os.environ.get("LLM2_API_KEY", "")
LLM2_MODELS = [m.strip() for m in os.environ.get("LLM2_MODELS", "gpt-oss-120b").split(",") if m.strip()] if (LLM2_BASE_URL and LLM2_API_KEY) else []
MODEL_API = {m: (LLM_BASE_URL, LLM_API_KEY) for m in LLM_MODELS} if LLM_API_KEY else {}      # model name -> (base url, key)
MODEL_API.update({m: (LLM2_BASE_URL, LLM2_API_KEY) for m in LLM2_MODELS})
# Optional third provider (same idea, e.g. Cerebras: LLM3_BASE_URL=https://api.cerebras.ai/v1, LLM3_MODELS=gpt-oss-120b)
LLM3_BASE_URL = os.environ.get("LLM3_BASE_URL", "").rstrip("/")
LLM3_API_KEY = os.environ.get("LLM3_API_KEY", "")
LLM3_MODELS = [m.strip() for m in os.environ.get("LLM3_MODELS", "gpt-oss-120b").split(",") if m.strip()] if (LLM3_BASE_URL and LLM3_API_KEY) else []
MODEL_API.update({m: (LLM3_BASE_URL, LLM3_API_KEY) for m in LLM3_MODELS if m not in MODEL_API})
ALL_MODELS = [m for m in LLM_MODELS if LLM_API_KEY] + [m for m in LLM2_MODELS + LLM3_MODELS if m not in LLM_MODELS]
# Best model first whatever the provider: a quota running out at one provider must not drop us to a weak model while the same strong model is free elsewhere.
ALL_MODELS.sort(key=lambda m: ("120b" not in m, m.startswith("@cf/")))
# Voice notes -> text (Whisper API of the same provider by default). STT_LANGUAGE empty = auto-detect, or e.g. "fr".
STT_BASE_URL = os.environ.get("STT_BASE_URL", LLM_BASE_URL).rstrip("/")
STT_API_KEY = os.environ.get("STT_API_KEY") or LLM_API_KEY
STT_MODEL = os.environ.get("STT_MODEL", "whisper-large-v3-turbo")
STT_LANGUAGE = os.environ.get("STT_LANGUAGE", "")
# Optional safety net: Google Gemini, tried when the main provider is down. Leave GEMINI_API_KEY empty to run without it.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
# Modeles essayes dans l'ordre (gratuits, chacun avec son propre quota ; Gemma en dernier recours).
MODELS = os.environ.get(
    "GEMINI_MODELS",
    "gemini-3.5-flash,gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-flash-lite-latest",
).split(",")
# Palier gratuit Gemini : ~5 requetes/min et ~20/jour PAR MODELE ; avec 5 modeles en secours on a bien plus.
# Garde-fou contre les boucles : large, car le vrai plafond vient du fournisseur (Groq, etc.), gere par le repli entre modeles.
MAX_PER_MIN = int(os.environ.get("MAX_PER_MIN", "15") or 15)
MAX_PER_DAY = int(os.environ.get("MAX_PER_DAY", "600") or 600)
HISTORY_TURNS = 12         # nombre d'echanges gardes en memoire courte
HISTORY_TTL = 86400        # 24 h : la conversation reprend meme le lendemain

TG = f"https://api.telegram.org/bot{TOKEN}"
