"""ACM-Journals: dl.acm.org blockt alles – wir nutzen Wayback-Machine-Snapshots.

CFP-Deadlines laufen über Monate; ein einige Wochen alter Snapshot ist daher
brauchbar. Zu alte Snapshots (>~1,5 Jahre) werden verworfen.
"""
import logging
import re

from bs4 import BeautifulSoup

from scraper.base import (clean, extract_deadline, get_html_wayback,
                          is_generic_title, normalize_title)

log = logging.getLogger("cfp.scraper.acm")


def scrape(journals):
    results = []
    for j in journals:
        if j.get("publisher") != "ACM":
            continue
        m = re.search(r"dl\.acm\.org/journal/(\w+)", j.get("homepage") or "")
        if not m:
            continue  # z.B. CACM (eigene Website ohne CFP-Liste)
        url = f"https://dl.acm.org/journal/{m.group(1)}/calls-for-papers"
        html = get_html_wayback(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        main = soup.find("main") or soup
        seen = set()
        for h in main.find_all(["h2", "h3", "h4", "h5"]):
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
            href = link["href"] if link else url
            # Wayback-Präfix aus Links entfernen, damit Original-URLs übrig bleiben
            href = re.sub(r"^https?://web\.archive\.org/web/\d+(?:id_)?/", "", href)
            results.append({
                "journal_id": j["id"],
                "title": normalize_title(title),
                "url": href if href.startswith("http") else url,
                "deadline": extract_deadline(ctx),
                "description": None,
            })
    log.info("ACM (Wayback): %d Treffer", len(results))
    return results
