#!/usr/bin/env python3
"""
Night scanner: time-windowed, read-only scanning (no replies, no posting).

Usage examples:
  python scripts/runners/night_scanner.py
  SCAN_WINDOWS="02:00-05:00,23:00-01:00" python scripts/runners/night_scanner.py
  python scripts/runners/night_scanner.py --windows "02:00-05:00" --timezone "America/Los_Angeles"
  python scripts/runners/night_scanner.py --schedule-path "config/schedule.json"

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
from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9
    ZoneInfo = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]

from shared.config_manager import ConfigManager
from shared.api_utils import fetch_posts, matched_keywords, normalize_post, make_reddit_client
from shared.console_tee import enable_console_tee
from shared.scan_store import (
    add_scanned_post,
    add_to_queue,
    build_run_paths,
    build_run_scanned_path,
    load_seen,
    normalize_reddit_url,
    save_seen,
    seen_key,
    log_summary,
    QUEUE_DEFAULT_PATH,
    SEEN_DEFAULT_PATH,
    SCANNED_DEFAULT_PATH,
)
from shared.scan_shards import compute_scan_shard


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
            url = f"https://old.reddit.com{permalink}"
        if url:
            info["url"] = normalize_reddit_url(url)
        combined = f"{info['title']} {info['body']}".lower()
        hits = matched_keywords(combined, keywords)
        if hits:
            yield info, hits

def main() -> None:
    enable_console_tee(os.getenv("CONSOLE_LOG_PATH", "logs/selenium_automation.log"))
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
    # No subreddit limits: always scan full configured list.

    queue_path = Path(args.queue_path)
    summary_path = Path(args.summary_path)
    scanned_path = Path(os.getenv("SCANNED_POSTS_PATH", SCANNED_DEFAULT_PATH))
    seen_path = Path(os.getenv("SEEN_POSTS_PATH", SEEN_DEFAULT_PATH))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset_logs:
        if summary_path.exists():
            summary_path.unlink()
    run_id = os.getenv("RUN_ID") or now_local.isoformat()
    _, run_queue_path, run_summary_path = build_run_paths(run_id)
    run_scanned_path = build_run_scanned_path(run_id)
    run_summary_path.parent.mkdir(parents=True, exist_ok=True)
    seen = set(load_seen(seen_path))

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

        def run_selenium_scan(
            account: str,
            cookie_path: str,
            sort: str,
            time_range: str,
            page_offset: int,
            account_subreddits: Sequence[str],
        ) -> None:
            if cookie_path:
                config.selenium_settings["cookie_file"] = cookie_path
            try:
                from tor_proxy import tor_proxy
                tor_enabled = os.getenv("USE_TOR_PROXY", "0") == "1"
            except ImportError:
                tor_enabled = False

            if tor_enabled:
                config.selenium_settings["use_tor"] = True

            bot = RedditAutomation(config=config)
            shard_label = f"sort={sort}, time={time_range or 'none'}, page_offset={page_offset}"
            subreddit_set = ",".join(account_subreddits)
            print(f"Account {account or 'default'}: {shard_label}")
            if not bot.setup():
                print(f"Browser setup failed for account {account or 'default'}; skipping.")
                return
            if not bot.login(use_cookies_only=True):
                print(f"Cookie login failed for account {account or 'default'}; skipping.")
                bot.close()
                return
            print(f"Logged in with cookies for account {account or 'default'}")

            if tor_enabled:
                time_mod.sleep(15)

            try:
                print(f"Subreddits for {account or 'default'}: {', '.join(account_subreddits)}")
                for subreddit in account_subreddits:
                    jitter_sleep(args.jitter_min, args.jitter_max)
                    print(f"[{account or 'default'}] Scanning r/{subreddit} ({shard_label})")
                    posts = bot.search_posts(
                        subreddit=subreddit,
                        limit=args.limit,
                        include_body=False,
                        include_comments=False,
                        sort=sort,
                        time_range=time_range,
                        page_offset=page_offset,
                    )
                    scanned_count = 0
                    matched_count = 0
                    for post in posts:
                        title = post.get("title", "")
                        body = post.get("body", "")
                        info = {
                            "id": post.get("id", ""),
                            "subreddit": post.get("subreddit", subreddit),
                            "title": title,
                            "body": body,
                            "url": normalize_reddit_url(post.get("url", "")),
                        }
                        key = seen_key(info)
                        if key and key in seen:
                            continue
                        if key:
                            seen.add(key)
                        scanned_count += 1
                        combined = f"{title} {body}".lower()
                        hits = matched_keywords(combined, keywords)
                        method = post.get("method", "selenium")
                        add_scanned_post(
                            scanned_path,
                            run_id,
                            account,
                            args.timezone,
                            active_window[2],
                            mode,
                            info,
                            hits,
                            method,
                            scan_sort=sort,
                            scan_time_range=time_range or "",
                            scan_page_offset=page_offset,
                            subreddit_set=subreddit_set,
                        )
                        add_scanned_post(
                            run_scanned_path,
                            run_id,
                            account,
                            args.timezone,
                            active_window[2],
                            mode,
                            info,
                            hits,
                            method,
                            scan_sort=sort,
                            scan_time_range=time_range or "",
                            scan_page_offset=page_offset,
                            subreddit_set=subreddit_set,
                        )
                        if hits:
                            matched_count += 1
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
                                scan_sort=sort,
                                scan_time_range=time_range or "",
                                scan_page_offset=page_offset,
                                subreddit_set=subreddit_set,
                            )
                            add_to_queue(
                                run_queue_path,
                                run_id,
                                account,
                                args.timezone,
                                active_window[2],
                                mode,
                                info,
                                hits,
                                method,
                                scan_sort=sort,
                                scan_time_range=time_range or "",
                                scan_page_offset=page_offset,
                                subreddit_set=subreddit_set,
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
                        scan_sort=sort,
                        scan_time_range=time_range or "",
                        scan_page_offset=page_offset,
                        subreddit_set=subreddit_set,
                    )
                    log_summary(
                        run_summary_path,
                        run_id,
                        account,
                        args.timezone,
                        active_window[2],
                        mode,
                        subreddit,
                        scanned_count,
                        matched_count,
                        scan_sort=sort,
                        scan_time_range=time_range or "",
                        scan_page_offset=page_offset,
                        subreddit_set=subreddit_set,
                    )
                    print(
                        f"[{account or 'default'}] r/{subreddit}: scanned {scanned_count}, matched {matched_count}"
                    )
                    save_seen(seen_path, seen)
            finally:
                bot.close()

        if accounts:
            enabled_accounts = [
                account
                for account in accounts
                if account.get("night_scanner_enabled", True)
            ]
            if not enabled_accounts:
                print("No accounts enabled for night scanner. Exiting.")
                return
            total_accounts = len(enabled_accounts)
            for idx, account in enumerate(enabled_accounts):
                account_name = account.get("name", "")
                cookie_path = account.get("cookies_path", "")
                if not cookie_path:
                    print(f"Skipping account {account_name or '(unnamed)'}: missing cookies_path.")
                    continue
                if not Path(cookie_path).exists():
                    print(f"Skipping account {account_name or '(unnamed)'}: cookie file not found at {cookie_path}.")
                    continue
                account_subreddits = account.get("subreddits") or subreddits
                default_sort, default_time, default_offset = compute_scan_shard(idx, total_accounts)
                sort = account.get("scan_sort") or default_sort
                if "scan_time_range" in account:
                    time_range = account.get("scan_time_range") or ""
                else:
                    time_range = default_time or ""
                if "scan_page_offset" in account:
                    page_offset = int(account.get("scan_page_offset") or 0)
                else:
                    page_offset = default_offset
                run_selenium_scan(
                    account_name,
                    cookie_path,
                    sort,
                    time_range or "",
                    page_offset,
                    account_subreddits,
                )
        else:
            run_selenium_scan(
                "",
                config.selenium_settings.get("cookie_file", "cookies.pkl"),
                "new",
                "",
                0,
                subreddits,
            )

        print(f"Scan complete. Logged queue to {queue_path} and {run_queue_path}.")
        return

    if mode == "mock":
        for subreddit in subreddits:
            jitter_sleep(args.jitter_min, args.jitter_max)
            scanned_count = 0
            matched_count = 0
            for info, hits in scan_posts(MOCK_POSTS, keywords, subreddit):
                key = seen_key(info)
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                scanned_count += 1
                matched_count += 1
                add_to_queue(queue_path, run_id, "", args.timezone, active_window[2], "mock", info, hits, "mock")
                add_to_queue(run_queue_path, run_id, "", args.timezone, active_window[2], "mock", info, hits, "mock")
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
            log_summary(
                run_summary_path,
                run_id,
                "",
                args.timezone,
                active_window[2],
                "mock",
                subreddit,
                scanned_count,
                matched_count,
            )
            save_seen(seen_path, seen)
        print(f"Mock scan complete. Logged queue to {queue_path} and {run_queue_path}.")
        return

    # API mode
    for subreddit in subreddits:
        jitter_sleep(args.jitter_min, args.jitter_max)
        posts = fetch_posts(reddit, subreddit, limit=args.limit, fallback_posts=MOCK_POSTS)
        scanned_count = 0
        matched_count = 0
        for post in posts:
            info = normalize_post(post, subreddit)
            url = getattr(post, "url", "") or ""
            if not url and isinstance(post, Mapping):
                url = post.get("url", "") or ""
            permalink = getattr(post, "permalink", "") or ""
            if permalink and not url:
                url = f"https://old.reddit.com{permalink}"
            if url:
                info["url"] = normalize_reddit_url(url)
            key = seen_key(info)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            scanned_count += 1
            combined = f"{info['title']} {info['body']}".lower()
            hits = matched_keywords(combined, keywords)
            if hits:
                matched_count += 1
                add_to_queue(queue_path, run_id, "", args.timezone, active_window[2], mode, info, hits, "api")
                add_to_queue(run_queue_path, run_id, "", args.timezone, active_window[2], mode, info, hits, "api")
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
        log_summary(
            run_summary_path,
            run_id,
            "",
            args.timezone,
            active_window[2],
            mode,
            subreddit,
            scanned_count,
            matched_count,
        )
        save_seen(seen_path, seen)

    print(f"Scan complete. Logged queue to {queue_path} and {run_queue_path}.")


if __name__ == "__main__":
    main()
