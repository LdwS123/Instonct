<p align="center">
  <img src="assets/logo.svg" alt="Instonct (Instant AI) - the self-hosted Instinct AI alternative, running on an old Mac mini" width="760">
</p>

<p align="center">
  <b>Instonct, your <i>Instant AI</i>: the self-hosted <a href="#instinct-ai-vs-instonct">Instinct AI alternative</a>.</b><br>
  A personal AI agent you text like a friend, on <b>WhatsApp</b> or <b>Telegram</b>, running on your own old Mac mini.<br>
  No invite list. No one else's cloud. Your mails, your calendar, your data stay home.
</p>

<p align="center">
  <b>English</b> ·
  <a href="docs/README.zh-CN.md">简体中文</a> ·
  <a href="docs/README.ko.md">한국어</a> ·
  <a href="docs/README.ja.md">日本語</a> ·
  <a href="docs/README.es.md">Español</a> ·
  <a href="docs/README.pt-BR.md">Português</a> ·
  <a href="docs/README.fr.md">Français</a> ·
  <a href="docs/README.de.md">Deutsch</a> ·
  <a href="docs/README.ru.md">Русский</a> ·
  <a href="docs/README.hi.md">हिन्दी</a> ·
  <a href="docs/README.ar.md">العربية</a>
</p>

> **Not affiliated with Instinct AI or Spear Street Technology.** "Instinct" belongs to its owner.
> Instonct is an independent hobby project. The name is a deliberate parody, and this page
> compares it with Instinct AI only so people looking for an alternative can find it.

---

**Instonct** is an open-source, self-hosted **personal AI agent**. You message it on **WhatsApp or Telegram**
(text or voice note) and it does things: reads and drafts your mail, manages your Google Calendar, sets reminders
and to-dos, browses and fills in web forms, scrapes a page into a CSV, watches a page and pings you when it
changes, plays music, even runs shell commands on the machine it lives on.

It runs 24/7 on a **2010 Mac mini** (Core 2 Duo, 4.6 GB of RAM, Lubuntu). If it runs there, it runs on
almost anything: a Raspberry Pi, an old laptop, a cheap VPS.

## What it can do

