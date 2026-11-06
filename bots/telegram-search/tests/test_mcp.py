"""Open-source MCP servers: run in locked containers (here replaced by a tiny fake server on stdio), honest about what works."""
import json
import re
import sys
import textwrap
import time

import pytest

from instonct import catalog, dispatch, kit_mcp, kits

FAKE_SERVER = textwrap.dedent('''
    import json, os, sys, time
    def send(m):
        sys.stdout.write(json.dumps(m) + "\\n"); sys.stdout.flush()
    for line in sys.stdin:
        m = json.loads(line)
        if "id" not in m or "method" not in m:          # a notification, or the answer to our own request
            continue
        if m["method"] == "initialize":
            send({"jsonrpc": "2.0", "method": "notifications/message", "params": {"data": "hello"}})
            send({"jsonrpc": "2.0", "id": 99, "method": "sampling/createMessage", "params": {}})
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": "2025-03-26", "capabilities": {}, "serverInfo": {"name": "fake", "version": "1"}}})
        elif m["method"] == "tools/call":
            name, args = m["params"]["name"], m["params"]["arguments"]
            if name == "echo":
                send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "echo: " + json.dumps(args, sort_keys=True)}]}})
            elif name == "image":
                send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "image", "data": "xx"}]}})
            elif name == "big":
                send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "z" * 9000}]}})
            elif name == "boom":
                send({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32000, "message": "bad input"}})
            elif name == "fail":
                send({"jsonrpc": "2.0", "id": m["id"], "result": {"isError": True, "content": [{"type": "text", "text": "not found"}]}})
            elif name == "slow":
                time.sleep(30)
            elif name == "dieonce":
                flag = os.environ["FLAG"]
                if not os.path.exists(flag):
                    open(flag, "w").close(); sys.exit(1)
                send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "second try"}]}})
        else:
            send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
''')


def tools(*names):
    return [{"nom": n, "sert_a": f"outil {n}", "args": {}, "requis": []} for n in names]


def entry(sid, **extra):
    base = {"id": sid, "nom": sid, "image": f"mcp/{sid}", "etat": "ok", "desc": "d", "sert_a": "faux serveur de test wikipedia", "mots": "faux test wikipedia",
            "sur": True, "outils": tools("echo", "image", "big", "boom", "fail", "slow", "dieonce")}
    base.update(extra)
    return base


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """A catalogue of fake servers; 'docker' is replaced by running the fake server with python."""
    script = tmp_path / "fake_server.py"
    script.write_text(FAKE_SERVER)
    flag = tmp_path / "flag"
    servers = {
        "alpha": entry("alpha"), "beta": entry("beta"), "gamma": entry("gamma"),
        "writer": entry("writer", sur=False, sert_a="ecrit des notes privees"),
        "acct": entry("acct", etat="compte", sert_a="demande une cle"), "wip": entry("wip", etat="essai"),
    }
    monkeypatch.setattr("instonct.mcp_host.entries", lambda: servers)
    monkeypatch.setattr("instonct.mcp_host.argv", lambda e, name: [sys.executable, "-u", str(script)])
    monkeypatch.setattr("instonct.mcp_host.ensure_network", lambda: None)
    monkeypatch.setattr("instonct.mcp_host.image_ready", lambda e: True)
    monkeypatch.setattr("instonct.mcp_host._sudo", lambda *a, timeout=30: (0, ""))
    monkeypatch.setenv("FLAG", str(flag))
    from instonct import mcp_host
    yield servers
    mcp_host.stop_all()


def call(server, tool, **arguments):
    return kit_mcp.mcp_appeler(1, {"serveur": server, "outil": tool, "arguments": json.dumps(arguments)})


# ---------------------------------------------------------------- running a server
def test_a_server_starts_answers_and_the_notifications_it_sends_do_not_get_in_the_way(fake):
    out = call("alpha", "echo", query="paris")
    assert out == {"resultat": 'echo: {"query": "paris"}'}
    assert call("alpha", "echo", query="lyon")["resultat"] == 'echo: {"query": "lyon"}'            # same running server


def test_errors_are_french_and_honest(fake):
    assert "refuse" in call("alpha", "boom")["erreur"] and "bad input" in call("alpha", "boom")["erreur"]
    assert "not found" in call("alpha", "fail")["erreur"]
    assert "non affiche" in call("alpha", "image")["resultat"]


def test_a_long_answer_is_cut_and_says_so(fake):
    out = call("alpha", "big")
    assert len(out["resultat"]) == kit_mcp.MAX_TEXT and out["coupe"] is True


