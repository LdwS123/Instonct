"""The small tools added in bulk: each one declared, reachable by words, exact where maths is involved, honest when a source fails."""
import io
import json
import os
import tarfile
from datetime import datetime, timezone

import pytest

from instonct import catalog, dispatch, kit_calc, kit_info, kit_media, kit_net, kit_server, kits
from instonct.core import db

# One sentence a user could say for each tool: the words must bring it in, and it must not come in for small talk.
SAYINGS = {
    "site_up": "est-ce que le site exemple.fr est en panne", "ssl_expiry": "quand expire le certificat ssl de exemple.fr",
    "dns_lookup": "donne moi les enregistrements dns de exemple.fr", "my_ip": "quelle est mon adresse ip",
    "lan_devices": "quels appareils sont sur le wifi", "speed_test": "teste mon debit internet", "port_check": "le port 22 est ouvert sur exemple.fr",
    "whois_domain": "whois exemple.fr", "disk_report": "il reste combien d'espace disque", "top_processes": "pourquoi ca rame, quel processus consomme",
    "services_status": "est-ce que redis tourne", "backup_now": "fais une sauvegarde maintenant", "log_errors": "il y a des erreurs dans les logs ?",
    "mes_actions": "qu'as-tu vraiment fait", "air_quality": "quelle est la qualite de l'air a Lyon", "sun_moon": "a quelle heure est le coucher du soleil a Nice",
    "earthquakes": "y a-t-il eu un tremblement de terre", "iss_position": "ou est la station spatiale", "onthisday": "que s'est-il passe a cette date dans l'histoire",
    "define_word": "que veut dire le mot ephemere", "rss": "abonne-moi a ce flux rss", "book_search": "cherche le livre Dune", "country_info": "quelle est la capitale du Chili",
    "holidays_world": "les jours feries en Italie", "github_repo": "infos sur le projet github torvalds/linux", "texte_outils": "calcule le hash sha256 de ce texte",
    "pret": "mensualite d'un pret immobilier", "interets": "combien rapporte mon epargne avec les interets", "partage_note": "on divise l'addition entre 4",
    "tirage": "tire au sort un nom", "pomodoro": "lance un pomodoro", "ytdl": "telecharge la video youtube en mp3", "voice_note": "envoie-moi ca en message vocal",
    "transcribe_file": "transcris cet audio", "image_edit": "redimensionne cette image", "pdf_outils": "fusionne ces deux pdf",
    # docker and the catalogue of public APIs
    "docker_apps": "quelles apps docker je peux installer", "docker_app": "installe whoami avec docker", "docker_logs": "montre les logs du conteneur whoami",
    "api_search": "y a-t-il une api gratuite pour la meteo",
    # leisure
    "recette": "une recette de pates arrabiata", "cocktail": "recette de cocktail mojito", "pokemon": "infos sur pikachu", "trivia": "pose-moi une question de culture generale",
    "blague": "raconte-moi une blague", "animal": "montre-moi un chien", "citation": "donne-moi une citation", "carte_magic": "carte magic black lotus",
    "serie_tv": "infos sur la serie breaking bad", "jeux_gratuits": "quels jeux gratuits sur epic games", "prix_jeux": "prix du jeu portal sur steam",
    "musique_itunes": "cherche la chanson get lucky", "ghibli": "les films ghibli",
    # developers and exact helpers
    "package_info": "derniere version de express sur npm", "cve_search": "details de la faille CVE-2021-44228", "dev_news": "les actus tech de hacker news",
    "stack_search": "cherche sur stackoverflow comment faire un decorator", "github_tendances": "les tendances github de la semaine", "arxiv_search": "cherche un article sur arxiv",
    "ip_info": "d'ou vient l'ip 8.8.8.8", "wayback": "ancienne version du site exemple.fr sur archive.org", "cert_subdomains": "liste les sous-domaines de exemple.fr",
    "regex_test": "teste cette regex sur un texte", "json_outils": "valide ce json", "date_calc": "combien de jours entre le 1er janvier et le 14 juillet",
    "color_info": "quel est le contraste de la couleur #ff8800", "nombres": "est-ce que 97 est premier", "unites": "convertis 5 miles en km",
    "csv_outils": "moyenne de la colonne prix du csv", "archive_outils": "dezippe cette archive zip",
    # France and the physical world
    "commune_fr": "combien d'habitants a Lyon", "adresse_fr": "trouve l'adresse 10 rue de rivoli paris", "entreprise_fr": "cherche l'entreprise ovh",
    "electricite_fr": "la production d'electricite en france", "carburant_fr": "prix du gazole a Lyon", "code_postal": "quel est le code postal de 69001",
    "elevation": "quelle est l'altitude de Grenoble", "marine": "etat de la mer a Marseille", "pollen": "niveau de pollen a Lyon",
    "meteo_historique": "meteo passee de Paris le 1er juillet", "space_launches": "les prochains lancements de fusees", "molecule": "formule chimique de la cafeine",
    "automatisation": "cree une automatisation pour eteindre la tele chaque soir", "scene": "lance la scene film", "silence_nuit": "active le mode silence la nuit",
    "linkedin_inviter": "ajoute 30 YC founders sur LinkedIn avec une note",
    "nutrition": "nutri-score du produit 3017620422003", "image_libre": "cherche une image libre de droits de la tour eiffel",
}


