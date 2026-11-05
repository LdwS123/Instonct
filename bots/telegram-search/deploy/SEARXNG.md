# Optional: your own search engine (SearXNG)

The bot searches DuckDuckGo first. If that finds nothing it asks a local SearXNG (about 80 MB of RAM, no key, no AVX needed), then spare engines.

```
mkdir -p ~/searxng && cd ~/searxng
git clone --depth 1 https://github.com/searxng/searxng src
python3 -m venv venv && ./venv/bin/pip install -U pip setuptools wheel pyyaml msgspec typing_extensions
cd src && ../venv/bin/pip install --use-pep517 --no-build-isolation -e . && ../venv/bin/pip install -r requirements.txt
```
Write `~/searxng/settings.yml` (listen on 127.0.0.1:8888, `formats: [html, json]`, `limiter: false`, your own `secret_key`), copy `searxng.service` to `/etc/systemd/system/`, then `sudo systemctl enable --now searxng`.
`SEARXNG_URL` in the bot's `.env` changes the address (empty = off).
