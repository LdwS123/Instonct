"""The menu by category, scenes, rules (« chaque jour a 7h30 : ... »), quiet hours, the button panel and self-repair.
The TV, the sound and the machine's services are always faked: nothing here can make the Mac mini speak or touch the real TV."""
import json
import re
from collections import namedtuple
from datetime import datetime
from pathlib import Path

import pytest

from instonct import automate, callbacks, guard, handlers, kit_auto, plus, quiet, rubriques, sound
from instonct.core import db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def world(monkeypatch):
    """A fake house: records what would have been done, answers like the real helpers."""
    calls, sent = [], []
    monkeypatch.setattr(automate.television, "tv_power", lambda want: (calls.append(("tele", want)), f"tele {want}")[1])
    monkeypatch.setattr(automate.television, "tv_channel", lambda n: (calls.append(("chaine", n)), f"chaine {n}")[1])
    monkeypatch.setattr(automate.music, "stop_all", lambda tv=False: calls.append(("musique", "stop")))
    monkeypatch.setattr(automate.sound, "set_volume", lambda pct, mac_only=False: calls.append(("volume", pct)))
    monkeypatch.setattr(automate.sound, "change_volume", lambda d: (calls.append(("volume", d)), f"volume {d:+d}")[1])
    monkeypatch.setattr(automate.life, "briefing_text", lambda: "BRIEFING")
    monkeypatch.setattr(automate.commands, "status", lambda: "STATUS")
    monkeypatch.setattr(automate.kit_server, "backup_now", lambda chat, a: (calls.append(("sauvegarde", "")), {"fichier": "/x/b.tgz"})[1])
    monkeypatch.setattr(automate, "send", lambda chat, text: sent.append(text))
    monkeypatch.setattr(automate, "_launch", lambda fn, *a: fn(*a))                 # no thread: everything happens on the spot
    db.set("owner_id", "42")
    return namedtuple("World", "calls sent")(calls, sent)


# ---------------------------------------------------------------- the menu
def _handler_commands():
    src = (ROOT / "instonct" / "handlers.py").read_text()
    names = set(re.findall(r'cmd == "/([a-z_]+)"', src))
    for group in re.findall(r"cmd in \(([^)]*)\)", src):
        names |= set(re.findall(r'"/([a-z_]+)"', group))
    return names


def test_every_command_is_in_the_menu_and_every_menu_command_exists():
    handled = _handler_commands()
    listed = {n for n, _ in rubriques.all_commands()}
    assert {"menu", "panneau", "scene", "auto", "silence"} <= handled
    assert handled - rubriques.HIDDEN <= listed, f"missing from the menu: {handled - rubriques.HIDDEN - listed}"
    assert listed <= handled, f"in the menu but nobody answers: {listed - handled}"


def test_telegram_accepts_the_command_list():
    cmds = rubriques.telegram_commands()
    assert 1 <= len(cmds) <= 100 and len({c for c, _ in cmds}) == len(cmds)
    for name, desc in cmds:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", name) and 3 <= len(desc) <= 256


def test_each_category_page_and_its_buttons_are_valid():
    assert {c[0] for c in rubriques.CATEGORIES} >= {"maison", "musique", "serveur", "auto"}
    for key, _, title, *_ in rubriques.CATEGORIES:
        text, rows = rubriques.page(key)
        assert title in text and rows[-1] == [("⬅ Menu", "menu:home")]
        for label, data in [b for row in rows for b in row]:
            assert label and len(data.encode()) <= 64
            assert data.startswith(("menu:", "go:")) and (not data.startswith("go:") or data[3:] in automate.QUICK)
    assert rubriques.page("nope")[0] == rubriques.home_text()
    flat = [b for row in rubriques.menu_rows() for b in row]
    assert {d for _, d in flat} == {f"menu:{c[0]}" for c in rubriques.CATEGORIES}


def test_help_lists_each_command_once():
    lines = [x for x in rubriques.aide_text().splitlines() if x.startswith("/")]
    names = [x.split(" ")[0] for x in lines]
    assert len(names) == len(set(names)) and "/auto" in names and "/silence" in names


