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
| **Mail triage** | Reads the text of each mail (no quota burned on ads): flags **rejections, interviews and offers**, hides newsletters. "Delete my rejections" reads the bodies, keeps interview and acceptance mails, and trashes (recoverably) only real rejections. |
| **Contacts** | "Write to Arslane": finds the address by itself in your received and sent mail, shows the draft with the address, sends only after **Yes**. Asks only if several people match. |
| **Remote screen** | `/connexion linkedin`: opens a temporary browser of the home server on your phone (noVNC over **Tailscale only**, random password, auto-closes) so you log in to LinkedIn, Instagram... **yourself**. The bot never sees a password; logins stay in the browser profile. |
| **Hey Siri, Steve** | `/siri`: an iPhone Shortcut named *Steve* sends what you say to the bot (Tailscale-only endpoint with a secret URL) and Siri reads the answer aloud, even with the phone locked. Starting a message with "Steve, ..." in chat also makes it answer by voice. |
| **Personal tools** | Tracker for applications and follow-ups (with automatic nudges), expenses, birthdays and key dates, a notebook, a safe calculator and unit converter, and the text of a YouTube video. No AI call needed. |
| **Watching** | "Tell me when this page says *in stock*." Checks every 10+ minutes, pings only on change. |
| **Memory** | Remembers who you are, your preferences and projects, learns from what you write (your words only), corrects old facts, and brings back what you said before on a subject. Local, no vector database. `/memoire` shows it. |
| **Real procedures** | "Book me a weekend in Lisbon", "Order this list", "Dispute this bill": keeps a dossier that survives over days, opens a real browser, fills the cart or the form, and **stops at payment**: you get the screen on your phone to log in and pay. It never pays. |
| **Calls** | "Prepare my call to the insurance": finds the number, gives a tap-to-call link and what to say. **You** make the call: no phone line is plugged in, and it can't claim otherwise. |
| **News and research** | "News about X", "Dig into this question" (reads the top pages and cites them), interview prep (your mails + the company + its news), time anywhere, public holidays. |
| **Health and speed** | `/sante` tells what works and what doesn't, with no key shown. `/vitesse` shows where the time goes. |
| **Learns your habits** | Counts (no AI call, nothing leaves the server) what you ask and when. Answers adapt to it, and when you do the same safe thing at the same hour on 4+ days (music, weather, agenda, mail, news, tasks) it **offers** to do it by itself every day, with **Yes / No** buttons. Never the TV. `/habitudes` shows what it learned, `/habitudes effacer` wipes it. |
| **Morning briefing** | `/matin 8:00 Paris`: every morning, weather, agenda, to-dos and unread mail in one message. Or just say "send me a summary every morning at 7:30". |
| **Routines & lists** | "When I say *good night*, lower the volume and say good night": saved once, then one word runs the whole chain. Shopping lists (and any other list): "add milk to the groceries". Paste a link alone and get a 5-line summary. |
| **Reminders** | Reminders and scheduled tasks, one-off or repeating. |
| **Voice** | Voice notes in (Whisper), voice notes or spoken answers out. |
| **Files** | Send it a photo, PDF or CSV and ask about it. It can send files back. |
| **Do anything** | Runs Python to compute or process data, reads and writes files, calls any web API (`http_request`), runs long jobs in the background and messages you when they finish. Risky or destructive steps ask for a **Yes** first. |
| **Documents** | Reads PDFs, Word, Excel and photos of text (OCR); creates PDF, Word, Excel, CSV files and sends them; QR codes; downloads files; charts with matplotlib. |
| **Places & more** | Sends a map pin or a poll, Wikipedia summaries, currency and crypto conversion, Wake-on-LAN, video/audio download with yt-dlp, ffmpeg conversions. |
| **News & weather** | "Latest news about X" (searched, then opened and cross-checked), "Weather in Lyon tomorrow". |
| **Dates** | "Remind me on 2027-01-15 at 9:00", scheduled tasks up to 60 days ahead. |
| **Favorites & images** | "Save this song", `/favoris`; it can generate or find an image and send it to you. |
| **Home** | Music, TV remote (buttons right in the chat), volume, server health, shell commands (with confirmation). |
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
- **Second provider** (recommended on free tiers, whose daily token quotas are small): add `LLM2_BASE_URL`, `LLM2_API_KEY` and `LLM2_MODELS`
  (for example Cerebras: `https://api.cerebras.ai/v1`, models `gpt-oss-120b`). Its models are tried after the first provider's.
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
| Phone calls | Yes (per press coverage) | **No.** It prepares the call (number, tap-to-call link, what to say) and you call. Real calls need a paid telephony provider, not included |
| Booking, groceries, disputes | Done for you (per press coverage) | Prepares everything in a real browser up to the payment, then hands you the screen. Sites that block bots (seen: Carrefour, Booking, Rome2Rio) can refuse it |
| Setup | Sign up | `./install.sh` on a Linux box, plus a Telegram token and a model key. Still your server |
| Power and reliability | A team and support | Free models with quotas, your hardware, no support. `/sante` tells you what broke |

Instinct AI is a real product built by a funded team; Instonct is one person's weekend-turned-daily-driver.
Pick Instonct if you want the same idea with your hands on the wheel.
This table was written by the author of Instonct, and its protections have **not been audited independently**: an agent with access to a shell, your mail and your calendar stays a real risk.

## How it works

