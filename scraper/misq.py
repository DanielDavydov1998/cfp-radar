"""MIS Quarterly: misq.umn.edu (Cloudflare-geschützt, nur per Browser erreichbar)."""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import clean, extract_deadline, get_html, is_generic_title, normalize_title

log = logging.getLogger("cfp.scraper.misq")

HOME = "https://misq.umn.edu/"
CFP_LINK_RE = re.compile(r"call[\s_-]*for[\s_-]*papers?|special[\s_-]*issue", re.I)


def scrape(journals):
    misq = next((j for j in journals if (j.get("abbrev") or "") == "MISQ"), None)
    if not misq:
        return []
    html = get_html(HOME)
    if not html:
        log.info("MISQ nicht erreichbar (Cloudflare)")
        return []
    soup = BeautifulSoup(html, "lxml")
    # CFP-Links auf der Startseite einsammeln und einzeln folgen
    targets, results, seen = [], [], set()
    for a in soup.find_all("a", href=True):
        text = clean(a.get_text())
        if CFP_LINK_RE.search(text) or CFP_LINK_RE.search(a["href"]):
            url = urljoin(HOME, a["href"])
            if url not in [t[0] for t in targets] and "misq" in url:
                targets.append((url, text))
    for url, link_text in targets[:6]:
        page = get_html(url)
        if not page:
            continue
        psoup = BeautifulSoup(page, "lxml")
        body = clean(psoup.get_text(" "))
        h1 = psoup.find(["h1", "h2"])
        title = clean(h1.get_text()) if h1 else link_text
        if len(title) < 12 or is_generic_title(title):
            # Sammelseite: einzelne CFP-Überschriften einsammeln
            for h in psoup.find_all(["h2", "h3"]):
                t = clean(h.get_text())
                if len(t) < 12 or is_generic_title(t) or t.lower() in seen:
                    continue
                ctx = " ".join(clean(s.get_text(" ")) for s in h.find_next_siblings(limit=6))
                if not re.search(r"deadline|submission", ctx, re.I):
                    continue
                seen.add(t.lower())
                link = h.find("a", href=True)
                results.append({
                    "journal_id": misq["id"],
                    "title": normalize_title(t),
                    "url": urljoin(url, link["href"]) if link else url,
                    "deadline": extract_deadline(ctx),
                    "description": None,
                })
            continue
        if title.lower() in seen:
            continue
        seen.add(title.lower())
        results.append({
            "journal_id": misq["id"],
            "title": normalize_title(title),
            "url": url,
            "deadline": extract_deadline(body),
            "description": None,
        })
    log.info("MISQ: %d Treffer", len(results))
    return results
