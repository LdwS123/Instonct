# Mac mini 2010 -> mini serveur maison

Un vieux Mac mini (2010, Core 2 Duo, ~4,6 Go de RAM) sous Lubuntu, transforme en petit serveur
pilote en SSH, qui fait tourner des bots 24h/24 (un service systemd par bot).

## Ce que contient ce depot

| Fichier | Role |
|---|---|
| `scripts/ecran-status` | Tableau de bord texte affiche sur l'ecran du Mac mini (IP, charge, temperature, RAM, bots) |
| `systemd/ecran-status.service` | Lance le tableau de bord sur `tty1` (a la place de l'interface graphique) |
| `scripts/cockpit-cert-renew` | Recupere un vrai certificat HTTPS via Tailscale et l'installe pour Cockpit |
| `systemd/cockpit-cert-renew.{service,timer}` | Renouvelle ce certificat chaque mois |
| `networkmanager/wifi-powersave-off.conf` | Coupe l'economie d'energie du Wi-Fi (evite les coupures) |

## Architecture

- **Acces a distance** : SSH par cle, puis [Tailscale](https://tailscale.com) (reseau prive entre mes appareils, aucun port ouvert sur la box).
- **Interface web** : [Cockpit](https://cockpit-project.org) sur le port 9090, joignable uniquement via Tailscale.
- **Securite** : `ufw` (tout refuse par defaut, SSH et Cockpit autorises seulement sur `tailscale0`), `fail2ban`.
- **Veille desactivee** (`systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`) et
  mode console par defaut (`systemctl set-default multi-user.target`) pour gagner de la RAM.
- **Bots** : un service `bot-<nom>.service` par bot, `Restart=always`. Les bots Telegram utilisent le
  long polling, donc aucun port entrant n'est necessaire.

## Installation (resume)

```bash
sudo install -m 755 scripts/ecran-status scripts/cockpit-cert-renew /usr/local/bin/
sudo install -m 644 systemd/*.service systemd/*.timer /etc/systemd/system/
sudo install -m 644 networkmanager/wifi-powersave-off.conf /etc/NetworkManager/conf.d/
sudo systemctl daemon-reload
sudo systemctl enable --now ecran-status.service cockpit-cert-renew.timer
```

Pour Cockpit en HTTPS : activer *HTTPS Certificates* dans la console admin Tailscale (DNS),
puis lancer une fois `sudo /usr/local/bin/cockpit-cert-renew`.

## Secrets

Tokens (Telegram, cles API) : **jamais dans ce depot**. Ils vivent dans un fichier `.env`
sur le serveur, lu par le service systemd via `EnvironmentFile=`.
