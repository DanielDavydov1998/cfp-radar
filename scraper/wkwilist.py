"""wkwi-Mailingliste (Wissenschaftliche Kommission Wirtschaftsinformatik).

Sympa-Archiv auf listserv.dfn.de – öffentlich lesbar nach einem
"I am not a spammer"-Bestätigungs-POST (Spider-Schutz, kein echter Login).
Fängt Journal-CFPs der deutschsprachigen WI-Community, die z.T. nicht auf
AISWorld ankommen (z.B. THCI-Special-Issues).
"""
import logging
import re
import time
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.base import (HEADERS, clean, extract_deadline, match_journals,
                          normalize_title)

log = logging.getLogger("cfp.scraper.wkwilist")

BASE = "https://www.listserv.dfn.de"
CFP_RE = re.compile(r"call\s+for\s+papers?|special\s+issue|\bcfp\b", re.I)
CONF_RE = re.compile(r"conference|workshop|symposium|\btrack\b|proceedings|"
                     r"\b(?:IC|EC|AMC|HIC|PAC|WHIC)IS\b|\bHICSS\b|\bCAiSE\b|"
                     r"\bPoEM\b|\bWI\d{2,4}\b|pre-icis|doctoral consortium|"
                     r"professur|stellenausschreibung|protokoll|treffen", re.I)
N_MONTHS = 2
MAX_MSG_FETCHES = 25


def _months(n):
    y, m = date.today().year, date.today().month
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def _confirmed_get(session, url):
    """Seite laden; falls Sympas Spider-Schutz kommt, bestätigen und neu laden."""
    r = session.get(url, timeout=30)
    if "response_action_confirm" not in r.text:
        return r.text
    soup = BeautifulSoup(r.text, "lxml")
    forms = [f for f in soup.find_all("form") if f.find("input", {"name": "action"})]
    if not forms:
        return None
    data = {i.get("name"): i.get("value") or ""
            for i in forms[0].find_all("input") if i.get("name")}
    data["response_action_confirm"] = "I am not a spammer"
    session.post(BASE + "/sympa", data=data, timeout=30)
    r = session.get(url, timeout=30)
    return r.text if "response_action_confirm" not in r.text else None


def scrape(journals):
    try:
        from curl_cffi import requests as _http
        session = _http.Session(impersonate="chrome")
    except ImportError:
        import requests as _http
        session = _http.Session()
        session.headers.update(HEADERS)

    results, fetched, seen = [], 0, set()
    for month in _months(N_MONTHS):
        index_url = f"{BASE}/sympa/arc/wkwi/{month}/"
        try:
            html = _confirmed_get(session, index_url)
        except Exception as e:
            log.warning("wkwi-Archiv %s nicht erreichbar: %s", month, e)
            continue
        if not html:
            log.info("wkwi-Archiv %s: Spider-Schutz nicht überwindbar", month)
            continue
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=re.compile(r"msg\d+\.html$")):
            subject = clean(a.get_text())
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
            url = urljoin(index_url, a["href"])
            deadline = None
            if fetched < MAX_MSG_FETCHES:
                try:
                    msg = _confirmed_get(session, url)
                except Exception:
                    msg = None
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
    log.info("wkwi: %d Treffer (%d Nachrichten geladen)", len(results), fetched)
    return results
