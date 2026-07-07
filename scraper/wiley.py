"""Wiley (Atypon): onlinelibrary.wiley.com/page/journal/{id}/call-for-papers."""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html, is_generic_title,
                          normalize_title)

log = logging.getLogger("cfp.scraper.wiley")


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "Wiley":
            continue
        m = re.search(r"onlinelibrary\.wiley\.com/journal/(\w+)", j.get("homepage") or "")
        if not m:
            continue
        url = f"https://onlinelibrary.wiley.com/page/journal/{m.group(1)}/call-for-papers"
        html = get_html(url)
        if not html:
            continue  # Journals ohne CFP-Seite liefern 404 – einfach überspringen
        soup = BeautifulSoup(html, "lxml")
        seen = set()
        # Einzel-Calls sind unter .../call-for-papers/si-... verlinkt
        for a in soup.find_all("a", href=re.compile(r"call-for-papers/", re.I)):
            title = clean(a.get_text())
            href = urljoin(url, a["href"])
            if (len(title) < 10 or href in seen or is_generic_title(title)
                    or href.rstrip("/") == url.rstrip("/")):
                continue
            seen.add(href)
            container = a.find_parent(["article", "li", "section", "div"]) or a
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": href,
                "deadline": extract_deadline(clean(container.get_text(" "))),
                "description": None,
            })
        # Fallback: Überschriften mit Deadline im Umfeld, falls keine si-Links vorhanden
        if not seen:
            for h in soup.find_all(["h2", "h3"]):
                title = clean(h.get_text())
                if len(title) < 15 or is_generic_title(title):
                    continue
                ctx = " ".join(clean(s.get_text(" ")) for s in h.find_next_siblings(limit=4))
                dl = extract_deadline(ctx)
                if dl:
                    results.append({
                        "journal_id": j["id"],
                        "title": normalize_title(title),
                        "url": url,
                        "deadline": dl,
                        "description": None,
                    })
    log.info("Wiley: %d Treffer", len(results))
    return results