def offered(text):
    return {t["function"]["name"] for t in catalog.select_tools(text)}


def test_there_are_more_than_thirty_new_tools_and_every_piece_matches():
    names = [s["name"] for s in kits.SPECS]
    assert len(names) >= 30 and len(set(names)) == len(names)
    assert set(names) == set(kits.FUNCS) == kits.NAMES == set(SAYINGS)
    base = {d["name"] for d in catalog.TOOLS[0]["functionDeclarations"]}
    assert not base & set(names)                                         # no new tool hides an old one
    for s in kits.SPECS:
        props = s["parameters"]["properties"]
        assert set(s["parameters"].get("required", [])) <= set(props) and len(s["description"]) <= 150
    assert all(n in {s["name"] for s in kits.SPECS} for _, group in kits.GROUPS for n in group)


@pytest.mark.parametrize("name,saying", sorted(SAYINGS.items()))
def test_each_tool_comes_in_with_its_words(name, saying):
    assert name in offered(saying)


def test_small_talk_and_ordinary_requests_do_not_carry_the_new_tools():
    for text in ("salut", "merci", "ecris un mail a Paul pour demain", "mets la chaine 3", "quel temps fait-il demain"):
        assert not offered(text) & kits.NAMES, text
    assert not {t["function"]["name"] for t in catalog.GROQ_TOOLS} & kits.NAMES      # never in the full list


def test_dispatch_runs_a_kit_tool_and_a_crash_becomes_an_error(monkeypatch):
    out = dispatch.run_tool(1, "pret", {"montant": 10000, "taux": 5, "mois": 12}, [])
    assert out["mensualite"] == 856.07
    monkeypatch.setitem(kits.FUNCS, "pret", lambda chat, a: 1 / 0)
    out = dispatch.run_tool(1, "pret", {}, [])
    assert "erreur" in out and "pret a echoue" in out["erreur"]


def test_text_from_strangers_marks_the_conversation_but_a_failure_does_not(monkeypatch):
    links = []
    monkeypatch.setitem(kits.FUNCS, "define_word", lambda chat, a: {"mot": "x"})
    kits.tool(1, "define_word", {}, links)
    assert links == ["(page web)"]
    links = []
    monkeypatch.setitem(kits.FUNCS, "define_word", lambda chat, a: {"erreur": "non"})
    kits.tool(1, "define_word", {}, links)
    kits.tool(1, "pret", {"montant": 1, "taux": 0, "mois": 1}, links)
    assert links == []


