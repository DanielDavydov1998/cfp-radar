"""callsforpapers.org (Julian Prester) – gepflegter CFP-Datensatz für die 13
Kern-IS-Journals, inkl. des kompletten AIS Basket of 11.

Die Rohdaten liegen als calls.json im öffentlichen GitHub-Repo; damit sind
genau die Verlage abgedeckt, die Scraper hart blockieren (Elsevier/Science-
Direct, Wiley, INFORMS, Sage, MISQ, T&F).
"""
import json
import logging
import re
from datetime import date, timedelta

from scraper.base import clean, get_html, normalize_title

log = logging.getLogger("cfp.scraper.cfpsorg")

DATA_URL = ("https://raw.githubusercontent.com/julianprester/"
            "calls-for-papers/main/www/_data/calls.json")


def _norm(name):
    n = (name or "").lower().strip()
    n = re.sub(r"^the\s+", "", n)
    n = n.replace("&", "and")
    return re.sub(r"\s+", " ", n)


def scrape(journals):
    raw = get_html(DATA_URL, browser_fallback=False)
    if not raw:
        log.warning("calls.json nicht erreichbar")
        return []
    try:
        calls = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("calls.json nicht parsebar")
        return []

    by_name = {_norm(j["name"]): j for j in journals}
    results, unmatched = [], set()
    for c in calls:
        j = by_name.get(_norm(c.get("journal")))
        if not j:
            unmatched.add(c.get("journal"))
            continue
        deadline = None
        for d in c.get("dates") or []:
            if d.get("is_full_paper_submission_deadline") and d.get("date"):
                deadline = d["date"][:10]
                break
        # Der Datensatz enthält auch ein Archiv alter Calls: Einträge ohne
        # Deadline nur übernehmen, wenn sie im letzten Jahr publiziert wurden
        if not deadline:
            pub = (c.get("pubDate") or "")[:10]
            if not pub or pub < (date.today() - timedelta(days=365)).isoformat():
                continue
        desc_raw = c.get("description")
        if isinstance(desc_raw, dict):
            desc_raw = " ".join(v for v in desc_raw.values() if isinstance(v, str))
        elif not isinstance(desc_raw, str):
            desc_raw = ""
        desc = clean(re.sub(r"<[^>]+>", " ", desc_raw))[:300] or None
        results.append({
            "journal_id": j["id"],
            "title": normalize_title(c.get("title") or c.get("metaTitle") or ""),
            "url": c.get("url") or f"https://callsforpapers.org/call/{c.get('slug')}",
            "deadline": deadline,
            "description": desc,
        })
    if unmatched:
        log.debug("Nicht zugeordnete Journals: %s", unmatched)
    log.info("callsforpapers.org: %d Treffer", len(results))
    return results
