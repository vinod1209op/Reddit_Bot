#!/usr/bin/env python3
"""
Night scanner: time-windowed, read-only scanning (no replies, no posting).

Usage examples:
  python scripts/night_scanner.py
  SCAN_WINDOWS="02:00-05:00,23:00-01:00" python scripts/night_scanner.py
  python scripts/night_scanner.py --windows "02:00-05:00" --timezone "America/Los_Angeles"
  python scripts/night_scanner.py --schedule-path "config/schedule.json"

Notes:
- This script only scans and queues matches. It never generates replies or posts.
- Schedule it via cron/Task Scheduler and run it periodically (e.g., every 15-30 minutes).
- Precedence: CLI args > env vars > schedule.json (if present).
"""
import argparse
import json
import os
import random
import sys
import time as time_mod
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse, urlunparse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9
    ZoneInfo = None  # type: ignore

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config_manager import ConfigManager
from shared.api_utils import append_log, fetch_posts, matched_keywords, normalize_post, make_reddit_client


MOCK_POSTS: List[Mapping[str, str]] = [
    {
        "id": "mock1",
        "subreddit": "learnpython",
        "title": "Mock post mentioning microdosing safety",
        "score": 10,
        "body": "Looking for harm-reduction info; no dosing details requested.",
    },
    {
        "id": "mock2",
        "subreddit": "learnpython",
        "title": "Mock unrelated post",
        "score": 5,
        "body": "This one should not match unless keywords change.",
    },
]

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
]

QUEUE_DEFAULT_PATH = "logs/night_queue.json"

def parse_time(value: str) -> time:
    return datetime.strptime(value.strip(), "%H:%M").time()


def parse_windows(value: str) -> List[Tuple[time, time, str]]:
    windows = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" not in part:
            raise ValueError(f"Invalid window '{part}', expected HH:MM-HH:MM")
        start_s, end_s = part.split("-", 1)
        start_t = parse_time(start_s)
        end_t = parse_time(end_s)
        windows.append((start_t, end_t, part))
    if not windows:
        raise ValueError("No valid scan windows provided")
    return windows


