<p align="center">
  <img src="assets/logo.svg" alt="Instonct - the self-hosted Instinct AI alternative, running on an old Mac mini" width="760">
</p>

<p align="center">
  <b>The self-hosted <a href="#instinct-ai-vs-instonct">Instinct AI alternative</a>.</b><br>
  A personal AI agent you text like a friend, running on your own old Mac mini.<br>
  No invite list. No one else's cloud. Your mails, your calendar, your data stay home.
</p>

<p align="center">
  <a href="#english">English</a> · <a href="#en-francais">Français</a> · <a href="#le-serveur-le-materiel">Le serveur</a>
</p>

> **Not affiliated with Instinct AI or Spear Street Technology.** "Instinct" belongs to its owner.
> Instonct is an independent hobby project. The name is a deliberate parody, and this page
> compares it with Instinct AI only so people looking for an alternative can find it.

---

## English

**Instonct** is an open-source, self-hosted **personal AI agent**. You text it on Telegram (or send a voice
note) and it does things: reads and drafts your mail, manages your Google Calendar, sets reminders and
to-dos, browses and fills in web forms, scrapes a page into a CSV, watches a page and pings you when it
changes, plays music, even runs shell commands on the machine it lives on.

It runs 24/7 on a **2010 Mac mini** (Core 2 Duo, 4.6 GB of RAM, Lubuntu). If it runs there, it runs on
almost anything: a Raspberry Pi, an old laptop, a cheap VPS.

### What it can do

