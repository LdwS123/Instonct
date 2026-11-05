"""Instonct: a Telegram (and WhatsApp) assistant that runs on a small home server.

Layout (each module has a one-line description at its top):
  config, texts, core            settings, fixed texts, shared infrastructure (leaf modules)
  llm, catalog, brain, dispatch  the AI: providers + fallback, tool catalogue, agent loop, tool routing
  music, cast, television, sound        sound, TV and voice
  mail, web, pagewatch, google   mail, browser, page watching, calendar
  media, life, system_tools      images/files, habits & lists, shell/files/HTTP tools
  handlers, callbacks, commands  Telegram messages, buttons, free commands
  reminders, monitor, remote_access, runner  background loops, remote screen & Siri, entry point
"""