def in_window(now_t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= now_t <= end
    # Window wraps past midnight
    return now_t >= start or now_t <= end


def jitter_sleep(min_s: float, max_s: float) -> None:
    if max_s <= 0:
        return
    delay = random.uniform(max(0, min_s), max(min_s, max_s))
    time_mod.sleep(delay)

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
    normalized = parsed._replace(scheme="https", netloc="www.reddit.com")
    return urlunparse(normalized)

def _truthy(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def _cli_flag_present(flag: str) -> bool:
    if flag in sys.argv:
        return True
    prefix = f"{flag}="
    return any(arg.startswith(prefix) for arg in sys.argv)


def load_schedule(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read schedule file {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        print(f"Schedule file {path} should contain a JSON object.")
        return {}
    return data


def extract_schedule_windows(schedule: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    windows = schedule.get("scan_windows") or schedule.get("windows")
    tz_name = schedule.get("timezone")
    if isinstance(windows, str):
        return windows.strip(), tz_name
    if not isinstance(windows, list):
        return None, tz_name
    parts: List[str] = []
    for entry in windows:
        if isinstance(entry, str):
            if entry.strip():
                parts.append(entry.strip())
            continue
        if isinstance(entry, dict):
            start = entry.get("start")
            end = entry.get("end")
            if start and end:
                parts.append(f"{start}-{end}")
            if not tz_name and entry.get("timezone"):
                tz_name = entry.get("timezone")
    return (", ".join(parts) if parts else None), tz_name


def load_accounts(path: Path, names_filter: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read accounts file {path}: {exc}")
        return []
    if not isinstance(data, list):
        print(f"Accounts file {path} should contain a JSON list.")
        return []
    accounts = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "") or "").strip()
        if names_filter and name not in names_filter:
            continue
        cookies_path = str(entry.get("cookies_path") or entry.get("cookie_path") or "").strip()
        accounts.append({"name": name, "cookies_path": cookies_path})
    return accounts


def scan_posts(
    posts: Iterable,
    keywords: Sequence[str],
    default_subreddit: str,
) -> Iterable[Tuple[Mapping[str, str], List[str]]]:
    for post in posts:
        info = normalize_post(post, default_subreddit)
        # Best-effort URL enrichment for logging.
        url = getattr(post, "url", "") or ""
        if not url and isinstance(post, Mapping):
            url = post.get("url", "") or ""
        permalink = getattr(post, "permalink", "") or ""
        if permalink and not url:
            url = f"https://www.reddit.com{permalink}"
        if url:
            info["url"] = normalize_reddit_url(url)
        combined = f"{info['title']} {info['body']}".lower()
        hits = matched_keywords(combined, keywords)
        if hits:
            yield info, hits

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
) -> None:
    local_time = datetime.now(ZoneInfo(tz_name)).isoformat()
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
    }
    append_log(path, row, SUMMARY_HEADER)

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
) -> None:
    entries = load_queue(path)
    existing = {queue_key(e) for e in entries}
    key = info.get("id") or info.get("url") or info.get("title") or ""
    if not key or key in existing:
        return
    entry = {
        "run_id": run_id,
        "account": account,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "timestamp_local": datetime.now(ZoneInfo(tz_name)).isoformat(),
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
    }
    entries.append(entry)
    write_queue(path, entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Time-windowed read-only scanner.")
    parser.add_argument(
        "--schedule-path",
        default=os.getenv("SCHEDULE_PATH", "config/schedule.json"),
        help="Optional schedule JSON file (default: config/schedule.json)",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("SCAN_TIMEZONE", "America/Los_Angeles"),
        help="IANA timezone name (default: America/Los_Angeles)",
    )
    parser.add_argument(
        "--windows",
        default=os.getenv("SCAN_WINDOWS", "02:00-05:00,23:00-01:00"),
        help="Comma-separated scan windows in HH:MM-HH:MM (default: 02:00-05:00,23:00-01:00)",
    )
    parser.add_argument("--limit", type=int, default=int(os.getenv("SCAN_LIMIT", "25")), help="Posts per subreddit")
    parser.add_argument(
        "--mode",
        choices=["auto", "api", "selenium", "mock"],
        default=os.getenv("SCAN_MODE", "auto"),
        help="Scan mode (default: auto)",
    )
    parser.add_argument(
        "--queue-path",
        default=os.getenv("SCAN_QUEUE_PATH", QUEUE_DEFAULT_PATH),
        help="JSON queue path (default: logs/night_queue.json)",
    )
    parser.add_argument(
        "--summary-path",
        default=os.getenv("SCAN_SUMMARY_PATH", "logs/night_scan_summary.csv"),
        help="CSV summary path",
    )
    parser.add_argument("--jitter-min", type=float, default=float(os.getenv("SCAN_JITTER_MIN", "2")))
    parser.add_argument("--jitter-max", type=float, default=float(os.getenv("SCAN_JITTER_MAX", "8")))
    parser.add_argument("--max-subreddits", type=int, default=int(os.getenv("SCAN_MAX_SUBREDDITS", "0")))
    parser.add_argument(
        "--accounts-path",
        default=os.getenv("SCAN_ACCOUNTS_PATH", ""),
        help="Optional accounts JSON for multi-account selenium scans",
    )
    parser.add_argument(
        "--account-names",
        default=os.getenv("SCAN_ACCOUNT_NAMES", ""),
        help="Comma-separated account names to include (optional)",
    )
    parser.add_argument(
        "--reset-logs",
        action="store_true",
        help="Overwrite summary log for this run (queue is preserved)",
    )
    args = parser.parse_args()

    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; use Python 3.9+")

    if _truthy(os.getenv("SCAN_RESET_LOGS")) and not _cli_flag_present("--reset-logs"):
        args.reset_logs = True

    schedule = load_schedule(Path(args.schedule_path))
    schedule_windows, schedule_tz = extract_schedule_windows(schedule)
    if schedule_windows and not _cli_flag_present("--windows") and not os.getenv("SCAN_WINDOWS"):
        args.windows = schedule_windows
    if schedule_tz and not _cli_flag_present("--timezone") and not os.getenv("SCAN_TIMEZONE"):
        args.timezone = schedule_tz
    if "limit" in schedule and not _cli_flag_present("--limit") and not os.getenv("SCAN_LIMIT"):
        args.limit = int(schedule["limit"])
    if "mode" in schedule and not _cli_flag_present("--mode") and not os.getenv("SCAN_MODE"):
        args.mode = str(schedule["mode"])
    if "queue_path" in schedule and not _cli_flag_present("--queue-path") and not os.getenv("SCAN_QUEUE_PATH"):
        args.queue_path = str(schedule["queue_path"])
    if "summary_path" in schedule and not _cli_flag_present("--summary-path") and not os.getenv("SCAN_SUMMARY_PATH"):
        args.summary_path = str(schedule["summary_path"])
    if "jitter_min" in schedule and not _cli_flag_present("--jitter-min") and not os.getenv("SCAN_JITTER_MIN"):
        args.jitter_min = float(schedule["jitter_min"])
    if "jitter_max" in schedule and not _cli_flag_present("--jitter-max") and not os.getenv("SCAN_JITTER_MAX"):
        args.jitter_max = float(schedule["jitter_max"])
    if "max_subreddits" in schedule and not _cli_flag_present("--max-subreddits") and not os.getenv("SCAN_MAX_SUBREDDITS"):
        args.max_subreddits = int(schedule["max_subreddits"])
    if "reset_logs" in schedule and not _cli_flag_present("--reset-logs") and not os.getenv("SCAN_RESET_LOGS"):
        args.reset_logs = _truthy(schedule["reset_logs"])
    if "accounts_path" in schedule and not _cli_flag_present("--accounts-path") and not os.getenv("SCAN_ACCOUNTS_PATH"):
        args.accounts_path = str(schedule["accounts_path"])
    if "account_names" in schedule and not _cli_flag_present("--account-names") and not os.getenv("SCAN_ACCOUNT_NAMES"):
        args.account_names = str(schedule["account_names"])

    tz = ZoneInfo(args.timezone)
    now_local = datetime.now(tz)
    now_t = now_local.time()
    windows = parse_windows(args.windows)
    active_window = next((w for w in windows if in_window(now_t, w[0], w[1])), None)

    if not active_window:
        print(f"Outside scan windows ({args.windows}) for {args.timezone}. Exiting.")
        return

    # Enforce read-only behavior.
    os.environ["ENABLE_POSTING"] = "0"
    os.environ["USE_LLM"] = "0"

    config = ConfigManager().load_all()
    subreddits = config.bot_settings.get("subreddits") or config.default_subreddits
    keywords = config.bot_settings.get("keywords") or config.default_keywords
    if args.max_subreddits > 0:
        subreddits = subreddits[: args.max_subreddits]

    queue_path = Path(args.queue_path)
    summary_path = Path(args.summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset_logs:
        if summary_path.exists():
            summary_path.unlink()
    run_id = os.getenv("RUN_ID") or now_local.isoformat()

    mode = args.mode
    if mode == "auto":
        if config.api_creds.get("client_id") and config.api_creds.get("client_secret"):
            mode = "api"
        elif config.bot_settings.get("mode") == "selenium":
            mode = "selenium"
        else:
            mode = "mock"

    print(f"Active window {active_window[2]} ({args.timezone}). Mode: {mode}.")

    if mode == "api":
        try:
            reddit = make_reddit_client(env_fallback=True)
        except Exception as exc:
            print(f"API client unavailable ({exc}); falling back to mock.")
            mode = "mock"
            reddit = None
    else:
        reddit = None

    if mode == "selenium":
        from selenium_automation.main import RedditAutomation
        account_names = {name.strip() for name in args.account_names.split(",") if name.strip()}
        accounts = []
        if args.accounts_path:
            accounts = load_accounts(Path(args.accounts_path), account_names or None)
            if not accounts:
                print(f"No accounts loaded from {args.accounts_path}. Exiting.")
                return

        def run_selenium_scan(account: str, cookie_path: str) -> None:
            if cookie_path:
                config.selenium_settings["cookie_file"] = cookie_path

            bot = RedditAutomation(config=config)
            if not bot.setup():
                print(f"Browser setup failed for account {account or 'default'}; skipping.")
                return
            if not bot.login(use_cookies_only=True):
                print(f"Cookie login failed for account {account or 'default'}; skipping.")
                bot.close()
                return

            try:
                for subreddit in subreddits:
                    jitter_sleep(args.jitter_min, args.jitter_max)
                    posts = bot.search_posts(subreddit=subreddit, limit=args.limit, include_body=False, include_comments=False)
                    scanned_count = 0
                    matched_count = 0
                    for post in posts:
                        scanned_count += 1
                        title = post.get("title", "")
                        body = post.get("body", "")
                        combined = f"{title} {body}".lower()
                        hits = matched_keywords(combined, keywords)
                        if hits:
                            matched_count += 1
                            info = {
                                "id": post.get("id", ""),
                                "subreddit": post.get("subreddit", subreddit),
                                "title": title,
                                "body": body,
                                "url": normalize_reddit_url(post.get("url", "")),
                            }
                            method = post.get("method", "selenium")
                            add_to_queue(
                                queue_path,
                                run_id,
                                account,
                                args.timezone,
                                active_window[2],
                                mode,
                                info,
                                hits,
                                method,
                            )
                    log_summary(
                        summary_path,
                        run_id,
                        account,
                        args.timezone,
                        active_window[2],
                        mode,
                        subreddit,
                        scanned_count,
                        matched_count,
                    )
            finally:
                bot.close()

        if accounts:
            for account in accounts:
                account_name = account.get("name", "")
                cookie_path = account.get("cookies_path", "")
                if not cookie_path:
                    print(f"Skipping account {account_name or '(unnamed)'}: missing cookies_path.")
                    continue
                if not Path(cookie_path).exists():
                    print(f"Skipping account {account_name or '(unnamed)'}: cookie file not found at {cookie_path}.")
                    continue
                run_selenium_scan(account_name, cookie_path)
        else:
            run_selenium_scan("", config.selenium_settings.get("cookie_file", "cookies.pkl"))

        print(f"Scan complete. Logged queue to {queue_path}.")
        return

    if mode == "mock":
        for subreddit in subreddits:
            jitter_sleep(args.jitter_min, args.jitter_max)
            scanned_count = len(MOCK_POSTS)
            matched_count = 0
            for info, hits in scan_posts(MOCK_POSTS, keywords, subreddit):
                matched_count += 1
                add_to_queue(queue_path, run_id, "", args.timezone, active_window[2], "mock", info, hits, "mock")
            log_summary(
                summary_path,
                run_id,
                "",
                args.timezone,
                active_window[2],
                "mock",
                subreddit,
                scanned_count,
                matched_count,
            )
        print(f"Mock scan complete. Logged queue to {queue_path}.")
        return

    # API mode
    for subreddit in subreddits:
        jitter_sleep(args.jitter_min, args.jitter_max)
        posts = fetch_posts(reddit, subreddit, limit=args.limit, fallback_posts=MOCK_POSTS)
        scanned_count = 0
        matched_count = 0
        for post in posts:
            scanned_count += 1
            info = normalize_post(post, subreddit)
            url = getattr(post, "url", "") or ""
            if not url and isinstance(post, Mapping):
                url = post.get("url", "") or ""
            permalink = getattr(post, "permalink", "") or ""
            if permalink and not url:
                url = f"https://www.reddit.com{permalink}"
            if url:
                info["url"] = normalize_reddit_url(url)
            combined = f"{info['title']} {info['body']}".lower()
            hits = matched_keywords(combined, keywords)
            if hits:
                matched_count += 1
                add_to_queue(queue_path, run_id, "", args.timezone, active_window[2], mode, info, hits, "api")
        log_summary(
            summary_path,
            run_id,
            "",
            args.timezone,
            active_window[2],
            mode,
            subreddit,
            scanned_count,
            matched_count,
        )

    print(f"Scan complete. Logged queue to {queue_path}.")


if __name__ == "__main__":
    main()