def test_menu_button_edits_the_message_and_go_button_runs_the_action(monkeypatch, world):
    edits, pressed = [], []
    monkeypatch.setattr(callbacks, "tg", lambda method, **p: edits.append((method, p)) or {})
    monkeypatch.setattr(callbacks.automate, "press", lambda chat, key: pressed.append((chat, key)))
    msg = {"chat": {"id": 42}, "message_id": 7}
    callbacks.handle_callback({"id": "1", "from": {"id": 42}, "message": msg, "data": "menu:serveur"})
    method, params = [e for e in edits if e[0] == "editMessageText"][0]
    assert params["message_id"] == 7 and rubriques.by_key("serveur")[2] in params["text"] and params["reply_markup"]["inline_keyboard"]
    callbacks.handle_callback({"id": "2", "from": {"id": 42}, "message": msg, "data": "go:status"})
    assert pressed == [(42, "status")]
    callbacks.handle_callback({"id": "3", "from": {"id": 999}, "message": msg, "data": "go:tele_off"})     # not the owner
    assert pressed == [(42, "status")]


def test_menu_command_sends_buttons_and_panel(monkeypatch, world):
    out = []
    monkeypatch.setattr(handlers, "tg", lambda method, **p: out.append((method, p)) or {})
    handlers.send_menu(42)
    handlers.send_panel(42)
    assert out[0][1]["reply_markup"]["inline_keyboard"] and out[1][1]["reply_markup"]["inline_keyboard"]
    sent = []
    monkeypatch.setattr(handlers, "send", lambda chat, text: sent.append(text))
    handlers.send_menu("wa:33600000000")
    assert "/auto" in sent[0]


# ---------------------------------------------------------------- steps and scenes
@pytest.mark.parametrize("text,want", [
    ("Allume la télé", ("tele", "on")), ("éteins la tele", ("tele", "off")), ("tele off", ("tele", "off")), ("musique stop", ("musique", "stop")),
    ("arrête la musique", ("musique", "stop")), ("volume 20", ("volume", "20")), ("volume 250", ("volume", "100")), ("volume +", ("volume", "+")),
    ("baisse le son", ("volume", "-")), ("chaîne 3", ("chaine", "3")), ("état", ("status", "")), ("résumé", ("briefing", "")), ("sauvegarde", ("sauvegarde", "")),
    ("scène film", ("scene", "film")), ("routine matin", ("routine", "matin")), ("silence on", ("silence", "on")), ("message Coucou, ça va ?", ("message", "Coucou, ça va ?")),
])
def test_one_step_is_understood(text, want):
    assert automate.parse_step(text) == want


def test_unknown_step_is_refused_with_the_list():
    assert automate.parse_step("fais la vaisselle") is None
    steps, err = automate.parse_steps("tele off, fais la vaisselle")
    assert steps == [] and "fais la vaisselle" in err and "Actions" in err
    assert automate.parse_steps("")[1]
    assert "Trop" in automate.parse_steps(", ".join(["status"] * 9))[1]


def test_steps_split_on_commas_and_words_and_the_message_takes_the_rest():
    steps, err = automate.parse_steps("tele off, musique stop puis volume 10 et message Bonne nuit, à demain ; dors bien")
    assert err is None
    assert steps == ["tele off", "musique stop", "volume 10", "message Bonne nuit, à demain ; dors bien"]


def test_a_scene_does_every_step_and_a_failure_does_not_stop_the_others(monkeypatch, world):
    monkeypatch.setattr(automate.television, "tv_power", lambda want: 1 / 0)
    lines = automate.run_scene(42, "dodo")
    assert any("n'a pas marché" in x for x in lines) and ("musique", "stop") in world.calls and any("Bonne nuit" in x for x in lines)
    assert quiet.config()["on"] is True                                       # « dodo » also switches quiet hours on


