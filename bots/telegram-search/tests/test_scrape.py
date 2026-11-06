"""The scraper kit (kit_scrape). No real website, Lightpanda or Chromium is touched, nothing is sent to a chat: a fake `web.safe_get` serves pages from a dict."""
import csv
import gzip
import os
import subprocess
import types

import pytest
import requests

from instonct import catalog, kit_media, kit_scrape, kits


class FakeResponse:
    def __init__(self, url, status, kind, body):
        self.final_url, self.status_code, self.body = url, status, body
        self.headers = {"content-type": kind}

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i:i + size]

    def close(self):
        pass


@pytest.fixture
def site(tmp_path, monkeypatch):
    """`site.pages[url] = html` (or (status, type, bytes)); records every request; a fake chat sender; a work folder in tmp."""
    work = tmp_path / "work"
    work.mkdir()
    state = types.SimpleNamespace(pages={}, hits=[], sent=[], work=work, runs=[], lightpanda=None)

    def fake_get(url, max_redirects=5, **kw):
        host = url.split("://", 1)[-1].split("/")[0]
        if not url.startswith("http") or host.startswith(("192.168.", "localhost", "127.")):
            raise ValueError("adresse refusee (site public en http ou https seulement)")
        state.hits.append(url)
        page = state.pages.get(url)
        if page is None:
            return FakeResponse(url, 404, "text/html", b"<html>not found</html>")
        if isinstance(page, Exception):
            raise page
        status, kind, body = page if isinstance(page, tuple) else (200, "text/html; charset=utf-8", page)
        return FakeResponse(url, status, kind, body.encode() if isinstance(body, str) else body)

    monkeypatch.setattr(kit_scrape.web, "safe_get", fake_get)
    monkeypatch.setattr(kit_scrape.web, "url_ok", lambda u: u.startswith("http") and not u.split("://", 1)[-1].startswith(("192.168.", "localhost", "127.")))
    monkeypatch.setattr(kit_scrape.time, "sleep", lambda s: None)
    monkeypatch.setattr(kit_scrape, "WORK", str(work))
    monkeypatch.setattr(kit_scrape, "LIGHTPANDA", "/nonexistent/lightpanda")
    monkeypatch.setattr(kit_scrape, "_send", lambda chat, path: state.sent.append(path) or True)
    monkeypatch.setattr(kit_media, "WORK", str(work))
    return state


def page(body, title="Page"):
    return f"<html lang='fr'><head><title>{title}</title></head><body>{body}</body></html>" + "<!-- " + "x" * 400 + " -->"


def run(name, **args):
    return kit_scrape.FUNCS[name](1, args)


# ---- scraper : the simple modes ---------------------------------------------------------------------------------------------------------------

def test_meta_reads_title_social_card_and_structured_data(site):
    site.pages["https://shop.example/a"] = """<html lang="fr"><head><title>Chaise</title><meta name="description" content="Une belle chaise">
        <link rel="canonical" href="https://shop.example/chaise"><meta property="og:title" content="Chaise OG">
        <script type="application/ld+json">{"@type":"Product","name":"Chaise","offers":{"price":"10"},"price":"12","priceCurrency":"EUR"}</script></head>
        <body><h1>Chaise</h1><h2>a</h2><h2>b</h2>""" + "x" * 400 + "</body></html>"
    out = run("scraper", url="https://shop.example/a", mode="meta")
    assert out["titre"] == "Chaise" and out["description"] == "Une belle chaise" and out["canonique"] == "https://shop.example/chaise"
    assert out["h1"] == ["Chaise"] and out["nb_h2"] == 2 and out["open_graph"] == {"title": "Chaise OG"} and out["langue"] == "fr"
    assert out["donnees_structurees"][0]["@type"] == "Product" and out["donnees_structurees"][0]["price"] == "12"


def test_texte_returns_the_main_text_and_cuts_long_pages(site):
    site.pages["https://blog.example/p"] = page("<article><p>" + "Bonjour le monde. " * 800 + "</p></article>")
    out = run("scraper", url="blog.example/p")                                   # no scheme, default mode
    assert out["url"] == "https://blog.example/p" and out["texte"].startswith("Bonjour") and len(out["texte"]) <= 6000 and "suite" in out