- **Brain**: any OpenAI-compatible model (Groq `gpt-oss-120b` / `20b` by default, with adaptive reasoning effort), optional Gemini fallback.
- **Tools**: the model calls ~60 tools, picking only the relevant ones per request to save tokens on free tiers (mail, calendar, browser, files, music, TV, shell...). See [`catalog.py`](bots/telegram-search/instonct/catalog.py).
- **Browser**: [Lightpanda](https://github.com/lightpanda-io/browser), a tiny headless browser (~25 MB of RAM) that even runs on a 2010 CPU. See [`webagent.py`](bots/telegram-search/instonct/webagent.py).
- **Channels**: Telegram by long polling (no open port), WhatsApp through [`whatsapp.py`](bots/telegram-search/instonct/whatsapp.py) (a small webhook on `127.0.0.1`).
- **State**: Redis (history, memory, reminders, watches).
- **Reach**: SSH + [Tailscale](https://tailscale.com), `ufw` closed by default. The server setup is in [`docs/home-server.md`](docs/home-server.md).

## Code layout

The bot is a small Python package (`bots/telegram-search/instonct/`), split by job so that each file fits in your head.
`bot.py` is only a three-line entry point, so the systemd unit (`python bot.py`) does not change.

| Section | Modules | What is inside |
|---|---|---|
| Foundations | `config`, `texts`, `core` | settings from `.env`, fixed texts, Redis + logging + Telegram/WhatsApp sending |
| The AI | `llm`, `catalog`, `brain`, `dispatch` | providers and fallback chain, tool catalogue, agent loop, tool routing |
| Home | `music`, `cast`, `television`, `sound` | music, Chromecast, Android TV remote, voice and volume |
| Work | `mail`, `web`, `realbrowser`, `demarche`, `monde`, `pagewatch`, `google` | mail and triage, browser agent and real browser, procedures and calls, news and research, page watching, calendar |
| Life | `media`, `life`, `recall`, `memlearn`, `system_tools` | images and files, habits, lists and routines, long memory, shell / files / HTTP tools |
| Chat | `handlers`, `callbacks`, `commands` | Telegram messages, Yes/No buttons, free commands |
| Background | `reminders`, `monitor`, `remote_access`, `health`, `perf`, `runner` | reminder and watch loops, remote screen and Siri, health check, timings, entry point |
| Optional libraries | `extras`, `habits`, `whatsapp`, `tvremote`, `gcal`, `webagent`, `plus`, `screen`, `mailtriage` | loaded through `optional.py`: the bot keeps running if one is missing |

Modules call each other as `module.function(...)` (resolved when called), so there are no import cycles to untangle.
A local variable must never reuse a module name: a test checks that.

```bash
cd bots/telegram-search
pip install -r requirements-dev.txt
redis-server --daemonize yes     # tests use Redis database 9 (REDIS_DB) and never touch your real data
pytest                           # fallback between AI providers, leaked-reasoning protection, tools, wiring
ruff check .
```

GitHub Actions runs the same checks on every push.

## Safety, because an agent with a shell needs it

- **Private**: on Telegram the first person to send `/start` becomes the only owner; on WhatsApp only the numbers in `WA_OWNER`
  are answered. Everyone else is ignored.
- **Nothing risky happens silently**: sending mail, submitting a form, deleting an event or running a command
  all ask for a **Yes / No** tap first.
- **It never pays**: "Buy / Pay / Checkout" buttons and card fields are refused by plain code, not left to the model. You get the screen and pay yourself.
- **Passwords never go through the model**: site logins are stored in a `0600` file and filled in by plain code.
  Saving them is Telegram-only because the bot deletes your message right after (WhatsApp would keep it).
- **Web pages are data, not orders**: text found on a page or in a mail cannot give instructions to the agent.
- **No local network via the browser**: only public `http(s)` addresses are allowed (SSRF guard).
- **Secrets never in this repo**: keys live in a `.env` on the server.

## Quick start

You need a Debian or Ubuntu box, a **Telegram bot token** (from [@BotFather](https://t.me/BotFather)) and one
**API key** from any provider above (Groq has a free tier).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
./install.sh            # add --dry-run to see what it would do first
```

It installs the packages, asks for your keys (hidden as you type, tested before saving, stored `0600`), starts the service
and checks that everything answers. Then **send `/start` to your bot right away, yourself**: the first person to do it becomes the only owner.

`/sante` shows what still needs setting up. Optional: `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` for mail, `scripts/google-auth.py`
for Google Calendar. The real browser needs `chromium`, `xvfb`, `openbox`, `x11vnc`, `novnc` and [Tailscale](https://tailscale.com); it takes about 800 MB of RAM
while open, so the service allows up to 1500 MB (`MemoryMax` in the unit).

Changing the keys later: edit `~/bots/.env`, then `sudo systemctl restart bot-telegram`. Check at any time with `python bot.py doctor`.

## Looking for...

Instant AI · Instinct AI alternative · open-source Instinct AI · self-hosted personal AI agent · text your AI assistant ·
AI assistant on WhatsApp · AI assistant on Telegram · WhatsApp AI agent · OpenClaw alternative · AI agent that reads your email and
manages your calendar · run an AI agent on a Raspberry Pi or old Mac mini · home server AI assistant · Groq agent · Gemini agent ·
Ollama agent · OpenRouter agent · Lightpanda browser agent · AI web scraper to CSV · private AI assistant, no cloud.

---

<sub>Instonct is an independent project, not affiliated with, endorsed by or sponsored by Instinct AI or
Spear Street Technology, Inc. All trademarks belong to their respective owners. MIT licence.</sub>
