"""Scraper-Orchestrierung: alle Quellen abrufen, neue CFPs speichern, Mails auslösen."""
import importlib
import logging
from datetime import date, timedelta

import db
import mailer
from scraper.base import close_browser, is_generic_title

log = logging.getLogger("cfp.scraper")

# cfpsorg zuerst: gepflegter Datensatz für die 13 Kern-IS-Journals (inkl.
# Basket of 11). informs/sage laufen über den Jina-Proxy, acm über Wayback,
# ieeecs über die zentrale computer.org-Liste (Jina), emerald direkt.
# elsevier/wiley bleiben deaktiviert: deren Bot-Erkennung greift überall
# (auch Jina bekommt nur "Are you a robot?"-Seiten).
SOURCES = ("cfpsorg", "springer", "emerald", "ieeecs", "informs", "sage",
           "acm", "tandf", "misq", "aisworld", "wikicfp")

# CFPs, deren Deadline länger her ist, werden weder aufgenommen noch angezeigt
DEADLINE_GRACE_DAYS = 14
# CFPs ohne Deadline gelten als abgelaufen, wenn die Quelle sie so lange nicht mehr listet
UNSEEN_EXPIRY_DAYS = 45


def run_all():
    """Kompletter Scrape-Lauf. Rückgabe: Anzahl neuer CFPs."""
    db.init_db()
    con = db.connect()
    journals = [dict(r) for r in db.get_journals(con)]
    journals_by_id = {j["id"]: j for j in journals}
    cutoff = (date.today() - timedelta(days=DEADLINE_GRACE_DAYS)).isoformat()

    new_ids = []
    try:
        for name in SOURCES:
            try:
                mod = importlib.import_module(f"scraper.{name}")
            except ImportError:
                continue
            try:
                results = mod.scrape(journals)
            except Exception:
                log.exception("Quelle %s fehlgeschlagen", name)
                continue
            seen_batch = set()
            for r in results:
                title = (r.get("title") or "").strip()
                if not title or is_generic_title(title):
                    continue
                if r.get("deadline") and r["deadline"] < cutoff:
                    continue  # Deadline lange vorbei – kein aktueller Call
                key = (r["journal_id"], title.lower())
                if key in seen_batch:
                    continue
                seen_batch.add(key)
                cfp_id = db.upsert_cfp(
                    con, r["journal_id"], title, r.get("url"),
                    r.get("deadline"), r.get("description"), name,
                )
                if cfp_id:
                    new_ids.append(cfp_id)
            con.commit()
    finally:
        close_browser()

    # Abgelaufene Calls deaktivieren
    con.execute("UPDATE cfps SET active=0 WHERE deadline IS NOT NULL AND deadline < ?", (cutoff,))
    unseen_cutoff = db.now_iso()[:10]
    con.execute(
        "UPDATE cfps SET active=0 WHERE deadline IS NULL AND date(last_seen) < date(?, ?)",
        (unseen_cutoff, f"-{UNSEEN_EXPIRY_DAYS} day"),
    )

    db.set_meta(con, "last_run", db.now_iso())
    db.set_meta(con, "last_new", str(len(new_ids)))
    con.commit()

    _notify(con, new_ids, journals_by_id)
    con.close()
    log.info("Scrape fertig: %d neue CFPs", len(new_ids))
    return len(new_ids)


def _notify(con, new_ids, journals_by_id):
    for cfp_id in new_ids:
        cfp = con.execute("SELECT * FROM cfps WHERE id=?", (cfp_id,)).fetchone()
        if not cfp:
            continue
        j = journals_by_id.get(cfp["journal_id"])
        for sub in db.subscribers_for_journal(con, cfp["journal_id"]):
            if db.already_notified(con, sub["id"], cfp_id):
                continue
            ok = mailer.notify_new_cfp(sub, j["name"], cfp["title"],
                                       cfp["url"], cfp["deadline"])
            if ok or not mailer.smtp_configured():
                db.mark_notified(con, sub["id"], cfp_id)
        con.commit()