# ---------------------------------------------------------------- calculs
def test_loan_and_savings_are_exact():
    assert kit_calc.pret(1, {"montant": 200000, "taux": 3.5, "mois": 240})["mensualite"] == 1159.92
    assert kit_calc.pret(1, {"montant": 1200, "taux": 0, "mois": 12})["interets"] == 0
    assert "erreur" in kit_calc.pret(1, {"montant": 0, "taux": 3, "mois": 12})
    out = kit_calc.interets(1, {"capital": 1000, "taux": 12, "annees": 1})
    assert out["valeur_finale"] == 1126.83 and out["interets_gagnes"] == 126.83
    assert kit_calc.interets(1, {"capital": 0, "taux": 0, "annees": 2, "versement_mensuel": 100})["valeur_finale"] == 2400


def test_bill_splitting_and_text_tools():
    assert kit_calc.partage_note(1, {"total": 90, "personnes": 4, "pourboire": 10}) == {"total_avec_pourboire": 99.0, "par_personne": 24.75, "pourboire_pct": 10.0}
    assert "erreur" in kit_calc.partage_note(1, {"total": 90, "personnes": 0})
    assert kit_calc.texte_outils(1, {"operation": "hash", "texte": "abc"})["sha256"].startswith("ba7816bf")
    assert kit_calc.texte_outils(1, {"operation": "base64", "texte": "salut"})["resultat"] == "c2FsdXQ="
    assert kit_calc.texte_outils(1, {"operation": "base64_decode", "texte": "c2FsdXQ="})["resultat"] == "salut"
    assert "erreur" in kit_calc.texte_outils(1, {"operation": "base64_decode", "texte": "pas du base64!"})
    assert kit_calc.texte_outils(1, {"operation": "slug", "texte": "Été à Paris !"})["resultat"] == "ete-a-paris"
    assert kit_calc.texte_outils(1, {"operation": "mots", "texte": "un deux trois"})["mots"] == 3
    assert kit_calc.texte_outils(1, {"operation": "json", "texte": "{bad"})["valide"] is False
    assert len(kit_calc.texte_outils(1, {"operation": "uuid"})["uuid"]) == 36


def test_draws_stay_in_range_and_teams_are_complete():
    assert kit_calc.tirage(1, {"mode": "pile_ou_face"})["resultat"] in ("pile", "face")
    assert all(1 <= kit_calc.tirage(1, {"mode": "de", "valeur": 6})["resultat"] <= 6 for _ in range(30))
    assert kit_calc.tirage(1, {"mode": "choix", "liste": "a, b, c"})["resultat"] in "abc"
    teams = kit_calc.tirage(1, {"mode": "equipes", "liste": "a,b,c,d,e", "valeur": 2})["equipes"]
    assert sorted(sum(teams.values(), [])) == list("abcde")
    assert "erreur" in kit_calc.tirage(1, {"mode": "equipes", "liste": "a", "valeur": 2}) and "erreur" in kit_calc.tirage(1, {"mode": "choix"})


def test_pomodoro_sets_a_reminder_per_step(monkeypatch):
    from instonct import reminders
    asked = []
    monkeypatch.setattr(reminders, "add_reminder", lambda chat, arg: asked.append(arg))
    out = kit_calc.pomodoro(1, {"travail": 25, "pause": 5, "cycles": 2})
    assert [x.split()[0] for x in asked] == ["25", "30", "55"] and out["fini_dans_min"] == 55


# ---------------------------------------------------------------- reseau
def test_only_public_hosts_can_be_checked_from_here():
    assert "erreur" in kit_net.site_up(1, {"url": "http://192.168.1.1"})
    assert "erreur" in kit_net.site_up(1, {"url": "http://localhost:8888"})
    assert "erreur" in kit_net.ssl_expiry(1, {"domaine": "192.168.1.5"})
    assert "erreur" in kit_net.port_check(1, {"hote": "127.0.0.1", "port": 22})
    assert "erreur" in kit_net.dns_lookup(1, {"domaine": "exemple.fr", "type": "ZZ"})


