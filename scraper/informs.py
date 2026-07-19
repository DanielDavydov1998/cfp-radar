"""INFORMS (Atypon): pubsonline.informs.org/page/{code}/calls-for-papers."""
import logging
import re

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html_hard,
                          is_generic_title, normalize_title)

log = logging.getLogger("cfp.scraper.informs")


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "INFORMS":
            continue
        m = re.search(r"pubsonline\.informs\.org/journal/(\w+)", j.get("homepage") or "")
        if not m:
            continue
        code = m.group(1)
        for page in ("calls-for-papers", "special-issues"):
            url = f"https://pubsonline.informs.org/page/{code}/{page}"
            html = get_html_hard(url)
            if not html:
                continue
            found = _parse_sections(html, url, j)
            results += found
            if found:
                break  # eine ergiebige Seite pro Journal reicht
    log.info("INFORMS: %d Treffer", len(results))
    return results


def _parse_sections(html, url, j):
    """CFPs stehen als Freitext-Abschnitte: Überschrift + Text mit 'Deadline: ...'."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    out, seen = [], set()
    for h in main.find_all(["h1", "h2", "h3", "h4"]):
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
        out.append({
            "journal_id": j["id"],
            "title": normalize_title(title),
            "url": link["href"] if link else url,
            "deadline": extract_deadline(ctx),
            "description": None,
        })
    return out
