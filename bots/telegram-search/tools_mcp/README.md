# Outils pour refaire le catalogue MCP

- `build_mcp_catalog.py` : fabrique `instonct/mcp_catalog.json` a partir du registre Docker (`reg2.json`, copie de github.com/docker/mcp-registry) et de `verified.json` (resultats de `mcp_check.py`).
- `mcp_check.py` : demarre chaque serveur dans un conteneur isole et liste ses outils (a lancer sur le Mac mini).
- `smoke.py` : appelle un outil de chaque serveur pour de vrai via `kit_mcp.mcp_appeler`.
