"""Scrapling runner (PARSER ONLY). Started by kit_scrape_pro in its own virtualenv (~/scrape-venv), never imported by the bot.

It does no network at all: the bot downloads the page itself (public addresses only) and sends the HTML on stdin, so Scrapling's own fetchers
(and their anti-bot "stealth" modes) are never used. What we use is its adaptive selector: the element is remembered by its shape
(tag, attributes, text, neighbours), and found again after a site redesign even when the CSS selector no longer matches.

stdin: one JSON line {"html", "url", "selector", "name", "db", "save", "attribute"}.
stdout: one JSON line {"found": [...], "adaptive": bool}.
"""
import json
import sys

from scrapling.parser import Selector


def main():
    cfg = json.loads(sys.stdin.readline())
    page = Selector(cfg["html"], url=cfg["url"], adaptive=True, storage_args={"storage_file": cfg["db"], "url": cfg["name"]})
    attribute = cfg.get("attribute") or ""

    def values(nodes):
        out = []
        for node in list(nodes)[:100]:
            value = node.attrib.get(attribute, "") if attribute else " ".join(str(node.get_all_text(strip=True)).split())
            out.append(str(value)[:300])
        return out

    if cfg.get("save"):
        found = page.css(cfg["selector"], auto_save=True)
        print(json.dumps({"found": values(found), "adaptive": False, "saved": bool(len(found))}, ensure_ascii=False))
        return
    found = page.css(cfg["selector"])
    if len(found):
        print(json.dumps({"found": values(found), "adaptive": False}, ensure_ascii=False))
        return
    found = page.css(cfg["selector"], adaptive=True)
    print(json.dumps({"found": values(found), "adaptive": True}, ensure_ascii=False))


main()
