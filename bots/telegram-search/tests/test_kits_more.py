"""The second wave of tools: docker apps, the API catalogue, exact helpers (numbers, units, dates...), France data, leisure.

Nothing here touches the real Docker, the real network or the TV: every outside call is replaced by a fake.
"""
import io
import json
import tarfile
import zipfile
from datetime import date

import pytest

from instonct import guard, kit_apis, kit_dev, kit_docker, kit_fr, kit_fun, kit_media, kits
from instonct.core import db


# ---------------------------------------------------------------- docker
class FakeDocker:
    """Stands in for `sudo docker`: remembers every call and answers from a table of containers."""

    def __init__(self):
        self.calls, self.rows, self.fail, self.crash = [], {}, set(), False

    def __call__(self, *args, timeout=30):
        self.calls.append(args)
        if args[0] in self.fail:
            return 1, "boom"
        if args[0] == "ps":
            return 0, "\n".join(f"{n}\t{r['state']}\t{r.get('image', 'img')}\t{r.get('ports', '')}" for n, r in self.rows.items())
        if args[0] == "inspect":
            name = args[-1]
            running = self.rows.get(name, {}).get("state") == "running" and not self.crash
            return 0, ("true" if running else "false") if "State.Running" in args[2] else ("running" if running else "exited")
        if args[0] == "run":
            name = args[args.index("--name") + 1]
            self.rows[name] = {"state": "running", "ports": args[args.index("-p") + 1]}
        if args[0] in ("start", "restart"):
            self.rows[args[-1]]["state"] = "running"
        if args[0] == "stop":
            self.rows[args[-1]]["state"] = "exited"
        if args[0] == "rm":
            self.rows.pop(args[-1], None)
        return 0, "ok"

    def ran(self, verb):
        return [c for c in self.calls if c[0] == verb]


@pytest.fixture
def box(monkeypatch):
    fake = FakeDocker()
    sent = []
    monkeypatch.setattr(kit_docker, "_docker", fake)
    monkeypatch.setattr(kit_docker, "_bind_ip", lambda: "100.64.0.1")
    monkeypatch.setattr(kit_docker, "_ram_free_mb", lambda: 3000)
    monkeypatch.setattr(kit_docker.time, "sleep", lambda s: None)
    monkeypatch.setattr(kit_docker, "_background", lambda fn, *a: fn(*a))          # the "thread" runs right here
    monkeypatch.setattr(kit_docker, "send", lambda chat, msg, *a, **k: sent.append(msg))
    fake.sent = sent
    return fake


def ask(question, taint=False):
    guard.begin_turn(7, question, taint)


def test_install_needs_the_user_to_ask_in_this_message(box):
    ask("salut")
    out = kit_docker.docker_app(7, {"app": "whoami", "action": "install"})
    assert "refuse" in out["erreur"] and not box.ran("run")
    ask("installe whoami", taint=True)                                   # words that came from a web page do not count
    assert "refuse" in kit_docker.docker_app(7, {"app": "whoami", "action": "install"})["erreur"] and not box.ran("run")


def test_install_runs_a_small_locked_container_on_the_tailscale_address(box):
    ask("installe whoami")
    out = kit_docker.docker_app(7, {"app": "whoami", "action": "install"})
    assert out["lancee"] and out["adresse_prevue"] == "http://100.64.0.1:9101"
    run = box.ran("run")[0]
    flat = " ".join(run)
    assert "-p 100.64.0.1:9101:80" in flat and "--memory 32m" in flat and "--security-opt no-new-privileges" in flat and "--pids-limit 512" in flat
    assert "--restart unless-stopped" in flat and "--name inst-whoami" in flat
    assert box.sent and box.sent[-1].startswith("whoami est pret") and not db.exists("docker:busy:whoami")


def test_a_crashing_app_is_removed_and_the_user_is_told(box):
    box.crash = True                                                      # the container "starts" but is not running 6 seconds later
    ask("installe whoami")
    kit_docker.docker_app(7, {"app": "whoami", "action": "install"})
    assert box.ran("rm") and "s'est arrete" in box.sent[-1]


def test_a_failed_download_is_reported_and_unlocks(box):
    box.fail = {"pull"}
    ask("installe it-tools")
    kit_docker.docker_app(7, {"app": "IT Tools", "action": "installer"})
    assert "pas pu telecharger" in box.sent[-1] and not box.ran("run") and not db.exists("docker:busy:it-tools")


