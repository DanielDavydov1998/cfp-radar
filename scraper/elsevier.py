"""Elsevier/ScienceDirect: /journal/{slug}/about/call-for-papers.

ScienceDirect blockt alle HTTP-Clients hart (403) – läuft komplett über den
Playwright-Browser-Fallback in base.get_html().
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import clean, extract_deadline, get_html, is_generic_title, normalize_title

log = logging.getLogger("cfp.scraper.elsevier")


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "Elsevier":
            continue
        m = re.search(r"sciencedirect\.com/journal/([a-z0-9-]+)", j.get("homepage") or "")
        if not m:
            continue
        url = f"https://www.sciencedirect.com/journal/{m.group(1)}/about/call-for-papers"
        html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        seen = set()
        # CFP-Einträge: Überschriften mit anschließendem Text inkl. Deadline
        for h in soup.find_all(["h2", "h3", "h4"]):
            title = clean(h.get_text())
            if len(title) < 12 or is_generic_title(title):
                continue
            ctx = " ".join(clean(s.get_text(" ")) for s in h.find_next_siblings(limit=6))
            if not re.search(r"deadline|submission|submit", ctx, re.I):
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            link = h.find("a", href=True) or (h.find_next_sibling("a", href=True))
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": urljoin(url, link["href"]) if link else url,
                "deadline": extract_deadline(ctx),
                "description": None,
            })
    log.info("Elsevier: %d Treffer", len(results))
    return results