| Area | What you can say |
|---|---|
| **Mail** | "Any important mail today?", "Reply to Paul, say I'm in." Sends only after you tap **Yes**. |
| **Calendar** | "Put dentist on Thursday at 3pm", "Add a Google Meet with Marie". Warns about conflicts. |
| **Browser** | "Go to news.ycombinator.com and give me a CSV of the top 30 titles", "Log me in to my gym site". |
| **Watching** | "Tell me when this page says *in stock*." Checks every 10+ minutes, pings only on change. |
| **Memory** | Remembers your preferences for good, and learns when you correct it. |
| **Routines** | A morning briefing (agenda, mail, weather, your #1 priority), reminders, scheduled tasks. |
| **Voice** | Voice notes in (Whisper), spoken answers out on the machine or a TV. |
| **Home** | Music, TV remote, volume, server health, shell commands (with confirmation). |

It has a personality too: short answers, one clear recommendation, no waffle. It is named *Steve*.

### Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| Access | Invite-only (per press coverage) | Clone the repo and run it |
| Where it runs | A company's cloud | **Your own machine** |
| Your data | Handed to a startup | Stays on your box (Redis + local files) |
| How you talk to it | Text, phone, WhatsApp (per press coverage) | Telegram, text or voice |
| Cost | Not public | Runs on Groq and Gemini API keys (free tiers in my setup) |
| Source code | Closed | **Right here** |

Instinct AI is a real product built by a funded team; Instonct is one person's weekend-turned-daily-driver.
Pick Instonct if you want the same idea with your hands on the wheel.

### How it works

- **Brain**: Groq (`gpt-oss-120b` / `20b`, with adaptive reasoning effort) with a Gemini fallback.
- **Tools**: the model calls ~35 tools (mail, calendar, browser, files, music, TV, shell...). See `TOOLS` in [`bots/telegram-search/bot.py`](bots/telegram-search/bot.py).
- **Browser**: [Lightpanda](https://github.com/lightpanda-io/browser), a tiny headless browser (~25 MB of RAM) that even runs on a 2010 CPU. See [`webagent.py`](bots/telegram-search/webagent.py).
- **State**: Redis (history, memory, reminders, watches). Long polling, so **no open port**.
- **Reach**: SSH + [Tailscale](https://tailscale.com), `ufw` closed by default.

### Safety, because an agent with a shell needs it

- **Private**: the first person to send `/start` becomes the only owner. Everyone else is ignored.
- **Nothing risky happens silently**: sending mail, submitting a form, deleting an event, running a command
  or clicking a "Buy / Pay / Delete" button all ask for a **Yes / No** tap first.
- **Passwords never go through the model**: site logins are stored in a `0600` file and filled in by plain code.
- **Web pages are data, not orders**: text found on a page or in a mail cannot give instructions to the agent.
- **No local network via the browser**: only public `http(s)` addresses are allowed (SSRF guard).
- **Secrets never in this repo**: keys live in a `.env` on the server.

### Quick start

You need a Linux box, Python 3, Redis, and three free keys: a **Telegram bot token** (from
[@BotFather](https://t.me/BotFather)), a **Groq API key** and a **Gemini API key**.

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # voice + music (optional)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp bots/telegram-search/*.py ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
GROQ_API_KEY=...
GEMINI_API_KEY=...
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # edit User= and paths first
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

Then open your bot in Telegram and send `/start`. Optional: Lightpanda in `~/lightpanda/lightpanda` for the
browser, `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` for mail, and `scripts/google-auth.py` for Google Calendar.

### Looking for...

Instinct AI alternative · open-source Instinct AI · self-hosted personal AI agent · text your AI assistant ·
AI assistant on Telegram · OpenClaw alternative · AI agent that reads your email and manages your calendar ·
run an AI agent on a Raspberry Pi or old Mac mini · home server AI assistant · Groq agent · Gemini agent ·
Lightpanda browser agent · AI web scraper to CSV · private AI assistant, no cloud.

---

## En français

**Instonct**, c'est un agent personnel IA **à toi, chez toi**. Tu lui écris sur Telegram (ou tu lui envoies
un message vocal) et il agit : il lit et prépare tes mails, gère ton agenda Google, te rappelle tes choses
à faire, va sur des sites pour remplir des formulaires, copie une page dans un tableau (CSV), surveille une
page et te prévient quand elle change, met de la musique, et lance même des commandes sur le serveur.

Il tourne jour et nuit sur un **vieux Mac mini de 2010**. Pas besoin de machine puissante, pas d'abonnement
à une startup, pas de liste d'attente : tu copies le projet et tu le lances.

**Pourquoi ce nom ?** C'est une provocation. Instinct AI est un assistant personnel du même genre, mais
réservé sur invitation et hébergé chez eux. Ici, c'est l'inverse : le nuage est barré, le Mac mini reste
allumé, et le **o** de *Instonct* est un bouton marche/arrêt, parce que c'est toi qui décides.

**Rien de risqué sans ton accord** : envoyer un mail, valider un formulaire, supprimer un rendez-vous ou
lancer une commande demandent toujours un appui sur **Oui / Non**. Les mots de passe ne passent jamais par
l'IA. Et seul le premier à écrire `/start` est le propriétaire du bot.

Le guide d'installation est dans la partie [Quick start](#quick-start) ci-dessus.

---

## Le serveur (le matériel)

Un vieux Mac mini (2010, Core 2 Duo, ~4,6 Go de RAM) sous Lubuntu, transformé en petit serveur
piloté en SSH, qui fait tourner des bots 24h/24 (un service systemd par bot).

### Ce que contient ce dépôt

| Fichier | Rôle |
|---|---|
| `bots/telegram-search/` | Le bot Instonct : cerveau (`bot.py`), agenda (`gcal.py`), navigateur (`webagent.py`), télécommande TV (`tvremote.py`) |
| `systemd/bot-telegram.service` | Lance le bot au démarrage et le relance s'il tombe |
| `scripts/google-auth.py` | Autorise le bot à utiliser ton Google Agenda (une fois) |
| `scripts/ecran-status` | Tableau de bord texte affiché sur l'écran du Mac mini (IP, charge, température, RAM, bots) |
| `systemd/ecran-status.service` | Lance le tableau de bord sur `tty1` (à la place de l'interface graphique) |
| `scripts/cockpit-cert-renew` | Récupère un vrai certificat HTTPS via Tailscale et l'installe pour Cockpit |
| `systemd/cockpit-cert-renew.{service,timer}` | Renouvelle ce certificat chaque mois |
| `networkmanager/wifi-powersave-off.conf` | Coupe l'économie d'énergie du Wi-Fi (évite les coupures) |

### Architecture

- **Accès à distance** : SSH par clé, puis [Tailscale](https://tailscale.com) (réseau privé entre mes appareils, aucun port ouvert sur la box).
- **Interface web** : [Cockpit](https://cockpit-project.org) sur le port 9090, joignable uniquement via Tailscale.
- **Sécurité** : `ufw` (tout refusé par défaut, SSH et Cockpit autorisés seulement sur `tailscale0`), `fail2ban`.
- **Veille désactivée** (`systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`) et
  mode console par défaut (`systemctl set-default multi-user.target`) pour gagner de la RAM.
- **Bots** : un service `bot-<nom>.service` par bot, `Restart=always`. Les bots Telegram utilisent le
  long polling, donc aucun port entrant n'est nécessaire.

### Installation du serveur (résumé)

```bash
sudo install -m 755 scripts/ecran-status scripts/cockpit-cert-renew /usr/local/bin/
sudo install -m 644 systemd/*.service systemd/*.timer /etc/systemd/system/
sudo install -m 644 networkmanager/wifi-powersave-off.conf /etc/NetworkManager/conf.d/
sudo systemctl daemon-reload
sudo systemctl enable --now ecran-status.service cockpit-cert-renew.timer
```

Pour Cockpit en HTTPS : activer *HTTPS Certificates* dans la console admin Tailscale (DNS),
puis lancer une fois `sudo /usr/local/bin/cockpit-cert-renew`.

### Secrets

Tokens (Telegram, clés API) : **jamais dans ce dépôt**. Ils vivent dans un fichier `.env`
sur le serveur, lu par le service systemd via `EnvironmentFile=`.

---

<sub>Instonct is an independent project, not affiliated with, endorsed by or sponsored by Instinct AI or
Spear Street Technology, Inc. All trademarks belong to their respective owners. MIT licence.</sub>