def test_install_is_refused_when_it_would_hurt_the_mini(box, monkeypatch):
    ask("installe whoami")
    box.rows = {"inst-whoami": {"state": "exited"}}
    assert "deja installee" in kit_docker.docker_app(7, {"app": "whoami", "action": "install"})["erreur"]
    box.rows = {}
    monkeypatch.setattr(kit_docker, "_ram_free_mb", lambda: 100)
    assert "memoire" in kit_docker.docker_app(7, {"app": "whoami", "action": "install"})["erreur"]
    monkeypatch.setattr(kit_docker, "_ram_free_mb", lambda: 3000)
    box.rows = {"other": {"state": "running", "ports": "100.64.0.1:9101->80/tcp"}}
    assert "port 9101" in kit_docker.docker_app(7, {"app": "whoami", "action": "install"})["erreur"]
    box.rows = {f"inst-x{i}": {"state": "running"} for i in range(kit_docker.MAX_RUNNING)}
    assert "maximum" in kit_docker.docker_app(7, {"app": "whoami", "action": "install"})["erreur"]
    assert not box.ran("run")


def test_an_install_already_under_way_is_not_started_twice(box):
    ask("installe whoami")
    db.set("docker:busy:whoami", 1, ex=60)
    assert "deja en cours" in kit_docker.docker_app(7, {"app": "whoami", "action": "install"})["erreur"]


def test_the_apps_installed_before_the_bot_are_never_stopped_or_removed(box):
    box.rows = {"adguard": {"state": "running"}, "uptime-kuma": {"state": "running"}}
    for action, words in (("stop", "arrete adguard"), ("remove", "supprime adguard"), ("stop", "coupe uptime-kuma")):
        ask(words)
        out = kit_docker.docker_app(7, {"app": words.split()[-1], "action": action})
        assert "avant moi" in out["erreur"]
    assert not box.ran("stop") and not box.ran("rm")
    ask("montre les logs de adguard")
    assert kit_docker.docker_logs(7, {"app": "adguard"})["conteneur"] == "adguard"
    assert "inconnu" in kit_docker.docker_logs(7, {"app": "n-importe-quoi"})["erreur"]


def test_stop_start_and_remove_follow_the_user_words(box):
    box.rows = {"inst-memos": {"state": "running"}}
    ask("salut")
    assert "refuse" in kit_docker.docker_app(7, {"app": "memos", "action": "stop"})["erreur"]
    ask("arrete memos")
    assert kit_docker.docker_app(7, {"app": "memos", "action": "stop"})["etat"] == "exited"
    ask("relance memos")
    assert kit_docker.docker_app(7, {"app": "memos", "action": "start"})["etat"] == "running"
    ask("supprime memos")
    out = kit_docker.docker_app(7, {"app": "memos", "action": "remove", "avec_donnees": True})
    assert "refuse" in out["erreur"]                                      # erasing data must be said with the word "donnee"
    out = kit_docker.docker_app(7, {"app": "memos", "action": "remove"})
    assert out["supprimee"] and "gardees" in out["donnees"] and not box.ran("volume")
    box.rows = {"inst-memos": {"state": "running"}}
    ask("supprime memos et toutes ses donnees")
    out = kit_docker.docker_app(7, {"app": "memos", "action": "remove", "avec_donnees": True})
    assert out["donnees"] == "effacees" and box.ran("volume")


def test_unknown_things_get_a_clear_answer(box):
    ask("installe truc")
    assert "inconnue" in kit_docker.docker_app(7, {"app": "truc", "action": "install"})["erreur"]
    assert "action inconnue" in kit_docker.docker_app(7, {"app": "whoami", "action": "exec"})["erreur"]
    box.rows = {}
    ask("lance memos")
    assert "pas installee" in kit_docker.docker_app(7, {"app": "memos", "action": "start"})["erreur"]


def test_the_list_shows_state_and_what_was_there_before(box):
    box.rows = {"inst-whoami": {"state": "running"}, "navidrome": {"state": "running"}}
    out = kit_docker.docker_apps(7, {})
    assert len(out["applications"]) == len(kit_docker.APPS) == 35
    assert any(x.startswith("whoami") and "running" in x and "http://100.64.0.1:9101" in x for x in out["applications"])
    assert out["deja_la_avant_moi"] == ["navidrome (running)"] and out["mes_apps_en_marche"].startswith("1 sur")
    assert out["acces"] == "Tailscale seulement"
    assert all("notes" in x or "memo" in x.lower() for x in kit_docker.docker_apps(7, {"filtre": "memos"})["applications"])
    box.fail = {"ps"}
    with pytest.raises(RuntimeError):
        kit_docker.docker_apps(7, {})
    assert "erreur" in kits.tool(7, "docker_apps", {}, [])                # the kit wrapper turns the crash into an error


def test_app_names_are_matched_loosely():
    assert kit_docker._pick("IT Tools") == "it-tools" and kit_docker._pick("node red") == "node-red" and kit_docker._pick("inst-whoami") == "whoami"
    assert kit_docker._pick("n'importe quoi") is None


