"""E-Mail-Versand über SMTP. Ohne Konfiguration werden Mails nur geloggt."""
import logging
import os
import smtplib
from email.mime.text import MIMEText

log = logging.getLogger("cfp.mailer")

# "or"-Fallbacks statt getenv-Default: in CI sind nicht gesetzte Secrets
# LEERE Strings, kein fehlender Key
SMTP_HOST = os.getenv("SMTP_HOST") or ""
SMTP_PORT = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER = os.getenv("SMTP_USER") or ""
SMTP_PASS = os.getenv("SMTP_PASS") or ""
FROM_EMAIL = os.getenv("FROM_EMAIL") or SMTP_USER or "cfp-radar@localhost"
BASE_URL = os.getenv("BASE_URL") or "http://127.0.0.1:8000"


def smtp_configured():
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


def send_mail(to_addr, subject, body):
    if not smtp_configured():
        log.warning("SMTP nicht konfiguriert – Mail an %s nur geloggt:\n%s\n%s",
                    to_addr, subject, body)
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(FROM_EMAIL, [to_addr], msg.as_string())
        return True
    except Exception:
        log.exception("Mailversand an %s fehlgeschlagen", to_addr)
        return False


def notify_new_cfp(subscriber, journal_name, cfp_title, cfp_url, deadline):
    subject = f"[CFP-Radar] Neuer Call for Papers: {journal_name}"
    lines = [
        f"Neuer Call for Papers bei {journal_name}:",
        "",
        f"  {cfp_title}",
    ]
    if deadline:
        lines.append(f"  Deadline: {deadline}")
    if cfp_url:
        lines.append(f"  Link: {cfp_url}")
    lines += [
        "",
        f"Alle aktuellen Calls: {BASE_URL}",
        f"Abmelden: {BASE_URL}/unsubscribe?token={subscriber['token']}",
    ]
    return send_mail(subscriber["email"], subject, "\n".join(lines))
