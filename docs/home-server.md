# The home server (hardware and setup)

An old Mac mini (2010, Core 2 Duo, ~4.6 GB of RAM) running Lubuntu, turned into a small SSH-managed server that
runs bots 24/7 (one systemd service per bot). Instonct is the main one.

## What is in this repo

| File | Purpose |
|---|---|
| `bots/telegram-search/` | The Instonct bot: brain (`bot.py`), calendar (`gcal.py`), browser (`webagent.py`), WhatsApp channel (`whatsapp.py`), TV remote (`tvremote.py`) |
| `systemd/bot-telegram.service` | Starts the bot at boot and restarts it if it crashes |
| `scripts/google-auth.py` | Authorizes the bot to use your Google Calendar (once) |
| `scripts/ecran-status` | Text dashboard shown on the Mac mini's own screen (IP, load, temperature, RAM, bots) |
| `systemd/ecran-status.service` | Runs the dashboard on `tty1` (instead of a graphical desktop) |
| `scripts/cockpit-cert-renew` | Gets a real HTTPS certificate through Tailscale and installs it for Cockpit |
| `systemd/cockpit-cert-renew.{service,timer}` | Renews that certificate every month |
| `networkmanager/wifi-powersave-off.conf` | Turns off Wi-Fi power saving (avoids drops) |

## Architecture

- **Remote access**: SSH keys, then [Tailscale](https://tailscale.com) (private network between my devices, no port open on the router).
- **Web interface**: [Cockpit](https://cockpit-project.org) on port 9090, reachable only through Tailscale.
- **Security**: `ufw` (deny everything by default, SSH and Cockpit allowed only on `tailscale0`), `fail2ban`.
- **Sleep disabled** (`systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`) and console
  mode by default (`systemctl set-default multi-user.target`) to save RAM.
- **Bots**: one `bot-<name>.service` per bot, `Restart=always`. Telegram uses long polling, so no inbound port is needed.
  (WhatsApp is the one exception: Meta must reach a public HTTPS URL. See "WhatsApp" in the main README.)

## Server install (summary)

```bash
sudo install -m 755 scripts/ecran-status scripts/cockpit-cert-renew /usr/local/bin/
sudo install -m 644 systemd/*.service systemd/*.timer /etc/systemd/system/
sudo install -m 644 networkmanager/wifi-powersave-off.conf /etc/NetworkManager/conf.d/
sudo systemctl daemon-reload
sudo systemctl enable --now ecran-status.service cockpit-cert-renew.timer
```

For Cockpit over HTTPS: enable *HTTPS Certificates* in the Tailscale admin console (DNS), then run
`sudo /usr/local/bin/cockpit-cert-renew` once.

## Secrets

Tokens (Telegram, API keys): **never in this repo**. They live in a `.env` file on the server, read by the systemd
service through `EnvironmentFile=`.
