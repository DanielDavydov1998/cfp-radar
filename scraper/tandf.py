"""Taylor & Francis: Special-Issue-Listing pro Journal (JS-gerendert -> Browser)
plus JMIS über die eigene Seite jmis-web.org."""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import clean, extract_deadline, get_html, is_generic_title, normalize_title

log = logging.getLogger("cfp.scraper.tandf")

JMIS_URL = "https://www.jmis-web.org/"


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "Taylor & Francis":
            continue
        if (j.get("abbrev") or "") == "JMIS":
            results += _scrape_jmis(j)
            continue
        m = re.search(r"tandfonline\.com/journals/(\w+)", j.get("homepage") or "")
        if not m:
            continue
        url = f"https://www.tandfonline.com/journals/{m.group(1)}/special-issues"
        html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = clean(a.get_text())
            if not ("special_issues" in href or "special-issue" in href
                    or re.search(r"call\s+for\s+papers?", text, re.I)):
                continue
            if len(text) < 15 or is_generic_title(text):
                continue
            full = urljoin(url, href)
            if full in seen or full.rstrip("/") == url.rstrip("/"):
                continue
            seen.add(full)
            container = a.find_parent(["article", "li", "section", "div"]) or a
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(text),
                "url": full,
                "deadline": extract_deadline(clean(container.get_text(" "))),
                "description": None,
            })
    log.info("T&F: %d Treffer", len(results))
    return results


def _scrape_jmis(j):
    html = get_html(JMIS_URL, browser_fallback=False)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = clean(a.get_text())
        if not re.search(r"special\s+issue|call\s+for\s+papers?", text, re.I):
            continue
        if len(text) < 15 or is_generic_title(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        container = a.find_parent(["article", "li", "section", "div"]) or a
        out.append({
            "journal_id": j["id"],
            "title": normalize_title(text),
            "url": urljoin(JMIS_URL, a["href"]),
            "deadline": extract_deadline(clean(container.get_text(" "))),
            "description": None,
        })
    return out
