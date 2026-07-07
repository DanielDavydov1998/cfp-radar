"""AISWorld-Mailinglisten-Archiv (Pipermail).

Hinweis: Das öffentliche Archiv wird seit der AIS-Plattform-Migration kaum noch
bespielt (letzter Post 10/2025). Der Adapter bleibt aktiv, falls die Liste
wieder auflebt – er kostet pro Lauf nur wenige Requests.
"""
import logging
import re
import time

from bs4 import BeautifulSoup

from scraper.base import clean, extract_deadline, get_html, match_journals, normalize_title

log = logging.getLogger("cfp.scraper.aisworld")

INDEX = "https://lists.aisnet.org/pipermail/aisworld_lists.aisnet.org/"
CFP_RE = re.compile(r"call\s+for\s+papers?|special\s+issue|\bcfp\b", re.I)
# Konferenz-CFPs aussortieren – uns interessieren nur Journal-Calls
CONF_RE = re.compile(r"conference|workshop|symposium|\btrack\b|proceedings|"
                     r"\b(?:IC|EC|AMC|HIC|PAC|WHIC)IS\b|\bHICSS\b|\bWI\d{2,4}\b", re.I)
N_PERIODS = 15  # wie viele der neuesten Archiv-Perioden durchsucht werden
MAX_MSG_FETCHES = 60  # Obergrenze Einzelnachrichten-Abrufe pro Lauf


def scrape(journals):
    html = get_html(INDEX, browser_fallback=False)
    if not html:
        log.warning("AISWorld-Index nicht erreichbar")
        return []
    periods = sorted(set(re.findall(r'href="(\d{8})/(?:thread|subject|date)\.html"',
                                    html, re.I)), reverse=True)
    results, fetched = [], 0
    for period in periods[:N_PERIODS]:
        sub = get_html(f"{INDEX}{period}/subject.html", browser_fallback=False)
        if not sub:
            continue
        soup = BeautifulSoup(sub, "lxml")
        for a in soup.find_all("a", href=re.compile(r"^\d+\.html$")):
            subject = clean(a.get_text())
            if not CFP_RE.search(subject) or CONF_RE.search(subject):
                continue
            matched = match_journals(subject, journals)
            if not matched:
                continue
            url = f"{INDEX}{period}/{a['href']}"
            deadline = None
            if fetched < MAX_MSG_FETCHES:
                msg = get_html(url, browser_fallback=False)
                fetched += 1
                time.sleep(0.3)
                if msg:
                    body = BeautifulSoup(msg, "lxml").get_text(" ")
                    deadline = extract_deadline(body)
            title = normalize_title(subject)
            for j in matched:
                results.append({
                    "journal_id": j["id"],
                    "title": title,
                    "url": url,
                    "deadline": deadline,
                    "description": None,
                })
    log.info("AISWorld: %d Treffer", len(results))
    return results
