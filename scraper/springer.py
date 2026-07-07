"""Springer: link.springer.com/journal/{id}/updates + BISE-Sonderfall (bise-journal.com)."""
import logging
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html, is_generic_title,
                          normalize_title)

log = logging.getLogger("cfp.scraper.springer")

CFP_RE = re.compile(r"call\s+for\s+papers?|special\s+issue|topical\s+collection", re.I)


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "Springer":
            continue
        if (j.get("abbrev") or "") == "BISE":
            results += _scrape_bise(j)
            continue
        m = re.search(r"link\.springer\.com/journal/(\d+)", j.get("homepage") or "")
        if not m:
            continue
        url = f"https://link.springer.com/journal/{m.group(1)}/updates"
        html = get_html(url, browser_fallback=False)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        seen = set()
        for a in soup.find_all("a", href=True):
            text = clean(a.get_text())
            if len(text) < 15 or not CFP_RE.search(text) or is_generic_title(text):
                continue
            href = urljoin(url, a["href"])
            if href in seen:
                continue
            seen.add(href)
            container = a.find_parent(["article", "li", "section", "div"]) or a
            ctx = clean(container.get_text(" "))
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(text),
                "url": href,
                "deadline": extract_deadline(ctx),
                "description": None,
            })
    log.info("Springer: %d Treffer", len(results))
    return results


ISSUE_PREFIX_RE = re.compile(r"^(\d{2})/(\d{4})")


def _scrape_bise(j):
    """BISE hat keine /updates-Seite; CFPs stehen auf bise-journal.com (WordPress, ?cat=6).

    Die Kategorie listet auch Jahre alte Calls – Titel tragen ein Heft-Präfix
    wie "01/2027", darüber filtern wir Veraltetes aus.
    """
    html = get_html("https://bise-journal.com/?cat=6", browser_fallback=False)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for h in soup.find_all(["h1", "h2", "h3"]):
        a = h.find("a", href=True)
        if not a:
            continue
        title = clean(a.get_text())
        if len(title) < 10 or is_generic_title(title) or title.lower() in seen:
            continue
        m = ISSUE_PREFIX_RE.match(title)
        if m and int(m.group(2)) < date.today().year:
            continue  # Call für ein bereits erschienenes/altes Heft
        seen.add(title.lower())
        container = h.find_parent(["article", "div"]) or h
        out.append({
            "journal_id": j["id"],
            "title": normalize_title(title),
            "url": a["href"],
            "deadline": extract_deadline(clean(container.get_text(" "))),
            "description": None,
        })
    return out