def test_scene_command_create_list_run_delete(world):
    assert "enregistrée" in automate.scene_command(42, "creer soiree = tele on, volume 30, message Bonne soirée")
    assert "soiree (à toi)" in automate.scene_command(42, "")
    out = automate.scene_command(42, "soiree")
    assert ("tele", "on") in world.calls and ("volume", 30) in world.calls and "Bonne soirée" in out
    assert "inconnue" in automate.scene_command(42, "nimporte").lower() or "ne connais pas" in automate.scene_command(42, "nimporte")
    assert "2 à 20" in automate.scene_command(42, "creer a = status")
    assert "Je ne connais pas l'action" in automate.scene_command(42, "creer x1 = danse")
    assert "effacée" in automate.scene_command(42, "suppr soiree")
    assert "ne trouve pas" in automate.scene_command(42, "suppr dodo")        # the ready-made ones stay


def test_a_scene_inside_a_scene_cannot_loop_forever(world):
    automate.scene_command(42, "creer boucle = scene boucle")
    assert "Trop" in "\n".join(automate.run_scene(42, "boucle"))


def test_scene_phrases_are_orders_and_other_phrases_are_not(world):
    assert "Bonne séance" in automate.quick(42, "Mode film")
    assert ("tele", "on") in world.calls
    assert automate.quick(42, "lance la scène dodo") is not None
    assert automate.quick(42, "mode avion") is None and automate.quick(42, "mets la chaine 3") is None and automate.quick(42, "salut") is None


# ---------------------------------------------------------------- moments and rules
@pytest.mark.parametrize("text,want", [
    ("chaque jour à 7h30", {"type": "daily", "time": "07:30", "days": None}),
    ("tous les jours à 22h", {"type": "daily", "time": "22:00", "days": None}),
    ("en semaine à 7h", {"type": "daily", "time": "07:00", "days": [0, 1, 2, 3, 4]}),
    ("le weekend à 9:15", {"type": "daily", "time": "09:15", "days": [5, 6]}),
    ("tous les lundis à 8h", {"type": "daily", "time": "08:00", "days": [0]}),
    ("toutes les 30 minutes", {"type": "every", "min": 30}), ("toutes les 2 heures", {"type": "every", "min": 120}), ("chaque heure", {"type": "every", "min": 60}),
    ("si le disque < 15", {"type": "disk", "pct": 15}), ("si la température > 80", {"type": "temp", "deg": 80}),
    ("si le site exemple.fr tombe", {"type": "site", "host": "exemple.fr"}),
])
def test_moments_are_understood(text, want):
    assert automate.parse_when(text) == (want, None)


@pytest.mark.parametrize("text", ["toutes les 2 minutes", "toutes les 48 heures", "si le disque", "si la température 20", "un de ces jours", "chaque jour"])
def test_bad_moments_get_an_explanation(text):
    when, err = automate.parse_when(text)
    assert when is None and err


def test_add_list_pause_resume_run_and_delete_a_rule(world):
    out = automate.auto_command(42, "ajoute chaque jour à 7h30 : briefing")
    assert "enregistrée" in out
    rid = automate.rules()[0]["id"]
    assert "7h30".replace("h", ":") in automate.auto_command(42, "liste") or "07:30" in automate.auto_command(42, "liste")
    assert "en pause" in automate.auto_command(42, f"pause {rid}") and automate.rules()[0]["on"] is False
    assert "reprise" in automate.auto_command(42, f"reprise {rid}") and automate.rules()[0]["on"] is True
    assert "BRIEFING" in automate.auto_command(42, f"lance {rid}")
    assert "effacée" in automate.auto_command(42, f"suppr {rid}") and automate.rules() == []
    assert "ne trouve pas" in automate.auto_command(42, "suppr zzzz")


@pytest.mark.parametrize("text", ["chaque jour à 7h30", "chaque jour à 7h30 : danse", "un jour : status", "chaque jour à 7h30 :"])
def test_a_bad_rule_is_refused_and_saves_nothing(world, text):
    out = automate.auto_command(42, "ajoute " + text)
    assert "enregistrée" not in out and automate.rules() == []


def test_alternative_separators_and_the_30_rule_limit(world):
    assert "enregistrée" in automate.auto_command(42, "ajoute en semaine à 22h30 alors scene dodo")
    assert "enregistrée" in automate.auto_command(42, "ajoute toutes les 3 heures -> sauvegarde")
    for i in range(automate.MAX_RULES - 2):
        assert automate.add_rule(f"chaque jour à {i % 24}h{i:02d} : status")[1] is None
    assert "Déjà" in automate.auto_command(42, "ajoute chaque jour à 5h : status")