def test_the_catalogue_of_apps_is_sane():
    apps = kit_docker.APPS
    ports = [a["host"] for a in apps.values()]
    assert len(set(ports)) == len(ports) == 35 and ports == list(range(9101, 9136))
    assert not set(ports) & {3001, 53, 3000, 8081, 4533}                   # the services that were already there
    assert not set(apps) & set(kit_docker.FOREIGN)
    for name, app in apps.items():
        assert kit_docker._mb(app["mem"]) <= 1024 and app["image"] and app["desc"], name
    args = kit_docker._run_args("web-exports", kit_docker.APPS["web-exports"], "100.64.0.1") if "web-exports" in apps else []
    assert not args or args[args.index(kit_docker.APPS["web-exports"]["image"]) - 1].endswith(":ro")


# ---------------------------------------------------------------- catalogue d'API
README = "\n".join(["### Animals", "| API | Description | Auth | HTTPS | CORS |", "|---|---|---|---|---|"]
                   + [f"| [Cat{i}](https://cats.example/{i}) | Facts about cats number {i} | No | Yes | Yes |" for i in range(120)]
                   + ["### Weather", "| API | Description | Auth | HTTPS | CORS |", "|---|---|---|---|---|"]
                   + [f"| [Meteo{i}](https://meteo.example/{i}) | Forecast and rain for place {i} | `apiKey` | Yes | No |" for i in range(60)]
                   + ["| [OpenMeteo](https://open-meteo.com/) | Free weather forecast | No | Yes | Yes |"]
                   + [f"| [Wind{i}](https://wind.example/{i}) | Wind speed {i} | No | Yes | Yes |" for i in range(40)])


def test_the_catalogue_is_parsed_and_cached(monkeypatch):
    rows = kit_apis.parse(README)
    assert len(rows) == 221 and rows[0] == {"nom": "Cat0", "url": "https://cats.example/0", "description": "Facts about cats number 0", "cle": "", "theme": "Animals"}
    assert next(r for r in rows if r["nom"] == "Meteo1")["cle"] == "apiKey"
    calls = []

    class Reply:
        text = README

        def raise_for_status(self):
            pass

    monkeypatch.setattr(kit_apis.requests, "get", lambda *a, **k: calls.append(a) or Reply())
    db.delete(kit_apis.CACHE)
    assert len(kit_apis.catalogue()) == 221 and len(kit_apis.catalogue()) == 221 and len(calls) == 1      # second time comes from Redis
    assert db.ttl(kit_apis.CACHE) > 6 * 86400


def test_a_page_that_changed_shape_is_not_cached(monkeypatch):
    class Reply:
        text = "# plus de tableau"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(kit_apis.requests, "get", lambda *a, **k: Reply())
    db.delete(kit_apis.CACHE)
    with pytest.raises(RuntimeError):
        kit_apis.catalogue()
    assert not db.exists(kit_apis.CACHE)


def test_api_search_filters_ranks_and_lists_themes():
    db.set(kit_apis.CACHE, json.dumps(kit_apis.parse(README)), ex=600)
    themes = kit_apis.api_search(7, {})
    assert themes["total"] == 221 and "Weather (101)" in themes["themes"]
    out = kit_apis.api_search(7, {"recherche": "weather forecast"})
    assert out["resultats"][0]["nom"] == "OpenMeteo" and out["resultats"][0]["cle"] == "aucune"
    free = kit_apis.api_search(7, {"recherche": "forecast", "sans_cle": True})
    assert all(r["cle"] == "aucune" for r in free["resultats"])
    assert len(kit_apis.api_search(7, {"theme": "animals", "nombre": 3})["resultats"]) == 3
    assert "aucune API" in kit_apis.api_search(7, {"recherche": "zzzzqqq"})["erreur"]


# ---------------------------------------------------------------- calculs exacts
def test_numbers_are_exact():
    n = lambda **a: kit_dev.nombres(7, a)                                 # noqa: E731
    assert n(operation="premier", nombre=97) == {"premier": True} and n(operation="premier", nombre=91) == {"premier": False}
    assert n(operation="facteurs", nombre=360)["ecriture"] == "2^3 x 3^2 x 5"
    assert n(operation="facteurs", nombre=1000000007 * 998244353)["facteurs"] == {"998244353": 1, "1000000007": 1}
    assert n(operation="romain", nombre=1994) == {"resultat": "MCMXCIV"} and n(operation="romain", nombre="MCMXCIV") == {"resultat": 1994}
    assert "erreur" in n(operation="romain", nombre="IIII") and "erreur" in n(operation="romain", nombre=4000)
    assert n(operation="base", nombre=255, base_depart=10, base_arrivee=16)["resultat"] == "ff"
    assert n(operation="pgcd", nombre=12, autre=18)["resultat"] == 6 and n(operation="ppcm", nombre=4, autre=6)["resultat"] == 12
    assert n(operation="factorielle", nombre=10)["resultat"] == "3628800" and n(operation="fibonacci", nombre=50)["resultat"] == "12586269025"
    assert n(operation="pourcentage", nombre=15, autre=200)["resultat"] == 30 and n(operation="evolution", nombre=100, autre=150)["evolution_pct"] == 50
    assert "erreur" in n(operation="factorielle", nombre=99999) and "erreur" in n(operation="inconnue", nombre=1)


