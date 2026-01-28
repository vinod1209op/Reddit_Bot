#!/usr/bin/env python3
"""
Download account health + status events from Supabase Postgres and
write data/account_status.json for the runner.
"""

from __future__ import annotations

from microdose_study_bot.core.logging import UnifiedLogger
logger = UnifiedLogger('DownloadAccountHealthSupabaseDb').get_logger()

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests
from microdose_study_bot.core.utils.http import get_with_retry


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _fetch_rows(url: str, key: str, params: Dict[str, str]) -> List[dict]:
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Accept": "application/json",
    }
    resp = get_with_retry(url, headers=headers, params=params, timeout=30)
    if resp.status_code >= 300:
        raise RuntimeError(f"{resp.status_code}: {resp.text}")
    return resp.json() if resp.content else []


def main() -> None:
    base_url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    rest = f"{base_url.rstrip('/')}/rest/v1"
    health_rows = _fetch_rows(
        f"{rest}/account_health",
        key,
        {"select": "account_name,current_status,last_success_at,last_status_change_at,updated_at"},
    )
    event_rows = _fetch_rows(
        f"{rest}/account_status_events",
        key,
        {"select": "account_name,status,reason,detected_at", "order": "detected_at.desc", "limit": "500"},
    )

    history: Dict[str, List[dict]] = {}
    for row in event_rows:
        name = row.get("account_name")
        if not name:
            continue
        history.setdefault(name, []).append(
            {
                "timestamp": row.get("detected_at"),
                "status": row.get("status"),
                "details": {"reason": row.get("reason")},
            }
        )

    status_data: Dict[str, dict] = {}
    for row in health_rows:
        name = row.get("account_name")
        if not name:
            continue
        status_data[name] = {
            "current_status": row.get("current_status", "unknown"),
            "status_history": history.get(name, []),
            "last_success": row.get("last_success_at"),
            "last_updated": row.get("last_status_change_at") or row.get("updated_at"),
        }

    if not status_data:
        logger.info("No account health rows found.")
        return

    out_path = Path(__file__).resolve().parents[2] / "data" / "account_status.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status_data, indent=2))
    logger.info(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
