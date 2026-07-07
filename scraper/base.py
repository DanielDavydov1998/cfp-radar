"""Gemeinsame Helfer für alle Scraper-Adapter.

Abruf-Strategie: erst normales HTTP (curl_cffi mit Chrome-TLS-Fingerprint,
Fallback requests). Wenn eine Seite blockt (403/Cloudflare-Challenge),
übernimmt ein Headless-Chromium (Playwright) – damit sind auch ScienceDirect,
Wiley, INFORMS, Sage & Co. lesbar.
"""
import logging
import re
import time

import dateparser

log = logging.getLogger("cfp.scraper")

try:
    from curl_cffi import requests as _http
    _IMPERSONATE = {"impersonate": "chrome"}
except ImportError:
    import requests as _http
    _IMPERSONATE = {}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

TIMEOUT = 30

_session = None
_pw = None
_browser = None
_page = None


def _get_session():
    global _session
    if _session is None:
        _session = _http.Session()
        _session.headers.update(HEADERS)
    return _session


BLOCK_MARKERS = ("Just a moment", "Access Denied", "challenge-platform",
                 "Verifying you are human")


def _looks_blocked(text):
    head = text[:4000]
    return any(m in head for m in BLOCK_MARKERS)


def _http_get(url):
    try:
        r = _get_session().get(url, timeout=TIMEOUT, **_IMPERSONATE)
        return r.status_code, r.text
    except Exception as e:
        log.debug("HTTP-Fehler %s: %s", url, e)
        return None, ""


def _browser_page():
    """Lazy-Start eines geteilten Headless-Chromium für den ganzen Lauf."""
    global _pw, _browser, _page
    if _page is not None:
        return _page
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright nicht installiert – Browser-Fallback deaktiviert")
        return None
    try:
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = _browser.new_context(user_agent=HEADERS["User-Agent"],
                                   locale="en-US", viewport={"width": 1366, "height": 900})
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        _page = ctx.new_page()
        return _page
    except Exception:
        log.exception("Browser-Start fehlgeschlagen")
        return None


def _browser_get(url, wait_s=2.5):
    page = _browser_page()
    if page is None:
        return None
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass  # Seiten mit Dauer-Requests: einfach weiter
        page.wait_for_timeout(int(wait_s * 1000))
        html = page.content()
        if _looks_blocked(html):
            # Cloudflare-Challenge: kurz warten, oft löst sie sich von selbst
            page.wait_for_timeout(8000)
            html = page.content()
        if _looks_blocked(html):
            log.info("Auch Browser blockiert: %s", url)
            return None
        return html
    except Exception as e:
        log.info("Browser-Abruf fehlgeschlagen %s: %s", url, e)
        return None


def close_browser():
    """Am Ende eines Scrape-Laufs aufrufen."""
    global _pw, _browser, _page
    try:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _pw = _browser = _page = None


def get_html(url, browser_fallback=True, not_found_ok=True):
    """Liefert HTML als String oder None. Blockierte Seiten gehen durch den Browser."""
    status, text = _http_get(url)
    if status == 200 and not _looks_blocked(text):
        return text
    if status == 404 and not_found_ok:
        return None
    if browser_fallback:
        return _browser_get(url)
    return None


DEADLINE_RE = re.compile(
    r"(?:submission\s+deadline|deadline(?:\s+for\s+(?:full\s+)?(?:paper\s+)?submissions?)?|"
    r"submissions?\s+due|due\s+date|papers?\s+due)\s*[:\-–]?\s*"
    r"([A-Za-z]{3,9}\.?\s+\d{1,2}\s*(?:st|nd|rd|th)?\s*,?\s+\d{4}|"
    r"\d{1,2}\s*(?:st|nd|rd|th)?\.?\s+(?:of\s+)?[A-Za-z]{3,9}\.?,?\s+\d{4}|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4})",
    re.IGNORECASE,
)


def extract_deadline(text):
    """Sucht eine Submission-Deadline im Text, Rückgabe ISO-Datum oder None."""
    if not text:
        return None
    m = DEADLINE_RE.search(text)
    if not m:
        return None
    raw = re.sub(r"(\d)(st|nd|rd|th)", r"\1", m.group(1))
    dt = dateparser.parse(raw, languages=["en", "de"])
    return dt.strftime("%Y-%m-%d") if dt else None


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


TITLE_NOISE_RE = re.compile(
    r"^(?:\[aisworld\]|re:|fwd?:|reminder[:\-\s]*|final\s+(?:reminder|call)[:\-\s]*|"
    r"(?:1st|2nd|3rd|first|second|third|last)\s+(?:cfp|call(?:\s+for\s+papers)?)[:\-\s]*|"
    r"cfp[:\-\s]+|call\s+for\s+papers?[:\-\s]*|deadline\s+extension[:\-\s]*|"
    r"extended\s+deadline[:\-\s]*|special\s+issue(?:\s+on)?[:\-\s]+)+",
    re.IGNORECASE,
)


def normalize_title(title):
    """Entfernt Mailinglisten-/Reminder-Präfixe, damit Reposts nicht als neue CFPs zählen."""
    t = clean(title)
    prev = None
    while prev != t:
        prev = t
        t = TITLE_NOISE_RE.sub("", t).strip(" -–:.,")
    return t or clean(title)


# Navigations-/Sammelseiten-Titel, die keine echten CFPs sind
GENERIC_TITLE_RE = re.compile(
    r"^(?:calls?\s+for\s+papers?|special\s+issues?|previous\s+special\s+issues?|"
    r"past\s+special\s+issues?|forthcoming\s+special\s+issues?|topical\s+collections?.*|"
    r".*guidelines.*|information\s+for\s+guest\s+editors?|guest\s+editors?.*|"
    r"see\s+all|read\s+more|learn\s+more|view\s+all.*|submit.*|about.*|"
    r"new\s+content\s+alerts?|content\s+alerts?|sign\s+up.*|subscribe.*|"
    r"quicklinks.*|resources|latest\s+(?:articles?|issues?)|browse.*|"
    r"editorial\s+board.*|aims\s+and\s+scope.*)$",
    re.IGNORECASE,
)


def is_generic_title(title):
    return bool(GENERIC_TITLE_RE.fullmatch(clean(title)))


# Journalnamen, die zu generisch sind, um sie per Volltext zu matchen
# ("Information Systems" steckt in zig Konferenz-/Journalnamen; das Elsevier-
# Journal dieses Namens wird ohnehin direkt über seine URL gescrapt)
GENERIC_NAMES = {"computer", "information systems", "omega"}


def match_journals(text, journals):
    """Findet Journals, deren Name oder Abkürzung im Text vorkommt.

    Überlappende Treffer werden unterdrückt (längster gewinnt), damit
    "Information Systems Research" nicht zusätzlich "Information Systems" matcht.
    """
    spans = []  # (start, ende, journal)
    lower = text.lower()
    for j in journals:
        name = (j.get("name") or "").lower()
        if name and name not in GENERIC_NAMES:
            for m in re.finditer(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", lower):
                spans.append((m.start(), m.end(), j))
        abbrev = j.get("abbrev") or ""
        if len(abbrev) >= 4 and abbrev.isalnum():
            for m in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(abbrev) + r"(?![A-Za-z0-9])", text):
                spans.append((m.start(), m.end(), j))
    spans.sort(key=lambda s: s[1] - s[0], reverse=True)
    kept, hits = [], []
    for start, end, j in spans:
        if any(start < ke and ks < end for ks, ke in kept):
            continue
        kept.append((start, end))
        if j["id"] not in [x["id"] for x in hits]:
            hits.append(j)
    return hits