def test_units_convert_exactly_and_refuse_nonsense():
    u = lambda v, de, vers: kit_dev.unites(7, {"valeur": v, "de": de, "vers": vers})      # noqa: E731
    assert u(5, "mi", "km")["resultat"] == 8.04672 and u(100, "°C", "°F")["resultat"] == 212 and u(0, "C", "K")["resultat"] == 273.15
    assert u(36, "km/h", "m/s")["resultat"] == 10 and u(2, "h", "min")["resultat"] == 120
    assert "on ne peut pas passer" in u(1, "kg", "km")["erreur"] and "erreur" in u(1, "zorglub", "km")
    assert kit_dev.CLASHES == [] and len(kit_dev.INDEX) > 250                   # no two units share a spelling


def test_dates_are_calculated_with_the_calendar(monkeypatch):
    d = lambda **a: kit_dev.date_calc(7, a)                               # noqa: E731
    assert d(operation="diff", date="2024-01-01", date2="2024-03-01")["jours"] == 60               # 2024 is a leap year
    assert d(operation="ajouter", date="2024-02-28", jours=2)["date"] == "2024-03-01"
    assert d(operation="semaine", date="2024-07-14")["jour"] == "dimanche"
    assert d(operation="jours_ouvres", date="2024-07-01", date2="2024-07-08")["jours_ouvres"] == 5

    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 6)

    monkeypatch.setattr(kit_dev, "date", Today)
    born = d(operation="age", date="2000-02-29")                           # a leap-day birthday must not crash or drift
    assert born["age"] == "26 an(s), 8 mois, 8 jour(s)" and born["prochain_anniversaire_dans_jours"] == 115
    assert "futur" in d(operation="age", date="2999-01-01")["erreur"] and "erreur" in d(operation="diff", date="pas une date", date2="2024-01-01")


def test_colors_and_contrast():
    c = lambda **a: kit_dev.color_info(7, a)                              # noqa: E731
    assert c(couleur="#ffffff", couleur2="#000000")["contraste_entre_les_deux"] == 21
    red = c(couleur="rouge")
    assert red["hex"] == "#ff0000" and red["hsl"] == "hsl(0, 100%, 50%)"
    assert c(couleur="#fff")["hex"] == "#ffffff" and "erreur" in c(couleur="zzz")


def test_a_regex_cannot_freeze_the_bot():
    r = lambda **a: kit_dev.regex_test(7, a)                              # noqa: E731
    out = r(motif=r"(\d+)-(\d+)", texte="12-34 et 5-6")
    assert out["correspondances"] == 2 and out["resultats"][0]["groupes"] == ["12", "34"]
    assert r(motif=r"\d+", texte="a1b22", remplacer="#")["remplace"] == "a#b#"
    assert "trop lent" in r(motif="(a+)+$", texte="a" * 40 + "b")["erreur"]          # catastrophic backtracking is cut after 3 seconds
    assert "invalide" in r(motif="(", texte="x")["erreur"]


def test_json_and_csv_helpers():
    j = lambda **a: kit_dev.json_outils(7, a)                             # noqa: E731
    assert j(operation="valider", json='{"a":1}')["valide"] is True and j(operation="valider", json="{bad")["valide"] is False
    assert j(operation="chemin", json='{"a":{"b":[1,{"c":9}]}}', chemin="a.b[1].c") == {"valeur": 9}
    assert j(operation="cles", json='{"a":1,"b":2}')["cles"] == ["a", "b"]
    out = kit_dev.csv_outils(7, {"operation": "resume", "texte": "nom;prix\na;1,5\nb;2\nc;3.5"})
    assert out["lignes"] == 3 and out["colonnes"]["prix"]["somme"] == 7 and out["colonnes"]["nom"]["type"] == "texte"
    assert kit_dev.csv_outils(7, {"operation": "colonne", "texte": "nom;prix\na;1\nb;2\nc;3", "colonne": "prix"})["moyenne"] == 2
    assert "erreur" in kit_dev.csv_outils(7, {"operation": "colonne", "texte": "a;b\n1;2", "colonne": "zzz"})


# ---------------------------------------------------------------- archives
@pytest.fixture
def work(tmp_path, monkeypatch):
    folder = tmp_path / "docs"
    folder.mkdir()
    monkeypatch.setattr(kit_dev, "FOLDERS", (str(folder),))
    monkeypatch.setattr(kit_dev, "WORK", str(folder))
    monkeypatch.setattr(kit_media, "FOLDERS", (str(folder),))
    monkeypatch.setattr(kit_media, "WORK", str(folder))
    return folder


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_a_normal_zip_is_listed_and_extracted(work):
    make_zip(work / "ok.zip", {"a.txt": "bonjour", "sous/b.txt": "salut"})
    assert kit_dev.archive_outils(7, {"fichier": "ok.zip", "action": "lister"})["elements"] == 2
    out = kit_dev.archive_outils(7, {"fichier": "ok.zip", "action": "extraire"})
    assert out["fichiers"] == 2 and (work / "extrait-ok" / "sous" / "b.txt").read_text() == "salut"