def test_liens_split_internal_and_external_and_skip_junk(site):
    site.pages["https://a.example/"] = page("<a href='/x'>X</a><a href='https://b.example/y'>Y</a><a href='mailto:z@z.fr'>Z</a><a href='javascript:void(0)'>J</a><a href='/x#top'>X2</a>")
    out = run("scraper", url="https://a.example/", mode="liens")
    assert out["total"] == 2 and out["internes"] == 1
    assert {x["lien"] for x in out["liens"]} == {"https://a.example/x", "https://b.example/y"}


def test_images_skip_inline_data(site):
    site.pages["https://a.example/"] = page("<img src='/p.png' alt='photo'><img src='data:image/png;base64,AAAA'>")
    out = run("scraper", url="https://a.example/", mode="images")
    assert out["total"] == 1 and out["images"][0] == {"image": "https://a.example/p.png", "alt": "photo"}


def test_tableaux_picks_the_biggest_table_and_exports_csv(site):
    site.pages["https://a.example/t"] = page("<table><tr><th>Nom</th><th>Prix</th></tr><tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr></table><table><tr><td>z</td></tr></table>")
    out = run("scraper", url="https://a.example/t", mode="tableaux", csv="prix")
    assert out["colonnes"] == ["Nom", "Prix"] and out["lignes"] == 2 and out["envoye"] is True
    path = site.sent[0]
    assert path.startswith(str(site.work / "scrapes")) and path.endswith(".csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    assert rows == [{"Nom": "A", "Prix": "1"}, {"Nom": "B", "Prix": "2"}]


def test_a_page_cannot_plant_a_spreadsheet_formula_in_the_csv(site):
    site.pages["https://a.example/t"] = page("<table><tr><th>Nom</th></tr><tr><td>=HYPERLINK(\"http://evil\")</td></tr><tr><td>+1+1</td></tr></table>")
    run("scraper", url="https://a.example/t", mode="tableaux", csv="x")
    values = [r["Nom"] for r in csv.DictReader(open(site.sent[0], encoding="utf-8-sig"))]
    assert all(v.startswith("'") for v in values)


def test_no_table_says_so(site):
    site.pages["https://a.example/"] = page("<p>rien</p>")
    assert "aucun tableau" in run("scraper", url="https://a.example/", mode="tableaux")["resultat"]


# ---- scraper : contacts -----------------------------------------------------------------------------------------------------------------------

def test_contacts_finds_public_emails_phones_and_socials(site):
    site.pages["https://co.example/"] = page("<p>Ecrivez a Jean@Co.example ou appelez le 01 23 45 67 89.</p><a href='mailto:vente@co.example?subject=hi'>m</a>"
                                             "<a href='tel:+33123456789'>t</a><a href='https://www.linkedin.com/company/co?trk=1'>in</a><img src='logo@2x.png'>")
    out = run("scraper", url="https://co.example/", mode="contacts")
    assert out["emails"] == ["jean@co.example", "vente@co.example"]
    assert "+33123456789" in out["telephones"] and "01 23 45 67 89" in out["telephones"]
    assert out["reseaux"] == ["https://www.linkedin.com/company/co"] and "publiquement" in out["note"]


def test_contacts_looks_one_contact_page_further_when_the_home_has_no_address(site):
    site.pages["https://co.example/"] = page("<a href='/contact'>Contact</a><a href='/blog'>Blog</a>")
    site.pages["https://co.example/contact"] = page("<p>hello@co.example</p>")
    out = run("scraper", url="https://co.example/", mode="contacts")
    assert out["emails"] == ["hello@co.example"] and out["aussi_lu"] == "https://co.example/contact"
    assert "https://co.example/blog" not in site.hits


def test_contacts_none(site):
    site.pages["https://co.example/"] = page("<p>rien</p>")
    assert run("scraper", url="https://co.example/", mode="contacts")["resultat"].startswith("aucun contact")


# ---- scraper : champs (rows by CSS) + pagination --------------------------------------------------------------------------------------------

def products(names, nxt=None):
    items = "".join(f"<div class='p'><h2>{n}</h2><span class='prix'>{i}€</span><a href='/item/{n}'>voir</a></div>" for i, n in enumerate(names, 1))
    return page(items + (f"<a class='next' href='{nxt}'>suivant</a>" if nxt else ""))


CHAMPS = '{"titre":"h2","prix":".prix","lien":"a@href"}'


def test_champs_extracts_rows_follows_next_pages_and_exports(site):
    site.pages["https://shop.example/robots.txt"] = (200, "text/plain", "User-agent: *\nDisallow: /prive/")
    site.pages["https://shop.example/l?p=1"] = products(["a", "b"], "/l?p=2")
    site.pages["https://shop.example/l?p=2"] = products(["c"], "/l?p=3")
    site.pages["https://shop.example/l?p=3"] = products(["d"])
    out = run("scraper", url="https://shop.example/l?p=1", mode="champs", selecteur=".p", champs=CHAMPS, suivant="a.next", pages=3, csv="produits")
    assert out["lignes"] == 4 and out["pages_lues"] == 3
    assert out["apercu"][0]["titre"] == "a" and out["apercu"][0]["lien"] == "https://shop.example/item/a" and out["apercu"][0]["prix"] == "1€"
    assert len(list(csv.DictReader(open(site.sent[0], encoding="utf-8-sig")))) == 4


def test_champs_respects_robots_txt_when_paging(site):
    site.pages["https://shop.example/robots.txt"] = (200, "text/plain", "User-agent: *\nDisallow: /l?p=2")
    site.pages["https://shop.example/l?p=1"] = products(["a"], "/l?p=2")
    site.pages["https://shop.example/l?p=2"] = products(["b"])
    out = run("scraper", url="https://shop.example/l?p=1", mode="champs", selecteur=".p", champs=CHAMPS, suivant="a.next", pages=5)
    assert out["lignes"] == 1 and "https://shop.example/l?p=2" not in site.hits


def test_champs_never_follows_a_next_link_to_another_site_or_in_a_loop(site):
    site.pages["https://shop.example/l"] = products(["a"], "https://evil.example/l")
    out = run("scraper", url="https://shop.example/l", mode="champs", selecteur=".p", champs=CHAMPS, suivant="a.next", pages=5)
    assert out["pages_lues"] == 1 and not any("evil.example" in h for h in site.hits)
    site.pages["https://shop.example/m"] = products(["a"], "/m")
    assert run("scraper", url="https://shop.example/m", mode="champs", selecteur=".p", champs=CHAMPS, suivant="a.next", pages=5)["pages_lues"] == 1


def test_champs_errors_are_explained(site):
    site.pages["https://shop.example/l"] = products(["a"])
    assert "selecteur" in run("scraper", url="https://shop.example/l", mode="champs")["erreur"]
    assert "JSON" in run("scraper", url="https://shop.example/l", mode="champs", selecteur=".p", champs="pas du json")["erreur"]
    assert "invalide" in run("scraper", url="https://shop.example/l", mode="champs", selecteur="div[[[", champs=CHAMPS)["erreur"]
    assert "rien trouve" in run("scraper", url="https://shop.example/l", mode="champs", selecteur=".absent", champs=CHAMPS)["resultat"]


def test_champs_without_fields_gives_text_and_link(site):
    site.pages["https://shop.example/l"] = products(["a"])
    out = run("scraper", url="https://shop.example/l", mode="champs", selecteur=".p")
    assert out["apercu"][0]["lien"] == "https://shop.example/item/a" and "a" in out["apercu"][0]["texte"]


# ---- scraper : safety and robustness --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["http://192.168.1.64:8080/", "http://localhost/admin", "file:///etc/passwd", "javascript:alert(1)", "", "ftp://x.example/a"])
def test_private_and_odd_addresses_are_refused_and_nothing_is_fetched(site, url):
    out = run("scraper", url=url)
    assert "erreur" in out and site.hits == []


def test_download_errors_and_http_errors_are_reported(site):
    site.pages["https://a.example/boom"] = requests.ConnectionError("dns")
    site.pages["https://a.example/gone"] = (503, "text/html", "<html></html>")
    assert "erreur" in run("scraper", url="https://a.example/boom")
    assert "503" in run("scraper", url="https://a.example/gone")["erreur"]


def test_binary_content_is_refused(site):
    site.pages["https://a.example/f.zip"] = (200, "application/zip", b"PK\x03\x04")
    assert "pas une page web" in run("scraper", url="https://a.example/f.zip")["erreur"]


def test_unknown_mode_and_the_body_is_cut(site):
    assert "mode" in run("scraper", url="https://a.example/", mode="hack")["erreur"]
    site.pages["https://a.example/big"] = "<html><body>" + "a" * (kit_scrape.PAGE_BYTES + 500_000)
    seen = []
    orig = kit_scrape._soup
    kit_scrape._soup = lambda raw: seen.append(len(raw)) or orig(raw)
    try:
        run("scraper", url="https://a.example/big", mode="meta")
    finally:
        kit_scrape._soup = orig
    assert seen and seen[0] <= kit_scrape.PAGE_BYTES


def test_an_empty_shell_is_rendered_with_lightpanda(site, monkeypatch):
    site.pages["https://app.example/"] = "<html><head><title>x</title></head><body><div id='root'></div></body></html>"
    monkeypatch.setattr(kit_scrape, "LIGHTPANDA", __file__)                      # "exists"
    seen = []

    def fake_run(cmd, capture_output=True, timeout=None):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"<html><body><h1>Rendu</h1>" + b"y" * 400 + b"</body></html>", b"")
    monkeypatch.setattr(kit_scrape.subprocess, "run", fake_run)
    out = run("scraper", url="https://app.example/", mode="meta")
    assert out["h1"] == ["Rendu"] and seen[0][:3] == ["nice", "-n", "10"] and seen[0][-1] == "https://app.example/"


