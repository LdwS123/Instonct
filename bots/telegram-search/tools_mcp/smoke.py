import json, sys, time
from instonct import kit_mcp, mcp_host
CASES = [
 ("time","get_current_time",{"timezone":"Europe/Paris"}),
 ("fetch","fetch",{"url":"https://example.com"}),
 ("duckduckgo","search",{"query":"oqro.io"}),
 ("wikipedia-mcp","search_wikipedia",{"query":"Paris"}),
 ("hackernews-mcp","get_stories",{"story_type":"top","num_stories":3}),
 ("youtube-transcript","get_transcript",{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}),
 ("paper-search","search_arxiv",{"query":"transformers","max_results":2}),
 ("vuln-nist-mcp-server","get_cve_by_id",{"cve_id":"CVE-2021-44228"}),
 ("npm-sentinel","npmLatest",{"packages":["express"]}),
 ("sequentialthinking","sequentialthinking",{"thought":"test","nextThoughtNeeded":False,"thoughtNumber":1,"totalThoughts":1}),
 ("memory","read_graph",{}),
 ("sqlite","list_tables",{}),
 ("google-flights","get_flights_on_date",{"origin":"CDG","destination":"JFK","date":"2026-12-15","adults":1,"seat_type":"economy","return_cheapest_only":True}),
 ("openbnb-airbnb","airbnb_search",{"location":"Paris"}),
 ("minecraft-wiki","MinecraftWiki_searchWiki",{"query":"creeper"}),
 ("terraform-mcp-server","get_latest_provider_version",{"namespace":"hashicorp","name":"aws"}),
 ("effect-mcp","effect_docs_search",{"query":"Effect.gen"}),
 ("osp_marketing_tools","get_meta_guide",{}),
 ("arxiv-mcp-server","search_papers",{"query":"attention","max_results":2}),
 ("openapi","get_list_of_operations",{"addressOrFileContents":"https://petstore3.swagger.io/api/v3/openapi.json"}),
]
only = sys.argv[1:]
res = {}
for sid, tool, args in CASES:
    if only and sid not in only: continue
    t=time.time()
    try:
        entry = mcp_host.entries()[sid]
        names = {x["nom"] for x in entry.get("outils",[])}
        if tool not in names:
            res[sid]=("TOOL?", sorted(names)); print(sid, "TOOL?", sorted(names)); continue
        r = kit_mcp.mcp_appeler(1, {"serveur":sid,"outil":tool,"arguments":json.dumps(args)})
        res[sid]=r
        print(sid, round(time.time()-t,1), "s", json.dumps(r, ensure_ascii=False)[:230], flush=True)
    except Exception as e:
        print(sid, "EXC", type(e).__name__, str(e)[:150], flush=True)
mcp_host.stop_all()
