#!/usr/bin/env python3
"""
Upsert account health + status events into Supabase Postgres.
Uses data/account_status.json as source.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _recent_count(history: List[Dict[str, Any]], status: str, days: int = 7) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    for item in history:
        if item.get("status") != status:
            continue
        ts = _parse_time(item.get("timestamp"))
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts and ts >= cutoff:
            count += 1
    return count


def _post_json(url: str, key: str, payload: Any, on_conflict: str | None = None) -> None:
    endpoint = url
    if on_conflict:
        endpoint = f"{url}?on_conflict={on_conflict}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    resp = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=30)
    if resp.status_code >= 300:
        raise RuntimeError(f"{resp.status_code}: {resp.text}")


def main() -> None:
    base_url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    status_file = Path(__file__).resolve().parents[2] / "data" / "account_status.json"
    if not status_file.exists():
        print("No account_status.json found; skipping.")
        return

    data: Dict[str, Any] = json.loads(status_file.read_text(encoding="utf-8"))
    if not data:
        print("account_status.json empty; skipping.")
        return

    rest = f"{base_url.rstrip('/')}/rest/v1"
    accounts_payload = []
    health_payload = []
    events_payload = []

    for name, info in data.items():
        current = info.get("current_status", "unknown")
        accounts_payload.append({"account_name": name, "status": current})

        history = info.get("status_history", []) or []
        last_success = info.get("last_success")
        last_updated = info.get("last_updated")
        last_success_dt = _parse_time(last_success)
        last_updated_dt = _parse_time(last_updated)

        last_failure_at = None
        last_failure_reason = None
        if current != "active":
            last_failure_at = last_updated_dt.isoformat() if last_updated_dt else None
            last_failure_reason = current

        health_payload.append(
            {
                "account_name": name,
                "current_status": current,
                "last_success_at": last_success_dt.isoformat() if last_success_dt else None,
                "last_failure_at": last_failure_at,
                "last_failure_reason": last_failure_reason,
                "captcha_count_7d": _recent_count(history, "captcha", 7),
                "rate_limit_count_7d": _recent_count(history, "rate_limited", 7),
                "consecutive_failures": int(info.get("failed_login_attempts", 0) or 0),
                "last_status_change_at": last_updated_dt.isoformat() if last_updated_dt else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        if history:
            last = history[-1]
            events_payload.append(
                {
                    "account_name": name,
                    "status": last.get("status", current),
                    "reason": (last.get("details") or {}).get("reason"),
                    "source": "runner",
                    "detected_at": last.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                }
            )

    _post_json(f"{rest}/accounts", key, accounts_payload, on_conflict="account_name")
    _post_json(f"{rest}/account_health", key, health_payload, on_conflict="account_name")
    if events_payload:
        _post_json(f"{rest}/account_status_events", key, events_payload)

    print(
        f"Upserted {len(accounts_payload)} accounts, "
        f"{len(health_payload)} health rows, "
        f"{len(events_payload)} events."
    )


if __name__ == "__main__":
    main()
