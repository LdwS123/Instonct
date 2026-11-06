import json, sys, time
from instonct import mcp_host as h

ids = sys.argv[1:] or [k for k, v in h.entries().items() if v["etat"] == "essai"]
res = {}
for sid in ids:
    e = h.entries()[sid]
    e["etat"] = "ok"
    t0 = time.time()
    rc, out = h._sudo("docker", "pull", "-q", e["image"], timeout=1500)
    print(sid, "pull rc", rc, round(time.time() - t0), "s", out[-100:] if rc else "", flush=True)
    if rc:
        res[sid] = {"ok": False, "note": "pull: " + out[-100:]}
        continue
    _, dig = h._sudo("docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", e["image"])
    for ro in (True, False):
        e["ro"] = ro
        h.stop_all()
        t1 = time.time()
        try:
            r = h.request(sid, "tools/list", {}, 60)
            tools = [{"nom": t["name"], "desc": t.get("description", ""), "args": t.get("inputSchema", {})} for t in r.get("tools", [])]
            print("  OK ro=%s %.1fs %d outils: %s" % (ro, time.time() - t1, len(tools), [t["nom"] for t in tools][:10]), flush=True)
            res[sid] = {"ok": bool(tools), "outils": len(tools), "ro": ro, "digest": dig, "tools": tools}
            break
        except Exception as ex:
            print("  FAIL ro=%s %s %s" % (ro, type(ex).__name__, str(ex)[:150]), flush=True)
            res[sid] = {"ok": False, "note": type(ex).__name__ + " " + str(ex)[:100]}
    h.stop_all()
    json.dump(res, open("/tmp/mcp_check_result.json", "w"), ensure_ascii=False, indent=1)
print("DONE", flush=True)