def _at(h, m, day=6):                                                             # 2026-11-06 is a Friday (weekday 4)
    return datetime(2026, 11, day, h, m, 5)


def test_a_daily_rule_fires_once_a_day_even_if_the_bot_restarts_late(world):
    automate.add_rule("chaque jour à 7h30 : message Debout")
    automate.tick(_at(7, 29))
    assert world.sent == []                                                       # not yet
    automate.tick(_at(7, 31))
    automate.tick(_at(7, 32))                                                     # the loop ticks again: no second send
    assert len(world.sent) == 1 and "Debout" in world.sent[0]
    automate.tick(_at(7, 31, day=7))                                              # next day: again
    assert len(world.sent) == 2


def test_a_daily_rule_does_not_fire_hours_late_and_respects_the_days(world):
    automate.add_rule("chaque jour à 7h30 : message A")
    automate.add_rule("le weekend à 9h : message B")
    automate.tick(_at(10, 0))
    assert world.sent == []                                                       # too late (more than 10 minutes)
    automate.tick(_at(9, 2))                                                      # Friday: the weekend rule stays quiet
    assert world.sent == []
    automate.tick(_at(9, 2, day=7))                                               # Saturday
    assert len(world.sent) == 1 and "B" in world.sent[0]


def test_a_paused_rule_and_a_missing_owner_do_nothing(world):
    automate.add_rule("chaque jour à 7h30 : message A")
    automate.auto_command(42, f"pause {automate.rules()[0]['id']}")
    automate.tick(_at(7, 31))
    assert world.sent == []
    db.delete("owner_id")
    automate.auto_command(42, f"reprise {automate.rules()[0]['id']}")
    automate.tick(_at(7, 31))
    assert world.sent == []


def test_an_every_rule_waits_a_full_period_first(world):
    automate.add_rule("toutes les 30 minutes : message ping")
    t0 = _at(12, 0)
    automate.tick(t0)                                                             # first sight: only schedules
    assert world.sent == []
    automate.tick(datetime.fromtimestamp(t0.timestamp() + 29 * 60))
    assert world.sent == []
    automate.tick(datetime.fromtimestamp(t0.timestamp() + 31 * 60))
    assert len(world.sent) == 1
    automate.tick(datetime.fromtimestamp(t0.timestamp() + 32 * 60))
    assert len(world.sent) == 1


def test_a_condition_rule_checks_every_10_minutes_and_rings_once_per_6_hours(monkeypatch, world):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(automate.shutil, "disk_usage", lambda p: Usage(100, 95, 5))
    automate.add_rule("si le disque < 15 : message Disque presque plein")
    automate.tick(_at(12, 0))
    automate.tick(_at(12, 0))                                                     # same 10 minutes: not checked twice
    assert len(world.sent) == 1 and "Disque presque plein" in world.sent[0]
    db.delete(f"auto:chk:{automate.rules()[0]['id']}")                            # 10 minutes later the check runs, but the 6 h cool-down holds
    automate.tick(_at(12, 11))
    assert len(world.sent) == 1


def test_a_condition_that_is_not_met_stays_silent(monkeypatch, world):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(automate.shutil, "disk_usage", lambda p: Usage(100, 50, 50))
    monkeypatch.setattr(automate.commands, "cpu_temp", lambda: "55 C")
    automate.add_rule("si le disque < 15 : message A")
    automate.add_rule("si la température > 80 : message B")
    automate.tick(_at(12, 0))
    assert world.sent == []
    monkeypatch.setattr(automate.commands, "cpu_temp", lambda: "91 C")
    for r in automate.rules():
        db.delete(f"auto:chk:{r['id']}")
    automate.tick(_at(12, 20))
    assert len(world.sent) == 1 and "B" in world.sent[0]


