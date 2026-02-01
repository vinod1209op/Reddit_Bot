#!/usr/bin/env python3
"""
Simple scheduled posting runner (templates only).
Keeps a queue of scheduled posts, tops it up to target, then posts due items.
Supports random account choice, per-account proxies, per-account time windows,
per-account schedule files, and a locked subreddit list.
"""
import argparse
from datetime import datetime, timedelta
import random
import os
from pathlib import Path
import json
import requests
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

from microdose_study_bot.core.logging import UnifiedLogger
from scripts.content_scheduling.schedule_posts import MCRDSEPostScheduler

logger = UnifiedLogger("SimplePosting").get_logger()


def load_account_config(name: str) -> dict:
    try:
        acct_path = Path("config/accounts.json")
        if acct_path.exists():
            data = json.loads(acct_path.read_text())
            for row in data:
                if row.get("name") == name:
                    return row
    except Exception:
        pass
    return {}


def derive_window_from_persona(cfg: dict) -> dict:
    # Map persona.active_hours buckets to local posting windows
    active = (cfg.get("persona") or {}).get("active_hours", "") or ""
    active = active.lower()
    if active == "morning":
        return {"start": "07:00", "end": "12:00"}
    if active == "afternoon":
        return {"start": "12:00", "end": "18:00"}
    if active == "late_night":
        return {"start": "21:00", "end": "01:00"}
    if active == "manual":
        return {"start": "09:00", "end": "21:00"}
    return {"start": "09:00", "end": "21:00"}


