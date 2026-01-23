#!/usr/bin/env python3
"""
Send a simple alert email via SMTP.
Requires: SMTP_USERNAME, SMTP_PASSWORD, ALERT_EMAIL_TO
Optional: ALERT_EMAIL_FROM
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def main() -> int:
    smtp_user = os.getenv("SMTP_USERNAME", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    to_addr = os.getenv("ALERT_EMAIL_TO", "").strip()
    from_addr = os.getenv("ALERT_EMAIL_FROM", smtp_user).strip()
    subject = os.getenv("ALERT_EMAIL_SUBJECT", "Automation Alert").strip()
    body = os.getenv("ALERT_EMAIL_BODY", "See logs for details.").strip()

    if not smtp_user or not smtp_pass or not to_addr:
        raise SystemExit("Missing SMTP_USERNAME/SMTP_PASSWORD/ALERT_EMAIL_TO")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print("Alert email sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
