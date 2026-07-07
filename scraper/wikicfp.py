"""WikiCFP als Ergänzungsquelle (nur http://, https ist dort kaputt)."""
import logging
import re

import dateparser
from bs4 import BeautifulSoup

from scraper.base import clean, get_html, match_journals, normalize_title

log = logging.getLogger("cfp.scraper.wikicfp")

SEARCH_URL = 'http://www.wikicfp.com/cfp/servlet/tool.search?q=%22special+issue%22&year=t'
BASE = "http://www.wikicfp.com"


def scrape(journals):
    html = get_html(SEARCH_URL, browser_fallback=False)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    results, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"event\.showcfp\?eventid=")):
        tr = a.find_parent("tr")
        if tr is None:
            continue
        next_tr = tr.find_next_sibling("tr")
        row_text = clean(tr.get_text(" ")) + " " + (clean(next_tr.get_text(" ")) if next_tr else "")
        matched = match_journals(row_text, journals)
        if not matched:
            continue
        href = BASE + a["href"] if a["href"].startswith("/") else a["href"]
        if href in seen:
            continue
        seen.add(href)
        # Deadline steht in der letzten Spalte der zweiten Zeile
        deadline = None
        if next_tr:
            cells = [clean(td.get_text()) for td in next_tr.find_all("td")]
            if cells:
                m = re.search(r"[A-Za-z]{3}\s+\d{1,2},\s+\d{4}", cells[-1])
                if m:
                    dt = dateparser.parse(m.group(0), languages=["en"])
                    deadline = dt.strftime("%Y-%m-%d") if dt else None
        title = clean(tr.get_text(" "))
        for j in matched:
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": href,
                "deadline": deadline,
                "description": None,
            })
    log.info("WikiCFP: %d Treffer", len(results))
    return results
