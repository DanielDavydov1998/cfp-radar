"""IEEE Computer Society: zentrale CFP-Seite auf computer.org (via Jina-Proxy).

Struktur (Next.js, gerendert): Karten-Divs mit einem Link "Call for Papers: ..."
plus Label "Journal - <Name>" und Beschreibungstext. Deadlines stehen meist
erst auf der Detailseite (direkt abrufbar, Deadline steckt im RSC-Payload).
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html, get_html_jina,
                          match_journals, normalize_title)

log = logging.getLogger("cfp.scraper.ieeecs")

URL = "https://www.computer.org/publications/author-resources/calls-for-papers"
MAX_DETAIL_FETCHES = 12


def scrape(journals):
    ieee_journals = [j for j in journals if j.get("publisher") == "IEEE"]
    if not ieee_journals:
        return []
    html = get_html_jina(URL) or get_html(URL, browser_fallback=False)
    if not html:
        log.warning("computer.org nicht erreichbar")
        return []
    soup = BeautifulSoup(html, "lxml")
    results, seen, detail_fetches = [], set(), 0
    for a in soup.find_all("a", href=True):
        a_text = clean(a.get_text())
        if not a_text.lower().startswith("call for papers"):
            continue
        title = re.sub(r"^call\s+for\s+papers?\s*[:\-–]?\s*", "", a_text, flags=re.I)
        card = a
        for _ in range(4):
            if card.parent is None:
                break
            card = card.parent
            if len(clean(card.get_text())) > 150:
                break
        card_text = clean(card.get_text(" "))[:800]
        matched = match_journals(card_text, ieee_journals)
        if not matched or len(title) < 5:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        href = urljoin(URL, a["href"])
        deadline = extract_deadline(card_text)
        if not deadline and detail_fetches < MAX_DETAIL_FETCHES:
            detail_fetches += 1
            detail = get_html(href, browser_fallback=False)
            if detail:
                # Deadline steckt oft im eingebetteten Next.js-Payload ->
                # Regex über das rohe HTML statt über den sichtbaren Text
                deadline = extract_deadline(detail)
        # Karten ohne Topic (Titel = nur Journalname) sind Dauer-Aufrufe des
        # Journals, keine Special Issues - nur behalten, wenn Deadline dran ist
        plain_journal = any(title.lower() == (j["name"] or "").lower()
                            or title.lower() == f"ieee {j['name']}".lower()
                            for j in matched)
        if plain_journal and not deadline:
            continue
        for j in matched:
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": href,
                "deadline": deadline,
                "description": None,
            })
    log.info("IEEE CS: %d Treffer", len(results))
    return results
