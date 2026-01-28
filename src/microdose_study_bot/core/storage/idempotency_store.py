"""
Purpose: Idempotency guard for posting actions.
Constraints: Storage only; no network calls or automation.
"""

from __future__ import annotations

import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from microdose_study_bot.core.storage.scan_store import normalize_reddit_url


IDEMPOTENCY_DEFAULT_PATH = "data/idempotency.json"


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_idempotency(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_idempotency(path: Path, data: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def build_post_key(info: Mapping[str, Any]) -> str:
    post_id = str(info.get("id") or info.get("post_id") or "").strip()
    if post_id:
        return post_id
    url = normalize_reddit_url(str(info.get("url") or info.get("permalink") or "").strip())
    if url:
        return url
    subreddit = str(info.get("subreddit") or "").strip()
    title = str(info.get("title") or "").strip()
    body = str(info.get("body") or info.get("content") or "").strip()
    raw = f"{subreddit}|{title}|{body}".strip()
    if not raw:
        return ""
    return sha256(raw.encode("utf-8")).hexdigest()


def can_attempt(path: Path, key: str) -> bool:
    if not key:
        return True
    data = load_idempotency(path)
    record = data.get(key)
    if not record:
        return True
    return record.get("status") not in {"success", "posted"}


def mark_attempt(path: Path, key: str, meta: Optional[Mapping[str, Any]] = None) -> None:
    if not key:
        return
    data = load_idempotency(path)
    data[key] = {
        "status": "inflight",
        "last_attempt_utc": _now_utc(),
        "meta": dict(meta or {}),
    }
    save_idempotency(path, data)


def mark_success(path: Path, key: str, meta: Optional[Mapping[str, Any]] = None) -> None:
    if not key:
        return
    data = load_idempotency(path)
    data[key] = {
        "status": "success",
        "last_success_utc": _now_utc(),
        "meta": dict(meta or {}),
    }
    save_idempotency(path, data)


def mark_failure(path: Path, key: str, error: str = "", meta: Optional[Mapping[str, Any]] = None) -> None:
    if not key:
        return
    data = load_idempotency(path)
    data[key] = {
        "status": "failed",
        "last_failure_utc": _now_utc(),
        "error": error,
        "meta": dict(meta or {}),
    }
    save_idempotency(path, data)
