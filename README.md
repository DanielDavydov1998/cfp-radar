# 📡 CFP-Radar

Überwacht Calls for Papers (Special-Issue-Calls) der Wirtschaftsinformatik-
Journals (VHB-Rating 2024 ab B + AIS Senior Scholars' Basket of 11) und zeigt
sie in einer Weboberfläche. Bei neuen Calls gibt es E-Mail-Benachrichtigungen.

Es gibt zwei Betriebsmodi:

## Modus 1: GitHub Actions + Pages (empfohlen, kostenlos, 24/7)

- `.github/workflows/scrape.yml` scrapt zweimal täglich in der GitHub-Cloud,
  schreibt `docs/data.json` und verschickt Mails für neue Calls.
- GitHub Pages liefert `docs/index.html` als öffentliche Übersicht aus.

### Einrichtung (einmalig)

1. Repo auf GitHub (public – nötig für kostenloses Pages)
2. **Settings → Pages**: Source „Deploy from a branch", Branch `main`, Ordner `/docs`
3. **Settings → Secrets and variables → Actions → Secrets** anlegen:
   - `SMTP_HOST` (z. B. `smtp.gmail.com`), `SMTP_PORT` (`587`),
     `SMTP_USER` (Gmail-Adresse), `SMTP_PASS` (App-Passwort:
     https://myaccount.google.com/apppasswords)
   - `SUBSCRIBERS`: JSON-Array wie in `subscribers.example.json` –
     bewusst als Secret, damit keine E-Mail-Adressen im öffentlichen Repo liegen
4. Workflow einmal von Hand starten: **Actions → „CFPs scrapen" → Run workflow**

Abonnenten ändern = Secret `SUBSCRIBERS` bearbeiten. `"journals": ["*"]`
bedeutet „alle Journals"; sonst Abkürzungen (`"MISQ"`) oder volle Namen.

## Modus 2: Lokal (FastAPI + SQLite)

Doppelklick auf `start.bat` → http://127.0.0.1:8000. Mit Abo-Formular in der
Oberfläche; SMTP-Konfiguration über `.env` (siehe `.env.example`).
Scrapt automatisch alle 6 h, solange die App läuft.

## Aufbau

| Datei | Zweck |
|---|---|
| `journals.json` | Journal-Stammdaten (Name, VHB-2024-Rating, Basket 11, Verlag) |
| `scraper/` | Ein Adapter pro Quelle; Orchestrierung in `__init__.py` (lokal) |
| `ci_run.py` | CI-Einstieg: JSON-Zustand statt SQLite, Mails aus Secret |
| `docs/` | Statische Seite + Daten für GitHub Pages |
| `app.py`, `db.py`, `templates/` | Lokaler Modus |
| `mailer.py` | SMTP-Versand (beide Modi) |

## Datenquellen & Grenzen

- **Hauptquelle:** öffentlicher Datensatz von callsforpapers.org
  (GitHub: julianprester/calls-for-papers) – deckt die 13 Kern-IS-Journals
  inkl. des kompletten Basket of 11 ab.
- Direkt gescrapt: Springer (`/updates`), bise-journal.com, jmis-web.org,
  MISQ (per Headless-Browser), WikiCFP.
- **Nicht abgedeckt:** ACM-, IEEE-, Emerald-Journals u. a. – deren Verlags-
  seiten blockieren automatisierte Abrufe hart (403/Cloudflare), auch per
  Headless-Browser. Adapter für Elsevier/Wiley/INFORMS/Sage liegen in
  `scraper/`, sind aber deaktiviert, bis sich die Blockade-Lage ändert.
- Journals pflegen: `journals.json` bearbeiten (im GitHub-Modus: committen).