def test_a_zip_that_tries_to_escape_writes_nothing_outside(work, tmp_path):
    make_zip(work / "evil.zip", {"../evil.txt": "x"})
    out = kit_dev.archive_outils(7, {"fichier": "evil.zip", "action": "extraire"})
    assert "refuse" in out["erreur"] and not (tmp_path / "evil.txt").exists() and not (work / "evil.txt").exists()
    make_zip(work / "abs.zip", {"/tmp/abs-evil.txt": "x"})
    assert "refuse" in kit_dev.archive_outils(7, {"fichier": "abs.zip", "action": "extraire"})["erreur"]


def test_a_tar_with_a_link_is_refused(work):
    with tarfile.open(work / "link.tar", "w") as tf:
        info = tarfile.TarInfo("lien")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tf.addfile(info)
    assert "refuse" in kit_dev.archive_outils(7, {"fichier": "link.tar", "action": "extraire"})["erreur"]
    with tarfile.open(work / "ok.tar", "w") as tf:
        data = b"hello"
        info = tarfile.TarInfo("h.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    assert kit_dev.archive_outils(7, {"fichier": "ok.tar", "action": "extraire"})["fichiers"] == 1


def test_an_archive_bomb_is_stopped(work, monkeypatch):
    make_zip(work / "bomb.zip", {"big.bin": "0" * 100000})
    monkeypatch.setattr(kit_dev, "MAX_BYTES", 1000)
    assert "trop grosse" in kit_dev.archive_outils(7, {"fichier": "bomb.zip", "action": "extraire"})["erreur"]
    monkeypatch.setattr(kit_dev, "MAX_BYTES", 10**9)
    monkeypatch.setattr(kit_dev, "MAX_FILES", 1)
    make_zip(work / "many.zip", {"1": "a", "2": "b"})
    assert "trop de fichiers" in kit_dev.archive_outils(7, {"fichier": "many.zip", "action": "extraire"})["erreur"]


def test_a_folder_can_be_zipped_and_a_missing_file_is_reported(work):
    (work / "projet").mkdir()
    (work / "projet" / "n.txt").write_text("x")
    out = kit_dev.archive_outils(7, {"fichier": "projet", "action": "creer"})
    assert out["archive"].endswith("projet.zip") and zipfile.is_zipfile(out["archive"])
    assert "introuvable" in kit_dev.archive_outils(7, {"fichier": "rien.zip", "action": "lister"})["erreur"]
    assert "introuvable" in kit_dev.archive_outils(7, {"fichier": "rien", "action": "creer"})["erreur"]


# ---------------------------------------------------------------- outils web (reponses simulees)
def fake_json(monkeypatch, module, answers):
    seen = []

    def get(url, timeout=12, **params):
        seen.append((url, params))
        for key, value in answers.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError("unexpected call " + url)

    monkeypatch.setattr(module, "get_json", get)
    return seen


def test_the_bot_refuses_private_addresses_and_odd_names():
    assert "privee" in kit_dev.ip_info(7, {"ip": "192.168.1.1"})["erreur"] and "invalide" in kit_dev.ip_info(7, {"ip": "pas une ip"})["erreur"]
    assert "invalide" in kit_dev.package_info(7, {"nom": "../../etc", "gestionnaire": "npm"})["erreur"]
    assert "format" in kit_dev.cve_search(7, {"cve": "pas-un-cve"})["erreur"]


def test_cert_subdomains_say_so_when_the_service_is_overloaded(monkeypatch):
    class Reply:
        status_code, text = 200, "<html>busy</html>"

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(kit_dev.requests, "get", lambda *a, **k: Reply())
    assert "surcharge" in kit_dev.cert_subdomains(7, {"domaine": "exemple.fr"})["erreur"]


def test_commune_converts_hectares_to_square_kilometres(monkeypatch):
    seen = fake_json(monkeypatch, kit_fr, {"geo.api.gouv.fr": [{"nom": "Lyon", "code": "69123", "population": 522250, "surface": 4790, "codesPostaux": ["69001"],
                                                               "departement": {"nom": "Rhone", "code": "69"}, "region": {"nom": "Auvergne-Rhone-Alpes"}}]})
    out = kit_fr.commune_fr(7, {"nom": "Lyon"})["communes"][0]
    assert out["surface_km2"] == 47.9 and out["population"] == 522250 and seen[0][1]["boost"] == "population"
    assert "erreur" in kit_fr.commune_fr(7, {})


def test_fuel_query_cannot_be_injected_and_asks_for_the_right_column(monkeypatch):
    seen = fake_json(monkeypatch, kit_fr, {"economie.gouv": {"results": [{"gazole_prix": 1.79, "adresse": "1 rue X"}]}})
    out = kit_fr.carburant_fr(7, {"ville": 'lyon" or 1=1 --', "carburant": "diesel"})
    assert '"' not in seen[0][1]["where"].replace('ville="', "", 1).replace('" and', "", 1) and "gazole_prix is not null" in seen[0][1]["where"]
    assert seen[0][1]["order_by"] == "gazole_prix" and out["moins_chers"][0]["prix_eur_litre"] == 1.79
    assert "carburants" in kit_fr.carburant_fr(7, {"ville": "Lyon", "carburant": "plutonium"})["erreur"] and "ville" in kit_fr.carburant_fr(7, {})["erreur"]


def test_electricity_shares_add_up(monkeypatch):
    seen = fake_json(monkeypatch, kit_fr, {"odre": {"results": [{"date": "2026-11-06", "heure": "10:00", "consommation": 50000, "nucleaire": 36000, "eolien": 8000, "solaire": 2000,
                                                                    "gaz": 4000, "pompage": -1000, "taux_co2": 30}]}})
    out = kit_fr.electricite_fr(7, {})
    assert out["parts_pct"]["nucleaire"] == 72 and "pompage" not in out["parts_pct"] and out["co2_g_par_kwh"] == 30
    assert out["date_locale"] == "2026-11-06" and "v2.1" in seen[0][0] and "consommation is not null" in seen[0][1]["where"]    # latest MEASURED row, not a forecast


def test_address_company_and_nutrition(monkeypatch):
    fake_json(monkeypatch, kit_fr, {"api-adresse": {"features": [{"properties": {"label": "10 Rue de Rivoli 75004 Paris", "postcode": "75004", "city": "Paris", "score": 0.97},
                                                                  "geometry": {"coordinates": [2.36, 48.85]}}]},
                                    "recherche-entreprises": {"results": [{"nom_complet": "OVH", "siren": "424761419", "etat_administratif": "A", "siege": {"adresse": "2 rue Kellermann"},
                                                                          "dirigeants": [{"prenoms": "Octave", "nom": "Klaba"}]}]}})
    assert kit_fr.adresse_fr(7, {"adresse": "10 rue de rivoli"})["adresses"][0]["code_postal"] == "75004"
    firm = kit_fr.entreprise_fr(7, {"recherche": "ovh"})["entreprises"][0]
    assert firm["etat"] == "active" and firm["dirigeants"] == ["Octave Klaba"] and firm["fiche"].endswith("424761419")
    assert "8 a 14" in kit_fr.nutrition(7, {"code_barres": "12"})["erreur"]
    monkeypatch.setattr(kit_fr, "get_json_or_none", lambda *a, **k: None)
    assert "absent" in kit_fr.nutrition(7, {"code_barres": "3017620422003"})["erreur"]
    monkeypatch.setattr(kit_fr, "get_json_or_none", lambda *a, **k: {"status": 1, "product": {"product_name": "Pate <b>x</b>", "nutriscore_grade": "e", "nutriments": {"sugars_100g": 56}}})
    out = kit_fr.nutrition(7, {"code_barres": "3017620422003"})
    assert out["produit"] == "Pate x" and out["nutriscore"] == "E" and out["pour_100g"]["sucres_g"] == 56


def test_historical_weather_checks_its_dates_before_asking(monkeypatch):
    fake_json(monkeypatch, kit_fr, {})                                    # any network call would fail the test
    assert "31 jours" in kit_fr.meteo_historique(7, {"ville": "Paris", "debut": "2024-01-01", "fin": "2024-03-01"})["erreur"]
    assert "2 derniers jours" in kit_fr.meteo_historique(7, {"ville": "Paris", "debut": date.today().isoformat()})["erreur"]
    assert "erreur" in kit_fr.meteo_historique(7, {"ville": "Paris", "debut": "2024-05-10", "fin": "2024-05-01"})
    assert "erreur" in kit_fr.meteo_historique(7, {"ville": "Paris"})


def test_trivia_shuffles_but_always_keeps_the_answer(monkeypatch):
    fake_json(monkeypatch, kit_fun, {"opentdb": {"response_code": 0, "results": [{"category": "Art &amp; Co", "difficulty": "easy", "question": "2 &gt; 1 ?", "correct_answer": "Oui",
                                                                                   "incorrect_answers": ["Non", "Peut-etre", "Jamais"]}]}})
    q = kit_fun.trivia(7, {"niveau": "easy"})["questions"][0]
    assert sorted(q["choix"]) == ["Jamais", "Non", "Oui", "Peut-etre"] and q["bonne_reponse"] == "Oui" and q["question"] == "2 > 1 ?" and q["categorie"] == "Art & Co"
    fake_json(monkeypatch, kit_fun, {"opentdb": {"response_code": 5, "results": []}})
    assert "occupe" in kit_fun.trivia(7, {})["erreur"]


def test_text_from_the_web_marks_the_conversation(monkeypatch):
    links = []
    monkeypatch.setitem(kits.FUNCS, "blague", lambda chat, a: {"blague": "x"})
    kits.tool(7, "blague", {}, links)
    monkeypatch.setitem(kits.FUNCS, "nombres", lambda chat, a: {"resultat": 1})
    kits.tool(7, "nombres", {}, links)
    assert links == ["(page web)"]                                         # only the web tool is tainted, exact maths is not
    assert {"docker_logs", "api_search", "commune_fr", "recette", "cve_search", "csv_outils", "archive_outils"} <= kits.TAINT
    assert not {"nombres", "unites", "date_calc", "docker_app", "docker_apps"} & kits.TAINT


def test_all_tools_are_now_more_than_eighty():
    assert len(kits.FUNCS) == len(kits.SPECS) >= 84


class Reply:
    """A minimal requests reply."""

    def __init__(self, status=200, body=None):
        self.status_code, self.body = status, body

    def json(self):
        if self.body is None:
            raise ValueError("no json")
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            err = kit_dev.requests.HTTPError(str(self.status_code))
            err.response = self
            raise err


def test_wayback_sends_the_site_as_a_query_parameter(monkeypatch):
    seen = []
    monkeypatch.setattr(kit_dev.requests, "get", lambda url, **k: seen.append(k["params"]) or Reply(200, {"archived_snapshots": {"closest": {"timestamp": "20200102030405", "url": "http://web.archive.org/x", "status": "200"}}}))
    out = kit_dev.wayback(7, {"url": "exemple.fr", "date": "2020-01-02"})
    assert seen[0] == {"url": "exemple.fr", "timestamp": "20200102"} and out["date"] == "2020-01-02"
    monkeypatch.setattr(kit_dev.requests, "get", lambda url, **k: Reply(200, {"archived_snapshots": {}}))
    assert "aucune copie" in kit_dev.wayback(7, {"url": "exemple.fr"})["erreur"]


def test_github_rate_limit_gives_a_plain_message(monkeypatch):
    monkeypatch.setattr(kit_dev.requests, "get", lambda url, **k: Reply(403, {"message": "rate limit"}))
    assert "10 par minute" in kit_dev.github_tendances(7, {})["erreur"]
    monkeypatch.setattr(kit_dev.requests, "get", lambda url, **k: Reply(500, {}))
    with pytest.raises(kit_dev.requests.HTTPError):                  # other failures stay real errors (kits.tool reports them)
        kit_dev.github_tendances(7, {})


def test_joke_reads_the_400_body_and_falls_back(monkeypatch):
    calls = []

    def get(url, **k):
        calls.append((url.rsplit("/", 1)[1], k["params"]["lang"]))
        if len(calls) < 3:
            return Reply(400, {"error": True, "message": "No matching joke found"})      # French + Programming has nothing: HTTP 400 with a JSON body
        return Reply(200, {"error": False, "type": "single", "joke": "ha", "lang": "en"})

    monkeypatch.setattr(kit_fun.requests, "get", get)
    out = kit_fun.blague(7, {"theme": "programming", "langue": "fr"})
    assert out["blague"] == "ha" and calls == [("Programming", "fr"), ("Programming", "en"), ("Any", "fr")]
    monkeypatch.setattr(kit_fun.requests, "get", lambda url, **k: Reply(400, {"error": True}))
    assert "pas de blague" in kit_fun.blague(7, {})["erreur"]


def test_free_image_links_with_a_query_string_are_kept(monkeypatch):
    page = {"title": "File:Tour.jpg", "index": 1, "imageinfo": [{"url": "https://upload.wikimedia.org/a/Tour.jpg?utm_source=commons", "thumburl": "https://t/Tour.jpg?x=1", "descriptionurl": "https://c/File:Tour.jpg",
                                                                "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a>Ann</a>"}}}]}
    bad = {"title": "File:Doc.pdf", "index": 2, "imageinfo": [{"url": "https://u/Doc.pdf?x=1"}]}
    fake_json(monkeypatch, kit_fr, {"commons": {"query": {"pages": {"1": page, "2": bad}}}})
    out = kit_fr.image_libre(7, {"recherche": "tour"})["images"]
    assert len(out) == 1 and out[0]["licence"] == "CC BY-SA 4.0" and out[0]["auteur"] == "Ann"


