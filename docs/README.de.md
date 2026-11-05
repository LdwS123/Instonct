<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - die selbst gehostete Instinct-AI-Alternative, die auf einem alten Mac mini läuft" width="760">
</p>

<p align="center">
  <b>Instonct, deine <i>Instant AI</i>: die selbst gehostete <a href="../README.md#instinct-ai-vs-instonct">Instinct-AI-Alternative</a>.</b><br>
  Ein persönlicher KI-Agent, dem du wie einem Freund schreibst, per <b>WhatsApp</b> oder <b>Telegram</b>, und der auf deinem eigenen alten Mac mini läuft.<br>
  Keine Einladungsliste. Keine fremde Cloud. Deine Mails, dein Kalender, deine Daten bleiben zu Hause.
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="README.fr.md">Français</a> ·
  <b>Deutsch</b> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **Nicht mit Instinct AI oder Spear Street Technology verbunden.** „Instinct“ gehört seinem Inhaber.
> Instonct ist ein unabhängiges Hobbyprojekt. Der Name ist eine bewusste Parodie, und diese Seite
> vergleicht es nur deshalb mit Instinct AI, damit Leute, die nach einer Alternative suchen, es finden können.

---

**Instonct** ist ein quelloffener, selbst gehosteter **persönlicher KI-Agent**. Du schreibst ihm per **WhatsApp oder Telegram**
(Text oder Sprachnachricht) und er erledigt Dinge: Er liest und entwirft deine Mails, verwaltet deinen Google Kalender, setzt Erinnerungen
und To-dos, surft im Web und füllt Formulare aus, überführt eine Webseite in eine CSV-Datei, beobachtet eine Seite und meldet sich, wenn sie
sich ändert, spielt Musik und führt sogar Shell-Befehle auf dem Rechner aus, auf dem er läuft.

Er läuft rund um die Uhr auf einem **Mac mini von 2010** (Core 2 Duo, 4,6 GB RAM, Lubuntu). Wenn er dort läuft, läuft er auf
fast allem: einem Raspberry Pi, einem alten Laptop, einem günstigen VPS.

## Was er kann

| Bereich | Was du sagen kannst |
|---|---|
| **Mail** | „Gibt es heute wichtige Mails?“, „Antworte Paul, ich bin dabei.“ Sendet erst, nachdem du auf **Ja** getippt hast. |
| **Kalender** | „Trag Zahnarzt am Donnerstag um 15 Uhr ein“, „Füge ein Google Meet mit Marie hinzu“. Warnt vor Terminkonflikten. |
| **Browser** | „Geh auf news.ycombinator.com und gib mir eine CSV mit den Top-30-Titeln“, „Melde mich auf der Seite meines Fitnessstudios an“. |
| **Beobachten** | „Sag mir Bescheid, wenn diese Seite *auf Lager* anzeigt.“ Prüft alle 10+ Minuten und meldet sich nur bei Änderungen. |
| **Gedächtnis** | Merkt sich deine Vorlieben dauerhaft und lernt, wenn du ihn korrigierst. |
| **Routinen** | Ein Morgenbriefing (Termine, Mails, Wetter, deine Priorität Nr. 1), Erinnerungen, geplante Aufgaben. |
| **Sprache** | Sprachnachrichten als Eingabe (Whisper), Sprachnachrichten oder gesprochene Antworten als Ausgabe. |
| **Dateien** | Schick ihm ein Foto, PDF oder eine CSV und stell Fragen dazu. Er kann auch Dateien zurückschicken. |
| **Zuhause** | Musik, TV-Fernbedienung, Lautstärke, Serverzustand, Shell-Befehle (mit Bestätigung). |
| **Jede Sprache** | Er antwortet in der Sprache, in der du schreibst oder sprichst. |

Er hat auch eine Persönlichkeit: kurze Antworten, eine klare Empfehlung, kein Geschwafel. Er heißt *Steve*.

## Such dir dein Gehirn aus: jedes Modell, jeder Anbieter

Instonct spricht mit jeder **OpenAI-kompatiblen API**, du bist also nicht an ein einzelnes Unternehmen gebunden. Setze drei Zeilen in der `.env`:

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # der Standard
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # in dieser Reihenfolge probiert
```

| Anbieter | `LLM_BASE_URL` |
|---|---|
| Groq (Standard, schnell, kostenloses Kontingent) | `https://api.groq.com/openai/v1` |
| OpenRouter (Hunderte Modelle) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (100 % lokal, ohne Schlüssel) | `http://localhost:11434/v1` |

Verwende die Modellnamen genau so, wie dein Anbieter sie schreibt, und wähle Modelle, die Tool Calling unterstützen.

