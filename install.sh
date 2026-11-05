#!/usr/bin/env bash
# Instonct, turnkey install on Debian or Ubuntu. Run it as yourself, from the cloned repo:   ./install.sh
# Safe to run again: it updates the code and keeps your keys and your systemd unit.   --dry-run shows what would be done.
set -euo pipefail

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOTS="$HOME/bots"
CODE="$BOTS/telegram-search"
VENV="$BOTS/venv"
ENV_FILE="$BOTS/.env"
UNIT=/etc/systemd/system/bot-telegram.service
PANDA="$HOME/lightpanda/lightpanda"
PANDA_URL=https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux
PACKAGES=(redis-server python3-venv curl espeak-ng mpv alsa-utils ffmpeg tesseract-ocr tesseract-ocr-fra pandoc poppler-utils imagemagick)

say() { printf '\n== %s\n' "$*"; }
run() { echo "+ $*"; if [[ $DRY == 0 ]]; then "$@"; fi; }

if [[ $EUID == 0 ]]; then
    echo "Lance ce script avec ton compte normal, pas en root : le bot ne doit pas tourner en root." >&2
    exit 1
fi
if [[ $DRY == 0 ]] && ! command -v apt-get >/dev/null; then
    echo "Ce script sait installer sur Debian et Ubuntu. Ailleurs, suis les etapes manuelles du README." >&2
    exit 1
fi

say "Programmes (sudo peut demander ton mot de passe)"
run sudo apt-get update -qq
run sudo apt-get install -y -qq "${PACKAGES[@]}"
run sudo systemctl enable --now redis-server

say "Code et Python"
run mkdir -p "$CODE"
run cp -r "$REPO/bots/telegram-search/bot.py" "$REPO/bots/telegram-search/instonct" "$CODE/"
[[ -d "$VENV" ]] || run python3 -m venv "$VENV"
run "$VENV/bin/pip" install -q -r "$REPO/bots/telegram-search/requirements.txt"

say "Navigateur leger Lightpanda (facultatif)"
if [[ -x "$PANDA" ]]; then
    echo "Deja la."
elif [[ "$(uname -m)" != x86_64 ]]; then
    echo "Pas de version pour cette machine ici : le bot lira les pages sans lui."
elif [[ $DRY == 1 ]]; then
    echo "+ curl $PANDA_URL -> $PANDA"
else
    mkdir -p "$(dirname "$PANDA")"
    if curl -fsSL -o "$PANDA.tmp" "$PANDA_URL"; then
        chmod +x "$PANDA.tmp"
        mv "$PANDA.tmp" "$PANDA"
    else
        rm -f "$PANDA.tmp"
        echo "Telechargement rate : le bot lira les pages sans lui."
    fi
fi

say "Tes cles"
run "$VENV/bin/python" "$REPO/scripts/setup_wizard.py" --env "$ENV_FILE"

say "Service systemd"
if [[ -e "$UNIT" ]]; then
    echo "$UNIT existe deja : je le garde."
else
    NEW_UNIT="[Unit]
Description=Instonct (agent personnel)
After=network-online.target redis-server.service
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$CODE
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python bot.py
Restart=always
RestartSec=5
# The bot alone uses about 50 MB. Its browser window (Chromium, measured up to about 800 MB) counts in the same limit.
MemoryMax=1500M
# If the kernel kills the browser for memory, the bot stays up.
OOMPolicy=continue

[Install]
WantedBy=multi-user.target"
    if [[ $DRY == 1 ]]; then
        printf '%s\n' "$NEW_UNIT"
    else
        printf '%s\n' "$NEW_UNIT" | sudo tee "$UNIT" >/dev/null
    fi
    run sudo systemctl daemon-reload
    run sudo systemctl enable bot-telegram
fi
run sudo systemctl restart bot-telegram

say "Verification"
if [[ $DRY == 0 ]]; then
    (cd "$CODE" && INSTONCT_ENV="$ENV_FILE" "$VENV/bin/python" bot.py doctor) || echo "Regarde les lignes PANNE ci-dessus, puis relance : cd $CODE && $VENV/bin/python bot.py doctor"
fi

cat <<'END'

Fini. Envoie /start a ton bot TOUT DE SUITE, toi-meme : le premier compte qui envoie /start devient son unique maitre.
Ensuite :
  /sante       ce qui marche et ce qui ne marche pas
  /aide        ce que le bot sait faire
Pour l'ecran a distance (connexion aux sites, passage de main pour payer), il faut aussi : tailscale, xvfb, openbox, x11vnc, novnc, websockify, chromium.
END
