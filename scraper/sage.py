"""Sage: journals.sagepub.com/page/{code}/call-for-papers."""
import logging
import re

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html, is_generic_title,
                          normalize_title)

log = logging.getLogger("cfp.scraper.sage")


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "Sage":
            continue
        m = re.search(r"journals\.sagepub\.com/home/(\w+)", j.get("homepage") or "")
        if not m:
            continue
        url = f"https://journals.sagepub.com/page/{m.group(1)}/call-for-papers"
        html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        main = soup.find("main") or soup
        seen = set()
        for h in main.find_all(["h2", "h3", "h4"]):
            title = clean(h.get_text())
            if len(title) < 12 or is_generic_title(title):
                continue
            ctx = " ".join(clean(s.get_text(" ")) for s in h.find_next_siblings(limit=6))
            if not re.search(r"deadline|submission", ctx, re.I):
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            link = h.find("a", href=True)
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": link["href"] if link else url,
                "deadline": extract_deadline(ctx),
                "description": None,
            })
    log.info("Sage: %d Treffer", len(results))
    return results