- **Im Handumdrehen wechseln**: Sende `/model`, um die Liste zu sehen, `/model 2`, um zuerst Nummer 2 zu verwenden, und `/model auto`, um zurückzukehren.
- **Automatischer Fallback**: Ist ein Modell ratenbegrenzt oder nicht erreichbar, springt von selbst das nächste ein.
- **Optionales Sicherheitsnetz**: Füge `GEMINI_API_KEY` hinzu, und Google Gemini antwortet, wenn dein Hauptanbieter ausfällt (und liest Bilder).
  Ohne ihn läuft Instonct problemlos mit nur einem Anbieter.
- **Sprachnachrichten**: werden mit einer Whisper-API transkribiert (`STT_MODEL`, `STT_BASE_URL`, `STT_LANGUAGE`, standardmäßig derselbe Anbieter).

## WhatsApp oder Telegram?

Beide funktionieren gleichzeitig, mit demselben Gehirn, demselben Gedächtnis und denselben Sicherheitsregeln.

| | Telegram | WhatsApp |
|---|---|---|
| Einrichtung | 2 Minuten mit @BotFather | Meta-Entwicklerkonto, eine Nummer, ein Token (etwa 30 Minuten) |
| Öffentliche Adresse nötig | Nein (der Bot ruft nach außen) | Ja (Meta ruft deinen Server auf: Tailscale Funnel funktioniert) |
| Ja-/Nein-Buttons, Sprache, Dateien | Ja | Ja |
| TV-Fernbedienungstastatur, Passwortspeicherung mit `/site` | Ja | Nur Telegram (mit Absicht, siehe Sicherheit) |
| Vom Bot selbstständig gesendete Nachrichten (Erinnerungen) | Immer | Nur innerhalb von 24 Std. nach deiner letzten Nachricht |
| Schon auf deinem Handy | Vielleicht | So gut wie sicher |

**Ehrlicher Rat**: Fang mit Telegram an, es ist einfacher und sicherer. Nimm WhatsApp dazu, wenn du mit ihm in der App sprechen willst,
die du ohnehin jeden Tag benutzt. Instonct verwendet Metas **offizielle WhatsApp Cloud API**, niemals eine inoffizielle Bibliothek, sodass
kein Risiko besteht, dass deine Nummer gesperrt wird.

### WhatsApp hinzufügen (optional)