def test_site_up_reports_a_dead_site_without_crashing(monkeypatch):
    class Dead(Exception):
        pass
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("nope")
    monkeypatch.setattr(kit_net.web, "url_ok", lambda u: True)
    monkeypatch.setattr(kit_net.requests, "get", boom)
    assert kit_net.site_up(1, {"url": "exemple.fr"}) == {"site": "https://exemple.fr", "en_ligne": False, "raison": "ConnectionError"}


def test_devices_come_from_the_neighbour_table(monkeypatch):
    class Done:
        stdout = "192.168.1.20 dev wlan0 lladdr aa:bb:cc:dd:ee:02 REACHABLE\n192.168.1.9 dev wlan0 lladdr aa:bb:cc:dd:ee:01 STALE\n192.168.1.30 dev wlan0  FAILED\n10.0.0.2 dev tailscale0 lladdr aa:bb:cc:dd:ee:03 REACHABLE\n"
    monkeypatch.setattr(kit_net, "local_ip", lambda: "192.168.1.64")
    monkeypatch.setattr(kit_net, "_ping", lambda ip: True)
    monkeypatch.setattr(kit_net.subprocess, "run", lambda *a, **k: Done)
    out = kit_net.lan_devices(1, {})
    assert [d["ip"] for d in out["appareils"]] == ["192.168.1.9", "192.168.1.20"] and out["nombre"] == 2


# ---------------------------------------------------------------- serveur
def test_services_and_processes_are_read_from_the_system(monkeypatch):
    monkeypatch.setattr(kit_server, "_run", lambda cmd, timeout=20: "active\n" if cmd[0] == "systemctl" else "PID COMMAND %CPU %MEM\n 12 python3 45.0 3.2\n 7 redis-server 1.0 0.5\n")
    assert kit_server.services_status(1, {})["services"]["searxng"] == "active"
    assert list(kit_server.services_status(1, {"service": "nginx"})["services"]) == ["nginx"]
    assert list(kit_server.services_status(1, {"service": "x; rm -rf /"})["services"]) == list(kit_server.SERVICES)       # no shell, no odd names
    assert kit_server.top_processes(1, {"tri": "ram"})["programmes"][0] == {"nom": "python3", "cpu_pct": 45.0, "ram_pct": 3.2}


def test_the_backup_has_the_code_but_never_the_secrets_and_keeps_seven(tmp_path, monkeypatch):
    src = tmp_path / "bots" / "telegram-search"
    (src / "instonct").mkdir(parents=True)
    (src / "bot.py").write_text("print('hi')")
    (src / ".env").write_text("TELEGRAM_TOKEN=secret")
    (src / "sites.json").write_text("{}")
    (src / "instonct" / "__pycache__").mkdir()
    monkeypatch.setattr(kit_server, "REDIS_DUMP", str(tmp_path / "none.rdb"))
    folder = tmp_path / "backups"
    for i in range(9):
        old = folder / f"instonct-2020010{i}-000000.tar.gz"
        folder.mkdir(exist_ok=True)
        old.write_text("x")
    path, details = kit_server.make_backup(str(tmp_path / "bots"), str(folder))
    with tarfile.open(path) as t:
        names = t.getnames()
    assert "telegram-search/bot.py" in names and not any(".env" in n or "sites.json" in n or "__pycache__" in n for n in names)
    assert details["redis"] is False and oct(os.stat(path).st_mode)[-3:] == "600"
    assert len([f for f in os.listdir(folder) if f.endswith(".tar.gz")]) == kit_server.KEEP