def test_site_rule_fires_only_when_the_site_is_really_down(monkeypatch, world):
    from instonct import kit_net
    answers = iter([{"en_ligne": True}, {"en_ligne": False}, {"erreur": "seulement les sites publics"}])
    monkeypatch.setattr(kit_net, "site_up", lambda chat, a: next(answers))
    automate.add_rule("si le site exemple.fr tombe : message Le site est tombé")
    rid = automate.rules()[0]["id"]
    automate.tick(_at(12, 0))
    assert world.sent == []
    db.delete(f"auto:chk:{rid}")
    automate.tick(_at(12, 11))
    assert len(world.sent) == 1
    db.delete(f"auto:chk:{rid}")
    db.delete(f"auto:cool:{rid}")
    automate.tick(_at(12, 22))                                                    # an error answer is not « down »
    assert len(world.sent) == 1


def test_panel_buttons_run_the_action_and_unknown_buttons_do_nothing(world):
    assert automate.press(42, "tele_off") == automate.QUICK_LABELS["tele_off"]
    assert ("tele", "off") in world.calls and "tele off" in world.sent[0]
    assert automate.press(42, "nimporte") == "Bouton inconnu."
    rows = automate.panel_markup()["inline_keyboard"]
    assert {b["callback_data"] for r in rows for b in r} == {f"go:{k}" for k in automate.QUICK}
    assert set(automate.QUICK) == set(automate.QUICK_LABELS)
    assert all(automate.parse_step(s) for s in automate.QUICK.values())


# ---------------------------------------------------------------- quiet hours
def test_quiet_hours_across_midnight_and_inside_a_day():
    db.hset("quiet", mapping={"on": "1", "start": "23:00", "end": "07:00"})
    assert quiet.is_quiet(datetime(2026, 11, 6, 23, 30)) and quiet.is_quiet(datetime(2026, 11, 7, 6, 59))
    assert not quiet.is_quiet(datetime(2026, 11, 7, 7, 0)) and not quiet.is_quiet(datetime(2026, 11, 6, 12, 0))
    db.hset("quiet", mapping={"on": "1", "start": "13:00", "end": "14:30"})
    assert quiet.is_quiet(datetime(2026, 11, 6, 14, 0)) and not quiet.is_quiet(datetime(2026, 11, 6, 15, 0))
    db.hset("quiet", "on", "0")
    assert not quiet.is_quiet(datetime(2026, 11, 6, 14, 0))


def test_silence_command():
    assert "coupé" in quiet.command("")
    assert "activé de 23:00 à 07:00" in quiet.command("on")
    assert "de 22:30 à 06:45" in quiet.command("22h30 6h45") and quiet.config()["start"] == "22:30"
    assert "coupé" in quiet.command("off") and not quiet.config()["on"]
    assert "23:00" in quiet.command("bizarre") or "silence" in quiet.command("bizarre").lower()
    assert quiet.parse_time("25h") is None and quiet.parse_time("7h99") is None


def test_the_mac_mini_stays_silent_during_quiet_hours(monkeypatch):
    spoken = []
    monkeypatch.setattr(sound, "speak", lambda *a, **k: spoken.append(a))
    monkeypatch.setattr(sound, "clean_for_speech", lambda t: t)
    db.set("voice_on", 1)
    monkeypatch.setattr(quiet, "is_quiet", lambda now=None: True)
    sound.say_async("bonjour")
    monkeypatch.setattr(quiet, "is_quiet", lambda now=None: False)
    sound.say_async("bonjour")
    import time
    time.sleep(0.3)
    assert len(spoken) == 1                                                       # only the call outside quiet hours spoke


def test_the_watch_loop_keeps_only_the_machine_guards_while_quiet(monkeypatch):
    from instonct import monitor
    monkeypatch.setattr(quiet, "is_quiet", lambda now=None: True)
    night = {f.__name__ for f in monitor.checks_now()}
    assert night == {"check_system", "check_screen", "check_google", "check_backup", "check_selfheal"}
    monkeypatch.setattr(quiet, "is_quiet", lambda now=None: False)
    day = {f.__name__ for f in monitor.checks_now()}
    assert night < day and "check_mail" in day and "check_selfheal" in day


# ---------------------------------------------------------------- self-repair
def _heal(monkeypatch, failed, free_pct=50):
    ran = []
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(automate.shutil, "disk_usage", lambda p: Usage(100, 100 - free_pct, free_pct))

    def fake(cmd, timeout=60):
        ran.append(cmd)
        return namedtuple("R", "stdout returncode")(failed if cmd[0] == "systemctl" else "", 0)
    monkeypatch.setattr(automate, "_run", fake)
    return ran