| Area | What you can say |
|---|---|
| **Mail** | "Any important mail today?", "Reply to Paul, say I'm in." Sends only after you tap **Yes**. |
| **Calendar** | "Put dentist on Thursday at 3pm", "Add a Google Meet with Marie". Warns about conflicts. |
| **Browser** | "Go to news.ycombinator.com and give me a CSV of the top 30 titles", "Log me in to my gym site". |
| **Watching** | "Tell me when this page says *in stock*." Checks every 10+ minutes, pings only on change. |
| **Memory** | Remembers your preferences for good, and learns when you correct it. |
| **Routines** | A morning briefing (agenda, mail, weather, your #1 priority), reminders, scheduled tasks. |
| **Voice** | Voice notes in (Whisper), voice notes or spoken answers out. |
| **Files** | Send it a photo, PDF or CSV and ask about it. It can send files back. |
| **Home** | Music, TV remote, volume, server health, shell commands (with confirmation). |
| **Any language** | It answers in the language you write or speak. |

It has a personality too: short answers, one clear recommendation, no waffle. It is named *Steve*.

## Pick your brain: any model, any provider

Instonct talks to any **OpenAI-compatible API**, so you are not locked to one company. Set three lines in `.env`:

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # the default
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # tried in this order
```

| Provider | `LLM_BASE_URL` |
|---|---|
| Groq (default, fast, free tier) | `https://api.groq.com/openai/v1` |
| OpenRouter (hundreds of models) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (100% local, no key) | `http://localhost:11434/v1` |

Use model names exactly as your provider writes them, and pick models that support tool calling.

- **Switch on the fly**: send `/model` to see the list, `/model 2` to use number 2 first, `/model auto` to go back.
- **Automatic fallback**: if a model is rate-limited or down, the next one takes over by itself.
- **Optional safety net**: add `GEMINI_API_KEY` and Google Gemini answers when your main provider is down (and reads images).
  Without it, Instonct runs fine on a single provider.
- **Voice notes**: transcribed with a Whisper API (`STT_MODEL`, `STT_BASE_URL`, `STT_LANGUAGE`, same provider by default).

## WhatsApp or Telegram?

Both work, at the same time, with the same brain, memory and safety rules.

| | Telegram | WhatsApp |
|---|---|---|
| Setup | 2 minutes with @BotFather | Meta developer account, a number, a token (about 30 minutes) |
| Needs a public address | No (the bot calls out) | Yes (Meta calls your server: Tailscale Funnel works) |
| Yes / No buttons, voice, files | Yes | Yes |
| TV remote keyboard, `/site` password saving | Yes | Telegram only (on purpose, see Safety) |
| Messages sent by the bot on its own (reminders) | Always | Only within 24 h of your last message |
| Already on your phone | Maybe | Almost surely |

**Honest advice**: start with Telegram, it is simpler and safer. Add WhatsApp when you want to talk to it from the app
you already use every day. Instonct uses Meta's **official WhatsApp Cloud API**, never an unofficial library, so there
is no risk of getting your number banned.

### Add WhatsApp (optional)

1. On [developers.facebook.com](https://developers.facebook.com) create an app, add the **WhatsApp** product, and note the
   **Phone number ID**. The free test number works to try it; later you can attach your own number.
2. Create a permanent access token (a *System User* token in Meta Business settings) and copy the **App secret**
   (App settings, Basic).
3. Add to `~/bots/.env` (your own number: digits only, country code first, no `+`):
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. Give Meta a public HTTPS address for the local webhook (port 8088, bound to `127.0.0.1`). With Tailscale:
   `sudo tailscale funnel --bg 8088`. It prints a `https://<machine>.<tailnet>.ts.net` address.
5. In the WhatsApp settings of your Meta app, set the webhook **Callback URL** to that address and the **Verify token**
   to your `WA_VERIFY_TOKEN`, then subscribe to the **messages** field.
6. Restart the bot (`sudo systemctl restart bot-telegram`) and text your WhatsApp number.

Every incoming call is rejected unless its `X-Hub-Signature-256` matches your app secret, and only the numbers in
`WA_OWNER` get an answer. Dashboard labels at Meta change from time to time; the idea stays the same.
The API version defaults to `v23.0`; override it with `WA_API_VERSION` if Meta retires it.

## Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| Access | Invite-only (per press coverage) | Clone the repo and run it |
| Where it runs | A company's cloud | **Your own machine** |
| Your data | Handed to a startup | Stays on your box (Redis + local files) |
| How you talk to it | Text, phone, WhatsApp (per press coverage) | WhatsApp or Telegram, text or voice |
| Models | Chosen for you | **Any OpenAI-compatible provider**, switch with `/model` |
| Cost | Not public | Free tiers work (Groq, Gemini); or fully local with Ollama |
| Source code | Closed | **Right here** |

Instinct AI is a real product built by a funded team; Instonct is one person's weekend-turned-daily-driver.
Pick Instonct if you want the same idea with your hands on the wheel.

## How it works

- **Brain**: any OpenAI-compatible model (Groq `gpt-oss-120b` / `20b` by default, with adaptive reasoning effort), optional Gemini fallback.
- **Tools**: the model calls ~35 tools (mail, calendar, browser, files, music, TV, shell...). See `TOOLS` in [`bots/telegram-search/bot.py`](bots/telegram-search/bot.py).
- **Browser**: [Lightpanda](https://github.com/lightpanda-io/browser), a tiny headless browser (~25 MB of RAM) that even runs on a 2010 CPU. See [`webagent.py`](bots/telegram-search/webagent.py).
- **Channels**: Telegram by long polling (no open port), WhatsApp through [`whatsapp.py`](bots/telegram-search/whatsapp.py) (a small webhook on `127.0.0.1`).
- **State**: Redis (history, memory, reminders, watches).
- **Reach**: SSH + [Tailscale](https://tailscale.com), `ufw` closed by default. The server setup is in [`docs/home-server.md`](docs/home-server.md).

## Safety, because an agent with a shell needs it

- **Private**: on Telegram the first person to send `/start` becomes the only owner; on WhatsApp only the numbers in `WA_OWNER`
  are answered. Everyone else is ignored.
- **Nothing risky happens silently**: sending mail, submitting a form, deleting an event, running a command
  or clicking a "Buy / Pay / Delete" button all ask for a **Yes / No** tap first.
- **Passwords never go through the model**: site logins are stored in a `0600` file and filled in by plain code.
  Saving them is Telegram-only because the bot deletes your message right after (WhatsApp would keep it).
- **Web pages are data, not orders**: text found on a page or in a mail cannot give instructions to the agent.
- **No local network via the browser**: only public `http(s)` addresses are allowed (SSRF guard).
- **Secrets never in this repo**: keys live in a `.env` on the server.

## Quick start

You need a Linux box, Python 3, Redis, a **Telegram bot token** (from [@BotFather](https://t.me/BotFather)) and one
**API key** from any provider above (Groq has a free tier).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # voice + music (optional)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp bots/telegram-search/*.py ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# optional: LLM_BASE_URL, LLM_MODELS, GEMINI_API_KEY, STT_LANGUAGE=en, WA_* (WhatsApp)
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # edit User= and paths first
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

Then open your bot in Telegram and send `/start`. Optional: Lightpanda in `~/lightpanda/lightpanda` for the
browser, `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` for mail, and `scripts/google-auth.py` for Google Calendar.

## Looking for...

Instant AI · Instinct AI alternative · open-source Instinct AI · self-hosted personal AI agent · text your AI assistant ·
AI assistant on WhatsApp · AI assistant on Telegram · WhatsApp AI agent · OpenClaw alternative · AI agent that reads your email and
manages your calendar · run an AI agent on a Raspberry Pi or old Mac mini · home server AI assistant · Groq agent · Gemini agent ·
Ollama agent · OpenRouter agent · Lightpanda browser agent · AI web scraper to CSV · private AI assistant, no cloud.

---

<sub>Instonct is an independent project, not affiliated with, endorsed by or sponsored by Instinct AI or
Spear Street Technology, Inc. All trademarks belong to their respective owners. MIT licence.</sub>
