"""Optional libraries: the bot keeps running when one of them is missing (its feature is simply off)."""
import logging

log = logging.getLogger("bot")

try:                                       # extra tools (documents, QR, places, Wikipedia, currencies...)
    from . import extras
except Exception:                          # noqa
    extras = None
try:                                       # habit learning (counting only, no AI call)
    from . import habits
except Exception:                          # noqa
    habits = None
try:                                       # WhatsApp only turns on when the WA_* variables are set
    from . import whatsapp
except Exception as _e:
    whatsapp = None
    log.warning("whatsapp module unavailable: %s", _e)
try:                                       # music and the rest work even without the TV remote
    from . import tvremote
except Exception as _e:
    tvremote = None
    log.warning("telecommande indisponible : %s", _e)
