"""Crawl4AI runner. It is started by kit_scrape_pro in its OWN virtualenv (~/scrape-venv), never imported by the bot.

stdin: one JSON line {"url", "out", "pages", "depth", "motif", "wait_for", "scroll", "item", "fields"}; "out" is a JSONL file (one page per line).
Last stdout line: a JSON summary. Safety: a Playwright route guard checks EVERY request the browser makes (page, redirects, images, scripts)
and aborts anything that is not a public http(s) address; robots.txt is obeyed; the crawl stays on the start site; pages, depth and time are capped.
"""
import asyncio
import ipaddress
import json
import re
import socket
import sys
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import DomainFilter, FilterChain, URLPatternFilter
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

_cache = {}


def public(url):
    """Same rule as web.url_ok in the bot (http(s), no login@host, every resolved address is global); data: URLs are harmless."""
    if url.startswith(("data:", "blob:", "about:blank")):
        return True
    parts = urlparse(url)
    if parts.scheme not in ("http", "https", "ws", "wss") or not parts.hostname or parts.username or parts.password or re.search(r"[\x00-\x20\x7f\\]", url.split("?", 1)[0]):
        return False
    host = parts.hostname
    if host not in _cache:
        try:
            _cache[host] = all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(host, None))
        except (OSError, ValueError):
            _cache[host] = False
    return _cache[host]


async def guard(page, context, **kwargs):
    async def check(route):
        if public(route.request.url):
            await route.continue_()
        else:
            await route.abort("blockedbyclient")
    await context.route("**/*", check)
    return page


def schema(cfg):
    fields = []
    for name, rule in (cfg.get("fields") or {}).items():
        css, _, attr = rule.partition("@")
        fields.append({"name": name, "selector": css.strip() or ":scope", "type": "attribute" if attr else "text", **({"attribute": attr} if attr else {})})
    return {"name": "items", "baseSelector": cfg["item"], "fields": fields}


async def main():
    cfg = json.loads(sys.stdin.readline())
    if not public(cfg["url"]):
        sys.exit("adresse refusee (site public en http ou https seulement)")
    site = (urlparse(cfg["url"]).hostname or "").lower()
    pages, depth = int(cfg.get("pages", 1)), int(cfg.get("depth", 1))
    options = dict(cache_mode=CacheMode.BYPASS, verbose=False, check_robots_txt=True, page_timeout=30000, word_count_threshold=5, remove_overlay_elements=False, exclude_external_links=True)
    if cfg.get("wait_for"):
        options["wait_for"] = "css:" + cfg["wait_for"]
    if cfg.get("scroll"):
        options["js_code"] = ["for (let i = 0; i < %d; i++) { window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 900)); }" % min(int(cfg["scroll"]), 12)]
    if cfg.get("item"):
        options["extraction_strategy"] = JsonCssExtractionStrategy(schema(cfg))
    if pages > 1:
        filters = [DomainFilter(allowed_domains=[site, "www." + site.removeprefix("www.")])]
        if cfg.get("motif"):
            filters.append(URLPatternFilter(patterns=["*" + cfg["motif"] + "*"]))
        options["deep_crawl_strategy"] = BFSDeepCrawlStrategy(max_depth=depth, max_pages=pages, include_external=False, filter_chain=FilterChain(filters))
    browser = BrowserConfig(headless=True, verbose=False, light_mode=True, text_mode=bool(cfg.get("sans_images", True)))
    done = {"pages": 0, "echecs": 0}
    async with AsyncWebCrawler(config=browser) as crawler:
        crawler.crawler_strategy.set_hook("on_page_context_created", guard)
        results = await asyncio.wait_for(crawler.arun(cfg["url"], config=CrawlerRunConfig(**options)), timeout=240)
        results = results if isinstance(results, list) or hasattr(results, "__iter__") and not hasattr(results, "markdown") else [results]
        with open(cfg["out"], "w", encoding="utf-8") as f:
            for r in results:
                ok = bool(getattr(r, "success", False))
                done["pages" if ok else "echecs"] += 1
                row = {"url": r.url, "statut": getattr(r, "status_code", None), "ok": ok, "titre": ((r.metadata or {}).get("title") or "")[:200], "profondeur": (r.metadata or {}).get("depth", 0)}
                if ok and cfg.get("item"):
                    try:
                        row["items"] = json.loads(r.extracted_content or "[]")[:500]
                    except ValueError:
                        row["items"] = []
                elif ok:
                    row["markdown"] = str(getattr(r.markdown, "fit_markdown", None) or r.markdown or "")[:200_000]
                else:
                    row["erreur"] = str(getattr(r, "error_message", ""))[:200]
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(done))


asyncio.run(main())