def test_a_lightpanda_timeout_falls_back_to_the_plain_page(site, monkeypatch):
    site.pages["https://app.example/"] = "<html><head><title>Coquille</title></head><body></body></html>"
    monkeypatch.setattr(kit_scrape, "LIGHTPANDA", __file__)

    def slow(cmd, capture_output=True, timeout=None):
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(kit_scrape.subprocess, "run", slow)
    assert run("scraper", url="https://app.example/", mode="meta")["titre"] == "Coquille"


# ---- crawler ------------------------------------------------------------------------------------------------------------------------------------

def small_site(site):
    site.pages["https://s.example/"] = page("<a href='/a'>a</a><a href='/b'>b</a><a href='/prive/x'>p</a><a href='https://other.example/z'>o</a><a href='/doc.pdf'>pdf</a><a href='/casse'>c</a>", "Accueil")
    site.pages["https://s.example/a"] = page("<a href='/'>home</a><a href='/b'>b</a>", "Page A")
    site.pages["https://s.example/b"] = page("<h1>B</h1>", "Page A")                                 # same title as /a: a duplicate
    site.pages["https://s.example/robots.txt"] = (200, "text/plain", "User-agent: *\nDisallow: /prive/")


def test_crawler_reads_the_site_reports_problems_and_exports(site):
    small_site(site)
    out = run("crawler", url="https://s.example/", pages=20)
    assert out["site"] == "s.example" and out["envoye"] is True
    assert out["liens_casses"] == [{"url": "https://s.example/casse", "statut": 404, "trouve_sur": "https://s.example/"}]
    assert out["titres_en_double"] == 1 and out["interdit_par_robots"] == 1 and out["sans_description"] >= 3
    assert not any("other.example" in h or h.endswith(".pdf") or "/prive/" in h and not h.endswith("robots.txt") for h in site.hits)
    rows = list(csv.DictReader(open(site.sent[0], encoding="utf-8-sig")))
    assert {r["url"] for r in rows} >= {"https://s.example/", "https://s.example/a", "https://s.example/casse"}