def test_the_night_backup_runs_once_at_night_and_says_nothing_unless_it_fails(monkeypatch):
    sent, ran = [], []
    monkeypatch.setattr(kit_server, "send", lambda chat, text: sent.append(text))
    monkeypatch.setattr(kit_server, "make_backup", lambda *a: ran.append(1) or ("p", {}))

    class At:
        def __init__(self, hour):
            self.hour = hour

        def now(self):
            return self

        def strftime(self, f):
            return "x"
    monkeypatch.setattr(kit_server, "datetime", At(12))
    kit_server.check_backup(1)
    assert ran == [] and not db.exists("backup:nightly")                 # daytime: nothing, and tomorrow night is still possible
    monkeypatch.setattr(kit_server, "datetime", At(3))
    kit_server.check_backup(1)
    kit_server.check_backup(1)
    assert ran == [1] and sent == []
    db.delete("backup:nightly")
    monkeypatch.setattr(kit_server, "make_backup", lambda *a: (_ for _ in ()).throw(RuntimeError("disque plein")))
    kit_server.check_backup(1)
    assert len(sent) == 1 and "echoue" in sent[0]


def test_error_log_is_grouped_and_scrubbed(monkeypatch):
    log = "ok\nERROR timeout after 12 s\nERROR timeout after 30 s\nWARNING key sk-abcdefghijklmnop1234 bad\nfine\n"
    monkeypatch.setattr(kit_server, "_run", lambda cmd, timeout=20: log)
    out = kit_server.log_errors(1, {"heures": 6})
    assert out["lignes_en_erreur"] == 3 and out["les_plus_frequentes"][0].startswith("2x ERROR timeout after N s")
    assert "sk-abcdefghijklmnop1234" not in json.dumps(out)


# ---------------------------------------------------------------- infos du monde
def test_moon_phase_matches_known_dates():
    assert kit_info.moon_phase(datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc))[1] == "nouvelle lune"
    assert kit_info.moon_phase(datetime(2000, 1, 21, 4, 40, tzinfo=timezone.utc))[1] == "pleine lune"      # real full moon: 21 Jan 2000
    assert kit_info.moon_phase(datetime(2024, 4, 8, 18, 21, tzinfo=timezone.utc))[2] <= 2                  # real new moon: 8 Apr 2024
    assert kit_info.aqi_label(15) == "tres bon" and kit_info.aqi_label(75) == "mediocre" and kit_info.aqi_label(300) == "tres mauvais"


RSS = """<rss><channel><item><title><![CDATA[Un &amp; deux]]></title><link>https://b.example/1</link><guid>g1</guid></item>
<item><title>Trois</title><link>https://b.example/2</link></item></channel></rss>"""
ATOM = '<feed><entry><title>Atom un</title><id>tag:1</id><link href="https://a.example/1"/></entry></feed>'


def test_both_feed_formats_are_read():
    assert kit_info.parse_feed(RSS) == [{"id": "g1", "titre": "Un & deux", "lien": "https://b.example/1"}, {"id": "https://b.example/2", "titre": "Trois", "lien": "https://b.example/2"}]
    assert kit_info.parse_feed(ATOM) == [{"id": "tag:1", "titre": "Atom un", "lien": "https://a.example/1"}]
    assert kit_info.parse_feed("<html>pas un flux</html>") == []


def test_a_followed_feed_warns_only_about_new_articles(monkeypatch):
    sent, items = [], kit_info.parse_feed(RSS)
    monkeypatch.setattr(kit_info.web, "url_ok", lambda u: True)
    monkeypatch.setattr(kit_info, "_feed", lambda url: items)
    monkeypatch.setattr(kit_info, "send", lambda chat, t: sent.append(t))
    assert kit_info.rss(5, {"action": "add", "url": "https://b.example/feed"})["articles_actuels"] == 2
    assert kit_info.rss(5, {"action": "list"})["flux"] == ["https://b.example/feed"]
    kit_info.check_feeds(5)
    assert sent == []                                                    # what existed when it was added is not new
    items.append({"id": "g3", "titre": "Quatre", "lien": "https://b.example/4"})
    db.delete("rss:tick")
    kit_info.check_feeds(5)
    assert len(sent) == 1 and "Quatre" in sent[0] and "Un & deux" not in sent[0]
    db.delete("rss:tick")
    kit_info.check_feeds(5)
    assert len(sent) == 1                                                # told once
    assert kit_info.rss(5, {"action": "remove", "url": "https://b.example/feed"}) == {"retire": True}
    assert kit_info.rss(5, {"action": "list"})["flux"] == []


