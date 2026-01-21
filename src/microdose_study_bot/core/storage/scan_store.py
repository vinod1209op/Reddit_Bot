import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, List, Tuple
from urllib.parse import urlparse, urlunparse

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from microdose_study_bot.core.utils.api_utils import append_log

SUMMARY_HEADER = [
    "run_id",
    "account",
    "timestamp_utc",
    "timestamp_local",
    "timezone",
    "scan_window",
    "mode",
    "subreddit",
    "posts_scanned",
    "matches_logged",
    "scan_sort",
    "scan_time_range",
    "scan_page_offset",
    "subreddit_set",
]

QUEUE_DEFAULT_PATH = "logs/night_queue.json"
SEEN_DEFAULT_PATH = "logs/seen_post_ids.json"
SCANNED_DEFAULT_PATH = "logs/scanned_posts.json"


def normalize_reddit_url(url: str) -> str:
    if not url:
        return url
    trimmed = url.strip()
    if not trimmed or "reddit.com" not in trimmed:
        return trimmed
    if "://" not in trimmed:
        trimmed = f"https://{trimmed.lstrip('/')}"
    parsed = urlparse(trimmed)
    if "reddit.com" not in parsed.netloc:
        return trimmed
    normalized = parsed._replace(scheme="https", netloc="old.reddit.com")
    return urlunparse(normalized)


def load_queue(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read queue file {path}: {exc}")
        return []
    if isinstance(data, list):
        return data
    print(f"Queue file {path} should contain a JSON list.")
    return []


def write_queue(path: Path, entries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def queue_key(entry: Mapping[str, Any]) -> str:
    url = normalize_reddit_url(entry.get("url", ""))
    return entry.get("post_id") or url or entry.get("title") or ""


def add_to_queue(
    path: Path,
    run_id: str,
    account: str,
    tz_name: str,
    scan_window: str,
    mode: str,
    info: Mapping[str, str],
    hits: Sequence[str],
    method: str,
    scan_sort: str = "",
    scan_time_range: str = "",
    scan_page_offset: int = 0,
    subreddit_set: str = "",
) -> None:
    entries = load_queue(path)
    existing = {queue_key(e) for e in entries}
    key = info.get("id") or info.get("url") or info.get("title") or ""
    if not key or key in existing:
        return
    tzinfo = ZoneInfo(tz_name) if ZoneInfo else None
    entry = {
        "run_id": run_id,
        "account": account,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "timestamp_local": datetime.now(tzinfo).isoformat() if tzinfo else datetime.now().isoformat(),
        "timezone": tz_name,
        "scan_window": scan_window,
        "mode": mode,
        "subreddit": info.get("subreddit", ""),
        "post_id": info.get("id", ""),
        "title": info.get("title", ""),
        "matched_keywords": list(hits),
        "url": info.get("url", ""),
        "method": method,
        "status": "pending",
        "scan_sort": scan_sort,
        "scan_time_range": scan_time_range,
        "scan_page_offset": scan_page_offset,
        "subreddit_set": subreddit_set,
    }
    entries.append(entry)
    write_queue(path, entries)


def add_scanned_post(
    path: Path,
    run_id: str,
    account: str,
    tz_name: str,
    scan_window: str,
    mode: str,
    info: Mapping[str, str],
    hits: Sequence[str],
    method: str,
    scan_sort: str = "",
    scan_time_range: str = "",
    scan_page_offset: int = 0,
    subreddit_set: str = "",
) -> None:
    entries = load_queue(path)
    existing = {queue_key(e) for e in entries}
    key = info.get("id") or info.get("url") or info.get("title") or ""
    if not key or key in existing:
        return
    tzinfo = ZoneInfo(tz_name) if ZoneInfo else None
    entry = {
        "post_key": key,
        "run_id": run_id,
        "account": account,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "timestamp_local": datetime.now(tzinfo).isoformat() if tzinfo else datetime.now().isoformat(),
        "timezone": tz_name,
        "scan_window": scan_window,
        "mode": mode,
        "subreddit": info.get("subreddit", ""),
        "post_id": info.get("id", ""),
        "title": info.get("title", ""),
        "matched_keywords": list(hits),
        "url": info.get("url", ""),
        "method": method,
        "status": "matched" if hits else "scanned",
        "is_match": bool(hits),
        "scan_sort": scan_sort,
        "scan_time_range": scan_time_range,
        "scan_page_offset": scan_page_offset,
        "subreddit_set": subreddit_set,
    }
    entries.append(entry)
    write_queue(path, entries)


def _append_summary(path: Path, row: Mapping[str, Any]) -> None:
    if not path.exists():
        append_log(path, row, SUMMARY_HEADER)
        return

    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline().strip()
    expected_header = ",".join(SUMMARY_HEADER)
    if not first_line:
        append_log(path, row, SUMMARY_HEADER)
        return
    if first_line != expected_header:
        rows = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for existing in reader:
                rows.append(existing)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_HEADER)
            writer.writeheader()
            for existing in rows:
                writer.writerow(existing)
    append_log(path, row, SUMMARY_HEADER)


def log_summary(
    path: Path,
    run_id: str,
    account: str,
    tz_name: str,
    scan_window: str,
    mode: str,
    subreddit: str,
    posts_scanned: int,
    matches_logged: int,
    scan_sort: str = "",
    scan_time_range: str = "",
    scan_page_offset: int = 0,
    subreddit_set: str = "",
) -> None:
    tzinfo = ZoneInfo(tz_name) if ZoneInfo else None
    local_time = datetime.now(tzinfo).isoformat() if tzinfo else datetime.now().isoformat()
    row = {
        "run_id": run_id,
        "account": account,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "timestamp_local": local_time,
        "timezone": tz_name,
        "scan_window": scan_window,
        "mode": mode,
        "subreddit": subreddit,
        "posts_scanned": str(posts_scanned),
        "matches_logged": str(matches_logged),
        "scan_sort": scan_sort,
        "scan_time_range": scan_time_range,
        "scan_page_offset": str(scan_page_offset),
        "subreddit_set": subreddit_set,
    }
    _append_summary(path, row)


def load_seen(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read seen file {path}: {exc}")
        return []
    if isinstance(data, list):
        return [str(item) for item in data if item]
    print(f"Seen file {path} should contain a JSON list.")
    return []


def save_seen(path: Path, seen_keys: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(set(seen_keys))), encoding="utf-8")


def seen_key(info: Mapping[str, str]) -> str:
    url = normalize_reddit_url(info.get("url", ""))
    return info.get("id") or url or info.get("title") or ""


def build_run_paths(run_id: str, base_dir: str = "logs") -> Tuple[Path, Path, Path]:
    safe_run_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in run_id)
    run_dir = Path(base_dir) / "runs" / safe_run_id
    return run_dir, run_dir / "night_queue.json", run_dir / "night_scan_summary.csv"


def build_run_scanned_path(run_id: str, base_dir: str = "logs") -> Path:
    run_dir, _, _ = build_run_paths(run_id, base_dir)
    return run_dir / "scanned_posts.json"