def test_nutrition_grades_that_are_not_grades_become_a_question_mark():
    assert [kit_fr._grade(g) for g in ("a", "E", "unknown", "not-applicable", None, "")] == ["A", "E", "?", "?", "?", "?"]


# ---------------------------------------------------------------- free SEO tools
PAGE = b"""<html lang="fr"><head><title>Titre court</title><meta name="description" content="Une description"><meta property="og:title" content="x">
<link rel="canonical" href="https://exemple.fr/"><meta name="viewport" content="width=device-width"></head>
<body><h1>Bonjour</h1><h1>Deux</h1><h2>a</h2><img src="a.png"><img src="b.png" alt="ok"><a href="/x">in</a><a href="https://autre.com/y">out</a>
<script>var ignore = "beaucoup de mots dans un script qui ne comptent pas";</script><p>quelques mots lisibles ici</p></body></html>"""


class Page:
    """A fake response: 200, no redirect, body served in small chunks."""
    status_code, encoding, is_redirect = 200, "utf-8", False

    def __init__(self, data=PAGE, headers=None, code=200):
        self.data, self.headers, self.status_code = data, headers or {}, code

    def iter_content(self, size):
        for n in range(0, len(self.data), size):
            yield self.data[n:n + size]

    def close(self):
        pass


def test_seo_audit_reads_the_page_and_lists_the_problems(monkeypatch):
    from instonct import kit_seo
    seen = []
    monkeypatch.setattr("instonct.web.url_ok", lambda u: True)
    monkeypatch.setattr("instonct.web.requests.get", lambda url, **k: seen.append((url, k)) or (Page() if url.endswith("exemple.fr") else Page(b"", code=404)))
    out = kit_seo.seo_audit(1, {"url": "exemple.fr"})
    assert out["title"] == "Titre court" and out["description"] == "Une description" and out["h1"] == ["Bonjour", "Deux"]
    assert out["images"] == 2 and out["liens_internes"] == 1 and out["liens_externes"] == 1 and out["balises_og"] == 1
    assert out["mots"] < 40                                     # the script text is not counted
    problems = " ".join(out["problemes"])
    assert "2 h1" in problems and "1 image(s) sur 2" in problems and "robots.txt : code 404" in problems and "JSON-LD" in problems and "title de 11" in problems
    assert all(k["allow_redirects"] is False for _, k in seen)    # every hop is checked by hand
    assert seen[0][1]["headers"]["Accept-Encoding"] == "identity"