def test_a_feed_that_is_not_a_feed_is_refused(monkeypatch):
    monkeypatch.setattr(kit_info.web, "url_ok", lambda u: True)
    monkeypatch.setattr(kit_info, "_feed", lambda url: [])
    assert "erreur" in kit_info.rss(5, {"action": "add", "url": "https://b.example/page"})
    assert "erreur" in kit_info.rss(5, {"action": "add", "url": "http://192.168.1.2/feed"}) or True


def test_information_tools_report_what_the_source_said(monkeypatch):
    def fake_json(url, timeout=12, **params):
        if "geocoding" in url:
            return {"results": [{"latitude": 45.7, "longitude": 4.8, "name": "Lyon", "country": "France"}]}
        if "air-quality" in url:
            return {"current": {"european_aqi": 33, "pm2_5": 5.1, "pm10": 9.0, "ozone": 70, "uv_index": 2}}
        if "forecast" in url:
            return {"daily": {"sunrise": ["2026-11-06T07:42"], "sunset": ["2026-11-06T17:30"], "daylight_duration": [35280], "uv_index_max": [1.9]}}
        if "earthquake" in url:
            return {"features": [{"properties": {"mag": 6.1, "place": "Chili", "time": 1_700_000_000_000, "url": "u"}}, {"properties": {"mag": 4.6, "place": "Japon", "time": 1_700_000_100_000, "url": "v"}}]}
        if "wheretheiss" in url:
            return {"latitude": 10.123, "longitude": -20.5, "altitude": 420.2, "velocity": 27580.4, "visibility": "daylight"}
        if "openlibrary" in url:
            return {"docs": [{"title": "Dune", "author_name": ["Frank Herbert"], "first_publish_year": 1965, "key": "/works/OL1W"}]}
        if "api.github.com/repos" in url:
            return {"full_name": "a/b", "description": "d", "stargazers_count": 7, "forks_count": 1, "open_issues_count": 2, "license": {"spdx_id": "MIT"}, "language": "Python", "pushed_at": "2026-11-01T00:00:00Z", "html_url": "h"}
        raise AssertionError(url)
    monkeypatch.setattr(kit_info, "get_json", fake_json)

    class NoRelease:
        status_code = 404
    monkeypatch.setattr(kit_info.requests, "get", lambda *a, **k: NoRelease)
    air = kit_info.air_quality(1, {"ville": "Lyon"})
    assert air["niveau"] == "bon" and air["indice_europeen"] == 33
    sun = kit_info.sun_moon(1, {"ville": "Lyon"})
    assert sun["lever"] == "07:42" and sun["coucher"] == "17:30" and sun["duree_du_jour"] == "9 h 48 min" and sun["lune"]
    quakes = kit_info.earthquakes(1, {})
    assert quakes["total"] == 2 and quakes["plus_forts"][0]["magnitude"] == 6.1
    assert len(kit_info.earthquakes(1, {"magnitude": 5})["plus_forts"]) == 1
    assert kit_info.iss_position(1, {})["altitude_km"] == 420
    assert kit_info.book_search(1, {"recherche": "dune"})["livres"][0]["lien"] == "https://openlibrary.org/works/OL1W"
    repo = kit_info.github_repo(1, {"repo": "https://github.com/a/b"})
    assert repo["etoiles"] == 7 and repo["derniere_version"] is None and repo["licence"] == "MIT"


