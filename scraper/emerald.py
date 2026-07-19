"""Emerald: zentrale CFP-Liste auf emeraldgrouppublishing.com (direkt abrufbar).

Die Liste umfasst alle Emerald-Journals mit Pagination; wir matchen die Karten
gegen unsere Journals (ITP, Internet Research, JOSM) und holen die Deadline
von der Detailseite.
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html, is_generic_title,
                          match_journals, normalize_title)

log = logging.getLogger("cfp.scraper.emerald")

BASE = "https://www.emeraldgrouppublishing.com"
LIST_URL = BASE + "/calls-for-papers"
MAX_PAGES = 15


def scrape(journals):
    emerald_journals = [j for j in journals if j.get("publisher") == "Emerald"]
    if not emerald_journals:
        return []
    results, seen = [], set()
    for page in range(MAX_PAGES):
        url = LIST_URL if page == 0 else f"{LIST_URL}?page={page}"
        html = get_html(url, browser_fallback=False)
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        cards = _cards(soup)
        if not cards:
            break
        for title, card_text, link in cards:
            matched = match_journals(card_text, emerald_journals)
            if not matched:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            detail_url = urljoin(BASE, link) if link else url
            deadline = None
            detail = get_html(detail_url, browser_fallback=False)
            if detail:
                deadline = extract_deadline(
                    clean(BeautifulSoup(detail, "lxml").get_text(" ")))
            for j in matched:
                results.append({
                    "journal_id": j["id"],
                    "title": normalize_title(title),
                    "url": detail_url,
                    "deadline": deadline,
                    "description": None,
                })
    log.info("Emerald: %d Treffer", len(results))
    return results


def _cards(soup):
    """(Titel, Kartentext, Link) je CFP-Karte der Übersichtsseite."""
    out = []
    for h in soup.find_all(["h2", "h3"]):
        title = clean(h.get_text())
        if len(title) < 25 or is_generic_title(title):
            continue
        if re.search(r"menu|pagination|footer", title, re.I):
            continue
        card = h
        for _ in range(4):
            parent = card.parent
            if parent is None or parent.name in ("body", "html", "main"):
                break
            card = parent
            if len(clean(card.get_text())) > 120:
                break
        link = None
        node = h
        for _ in range(5):
            if node is None:
                break
            if getattr(node, "name", None) == "a" and node.get("href"):
                link = node["href"]
                break
            found = node.find("a", href=re.compile(r"/calls-for-papers/")) \
                if hasattr(node, "find") else None
            if found is not None:
                link = found["href"]
                break
            node = node.parent
        out.append((title, clean(card.get_text(" "))[:600], link))
    return out