1. Erstelle auf [developers.facebook.com](https://developers.facebook.com) eine App, füge das Produkt **WhatsApp** hinzu und notiere dir die
   **Phone number ID**. Die kostenlose Testnummer reicht zum Ausprobieren; später kannst du deine eigene Nummer verknüpfen.
2. Erstelle ein dauerhaftes Zugriffstoken (ein *System User*-Token in den Meta-Business-Einstellungen) und kopiere das **App secret**
   (App-Einstellungen, Basic).
3. Füge in `~/bots/.env` hinzu (deine eigene Nummer: nur Ziffern, Ländervorwahl zuerst, ohne `+`):
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. Gib Meta eine öffentliche HTTPS-Adresse für den lokalen Webhook (Port 8088, an `127.0.0.1` gebunden). Mit Tailscale:
   `sudo tailscale funnel --bg 8088`. Es gibt eine Adresse der Form `https://<machine>.<tailnet>.ts.net` aus.
5. Setze in den WhatsApp-Einstellungen deiner Meta-App die **Callback URL** des Webhooks auf diese Adresse und das **Verify token**
   auf dein `WA_VERIFY_TOKEN`, und abonniere dann das Feld **messages**.
6. Starte den Bot neu (`sudo systemctl restart bot-telegram`) und schreib an deine WhatsApp-Nummer.

Jeder eingehende Aufruf wird abgelehnt, sofern sein `X-Hub-Signature-256` nicht zu deinem App secret passt, und nur die Nummern in
`WA_OWNER` bekommen eine Antwort. Die Bezeichnungen im Meta-Dashboard ändern sich von Zeit zu Zeit; das Prinzip bleibt dasselbe.
Die API-Version ist standardmäßig `v23.0`; überschreibe sie mit `WA_API_VERSION`, falls Meta sie abschaltet.

## Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| Zugang | Nur auf Einladung (laut Presseberichten) | Repo klonen und starten |
| Wo es läuft | In der Cloud eines Unternehmens | **Auf deinem eigenen Rechner** |
| Deine Daten | Einem Startup übergeben | Bleiben auf deiner Kiste (Redis + lokale Dateien) |
| Wie du mit ihm sprichst | Text, Telefon, WhatsApp (laut Presseberichten) | WhatsApp oder Telegram, Text oder Sprache |
| Modelle | Für dich ausgewählt | **Jeder OpenAI-kompatible Anbieter**, Wechsel mit `/model` |
| Kosten | Nicht öffentlich | Kostenlose Kontingente reichen (Groq, Gemini); oder komplett lokal mit Ollama |
| Quellcode | Geschlossen | **Genau hier** |

Instinct AI ist ein echtes Produkt eines finanzierten Teams; Instonct ist das Wochenendprojekt einer einzelnen Person, das zum täglichen Begleiter wurde.
Wähl Instonct, wenn du dieselbe Idee willst, aber selbst am Steuer sitzen möchtest.

## So funktioniert es

- **Gehirn**: jedes OpenAI-kompatible Modell (standardmäßig Groq `gpt-oss-120b` / `20b`, mit adaptivem Reasoning-Aufwand), optionaler Gemini-Fallback.
- **Tools**: Das Modell ruft ~35 Tools auf (Mail, Kalender, Browser, Dateien, Musik, TV, Shell ...). Siehe `TOOLS` in [`catalog.py`](../bots/telegram-search/instonct/catalog.py).
- **Browser**: [Lightpanda](https://github.com/lightpanda-io/browser), ein winziger Headless-Browser (~25 MB RAM), der sogar auf einer CPU von 2010 läuft. Siehe [`webagent.py`](../bots/telegram-search/instonct/webagent.py).
- **Kanäle**: Telegram per Long Polling (kein offener Port), WhatsApp über [`whatsapp.py`](../bots/telegram-search/instonct/whatsapp.py) (ein kleiner Webhook auf `127.0.0.1`).
- **Zustand**: Redis (Verlauf, Gedächtnis, Erinnerungen, Beobachtungen).
- **Erreichbarkeit**: SSH + [Tailscale](https://tailscale.com), `ufw` standardmäßig geschlossen. Die Server-Einrichtung steht in [`home-server.md`](home-server.md).

## Sicherheit, denn ein Agent mit Shell braucht sie

- **Privat**: Auf Telegram wird die erste Person, die `/start` sendet, zum einzigen Besitzer; auf WhatsApp werden nur die Nummern in `WA_OWNER`
  beantwortet. Alle anderen werden ignoriert.
- **Nichts Riskantes geschieht stillschweigend**: Mails senden, ein Formular absenden, einen Termin löschen, einen Befehl ausführen
  oder auf einen Button „Kaufen / Bezahlen / Löschen“ klicken, all das verlangt zuerst ein Tippen auf **Ja / Nein**.
- **Passwörter laufen nie durch das Modell**: Website-Logins liegen in einer `0600`-Datei und werden von schlichtem Code eingetragen.
  Sie zu speichern ist nur auf Telegram möglich, weil der Bot deine Nachricht gleich danach löscht (WhatsApp würde sie behalten).
- **Webseiten sind Daten, keine Befehle**: Text, der auf einer Seite oder in einer Mail steht, kann dem Agenten keine Anweisungen geben.
- **Kein lokales Netzwerk über den Browser**: Nur öffentliche `http(s)`-Adressen sind erlaubt (SSRF-Schutz).
- **Geheimnisse nie in diesem Repo**: Schlüssel liegen in einer `.env` auf dem Server.

## Schnellstart

Du brauchst eine Linux-Kiste, Python 3, Redis, ein **Telegram-Bot-Token** (von [@BotFather](https://t.me/BotFather)) und einen
**API-Schlüssel** eines der oben genannten Anbieter (Groq hat ein kostenloses Kontingent).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # Sprache + Musik (optional)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp -r bots/telegram-search/bot.py bots/telegram-search/instonct ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# optional: LLM_BASE_URL, LLM_MODELS, GEMINI_API_KEY, STT_LANGUAGE=en, WA_* (WhatsApp)
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # vorher User= und Pfade anpassen
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

Öffne dann deinen Bot in Telegram und sende `/start`. Optional: Lightpanda unter `~/lightpanda/lightpanda` für den
Browser, `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` für Mail und `scripts/google-auth.py` für den Google Kalender.

## Du suchst ...

Instant AI · Instinct AI alternative · quelloffenes Instinct AI · selbst gehosteter persönlicher KI-Agent · deinem KI-Assistenten schreiben ·
KI-Assistent auf WhatsApp · KI-Assistent auf Telegram · WhatsApp-KI-Agent · OpenClaw alternative · KI-Agent, der deine E-Mails liest und
deinen Kalender verwaltet · einen KI-Agenten auf einem Raspberry Pi oder alten Mac mini betreiben · KI-Assistent für den Heimserver · Groq-Agent · Gemini-Agent ·
Ollama-Agent · OpenRouter-Agent · Lightpanda-Browser-Agent · KI-Web-Scraper nach CSV · privater KI-Assistent, keine Cloud.

---

<sub>Instonct ist ein unabhängiges Projekt und weder mit Instinct AI oder Spear Street Technology, Inc. verbunden noch von ihnen unterstützt oder gesponsert.
Alle Marken gehören ihren jeweiligen Inhabern. MIT-Lizenz.</sub>