def test_crawler_stops_at_the_page_limit_and_the_pattern_filters(site):
    small_site(site)
    assert run("crawler", url="https://s.example/", pages=2)["pages_lues"] == 2
    site.hits.clear()
    run("crawler", url="https://s.example/", pages=20, motif="/a")
    assert "https://s.example/b" not in site.hits


def test_crawler_stops_on_the_time_limit_and_says_so(site, monkeypatch):
    small_site(site)
    clock = iter(range(0, 10_000, 100))
    monkeypatch.setattr(kit_scrape.time, "time", lambda: next(clock))
    out = run("crawler", url="https://s.example/", pages=20)
    assert "secondes" in out["note"] and out["pages_lues"] < 20


def test_crawler_refuses_private_sites_and_honours_a_full_robots_ban(site):
    assert "erreur" in run("crawler", url="http://192.168.1.64/")
    site.pages["https://s.example/robots.txt"] = (200, "text/plain", "User-agent: *\nDisallow: /")
    site.pages["https://s.example/"] = page("<a href='/a'>a</a>")
    out = run("crawler", url="https://s.example/")
    assert out["interdit_par_robots"] == 1 and "https://s.example/" not in site.hits


def test_a_server_error_on_robots_txt_means_do_not_crawl(site):
    site.pages["https://s.example/robots.txt"] = (503, "text/html", "down")
    site.pages["https://s.example/"] = page("<a href='/a'>a</a>")
    assert run("crawler", url="https://s.example/")["interdit_par_robots"] == 1


