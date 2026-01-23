#!/usr/bin/env python3
"""
Weekly account health report generator.

Generates a markdown + JSON summary from data/account_status.json.
If Supabase creds are set, it will try to pull the latest status first.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "account_status.json"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_JSON = LOG_DIR / "weekly_account_report.json"
REPORT_MD = LOG_DIR / "weekly_account_report.md"


def _supabase_status_location() -> tuple[str, str, str, str]:
    base_url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    bucket = os.getenv("SUPABASE_BUCKET", "").strip()
    prefix = os.getenv("SUPABASE_PREFIX", "scan-results/humanized").strip() or "scan-results/humanized"
    status_path = f"{prefix.rstrip('/')}/account_status.json"
    return base_url, key, bucket, status_path


def _download_latest_status() -> bool:
    base_url, key, bucket, status_path = _supabase_status_location()
    if not base_url or not key or not bucket:
        return False
    url = f"{base_url.rstrip('/')}/storage/v1/object/{bucket}/{status_path.lstrip('/')}"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {key}", "apikey": key}, timeout=30)
        if resp.status_code != 200:
            return False
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_bytes(resp.content)
        return True
    except Exception:
        return False


def _load_status() -> dict:
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception:
        return {}


def _summarize(status_data: dict) -> dict:
    counts = {"active": 0, "suspended": 0, "rate_limited": 0, "captcha": 0, "unknown": 0}
    per_account = {}
    for account, info in status_data.items():
        current = (info or {}).get("current_status", "unknown")
        if current not in counts:
            current = "unknown"
        counts[current] += 1
        per_account[account] = {
            "status": current,
            "last_updated": info.get("last_updated"),
            "last_success": info.get("last_success"),
        }
    total = sum(counts.values())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_accounts": total,
        "counts": counts,
        "accounts": per_account,
    }


def _write_reports(summary: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(summary, indent=2))

    lines = [
        "# Weekly Account Health Report",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        f"Total accounts: **{summary['total_accounts']}**",
        "",
        "## Status counts",
    ]
    for key, val in summary["counts"].items():
        lines.append(f"- {key}: {val}")
    lines.append("")
    lines.append("## Accounts")
    for name, info in summary["accounts"].items():
        lines.append(
            f"- **{name}** — {info['status']} (last updated: {info.get('last_updated')}, last success: {info.get('last_success')})"
        )
    REPORT_MD.write_text("\n".join(lines))


def main() -> int:
    _download_latest_status()
    status_data = _load_status()
    summary = _summarize(status_data)
    _write_reports(summary)
    print(f"Wrote {REPORT_JSON} and {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