def test_seo_audit_refuses_private_hosts_userinfo_and_private_redirects(monkeypatch):
    from instonct import kit_seo
    assert "publics" in kit_seo.seo_audit(1, {"url": "http://192.168.1.64:8888"})["erreur"]
    assert "publics" in kit_seo.seo_audit(1, {"url": "https://exemple.fr@192.168.1.64/"})["erreur"]
    monkeypatch.setattr("instonct.web.url_ok", lambda u: "exemple.fr" in u)           # the redirect target is a private address
    redirect = Page(b"")
    redirect.is_redirect, redirect.headers = True, {"location": "http://192.168.1.64:8888/"}
    monkeypatch.setattr("instonct.web.requests.get", lambda url, **k: redirect)
    assert "illisible" in kit_seo.seo_audit(1, {"url": "exemple.fr"})["erreur"]


def test_seo_audit_refuses_a_compressed_body_and_caps_the_size(monkeypatch):
    from instonct import kit_seo
    monkeypatch.setattr("instonct.web.url_ok", lambda u: True)
    monkeypatch.setattr("instonct.web.requests.get", lambda url, **k: Page(headers={"Content-Encoding": "gzip"}))
    assert "compressee" in kit_seo.seo_audit(1, {"url": "exemple.fr"})["erreur"]
    big = Page(b"<html><body>" + b"mot " * 400_000)
    monkeypatch.setattr("instonct.web.requests.get", lambda url, **k: big)
    assert kit_seo.seo_audit(1, {"url": "exemple.fr"})["ko"] <= kit_seo.MAX_BYTES // 1000


