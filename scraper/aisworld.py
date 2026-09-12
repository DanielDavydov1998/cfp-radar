"""AISWorld-Mailingliste – seit der AIS-Migration auf LISTSERV
(listserv.isworld.org, öffentlich lesbar, löst das tote Pipermail-Archiv ab).

Praktisch alle IS-Journals streuen ihre CFPs hier; damit sind auch Journals
ohne scrapebare Verlagsseite abgedeckt (THCI, CAIS, MISQE, Elsevier-IS-Titel).
"""
import logging
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import clean, extract_deadline, get_html, match_journals, normalize_title

log = logging.getLogger("cfp.scraper.aisworld")

BASE = "https://listserv.isworld.org"
HOME = BASE + "/scripts/wa-ISWORLD.exe?A0=AISWORLD"
CFP_RE = re.compile(r"call\s+for\s+papers?|special\s+issue|\bcfp\b", re.I)
# Konferenz-/Workshop-CFPs aussortieren – uns interessieren nur Journal-Calls
CONF_RE = re.compile(r"conference|workshop|symposium|\btrack\b|proceedings|"
                     r"\b(?:IC|EC|AMC|HIC|PAC|WHIC)IS\b|\bHICSS\b|\bCAiSE\b|"
                     r"\bWI\d{2,4}\b|pre-icis|doctoral consortium", re.I)
MAX_MSG_FETCHES = 40  # Obergrenze Einzelnachrichten-Abrufe pro Lauf


def scrape(journals):
    html = get_html(HOME, browser_fallback=False)
    if not html:
        log.warning("AISWorld-Archiv (listserv.isworld.org) nicht erreichbar")
        return []
    soup = BeautifulSoup(html, "lxml")
    results, fetched, seen = [], 0, set()
    for a in soup.find_all("a", href=re.compile(r"A2=")):
        subject = clean(a.get_text())
        # Mailinglisten-Präfixe wie "[wkwi]" vor der Prüfung entfernen
        subject = re.sub(r"^(?:\[[^\]]{1,20}\]\s*)+", "", subject)
        if not CFP_RE.search(subject) or CONF_RE.search(subject):
            continue
        matched = match_journals(subject, journals)
        if not matched:
            continue
        title = normalize_title(subject)
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        url = urljoin(BASE, a["href"])
        deadline = None
        if fetched < MAX_MSG_FETCHES:
            msg = get_html(url, browser_fallback=False)
            fetched += 1
            time.sleep(0.5)
            if msg:
                body = clean(BeautifulSoup(msg, "lxml").get_text(" "))
                deadline = extract_deadline(body)
        for j in matched:
            results.append({
                "journal_id": j["id"],
                "title": title,
                "url": url,
                "deadline": deadline,
                "description": None,
            })
    log.info("AISWorld: %d Treffer (%d Nachrichten geladen)", len(results), fetched)
    return results