def set_account_proxy(cfg: dict):
    http_proxy = cfg.get("http_proxy")
    https_proxy = cfg.get("https_proxy")
    # Clear existing proxies first to avoid bleed between accounts
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        os.environ.pop(var, None)
    if http_proxy:
        os.environ["HTTP_PROXY"] = http_proxy
        os.environ["http_proxy"] = http_proxy
    if https_proxy:
        os.environ["HTTPS_PROXY"] = https_proxy
        os.environ["https_proxy"] = https_proxy
    if cfg.get("use_tor_proxy"):
        os.environ["USE_TOR_PROXY"] = "1"
        tor_port = cfg.get("tor_socks_port")
        if tor_port:
            os.environ["TOR_SOCKS_PORT"] = str(tor_port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple template-based posting runner")
    parser.add_argument("--accounts", default="account4", help="Comma-separated accounts to choose from")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--target", type=int, default=6, help="Target scheduled posts to keep queued")
    parser.add_argument("--days", type=int, default=3, help="Days ahead to schedule generated posts")
    parser.add_argument("--supabase-prefix", default="posting", help="Supabase folder/prefix for schedules")
    parser.add_argument("--shared-schedule", action="store_true", help="Use a single shared post_schedule.json for all accounts")
    parser.add_argument("--force-due", action="store_true", help="Force newly generated posts to be due now (for manual runs)")
    parser.add_argument("--jitter-minutes", type=int, default=45, help="Max minutes to jitter scheduled time (+/-)")
    args = parser.parse_args()

    accounts = [a.strip() for a in args.accounts.split(",") if a.strip()]
    account = random.choice(accounts) if accounts else "account4"

    acct_cfg = load_account_config(account)
    # Ensure timezone from browser fingerprint or fallback
    tz = acct_cfg.get("timezone") or ((acct_cfg.get("browser_fingerprint") or {}).get("timezone"))
    if tz:
        acct_cfg["timezone"] = tz
    else:
        acct_cfg["timezone"] = "America/New_York"
    # Ensure posting window from persona or default
    if not acct_cfg.get("post_window_local"):
        acct_cfg["post_window_local"] = derive_window_from_persona(acct_cfg)
    set_account_proxy(acct_cfg)

    # Supabase helpers (best-effort)
    def sb_download(key: str):
        url = f"{os.environ.get('SUPABASE_URL','').rstrip('/')}/storage/v1/object/{os.environ.get('SUPABASE_BUCKET','')}/{key}"
        headers = {
            "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')}",
            "apikey": os.environ.get("SUPABASE_SERVICE_ROLE_KEY",""),
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.content
        except Exception:
            return None
        return None

    def sb_upload(key: str, data: bytes, content_type: str = "application/json"):
        url = f"{os.environ.get('SUPABASE_URL','').rstrip('/')}/storage/v1/object/{os.environ.get('SUPABASE_BUCKET','')}/{key}"
        headers = {
            "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')}",
            "apikey": os.environ.get("SUPABASE_SERVICE_ROLE_KEY",""),
            "Content-Type": content_type,
        }
        try:
            requests.put(url, headers=headers, data=data, timeout=15)
        except Exception:
            pass

    # Schedule files (shared or per-account)
    sched_dir = Path("scripts/content_scheduling/schedule")
    sched_dir.mkdir(parents=True, exist_ok=True)
    if args.shared_schedule:
        schedule_file = sched_dir / "post_schedule.json"
        legacy_file = sched_dir / "post_schedule_legacy.json"
        sb_key = f"{args.supabase_prefix}/post_schedule.json"
    else:
        schedule_file = sched_dir / f"post_schedule_{account}.json"
        legacy_file = sched_dir / f"post_schedule_{account}_legacy.json"
        sb_key = f"{args.supabase_prefix}/post_schedule_{account}.json"

    # Supabase schedule sync
    content = sb_download(sb_key)
    if content:
        try:
            schedule_file.write_text(content.decode() if isinstance(content, bytes) else content)
            logger.info("Downloaded schedule for %s from Supabase", account)
        except Exception as e:
            logger.warning("Failed to write downloaded schedule: %s", e)

    scheduler = MCRDSEPostScheduler(
        account_name=account,
        headless=args.headless,
        dry_run=args.dry_run,
    )
    scheduler.schedule_file = schedule_file
    scheduler.legacy_schedule_file = legacy_file

    # Restrict subreddits to the three target communities
    allowed_subs = ["ClinicalMicrodosingHu", "MagicWellness", "MindWellBeing"]
    dist = scheduler.config.get("subreddit_distribution", {})
    dist["primary_focus"] = allowed_subs
    dist["secondary_focus"] = []
    dist["crosspost_to"] = []
    scheduler.config["subreddit_distribution"] = dist

    enabled, reason = scheduler.is_feature_enabled("post_scheduling")
    if not enabled:
        logger.info("Post scheduling disabled (%s); exiting.", reason)
        scheduler.cleanup()
        return

    schedule_data = scheduler.load_schedule()
    scheduled_count = sum(1 for p in schedule_data if p.get("status") == "scheduled")
    logger.info("Scheduled posts in queue for %s: %s", account, scheduled_count)
    generated = False
    if scheduled_count < args.target:
        to_generate = max(0, args.target - scheduled_count)
        logger.info("Generating %s posts to reach target for %s", to_generate, account)
        if to_generate:
            for _ in range(to_generate):
                post_types = list(scheduler.config["content_strategy"]["content_mix"].keys())
                weights = list(scheduler.config["content_strategy"]["content_mix"].values())
                post_type = random.choices(post_types, weights=weights, k=1)[0]
                scheduled_time = scheduler.generate_scheduled_time()
                theme = scheduler._pick_theme_for_date(scheduled_time)
                themed_type = scheduler._select_post_type_for_theme(theme)
                if themed_type:
                    post_type = themed_type
                subreddit = random.choice(allowed_subs)
                post = scheduler.generate_post_from_template(post_type, subreddit=subreddit)
                if theme:
                    post["theme"] = theme
                if args.force_due:
                    scheduled_time = datetime.now(scheduled_time.tzinfo) if scheduled_time.tzinfo else datetime.now()
                else:
                    days_offset = random.randint(0, max(1, args.days) - 1)
                    scheduled_time = scheduled_time + timedelta(days=days_offset)
                # per-account posting window
                start_h, end_h, start_m, end_m = 8, 22, 0, 0
                window = acct_cfg.get("post_window_local")
                if isinstance(window, dict) and window.get("start") and window.get("end"):
                    try:
                        sh, sm = map(int, window["start"].split(":"))
                        eh, em = map(int, window["end"].split(":"))
                        start_h, start_m = sh, sm
                        end_h, end_m = eh, em
                    except Exception:
                        start_h, end_h, start_m, end_m = 8, 22, 0, 0
                if args.force_due:
                    hour = (scheduled_time.hour)
                    minute = (scheduled_time.minute)
                else:
                    hour = random.randint(start_h, max(start_h, end_h - 1))
                    minute = random.randint(0, 59)
                    # wobble within +/- jitter minutes
                    jitter = max(0, args.jitter_minutes)
                    delta_minutes = random.randint(-jitter, jitter)
                    base_dt = scheduled_time.replace(hour=hour, minute=minute)
                    base_dt = base_dt + timedelta(minutes=delta_minutes)
                    hour, minute = base_dt.hour, base_dt.minute
                try:
                    tz = None
                    tz_name = acct_cfg.get("timezone")
                    if tz_name and ZoneInfo:
                        tz = ZoneInfo(tz_name)
                    if tz:
                        scheduled_time = scheduled_time.replace(tzinfo=tz)
                    post["scheduled_for"] = scheduled_time.replace(hour=hour, minute=minute).isoformat()
                except Exception:
                    post["scheduled_for"] = scheduled_time.replace(hour=hour, minute=minute).isoformat()
                schedule_data.append(post)
            generated = True
    if generated:
        scheduler.save_schedule(schedule_data)

    # Process due posts
    due = scheduler.check_due_posts()
    if not due:
        logger.info("No posts due right now (%s).", datetime.now().isoformat())
        scheduler.cleanup()
        return

    if args.dry_run:
        logger.info("[dry-run] Would process %s due posts", len(due))
        scheduler.cleanup()
        return

    if not scheduler.setup_browser():
        logger.info("Failed to setup browser")
        scheduler.cleanup()
        return
    if not scheduler.login_with_cookies():
        logger.info("Login failed")
        scheduler.cleanup()
        return

    posted = scheduler.process_due_posts()
    logger.info("Posted %s due posts", posted)
    # Remove posted items from the queue
    schedule = scheduler.load_schedule()
    filtered = [p for p in schedule if p.get("status") != "posted"]
    if len(filtered) != len(schedule):
        scheduler.save_schedule(filtered)
        logger.info("Removed %s posted items from queue", len(schedule) - len(filtered))

    # Upload updated schedule back to Supabase (best effort, mirrors download key)
    try:
        sb_upload(sb_key, schedule_file.read_bytes())
    except Exception:
        logger.warning("Supabase upload skipped/failed for %s", sb_key)

    # Upload updated schedule back to Supabase
    try:
        remote_key = f"{args.supabase_prefix}/post_schedule_{account}.json"
        sb_upload(remote_key, scheduler.schedule_file.read_bytes(), content_type="application/json")
        logger.info("Uploaded schedule for %s to Supabase", account)
    except Exception as e:
        logger.warning("Supabase upload failed: %s", e)

    scheduler.cleanup()


if __name__ == "__main__":
    main()
