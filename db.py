"""SQLite-Datenbankschicht für CFP-Radar."""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "cfp.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS journals(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  abbrev TEXT,
  vhb_2024 TEXT,
  basket11 INTEGER DEFAULT 0,
  publisher TEXT,
  homepage TEXT,
  cfp_url TEXT
);
CREATE TABLE IF NOT EXISTS cfps(
  id INTEGER PRIMARY KEY,
  journal_id INTEGER NOT NULL REFERENCES journals(id),
  title TEXT NOT NULL,
  url TEXT,
  deadline TEXT,
  description TEXT,
  source TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  hash TEXT UNIQUE NOT NULL,
  active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS subscribers(
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  token TEXT UNIQUE NOT NULL,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions(
  subscriber_id INTEGER NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
  journal_id INTEGER NOT NULL REFERENCES journals(id),
  PRIMARY KEY(subscriber_id, journal_id)
);
CREATE TABLE IF NOT EXISTS notifications(
  subscriber_id INTEGER NOT NULL,
  cfp_id INTEGER NOT NULL,
  sent TEXT NOT NULL,
  PRIMARY KEY(subscriber_id, cfp_id)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def seed_journals(path):
    """Journals aus journals.json einlesen/aktualisieren (idempotent)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    con = connect()
    for j in data:
        con.execute(
            """INSERT INTO journals(name, abbrev, vhb_2024, basket11, publisher, homepage, cfp_url)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 abbrev=excluded.abbrev, vhb_2024=excluded.vhb_2024,
                 basket11=excluded.basket11, publisher=excluded.publisher,
                 homepage=excluded.homepage, cfp_url=excluded.cfp_url""",
            (j["name"], j.get("abbrev"), j.get("vhb_2024"),
             1 if j.get("basket11") else 0, j.get("publisher"),
             j.get("homepage"), j.get("cfp_url")),
        )
    con.commit()
    con.close()


def cfp_hash(journal_id, title, url=None):
    # Bewusst ohne URL: derselbe Call kann aus mehreren Quellen kommen
    # (z.B. callsforpapers.org UND misq.umn.edu) und soll ein Eintrag bleiben.
    raw = f"{journal_id}|{(title or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def upsert_cfp(con, journal_id, title, url, deadline, description, source):
    """Legt einen CFP an, falls neu. Rückgabe: cfp_id wenn NEU, sonst None."""
    h = cfp_hash(journal_id, title, url)
    ts = now_iso()
    row = con.execute("SELECT id FROM cfps WHERE hash=?", (h,)).fetchone()
    if row:
        con.execute("UPDATE cfps SET last_seen=?, active=1 WHERE id=?", (ts, row["id"]))
        return None
    cur = con.execute(
        """INSERT INTO cfps(journal_id, title, url, deadline, description, source,
                            first_seen, last_seen, hash, active)
           VALUES(?,?,?,?,?,?,?,?,?,1)""",
        (journal_id, title, url, deadline, description, source, ts, ts, h),
    )
    return cur.lastrowid


def get_journals(con):
    return con.execute(
        "SELECT * FROM journals ORDER BY basket11 DESC, vhb_2024, name"
    ).fetchall()


def get_cfps(con, active_only=True):
    q = """SELECT c.*, j.name AS journal, j.abbrev, j.vhb_2024, j.basket11
           FROM cfps c JOIN journals j ON j.id = c.journal_id"""
    if active_only:
        q += " WHERE c.active = 1"
    q += " ORDER BY c.first_seen DESC"
    return con.execute(q).fetchall()


def add_subscriber(con, email, journal_ids):
    email = email.strip().lower()
    row = con.execute("SELECT id, token FROM subscribers WHERE email=?", (email,)).fetchone()
    if row:
        sub_id, token = row["id"], row["token"]
    else:
        token = secrets.token_urlsafe(24)
        cur = con.execute(
            "INSERT INTO subscribers(email, token, created) VALUES(?,?,?)",
            (email, token, now_iso()),
        )
        sub_id = cur.lastrowid
    con.execute("DELETE FROM subscriptions WHERE subscriber_id=?", (sub_id,))
    for jid in journal_ids:
        con.execute(
            "INSERT OR IGNORE INTO subscriptions(subscriber_id, journal_id) VALUES(?,?)",
            (sub_id, jid),
        )
    return token


def remove_subscriber(con, token):
    row = con.execute("SELECT id FROM subscribers WHERE token=?", (token,)).fetchone()
    if not row:
        return False
    con.execute("DELETE FROM subscribers WHERE id=?", (row["id"],))
    return True


def subscribers_for_journal(con, journal_id):
    return con.execute(
        """SELECT s.* FROM subscribers s
           JOIN subscriptions su ON su.subscriber_id = s.id
           WHERE su.journal_id = ?""",
        (journal_id,),
    ).fetchall()


def mark_notified(con, subscriber_id, cfp_id):
    con.execute(
        "INSERT OR IGNORE INTO notifications(subscriber_id, cfp_id, sent) VALUES(?,?,?)",
        (subscriber_id, cfp_id, now_iso()),
    )


def already_notified(con, subscriber_id, cfp_id):
    return con.execute(
        "SELECT 1 FROM notifications WHERE subscriber_id=? AND cfp_id=?",
        (subscriber_id, cfp_id),
    ).fetchone() is not None


def set_meta(con, key, value):
    con.execute(
        "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(con, key):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None
