"""CI-Einstiegspunkt für GitHub Actions.

Statt SQLite + FastAPI (lokaler Modus, app.py) arbeitet dieser Modus mit einer
JSON-Datei als Zustand: docs/data.json wird von GitHub Pages ausgeliefert und
zugleich als Gedächtnis zwischen den Läufen benutzt (per Commit im Repo).

Abonnenten kommen aus dem Secret SUBSCRIBERS (JSON-Array), damit in einem
öffentlichen Repo keine E-Mail-Adressen liegen. Lokal alternativ aus
subscribers.json (gitignored). Format:
  [{"email": "kollege@uni.de", "journals": ["MISQ", "EJIS", "Decision Support Systems"]}]
Einträge in "journals" dürfen Abkürzung oder voller Name sein; ["*"] = alle.
"""
import hashlib
import importlib
import json
import logging
import os
import sys
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("cfp.ci")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scraper.base import close_browser, is_generic_title  # noqa: E402
import mailer  # noqa: E402

DOCS = ROOT / "docs"
DATA_FILE = DOCS / "data.json"

SOURCES = ("cfpsorg", "springer", "emerald", "ieeecs", "informs", "sage",
           "acm", "tandf", "misq", "aisworld", "wikicfp")
DEADLINE_GRACE_DAYS = 14
UNSEEN_EXPIRY_DAYS = 45


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cfp_hash(journal_name, title):
    # Journalname statt numerischer ID: bleibt stabil, auch wenn die
    # Reihenfolge in journals.json sich ändert
    raw = f"{journal_name.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def load_journals():
    with open(ROOT / "journals.json", encoding="utf-8") as f:
        journals = json.load(f)
    for i, j in enumerate(journals):
        j["id"] = i + 1
        j["basket11"] = bool(j.get("basket11"))
    return journals


def load_prev():
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            return {c["hash"]: c for c in json.load(f).get("cfps", [])}
    return {}


def scrape_all(journals):
    by_id = {j["id"]: j for j in journals}
    cutoff = (date.today() - timedelta(days=DEADLINE_GRACE_DAYS)).isoformat()
    found = {}
    try:
        for name in SOURCES:
            try:
                mod = importlib.import_module(f"scraper.{name}")
                results = mod.scrape(journals)
            except Exception:
                log.exception("Quelle %s fehlgeschlagen", name)
                continue
            for r in results:
                title = (r.get("title") or "").strip()
                j = by_id.get(r.get("journal_id"))
                if not title or not j or is_generic_title(title):
                    continue
                if r.get("deadline") and r["deadline"] < cutoff:
                    continue
                h = cfp_hash(j["name"], title)
                if h in found:
                    continue
                found[h] = {
                    "hash": h,
                    "journal": j["name"],
                    "abbrev": j.get("abbrev"),
                    "vhb_2024": j.get("vhb_2024"),
                    "basket11": j["basket11"],
                    "title": title,
                    "url": r.get("url"),
                    "deadline": r.get("deadline"),
                    "description": r.get("description"),
                    "source": name,
                }
    finally:
        close_browser()
    return found


def merge(prev, found):
    """Alt + neu zusammenführen; Rückgabe: (alle_cfps, neue_cfps)."""
    ts = now_iso()
    cutoff = (date.today() - timedelta(days=DEADLINE_GRACE_DAYS)).isoformat()
    unseen_cutoff = (date.today() - timedelta(days=UNSEEN_EXPIRY_DAYS)).isoformat()
    merged, new = {}, []
    for h, c in prev.items():
        c = dict(c)
        if h in found:
            c.update({k: v for k, v in found[h].items() if v is not None})
            c["last_seen"] = ts
        merged[h] = c
    for h, c in found.items():
        if h not in merged:
            c = dict(c)
            c["first_seen"] = ts
            c["last_seen"] = ts
            merged[h] = c
            new.append(c)
    # aktiv/inaktiv bestimmen
    for c in merged.values():
        if c.get("deadline"):
            c["active"] = c["deadline"] >= cutoff
        else:
            c["active"] = (c.get("last_seen") or ts)[:10] >= unseen_cutoff
    return merged, new


def load_subscribers():
    raw = os.getenv("SUBSCRIBERS", "").strip()
    if not raw and (ROOT / "subscribers.json").exists():
        raw = (ROOT / "subscribers.json").read_text(encoding="utf-8")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error("SUBSCRIBERS ist kein gültiges JSON – keine Mails verschickt")
        return []


def wants(sub, cfp):
    sel = sub.get("journals") or []
    if "*" in sel:
        return True
    keys = {s.strip().lower() for s in sel}
    return (cfp["journal"].lower() in keys
            or (cfp.get("abbrev") or "").lower() in keys)


def notify(new_cfps, base_url):
    subs = load_subscribers()
    if not subs or not new_cfps:
        return 0
    sent = 0
    for sub in subs:
        mine = [c for c in new_cfps if wants(sub, c)]
        if not mine:
            continue
        lines = ["Neue Calls for Papers:", ""]
        for c in mine:
            lines.append(f"• {c['journal']}: {c['title']}")
            if c.get("deadline"):
                lines.append(f"  Deadline: {c['deadline']}")
            if c.get("url"):
                lines.append(f"  {c['url']}")
            lines.append("")
        lines.append(f"Alle aktuellen Calls: {base_url}")
        lines.append("Abmelden/Journals ändern: einfach auf diese Mail antworten.")
        subject = (f"[CFP-Radar] Neuer Call: {mine[0]['journal']}" if len(mine) == 1
                   else f"[CFP-Radar] {len(mine)} neue Calls for Papers")
        if mailer.send_mail(sub["email"], subject, "\n".join(lines)):
            sent += 1
    return sent


def main():
    repo = os.getenv("GITHUB_REPOSITORY", "")  # z.B. "daniel/cfp-radar"
    if os.getenv("BASE_URL"):
        base_url = os.environ["BASE_URL"]
    elif "/" in repo:
        owner, name = repo.split("/", 1)
        base_url = f"https://{owner}.github.io/{name}/"
    else:
        base_url = "http://127.0.0.1:8000"

    journals = load_journals()
    prev = load_prev()
    found = scrape_all(journals)
    merged, new = merge(prev, found)

    active = [c for c in merged.values() if c["active"]]
    active.sort(key=lambda c: c.get("first_seen") or "", reverse=True)
    inactive = [c for c in merged.values() if not c["active"]]

    DOCS.mkdir(exist_ok=True)
    out = {
        "generated": now_iso(),
        "journal_count": len(journals),
        "journals": [{"name": j["name"], "abbrev": j.get("abbrev"),
                      "vhb_2024": j.get("vhb_2024"), "basket11": j["basket11"]}
                     for j in journals],
        "cfps": active + inactive,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    sent = notify(new, base_url)
    log.info("Fertig: %d gefunden, %d neu, %d aktiv, %d Mails verschickt",
             len(found), len(new), len(active), sent)


if __name__ == "__main__":
    main()