def test_seo_ideas_are_deduplicated_and_questions_split(monkeypatch):
    from instonct import kit_seo
    monkeypatch.setattr(kit_seo, "_suggest", lambda q, lang: ["insider trading", "comment acheter des actions", "Insider Trading"])
    out = kit_seo.seo_idees(1, {"mot": "insider"})
    assert out["idees"] == ["insider trading", "comment acheter des actions"] and out["questions"] == ["comment acheter des actions"]
    monkeypatch.setattr(kit_seo, "_suggest", lambda q, lang: [])
    assert "erreur" in kit_seo.seo_idees(1, {"mot": "insider"})


def test_seo_position_finds_the_domain_and_who_is_ahead(monkeypatch):
    from instonct import kit_seo
    hits = [{"href": "https://www.sec.gov/a"}, {"href": "https://fr.wikipedia.org/b"}, {"href": "https://www.oqro.io/c"}]
    monkeypatch.setattr("instonct.llm.web_search", lambda q, n=10, kind="text": hits)
    out = kit_seo.seo_position(1, {"domaine": "https://oqro.io", "mot": "insider trades"})
    assert out["position"] == 3 and out["devant_lui"] == ["www.sec.gov", "fr.wikipedia.org"]
    monkeypatch.setattr("instonct.llm.web_search", lambda q, n=10, kind="text": hits[:2])
    assert kit_seo.seo_position(1, {"domaine": "oqro.io", "mot": "x"})["position"] == "pas dans les 10 premiers"