def test_a_redirect_to_another_site_is_not_followed_further(site):
    site.pages["https://s.example/"] = page("<a href='/go'>go</a>")

    class Hop(FakeResponse):
        pass
    real = kit_scrape.web.safe_get
    kit_scrape.web.safe_get = lambda url, **kw: (Hop("https://elsewhere.example/landing", 200, "text/html", page("<a href='/more'>m</a>").encode()) if url.endswith("/go") else real(url, **kw))
    try:
        out = run("crawler", url="https://s.example/")
    finally:
        kit_scrape.web.safe_get = real
    assert out["pages_lues"] == 2 and not any("more" in h for h in site.hits)


# ---- sitemap_lire --------------------------------------------------------------------------------------------------------------------------------

URLSET = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>"""


def entries(*urls):
    return "".join(f"<url><loc>{u}</loc><lastmod>2026-10-0{i}</lastmod></url>" for i, u in enumerate(urls, 1))


def test_sitemap_follows_robots_txt_and_an_index_and_ignores_other_hosts(site):
    site.pages["https://s.example/robots.txt"] = (200, "text/plain", "Sitemap: https://s.example/index.xml\n")
    site.pages["https://s.example/index.xml"] = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://s.example/blog.xml</loc></sitemap><sitemap><loc>https://evil.example/x.xml</loc></sitemap></sitemapindex>"""
    site.pages["https://s.example/blog.xml"] = URLSET.format(entries("https://s.example/blog/a", "https://s.example/blog/b", "https://s.example/", "https://evil.example/c"))
    out = run("sitemap_lire", url="https://s.example/")
    assert out["pages"] == 3 and out["rubriques"]["blog"] == 2 and out["envoye"] is True
    assert out["dernieres_modifiees"][0]["url"] == "https://s.example/" and not any("evil.example" in h for h in site.hits)


def test_sitemap_default_location_gzip_and_nothing_found(site):
    site.pages["https://s.example/sitemap.xml"] = (200, "application/xml", URLSET.format(entries("https://s.example/a")))
    assert run("sitemap_lire", url="s.example")["pages"] == 1
    site.pages["https://g.example/s.xml.gz"] = (200, "application/gzip", gzip.compress(URLSET.format(entries("https://g.example/a")).encode()))
    assert run("sitemap_lire", url="https://g.example/s.xml.gz")["pages"] == 1
    assert "aucun sitemap" in run("sitemap_lire", url="https://nope.example/")["resultat"]


