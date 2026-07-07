"""CFP-Radar – lokales Webinterface + Scheduler."""
import logging
import os
import threading

from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import db
import scraper

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("cfp.app")

BASE_DIR = os.path.dirname(__file__)
SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "6"))

app = FastAPI(title="CFP-Radar")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

_scrape_lock = threading.Lock()


def scrape_job():
    if not _scrape_lock.acquire(blocking=False):
        log.info("Scrape läuft bereits – übersprungen")
        return
    try:
        scraper.run_all()
    finally:
        _scrape_lock.release()


@app.on_event("startup")
def startup():
    db.init_db()
    seed = os.path.join(BASE_DIR, "journals.json")
    if os.path.exists(seed):
        db.seed_journals(seed)
    sched = BackgroundScheduler()
    sched.add_job(scrape_job, "interval", hours=SCRAPE_INTERVAL_HOURS,
                  id="scrape", coalesce=True, max_instances=1)
    sched.start()
    app.state.scheduler = sched
    # Erster Lauf im Hintergrund, damit der Serverstart nicht blockiert
    threading.Thread(target=scrape_job, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/cfps")
def api_cfps():
    con = db.connect()
    rows = [dict(r) for r in db.get_cfps(con)]
    con.close()
    return rows


@app.get("/api/journals")
def api_journals():
    con = db.connect()
    rows = [dict(r) for r in db.get_journals(con)]
    con.close()
    return rows


@app.get("/api/status")
def api_status():
    con = db.connect()
    status = {
        "last_run": db.get_meta(con, "last_run"),
        "last_new": db.get_meta(con, "last_new"),
        "cfp_count": con.execute("SELECT COUNT(*) c FROM cfps WHERE active=1").fetchone()["c"],
        "journal_count": con.execute("SELECT COUNT(*) c FROM journals").fetchone()["c"],
        "subscriber_count": con.execute("SELECT COUNT(*) c FROM subscribers").fetchone()["c"],
        "smtp_configured": __import__("mailer").smtp_configured(),
        "scraping": _scrape_lock.locked(),
    }
    con.close()
    return status


class SubscribeBody(BaseModel):
    email: str
    journal_ids: list[int]


@app.post("/api/subscribe")
def api_subscribe(body: SubscribeBody):
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"ok": False, "error": "Ungültige E-Mail-Adresse"}, status_code=400)
    if not body.journal_ids:
        return JSONResponse({"ok": False, "error": "Mindestens ein Journal auswählen"}, status_code=400)
    con = db.connect()
    db.add_subscriber(con, email, body.journal_ids)
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str = ""):
    con = db.connect()
    ok = db.remove_subscriber(con, token)
    con.commit()
    con.close()
    msg = ("Du wurdest abgemeldet und erhältst keine Benachrichtigungen mehr."
           if ok else "Ungültiger oder bereits verwendeter Abmelde-Link.")
    return f"<html><body style='font-family:sans-serif;padding:3em'><h2>CFP-Radar</h2><p>{msg}</p><a href='/'>Zur Übersicht</a></body></html>"


@app.post("/api/scrape")
def api_scrape():
    if _scrape_lock.locked():
        return {"ok": False, "error": "Läuft bereits"}
    threading.Thread(target=scrape_job, daemon=True).start()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
