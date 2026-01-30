#!/usr/bin/env python3
"""
Deliver ecosystem exports to Discord webhook and optional newsletter email.
Skips delivery if required env vars are missing.
"""
import argparse
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Dict


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _send_discord(webhook_url: str, payload_path: Path) -> bool:
    try:
        import urllib.request
    except Exception:
        return False
    if not payload_path.exists():
        return False
    payload = _load_json(payload_path, {})
    messages = payload.get("messages", [])
    for msg in messages:
        content = f"**{msg.get('title')}**\n{msg.get('url') or ''}".strip()
        data = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    return True


def _send_newsletter(smtp_host: str, smtp_port: int, username: str, password: str, from_addr: str, to_addr: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Ecosystem delivery (Discord + newsletter)")
    parser.add_argument("--config", default="config/ecosystem_integration.json")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})
    delivery = config.get("delivery", {})
    exports = config.get("exports", {})

    # Discord
    webhook_env = delivery.get("discord_webhook_env", "DISCORD_WEBHOOK_URL")
    webhook_url = os.getenv(webhook_env, "")
    if webhook_url:
        payload_path = Path(exports.get("discord_payload", "exports/ecosystem/discord_payload.json"))
        _send_discord(webhook_url, payload_path)

    # Newsletter
    newsletter = delivery.get("newsletter", {})
    smtp_host = os.getenv(newsletter.get("smtp_host_env", "SMTP_HOST"), "")
    smtp_port = int(os.getenv(newsletter.get("smtp_port_env", "SMTP_PORT"), "587"))
    smtp_user = os.getenv(newsletter.get("smtp_user_env", "SMTP_USERNAME"), "")
    smtp_pass = os.getenv(newsletter.get("smtp_pass_env", "SMTP_PASSWORD"), "")
    from_addr = os.getenv(newsletter.get("from_env", "NEWSLETTER_FROM"), "")
    to_addr = os.getenv(newsletter.get("to_env", "NEWSLETTER_TO"), "")
    subject = newsletter.get("subject", "MCRDSE Weekly Digest")
    digest_path = Path(exports.get("weekly_digest", "exports/ecosystem/weekly_digest.md"))
    if smtp_host and from_addr and to_addr and digest_path.exists():
        _send_newsletter(
            smtp_host,
            smtp_port,
            smtp_user,
            smtp_pass,
            from_addr,
            to_addr,
            subject,
            digest_path.read_text(),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
