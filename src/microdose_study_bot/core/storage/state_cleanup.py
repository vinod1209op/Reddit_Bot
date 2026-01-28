"""
Purpose: Automated cleanup/rotation for local state files.
Constraints: Storage only; no network calls or automation.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

from microdose_study_bot.core.storage.idempotency_store import (
    IDEMPOTENCY_DEFAULT_PATH,
    load_idempotency,
    save_idempotency,
)
from microdose_study_bot.core.storage.scan_store import SEEN_DEFAULT_PATH, load_seen, save_seen


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _record_ts(record: Dict[str, Any]) -> datetime:
    for key in ("last_success_utc", "last_failure_utc", "last_attempt_utc"):
        dt = _parse_dt(str(record.get(key, "") or ""))
        if dt:
            return dt
    return datetime.fromtimestamp(0, tz=timezone.utc)


def cleanup_idempotency(path: Path, max_entries: int, max_age_days: int) -> int:
    data = load_idempotency(path)
    if not data:
        return 0

    if max_age_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        data = {k: v for k, v in data.items() if _record_ts(v) >= cutoff}

    if max_entries > 0 and len(data) > max_entries:
        items = sorted(data.items(), key=lambda kv: _record_ts(kv[1]), reverse=True)
        data = dict(items[:max_entries])

    save_idempotency(path, data)
    return len(data)


def cleanup_seen(path: Path, max_entries: int) -> int:
    seen = load_seen(path)
    if not seen:
        return 0
    if max_entries > 0 and len(seen) > max_entries:
        seen = seen[-max_entries:]
    save_seen(path, seen)
    return len(seen)


def cleanup_state() -> None:
    idem_path = Path(os.getenv("IDEMPOTENCY_PATH", IDEMPOTENCY_DEFAULT_PATH))
    seen_path = Path(os.getenv("SEEN_POSTS_PATH", SEEN_DEFAULT_PATH))

    max_idem_entries = int(os.getenv("IDEMPOTENCY_MAX_ENTRIES", "50000"))
    max_idem_age_days = int(os.getenv("IDEMPOTENCY_MAX_AGE_DAYS", "30"))
    max_seen_entries = int(os.getenv("SEEN_MAX_ENTRIES", "50000"))

    cleanup_idempotency(idem_path, max_idem_entries, max_idem_age_days)
    cleanup_seen(seen_path, max_seen_entries)