def test_a_failed_service_from_the_list_is_restarted_once_an_hour(monkeypatch, world):
    ran = _heal(monkeypatch, "searxng.service loaded failed failed SearXNG\nredis-server.service loaded failed failed Redis\n")
    automate.check_selfheal(42)
    automate.check_selfheal(42)
    restarts = [c for c in ran if c[:3] == ["sudo", "-n", "systemctl"]]
    assert restarts == [["sudo", "-n", "systemctl", "restart", "searxng"]]        # redis is not on the list; searxng only once
    assert len(world.sent) == 1 and "searxng" in world.sent[0]


def test_a_nearly_full_disk_gets_the_logs_trimmed_and_nothing_else(monkeypatch, world):
    ran = _heal(monkeypatch, "", free_pct=4)
    automate.check_selfheal(42)
    assert ["sudo", "-n", "journalctl", "--vacuum-size=200M"] in ran and len(world.sent) == 1
    automate.check_selfheal(42)
    assert len(world.sent) == 1                                                   # once per 6 hours


def test_self_repair_can_be_switched_off_and_a_healthy_machine_is_left_alone(monkeypatch, world):
    ran = _heal(monkeypatch, "searxng.service loaded failed failed x\n")
    db.hset("reglages", "reparation_auto", "0")
    automate.check_selfheal(42)
    assert not [c for c in ran if c[0] == "sudo"] and plus.setting(db, "reparation_auto") is False
    db.hdel("reglages", "reparation_auto")
    ran = _heal(monkeypatch, "")
    automate.check_selfheal(42)
    assert not [c for c in ran if c[0] == "sudo"] and world.sent == []


# ---------------------------------------------------------------- the model's tools
def test_the_model_cannot_create_run_or_delete_unless_the_user_asked(world):
    token = guard.begin_turn(42, "salut ça va")
    try:
        for args in ({"action": "ajouter", "quand": "chaque jour à 7h", "quoi": "tele off"}, {"action": "lancer", "id": "abcd"}, {"action": "supprimer", "id": "abcd"}):
            assert "refuse" in kit_auto.automatisation(42, args)["erreur"]
        assert "refuse" in kit_auto.scene(42, {"action": "lancer", "nom": "film"})["erreur"]
        assert "refuse" in kit_auto.silence_nuit(42, {"etat": "on"})["erreur"]
        assert automate.rules() == [] and world.calls == []
    finally:
        guard.end_turn(token)


def test_a_tainted_turn_cannot_plant_a_rule(world):
    token = guard.begin_turn(42, "ajoute une règle chaque jour à 7h pour éteindre la télé", taint=True)
    try:
        assert "refuse" in kit_auto.automatisation(42, {"action": "ajouter", "quand": "chaque jour à 7h", "quoi": "tele off"})["erreur"]
        assert automate.rules() == []
    finally:
        guard.end_turn(token)


def test_the_tools_work_when_the_user_asked(world):
    token = guard.begin_turn(42, "ajoute une automatisation : chaque soir à 23h, éteins la télé")
    try:
        out = kit_auto.automatisation(42, {"action": "ajouter", "quand": "chaque jour à 23h", "quoi": "tele off"})
        assert out["resultat"] == "regle enregistree" and automate.rules()[0]["steps"] == ["tele off"]
        assert "erreur" in kit_auto.automatisation(42, {"action": "ajouter", "quand": "un jour", "quoi": "tele off"})
        assert kit_auto.automatisation(42, {"action": "danser"})["erreur"]
    finally:
        guard.end_turn(token)
    assert "tele off" in json.dumps(kit_auto.automatisation(42, {"action": "lister"}))
    token = guard.begin_turn(42, "mets le mode film")
    try:
        kit_auto.scene(42, {"action": "lancer", "nom": "film"})
        assert ("tele", "on") in world.calls
    finally:
        guard.end_turn(token)
    assert "dodo" in kit_auto.scene(42, {"action": "lister"})["scenes"]
    assert "coupé" in kit_auto.silence_nuit(42, {})["resultat"]                   # looking is free
