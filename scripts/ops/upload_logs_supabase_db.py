#!/usr/bin/env python3
"""
Upload scan logs into Supabase Postgres (scan_runs + scan_events).

Required env vars:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
Optional:
  SUPABASE_SCHEMA (default: public)
  SUPABASE_QUEUE_PATH (default: logs/night_queue.json)
  SUPABASE_SUMMARY_PATH (default: logs/night_scan_summary.csv)
  SUPABASE_SCANNED_PATH (default: logs/scanned_posts.json)
"""

# Imports
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

from microdose_study_bot.core.utils.retry import retry


# Helpers
def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _post_records(base_url: str, key: str, table: str, records: List[Dict[str, Any]], on_conflict: str) -> None:
    if not records:
        return
    url = f"{base_url}/rest/v1/{table}?on_conflict={on_conflict}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    def _do_request():
        resp = requests.post(url, headers=headers, json=records, timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"{resp.status_code}: {resp.text}")
        return resp

    retry(_do_request, attempts=3, base_delay=1.0)


def _load_queue(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read queue file: {exc}")


def _load_summary(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    return rows


def _event_key(entry: Dict[str, Any]) -> str:
    key = entry.get("post_id") or entry.get("url") or entry.get("title") or ""
    return f"{entry.get('run_id','')}|{entry.get('account','')}|{key}"


def _stable_post_key(entry: Dict[str, Any]) -> str:
    raw = entry.get("post_id") or entry.get("url") or entry.get("title") or ""
    if not raw:
        return ""
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# Public API
def main() -> None:
    supabase_url = _get_env("SUPABASE_URL")
    supabase_key = _get_env("SUPABASE_SERVICE_ROLE_KEY")
    schema = _get_env("SUPABASE_SCHEMA", "public")
    queue_path = Path(_get_env("SUPABASE_QUEUE_PATH", "logs/night_queue.json"))
    summary_path = Path(_get_env("SUPABASE_SUMMARY_PATH", "logs/night_scan_summary.csv"))
    scanned_path = Path(_get_env("SUPABASE_SCANNED_PATH", "logs/scanned_posts.json"))

    if not supabase_url or not supabase_key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    base_url = supabase_url.rstrip("/")
    if schema != "public":
        base_url = f"{base_url}/rest/v1?schema={schema}"

    queue_entries = _load_queue(queue_path)
    summary_entries = _load_summary(summary_path)
    scanned_entries = _load_queue(scanned_path)

    scan_events: List[Dict[str, Any]] = []
    for entry in queue_entries:
        record = {
            "event_key": _event_key(entry),
            "run_id": entry.get("run_id", ""),
            "account": entry.get("account", ""),
            "timestamp_utc": entry.get("timestamp_utc"),
            "timestamp_local": entry.get("timestamp_local"),
            "timezone": entry.get("timezone", ""),
            "scan_window": entry.get("scan_window", ""),
            "mode": entry.get("mode", ""),
            "subreddit": entry.get("subreddit", ""),
            "post_id": entry.get("post_id", ""),
            "title": entry.get("title", ""),
            "matched_keywords": entry.get("matched_keywords", []),
            "url": entry.get("url", ""),
            "method": entry.get("method", ""),
            "status": entry.get("status", ""),
            "scan_sort": entry.get("scan_sort", ""),
            "scan_time_range": entry.get("scan_time_range", ""),
            "scan_page_offset": int(entry.get("scan_page_offset") or 0),
            "subreddit_set": entry.get("subreddit_set", ""),
        }
        scan_events.append(record)

    scan_runs: List[Dict[str, Any]] = []
    for row in summary_entries:
        record = {
            "run_id": row.get("run_id", ""),
            "account": row.get("account", ""),
            "timestamp_utc": row.get("timestamp_utc"),
            "timestamp_local": row.get("timestamp_local"),
            "timezone": row.get("timezone", ""),
            "scan_window": row.get("scan_window", ""),
            "mode": row.get("mode", ""),
            "subreddit": row.get("subreddit", ""),
            "posts_scanned": int(row.get("posts_scanned") or 0),
            "matches_logged": int(row.get("matches_logged") or 0),
            "scan_sort": row.get("scan_sort", ""),
            "scan_time_range": row.get("scan_time_range", ""),
            "scan_page_offset": int(row.get("scan_page_offset") or 0),
            "subreddit_set": row.get("subreddit_set", ""),
        }
        scan_runs.append(record)

    _post_records(base_url, supabase_key, "scan_events", scan_events, "event_key")
    _post_records(base_url, supabase_key, "scan_runs", scan_runs, "run_id,account,subreddit")
    scan_posts: List[Dict[str, Any]] = []
    for entry in scanned_entries:
        post_key = _stable_post_key(entry)
        if not post_key:
            continue
        matched_keywords = entry.get("matched_keywords") or []
        record = {
            "post_key": post_key,
            "post_id": entry.get("post_id", ""),
            "url": entry.get("url", ""),
            "title": entry.get("title", ""),
            "subreddit": entry.get("subreddit", ""),
            "last_seen_at": entry.get("timestamp_utc"),
            "last_run_id": entry.get("run_id", ""),
            "last_account": entry.get("account", ""),
            "mode": entry.get("mode", ""),
            "method": entry.get("method", ""),
            "is_match": bool(entry.get("is_match")) or bool(matched_keywords),
            "matched_keywords": matched_keywords,
            "scan_window": entry.get("scan_window", ""),
            "timezone": entry.get("timezone", ""),
            "scan_sort": entry.get("scan_sort", ""),
            "scan_time_range": entry.get("scan_time_range", ""),
            "scan_page_offset": int(entry.get("scan_page_offset") or 0),
            "subreddit_set": entry.get("subreddit_set", ""),
        }
        scan_posts.append(record)

    _post_records(base_url, supabase_key, "scan_posts", scan_posts, "post_key")

    print(
        f"Uploaded {len(scan_events)} scan_events, {len(scan_runs)} scan_runs, "
        f"{len(scan_posts)} scan_posts."
    )


# Entry point
if __name__ == "__main__":
    main()