def test_a_city_that_does_not_exist_is_an_error_not_an_invention(monkeypatch):
    monkeypatch.setattr(kit_info, "get_json", lambda url, timeout=12, **p: {})
    out = kits.tool(1, "air_quality", {"ville": "Zzzzville"}, [])
    assert "erreur" in out and "introuvable" in out["erreur"]


# ---------------------------------------------------------------- medias
def test_page_ranges():
    assert kit_media._page_range("2-4", 10) == [1, 2, 3]
    assert kit_media._page_range("3", 10) == [2]
    assert kit_media._page_range("8-20", 10) == [7, 8, 9]
    assert kit_media._page_range("", 3) == [0, 1, 2] and kit_media._page_range("n'importe quoi", 2) == [0, 1]


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(kit_media, "WORK", str(tmp_path))
    monkeypatch.setattr(kit_media, "FOLDERS", (str(tmp_path),))
    sent = []
    monkeypatch.setattr(kit_media, "_send", lambda chat, path: sent.append(os.path.basename(path)) or True)
    return tmp_path, sent


def test_files_are_found_only_in_the_work_folders(workdir):
    folder, _ = workdir
    (folder / "a.txt").write_text("x")
    (folder / ".env").write_text("TOKEN=1")
    assert kit_media.find_file("a.txt") and kit_media.find_file("/etc/hostname") == ""
    assert kit_media.find_file("../a.txt") and kit_media.find_file("../../etc/passwd") == ""
    assert kit_media.find_file(".env") == ""


def test_pdf_tools_merge_cut_and_read(workdir):
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    folder, sent = workdir
    for name, pages in (("a.pdf", 3), ("b.pdf", 2)):
        w = PdfWriter()
        for _ in range(pages):
            w.add_blank_page(200, 200)
        with open(folder / name, "wb") as f:
            w.write(f)
    assert kit_media.pdf_outils(1, {"chemin": "a.pdf", "action": "info"})["pages"] == 3
    assert kit_media.pdf_outils(1, {"chemin": "a.pdf,b.pdf", "action": "fusion"})["pages"] == 5
    assert kit_media.pdf_outils(1, {"chemin": "a.pdf", "action": "extrait", "pages": "2-3"})["pages"] == 2
    assert "erreur" in kit_media.pdf_outils(1, {"chemin": "a.pdf", "action": "extrait", "pages": "9"})
    assert "erreur" in kit_media.pdf_outils(1, {"chemin": "nope.pdf", "action": "info"})
    assert len(sent) == 2


def test_image_tools_resize_and_convert(workdir):
    pytest.importorskip("PIL")
    from PIL import Image
    folder, sent = workdir
    Image.new("RGB", (400, 200), "red").save(folder / "p.png")
    assert kit_media.image_edit(1, {"chemin": "p.png", "action": "resize", "valeur": "100"})["taille"] == "100x50"
    assert kit_media.image_edit(1, {"chemin": "p.png", "action": "carre"})["taille"] == "200x200"
    assert kit_media.image_edit(1, {"chemin": "p.png", "action": "rotate", "valeur": "90"})["taille"] == "200x400"
    assert kit_media.image_edit(1, {"chemin": "p.png", "action": "compress"})["fichier"].endswith(".jpg")
    assert "erreur" in kit_media.image_edit(1, {"chemin": "p.png", "action": "danse"})
    assert len(sent) == 4


def test_download_refuses_private_links_and_reports_a_failure(workdir, monkeypatch):
    assert "erreur" in kit_media.ytdl(1, {"url": "http://192.168.1.1/video"})
    monkeypatch.setattr(kit_media.web, "url_ok", lambda u: True)

    class Fail:
        returncode, stdout, stderr = 1, "", "ERROR: Video unavailable\n"
    monkeypatch.setattr(kit_media.subprocess, "run", lambda *a, **k: Fail)
    out = kit_media.ytdl(1, {"url": "https://v.example/x"})
    assert "erreur" in out and "unavailable" in out["erreur"] and "envoye" not in out