def test_a_wrong_tool_name_lists_the_real_ones(fake):
    out = call("alpha", "nope")
    assert "echo" in out["erreur"] and "n'a pas d'outil" in out["erreur"]
    assert "erreur" in kit_mcp.mcp_appeler(1, {"serveur": "alpha", "outil": "echo; rm -rf /"})


def test_bad_arguments_are_refused_before_anything_starts(fake):
    assert "JSON" in kit_mcp.mcp_appeler(1, {"serveur": "alpha", "outil": "echo", "arguments": "{pas du json"})["erreur"]
    assert "erreur" in kit_mcp.mcp_appeler(1, {"serveur": "alpha", "outil": "echo", "arguments": json.dumps({"x": "y" * 7000})})
    assert "erreur" in kit_mcp.mcp_appeler(1, {"serveur": "alpha", "outil": "echo", "arguments": "[1, 2]"})


def test_a_slow_server_times_out_and_the_next_call_gets_a_fresh_one(fake):
    from instonct import mcp_host
    with pytest.raises(TimeoutError):
        mcp_host.request("alpha", "tools/call", {"name": "slow", "arguments": {}}, timeout=1)
    assert call("alpha", "echo", a=1)["resultat"].startswith("echo")


def test_a_server_that_dies_is_started_again(fake):
    from instonct import mcp_host
    assert call("alpha", "echo", a=1)["resultat"]
    mcp_host._live["alpha"].p.kill()
    time.sleep(0.2)
    assert call("alpha", "echo", a=2)["resultat"].endswith('{"a": 2}')
    assert call("alpha", "dieonce")["resultat"] == "second try"                  # died during the call: one retry


def test_at_most_two_servers_live_and_the_oldest_idle_one_leaves(fake):
    from instonct import mcp_host
    call("alpha", "echo")
    time.sleep(0.05)
    call("beta", "echo")
    time.sleep(0.05)
    call("gamma", "echo")
    assert set(mcp_host._live) == {"beta", "gamma"}


def test_the_idle_reaper_rule_picks_only_old_unused_servers(fake, monkeypatch):
    from instonct import mcp_host
    call("alpha", "echo")
    proc = mcp_host._live["alpha"]
    assert not (time.time() - proc.last > mcp_host.IDLE_SECONDS)
    proc.last -= mcp_host.IDLE_SECONDS + 1
    assert time.time() - proc.last > mcp_host.IDLE_SECONDS and not proc.lock.locked()


def test_an_image_not_downloaded_yet_starts_the_download_and_says_so(fake, monkeypatch):
    started = []
    monkeypatch.setattr("instonct.mcp_host.image_ready", lambda e: False)
    monkeypatch.setattr("instonct.mcp_host.start_pull", lambda e: started.append(e["id"]) or "en cours")
    out = call("alpha", "echo")
    assert "pas encore telecharge" in out["erreur"] and started == ["alpha"]


# ---------------------------------------------------------------- what is usable, and why not
def test_only_working_servers_can_be_called_and_the_others_say_why(fake):
    assert "pas utilisable" in call("acct", "echo")["erreur"] and "cle" in call("acct", "echo")["erreur"]
    assert "pas utilisable" in call("wip", "echo")["erreur"]
    assert "inconnu" in call("zzz", "echo")["erreur"]
    assert "inconnu" in kit_mcp.mcp_outils(1, {"serveur": ""})["erreur"]


def test_the_catalogue_is_honest_about_unusable_servers(fake):
    plain = kit_mcp.mcp_serveurs(1, {})
    assert {s["id"] for s in plain["utilisables"]} == {"alpha", "beta", "gamma", "writer"}
    assert "1 demandent un compte" in plain["autres"]
    found = kit_mcp.mcp_serveurs(1, {"recherche": "demande une cle"})
    assert "inutilisable" in found["serveurs"][0] and found["serveurs"][0]["id"] == "acct"
    assert "erreur" in kit_mcp.mcp_serveurs(1, {"recherche": "zzzzqqq"})


def test_the_tools_of_a_server_come_from_the_reviewed_catalogue_not_from_the_server(fake):
    out = kit_mcp.mcp_outils(1, {"serveur": "alpha"})
    assert [t["nom"] for t in out["outils"]][:2] == ["echo", "image"]


