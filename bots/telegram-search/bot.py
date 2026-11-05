#!/usr/bin/env python3
"""Entry point kept for the systemd unit (`python bot.py`). The code lives in the `instonct` package.

`python bot.py doctor` says what works and what does not.
"""
import os
import shlex
import sys


def doctor():
    """Reads ~/bots/.env as systemd would, then runs the checks. Without a Telegram token there is nothing else to check."""
    path = os.environ.get("INSTONCT_ENV", os.path.expanduser("~/bots/.env"))
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    words = shlex.split(line, comments=True)
                except ValueError:
                    continue
                name, eq, value = (words[0] if len(words) == 1 else line.strip()).partition("=")
                if eq and not name.startswith("#"):
                    os.environ.setdefault(name.strip(), value)
    if not os.environ.get("TELEGRAM_TOKEN"):
        print(f"PANNE Telegram : pas de TELEGRAM_TOKEN dans {path}")
        return 1
    from instonct.health import main as checks
    return checks()


if __name__ == "__main__":
    if sys.argv[1:] == ["doctor"]:
        sys.exit(doctor())
    from instonct.runner import main
    main()
