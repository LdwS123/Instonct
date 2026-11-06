"""Scrapy runner. It is started by kit_scrape in its OWN virtualenv (~/scrape-venv), never imported by the bot.

stdin: one JSON line {"url", "out", "pages", "depth", "follow", "item", "fields", "delay"}; "out" is the JSONL file to write.
Safety lives here too, because Scrapy follows links by itself: every request (first one, links, redirects) goes through `PublicOnly`;
robots.txt is obeyed; the crawl stays on the start site; size, page and time limits are set; Scrapy's debug console is off.
"""
import ipaddress
import json
import re
import socket
import sys
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.exceptions import IgnoreRequest

SKIP = re.compile(r"\.(?:jpe?g|png|gif|webp|svg|ico|pdf|zip|gz|rar|7z|mp[34]|avi|mov|css|js|json|xml|woff2?|ttf|exe|dmg|docx?|xlsx?|pptx?)(?:$|\?)", re.I)


def public(url):
    """Same rule as web.url_ok in the bot: http(s) only, no login@host, every resolved address is global."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or re.search(r"[\x00-\x20\x7f\\]", url.split("?", 1)[0]):
        return False
    try:
        return all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(parts.hostname, None))
    except (OSError, ValueError):
        return False


class PublicOnly:
    """Downloader middleware: refuse any request to a private/internal address (links, redirects and the first URL alike)."""
    def process_request(self, request, spider=None):
        if not public(request.url):
            raise IgnoreRequest("adresse non publique")


def bare(host):
    return (host or "").lower().removeprefix("www.")


class Job(scrapy.Spider):
    name = "instonct"
    handle_httpstatus_all = True

    def __init__(self, cfg, **kw):
        super().__init__(**kw)
        self.cfg, self.start_urls = cfg, [cfg["url"]]
        self.site = bare(urlparse(cfg["url"]).hostname)
        self.follow = re.compile(cfg["follow"], re.I) if cfg.get("follow") else None
        self.seen = 0

    def parse(self, response):
        row = {"url": response.url, "statut": response.status}
        if response.status < 400 and hasattr(response, "css"):
            if not self.cfg.get("item"):
                row.update(titre=(response.css("title::text").get() or "").strip()[:200], h1=(response.css("h1 ::text").get() or "").strip()[:150],
                           description=(response.css("meta[name=description]::attr(content)").get() or "").strip()[:250])
            for name, rule in (self.cfg.get("fields") or {}).items():
                if not self.cfg.get("item"):
                    row[name] = self.pick(response, rule, response.url)
            if self.cfg.get("item"):
                for node in response.css(self.cfg["item"])[:500]:
                    yield {"page": response.url, **{name: self.pick(node, rule, response.url) for name, rule in (self.cfg.get("fields") or {}).items()}}
            else:
                yield row
            if response.meta.get("depth", 0) < self.cfg.get("depth", 3):
                for href in response.css("a::attr(href)").getall()[:400]:
                    url = response.urljoin(href.strip()).split("#")[0]
                    if url.startswith("http") and bare(urlparse(url).hostname) == self.site and not SKIP.search(url) and (not self.follow or self.follow.search(url)):
                        yield scrapy.Request(url, callback=self.parse)
        else:
            yield row

    @staticmethod
    def pick(node, rule, base=""):
        css, _, attr = rule.partition("@")
        sel = node.css(css) if css.strip() else node
        if attr:
            value = (sel.attrib.get(attr) or "").strip()
            return (urljoin(base, value) if value and attr in ("href", "src") and base else value)[:300]
        return " ".join(t.strip() for t in sel.css("::text").getall() if t.strip())[:300]


def main():
    cfg = json.loads(sys.stdin.readline())
    settings = {
        "USER_AGENT": "Instonct (+https://github.com/LdwS123/Instonct)", "ROBOTSTXT_OBEY": True, "LOG_LEVEL": "ERROR", "TELNETCONSOLE_ENABLED": False,
        "DOWNLOAD_DELAY": max(0.25, float(cfg.get("delay", 0.5))), "AUTOTHROTTLE_ENABLED": True, "AUTOTHROTTLE_START_DELAY": 0.5, "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
        "CONCURRENT_REQUESTS": 4, "CONCURRENT_REQUESTS_PER_DOMAIN": 2, "DOWNLOAD_TIMEOUT": 15, "DOWNLOAD_MAXSIZE": 3_000_000, "DOWNLOAD_WARNSIZE": 0,
        "RETRY_TIMES": 1, "REDIRECT_MAX_TIMES": 5, "DEPTH_LIMIT": int(cfg.get("depth", 3)) + 1, "CLOSESPIDER_PAGECOUNT": int(cfg.get("pages", 100)),
        "CLOSESPIDER_TIMEOUT": 240, "COOKIES_ENABLED": False, "HTTPERROR_ALLOW_ALL": True, "DNS_TIMEOUT": 8, "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        "DOWNLOADER_MIDDLEWARES": {"__main__.PublicOnly": 1}, "FEEDS": {cfg["out"]: {"format": "jsonlines", "encoding": "utf-8", "overwrite": True}},
        "EXTENSIONS": {"scrapy.extensions.telnet.TelnetConsole": None},
    }
    if not public(cfg["url"]):
        sys.exit("adresse refusee (site public en http ou https seulement)")
    process = CrawlerProcess(settings)
    process.crawl(Job, cfg=cfg)
    process.start()


if __name__ == "__main__":
    main()