def test_sitemap_does_not_expand_xml_entities_or_read_local_files(site):
    evil = """<?xml version="1.0"?><!DOCTYPE x [<!ENTITY f SYSTEM "file:///etc/passwd">]><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://s.example/&f;</loc></url></urlset>"""
    site.pages["https://s.example/sitemap.xml"] = (200, "application/xml", evil)
    out = run("sitemap_lire", url="https://s.example/")
    assert "root:" not in str(out)


def test_sitemap_refuses_private_hosts(site):
    assert "erreur" in run("sitemap_lire", url="http://localhost/")


# ---- capture_page --------------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def chromium(site, monkeypatch):
    site.pages["https://a.example/"] = page("hello")
    calls = site.runs

    def fake_run(cmd, capture_output=True, timeout=None):
        calls.append(cmd)
        assert cmd[:3] == ["nice", "-n", "10"]
        for arg in cmd:
            for flag in ("--screenshot=", "--print-to-pdf="):
                if arg.startswith(flag):
                    with open(arg[len(flag):], "wb") as f:
                        f.write(b"\x89PNG" + b"0" * 2048)
        return subprocess.CompletedProcess(cmd, 0, b"", b"dbus noise")
    monkeypatch.setattr(kit_scrape.subprocess, "run", fake_run)
    return site


def test_capture_page_png_is_sent_and_uses_a_throwaway_profile(chromium):
    out = run("capture_page", url="https://a.example/")
    cmd = chromium.runs[0]
    assert out["envoye"] is True and out["fichier"].endswith(".png") and out["page"] == "https://a.example/"
    assert chromium.sent[0].startswith(str(chromium.work)) and cmd[-1] == "https://a.example/"
    profile = next(a for a in cmd if a.startswith("--user-data-dir="))[len("--user-data-dir="):]
    assert not os.path.exists(profile) and "--headless=new" in cmd and "--window-size=1280,900" in cmd


def test_capture_page_pdf_and_full_page(chromium):
    out = run("capture_page", url="https://a.example/", format="pdf")
    assert out["fichier"].endswith(".pdf") and any(a.startswith("--print-to-pdf=") for a in chromium.runs[0]) and "--no-pdf-header-footer" in chromium.runs[0]
    run("capture_page", url="https://a.example/", pleine_page=True)
    assert "--window-size=1280,3000" in chromium.runs[1]


def test_capture_page_refuses_private_addresses_and_never_starts_chromium(chromium):
    for url in ("http://192.168.1.64:3001/", "http://localhost:9223/json", "file:///etc/passwd"):
        assert "erreur" in run("capture_page", url=url)
    assert chromium.runs == []


def test_capture_page_failure_is_reported(site, monkeypatch):
    site.pages["https://a.example/"] = page("hi")
    monkeypatch.setattr(kit_scrape.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b"boom"))
    assert "impossible" in run("capture_page", url="https://a.example/")["erreur"]


# ---- wiring -------------------------------------------------------------------------------------------------------------------------------------

def test_every_scraper_tool_is_tainted_registered_and_reachable_by_natural_french():
    assert kit_scrape.TAINT == set(kit_scrape.FUNCS) <= kits.TAINT
    for name in kit_scrape.FUNCS:
        assert name in kits.FUNCS
    for words, tool in (("scrape les prix de ce site", "scraper"), ("recupere les emails du site exemple.fr", "scraper"), ("extrais le tableau de cette page", "scraper"),
                        ("crawl tout le site", "crawler"), ("trouve les liens casses de mon site", "crawler"), ("lis le sitemap de oqro.io", "sitemap_lire"),
                        ("fais une capture d'ecran de cette page", "capture_page"), ("donne moi cette page en pdf", "capture_page")):
        assert tool in {t["function"]["name"] for t in catalog.select_tools(words)}, words


def test_small_talk_does_not_bring_the_scraper_tools():
    for words in ("salut", "merci beaucoup", "ecris un mail a Paul pour demain", "mets la chaine 3", "quel temps fait-il demain"):
        assert not {t["function"]["name"] for t in catalog.select_tools(words)} & set(kit_scrape.FUNCS), words
