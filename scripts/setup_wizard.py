#!/usr/bin/env python3
"""First-run questions, in your own terminal. Keys are typed hidden, tested, then saved to ~/bots/.env (readable by you only).

Nothing typed here is printed or sent anywhere but the service it belongs to. A key already in the file is kept.
"""
import argparse
import getpass
import os
import re
import stat
import sys
import tempfile

import requests

DEFAULT_ENV = os.path.expanduser("~/bots/.env")
PROVIDERS = {"1": ("Groq (a un palier gratuit)", ""),
             "2": ("Cerebras (a un palier gratuit)", "https://api.cerebras.ai/v1"),
             "3": ("OpenRouter", "https://openrouter.ai/api/v1"),
             "4": ("Autre service compatible OpenAI", None)}
GROQ = "https://api.groq.com/openai/v1"
CEREBRAS_MODELS = "gpt-oss-120b"


def read_env(path):
    """The names already set. Only the names: values are none of this script's business."""
    names = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\S", line)
                if m:
                    names.add(m.group(1))
    return names


def _quoted(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def add_to_env(path, values):
    """Adds the new names, keeps every existing line, and never leaves a half-written or readable file."""
    for value in values.values():
        if "\n" in value or "\r" in value:
            raise ValueError("une valeur contient un retour a la ligne")
    known = read_env(path)
    old = ""
    if os.path.exists(path):
        with open(path) as f:
            old = f.read()
    if old and not old.endswith("\n"):
        old += "\n"
    new = old + "".join(f"{k}={_quoted(v)}\n" for k, v in values.items() if v and k not in known)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".env.")      # mkstemp creates it 0600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(new)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def telegram_ok(token):
    """The bot's name, or None. The token goes in the URL: only Telegram's address is ever called, and errors are not printed."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        return r.json()["result"]["username"] if r.status_code == 200 else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def model_key_ok(base, key):
    try:
        return requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=10).status_code == 200
    except requests.RequestException:
        return False


def _ask_until(label, check, tries=3):
    for _ in range(tries):
        value = getpass.getpass(f"{label} (cache a l'ecran) : ").strip()
        if value and check(value):
            return value
        print("  Ca n'a pas marche. Verifie et recommence.")
    sys.exit("Trop d'essais. Relance l'installation quand tu as la bonne valeur.")


def wizard(path):
    known = read_env(path)
    found = {}
    if "TELEGRAM_TOKEN" in known:
        print("Telegram : deja configure, je n'y touche pas.")
    else:
        print("\n1. Telegram : parle a @BotFather, envoie /newbot, et copie le jeton.")
        found["TELEGRAM_TOKEN"] = _ask_until("Jeton Telegram", telegram_ok)
        print(f"  OK : @{telegram_ok(found['TELEGRAM_TOKEN'])}")
    if known & {"LLM_API_KEY", "GROQ_API_KEY"}:
        print("Modele : deja configure, je n'y touche pas.")
    else:
        print("\n2. Le cerveau : choisis un service et cree une cle API sur son site.")
        for number, (name, _) in PROVIDERS.items():
            print(f"  {number}. {name}")
        choice = input("Ton choix [1] : ").strip() or "1"
        _, base = PROVIDERS.get(choice, PROVIDERS["1"])
        if base is None:
            base = input("Adresse de l'API (https://...) : ").strip().rstrip("/")
            found["LLM_MODELS"] = input("Nom du modele : ").strip()
        if base:
            found["LLM_BASE_URL"] = base
        if choice == "2":
            found["LLM_MODELS"] = CEREBRAS_MODELS
        elif choice == "3":
            found["LLM_MODELS"] = input("Nom du modele (ex. sur openrouter.ai/models) : ").strip()
        found["LLM_API_KEY"] = _ask_until("Cle API", lambda key: model_key_ok(base or GROQ, key))
        print("  OK : cle acceptee.")
    if "GEMINI_API_KEY" not in known:
        gemini = getpass.getpass("\n3. Secours Gemini, facultatif (Entree pour passer, cache a l'ecran) : ").strip()
        if gemini:
            found["GEMINI_API_KEY"] = gemini
    if "MAIL_USER" not in known:
        user = input("\n4. Mail, facultatif : ton adresse (Entree pour passer) : ").strip()
        if user:
            found["MAIL_USER"] = user
            found["MAIL_PASS"] = getpass.getpass("   Mot de passe d'application de cette boite, pas ton mot de passe normal (cache a l'ecran) : ").strip()
            print("   Enregistre. La connexion sera essayee au premier passage du bot.")
    add_to_env(path, found)
    print(f"\nEnregistre dans {path}, lisible par toi seul.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=DEFAULT_ENV)
    wizard(parser.parse_args().env)


if __name__ == "__main__":
    main()
