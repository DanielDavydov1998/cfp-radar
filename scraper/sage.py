"""Sage: journals.sagepub.com/page/{code}/call-for-papers (via Jina-Proxy).

Struktur: jeder Call ist ein <p> in div.pb-rich-text nach dem Muster
"<Titel>: First round submission deadline: <Datum>."
"""
import logging
import re

from bs4 import BeautifulSoup

from scraper.base import (DEADLINE_RE, clean, extract_deadline, get_html_hard,
                          is_generic_title, normalize_title)

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
        html = get_html_hard(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        seen = set()
        for p in soup.select("div.pb-rich-text p") or soup.find_all("p"):
            text = clean(p.get_text(" "))
            dm = DEADLINE_RE.search(text)
            if not dm:
                continue
            # Titel = alles vor der Deadline-Phrase; ggf. "First round" abtrennen
            title = text[:dm.start()]
            title = re.sub(r"(?:first|second)\s+round\s*$", "", title, flags=re.I)
            title = title.strip(" :–-.,")
            if len(title) < 12 or is_generic_title(title):
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            link = p.find("a", href=True)
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": link["href"] if link else url,
                "deadline": extract_deadline(text),
                "description": None,
            })
    log.info("Sage: %d Treffer", len(results))
    return results