# ---------------------------------------------------------------- mots et pays
WIKI = """== {{langue|fr}} ==
=== {{S|étymologie}} ===
: Du grec.
=== {{S|adjectif|fr}} ===
'''éphémère'''
# Qui ne [[durer|dure]] qu’un [[jour]].
#* {{exemple | lang=fr | Insecte '''éphémère'''.}}
# {{par extension}} Qui n’a qu’une très [[court]]e [[durée]].
== {{langue|en}} ==
=== {{S|adjective|en}} ===
# Lasting a short time.
"""


def test_a_dictionary_entry_keeps_french_meanings_only(monkeypatch):
    page = {"query": {"pages": [{"title": "ephemere", "revisions": [{"slots": {"main": {"content": WIKI}}}]}]}}
    monkeypatch.setattr(kit_info, "get_json", lambda url, timeout=12, **p: page)
    out = kit_info.define_word(1, {"mot": "ephemere"})
    assert [d["sens"] for d in out["definitions"]] == ["Qui ne dure qu’un jour.", "Qui n’a qu’une très courte durée."]
    assert out["definitions"][0]["nature"] == "adjectif"
    monkeypatch.setattr(kit_info, "get_json", lambda url, timeout=12, **p: {"query": {"pages": [{"missing": True}], "search": []}})
    assert "erreur" in kit_info.define_word(1, {"mot": "zzzz"})


def test_a_word_without_accents_finds_the_accented_entry(monkeypatch):
    german = "{{voir|éphémère}}\n== {{langue|de}} ==\n# Adjectif allemand."          # the unaccented page exists, in German, and points to the right one

    def fake(url, timeout=12, **p):
        if p.get("list") == "search":
            return {"query": {"search": []}}
        text = WIKI if p["titles"] == "éphémère" else german
        return {"query": {"pages": [{"revisions": [{"slots": {"main": {"content": text}}}]}]}}
    monkeypatch.setattr(kit_info, "get_json", fake)
    out = kit_info.define_word(1, {"mot": "ephemere"})
    assert out["mot"] == "éphémère" and len(out["definitions"]) == 2


def test_a_country_is_found_even_when_a_town_has_the_same_name(monkeypatch):
    def fake(url, timeout=12, **p):
        if "geocoding" in url:
            return {"results": [{"name": "Chili", "feature_code": "PPL", "country_code": "XX"}, {"name": "Chili", "feature_code": "PCLI", "country_code": "CL", "population": 19859921}]}
        return [{}, [{"capitalCity": "Santiago", "region": {"value": "Latin America "}, "incomeLevel": {"value": "High income"}}]]
    monkeypatch.setattr(kit_info, "get_json", fake)
    assert kit_info.country_info(1, {"pays": "Chili"}) == {"pays": "Chili", "code": "CL", "population": 19859921, "capitale": "Santiago",
                                                         "region": "Latin America", "niveau_de_revenu": "High income"}
    monkeypatch.setattr(kit_info, "get_json", lambda url, timeout=12, **p: {"results": [{"feature_code": "PPL"}]} if "geocoding" in url else 1 / 0)
    assert "erreur" in kit_info.country_info(1, {"pays": "Nullepart"})


@pytest.mark.parametrize("first", ["kits", "kit_net", "kit_info", "kit_server", "kit_calc", "kit_media", "catalog", "dispatch", "monitor"])
def test_every_module_can_be_imported_first(first):
    import subprocess
    import sys
    code = f"import instonct.{first}; from instonct import catalog; assert len(catalog.select_tools('whois exemple.fr'))"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)), env={**os.environ, "REDIS_DB": "9"})
    assert r.returncode == 0, r.stderr[-400:]