# ---------------------------------------------------------------- security
def test_after_reading_the_web_only_read_only_servers_can_be_used(fake):
    links = ["https://exemple.fr"]
    out = kits.tool(1, "mcp_appeler", {"serveur": "writer", "outil": "echo"}, links)
    assert "refuse" in out["erreur"] and "peut ecrire" in out["erreur"]
    assert "resultat" in kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo"}, links)
    assert "resultat" in kits.tool(1, "mcp_appeler", {"serveur": "writer", "outil": "echo"}, [])        # fine when nothing was read


def test_what_a_server_says_marks_the_conversation_as_read_from_the_web(fake):
    links = []
    kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo"}, links)
    assert links == ["(page web)"]
    links = []
    kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "boom"}, links)
    assert links == ["(page web)"]                                                                    # a failure too: error text is written by the server


def test_after_reading_the_web_long_arguments_are_refused(fake):
    links = ["https://exemple.fr"]
    out = kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo", "arguments": json.dumps({"q": "x" * 400})}, links)
    assert "refuse" in out["erreur"] and "300" in out["erreur"]
    url = {"q": "https://a.fr/?" + "k=" + "v" * 300}
    many = {"a": ["y" * 90] * 5}                                                                      # each string small, together too much
    assert "refuse" in kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo", "arguments": json.dumps(many)}, links)["erreur"]
    assert "refuse" in kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo", "arguments": json.dumps(url)}, links)["erreur"]
    assert "refuse" in kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo", "arguments": "{pas json"}, links)["erreur"]
    assert "resultat" in kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo", "arguments": json.dumps({"q": "paris"})}, links)
    assert "resultat" in kits.tool(1, "mcp_appeler", {"serveur": "alpha", "outil": "echo", "arguments": json.dumps({"q": "x" * 400})}, [])   # nothing read: fine


def test_the_firewall_is_checked_before_every_start_not_only_the_first(monkeypatch):
    from instonct import mcp_host
    monkeypatch.setitem(mcp_host._net, "ok", True)                         # an earlier start succeeded...
    seen = []

    def fake_sudo(*args, timeout=30):
        seen.append(args)
        return (1, "flushed") if args[:2] == ("iptables", "-C") or args[:2] == ("iptables", "-I") else (0, "")
    monkeypatch.setattr("instonct.mcp_host._sudo", fake_sudo)
    with pytest.raises(RuntimeError, match="pare-feu"):                  # ...but the rules were flushed since: no start
        mcp_host.ensure_network()
    assert any(a[:2] == ("iptables", "-C") for a in seen)


def test_a_server_that_floods_us_is_cut_off_and_unasked_output_is_dropped(monkeypatch):
    from instonct import mcp_host
    monkeypatch.setattr("instonct.mcp_host._sudo", lambda *a, **k: (0, ""))
    code = "import sys,time\nsys.stdin.readline()\nfor i in range(2000): print('{\"jsonrpc\":\"2.0\",\"method\":\"n\"}')\nsys.stdout.flush()\ntime.sleep(20)"
    quiet = mcp_host.Proc({"id": "x"}, [sys.executable, "-c", code], "x")
    quiet.send({"a": 1})
    time.sleep(1.5)
    assert quiet.q.qsize() <= 1                                           # nobody asked: nothing stored (only the end marker at most)
    quiet.p.kill()
    loud = mcp_host.Proc({"id": "x"}, [sys.executable, "-c", code], "x")
    loud.busy = True
    loud.send({"a": 1})
    time.sleep(1.5)
    assert loud.q.qsize() <= 256 and not loud.alive()                     # bounded, and the flooding server was killed



def test_the_docker_command_line_is_locked_and_holds_no_text_from_the_user():
    from instonct import mcp_host
    e = {"id": "demo", "image": "mcp/demo", "digest": "mcp/demo@sha256:" + "a" * 64, "env": {"B": "2", "A": "1"}, "volumes": ["mcp-demo:/data"], "cmd": ["--db", "/data/x"]}
    a = mcp_host.argv(e, "mcp_demo")
    for flag in ("--cap-drop", "ALL", "no-new-privileges", "--read-only", "--rm", "--network", "mcpnet", "--memory", "--pids-limit", "--dns", "-i"):
        assert flag in a
    assert a[-3:] == ["mcp/demo@sha256:" + "a" * 64, "--db", "/data/x"] and "--privileged" not in a
    assert a.index("A=1") < a.index("B=2") and ["-v", "mcp-demo:/data"] == a[a.index("-v"):a.index("-v") + 2]
    assert "--tmpfs" in a and "--tmpfs" not in mcp_host.argv({**e, "ro": False}, "x")
    hostile = {"serveur": "demo; rm -rf /", "outil": "$(reboot)", "arguments": '{"q":"--privileged -v /:/host"}'}
    assert "erreur" in kit_mcp.mcp_appeler(1, hostile)                                                 # unknown server: nothing is ever started


def test_the_firewall_rules_cover_the_home_network_tailscale_and_the_machine_itself():
    from instonct import mcp_host
    rules = mcp_host._rules()
    blocked = {r[r.index("-d") + 1] for chain, r in rules if chain == "DOCKER-USER"}
    assert {"192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "100.64.0.0/10", "169.254.0.0/16"} <= blocked
    assert ("INPUT", ["-i", "br-mcp", "-j", "DROP"]) in rules


def test_the_network_is_not_used_unless_every_rule_is_proven(monkeypatch):
    from instonct import mcp_host
    monkeypatch.setitem(mcp_host._net, "ok", False)
    calls = []

    def fake_sudo(*args, timeout=30):
        calls.append(args)
        return (1, "no") if args[:2] == ("iptables", "-I") or args[:2] == ("iptables", "-C") else (0, "")
    monkeypatch.setattr("instonct.mcp_host._sudo", fake_sudo)
    with pytest.raises(RuntimeError, match="pare-feu"):
        mcp_host.ensure_network()
    assert mcp_host._net["ok"] is False


# ---------------------------------------------------------------- the real catalogue file
def test_the_real_catalogue_is_well_formed_and_every_working_server_is_pinned_and_reviewed():
    from instonct import mcp_host
    mcp_host.entries.cache_clear()
    every = mcp_host.entries()
    assert len(every) > 200
    working = [e for e in every.values() if e["etat"] == "ok"]
    assert len(working) >= 10
    for e in working:
        assert e.get("digest"), e["id"]                                                              # pinned: 'latest' cannot change under us
        assert e["outils"] and all(re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", t["nom"]) and len(t["sert_a"]) <= 140 for t in e["outils"]), e["id"]
        assert isinstance(e["sur"], bool) and e["sert_a"] and e["mots"], e["id"]
    assert all(e["etat"] in ("ok", "essai", "echec", "compte", "autre") for e in every.values())
    assert all(e["etat"] != "ok" or e.get("digest") for e in every.values())
    assert {e["id"] for e in every.values() if e.get("volumes")} >= set()                            # volumes are validated on load


def test_no_reviewed_text_tries_to_talk_to_the_model():
    from instonct import mcp_host
    bad = re.compile(r"ignore|ignorez|previous instructions|system prompt|you must|tu dois|<\s*/?\s*(?:system|instruction)", re.I)
    for e in mcp_host.entries().values():
        if e["etat"] == "ok":
            for text in [e["sert_a"], e["mots"], *(t["sert_a"] for t in e["outils"])]:
                assert not bad.search(text), (e["id"], text)


# ---------------------------------------------------------------- reaching them by words
def test_chercher_outil_points_at_the_servers_that_fit(fake):
    out = dispatch.run_tool(1, "chercher_outil", {"besoin": "chercher sur wikipedia faux test"}, [])
    names = [o["nom"] for o in out["outils_ajoutes"]]
    assert {"mcp_serveurs", "mcp_outils", "mcp_appeler"} <= set(names)
    assert out["serveurs_mcp"][0]["id"] in {"alpha", "beta", "gamma", "writer"}


def test_the_mcp_tools_come_in_with_their_words_and_not_for_small_talk():
    for text in ("cherche sur wikipedia", "les outils open source mcp", "les failles cve du moment", "airbnb a Lisbonne"):
        assert {"mcp_serveurs", "mcp_appeler"} <= {t["function"]["name"] for t in catalog.select_tools(text)}, text
    for text in ("salut", "merci beaucoup", "mets la chaine 3"):
        assert not {t["function"]["name"] for t in catalog.select_tools(text)} & kit_mcp.FUNCS.keys(), text


def test_cutting_a_server_removes_its_container_even_when_the_process_cannot_be_signalled(monkeypatch):
    from instonct import mcp_host
    calls = []
    monkeypatch.setattr("instonct.mcp_host._sudo", lambda *a, **k: calls.append(a) or (0, ""))
    proc = mcp_host.Proc({"id": "x"}, [sys.executable, "-c", "import time; time.sleep(30)"], "mcp_x")

    def refuse(*a):
        raise PermissionError("owned by root")
    real_kill = proc.p.kill
    proc.p.kill = refuse
    proc.p.terminate = refuse
    proc.close()                                                                                      # must not raise, must still remove the container
    assert ("docker", "rm", "-f", "mcp_x") in calls
    real_kill()
