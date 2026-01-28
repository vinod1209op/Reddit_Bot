#!/usr/bin/env python3
"""
Unified community manager runner for creation, moderation, and scheduling.
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from microdose_study_bot.core.account_status import AccountStatusTracker
from microdose_study_bot.core.logging import UnifiedLogger
from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.storage.state_cleanup import cleanup_state
from scripts.subreddit_creation.create_subreddits import SubredditCreator
from scripts.moderation.manage_moderation import SeleniumModerationManager
from scripts.content_scheduling.schedule_posts import MCRDSEPostScheduler

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


LOG_PATH = Path("logs/community_manager.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ACTIVITY_LOG = Path("data/community_activity_log.jsonl")
ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)

logger = UnifiedLogger("CommunityManager").get_logger()


def _resolve_timezone(activity_schedule: Dict, account: Dict) -> Optional[str]:
    tz = (account.get("browser_fingerprint") or {}).get("timezone")
    if tz:
        return tz
    return activity_schedule.get("timezone")


def _window_for_account(activity_schedule: Dict, account_name: str) -> Optional[Dict]:
    windows = activity_schedule.get("time_windows", []) or []
    for window in windows:
        name = window.get("name", "")
        if account_name.lower() in name.lower():
            return window
    return None


def _within_window(activity_schedule: Dict, account: Dict, account_name: str) -> Tuple[bool, str]:
    window = _window_for_account(activity_schedule, account_name)
    if not window:
        return True, "no_window"

    tz_name = window.get("timezone") or _resolve_timezone(activity_schedule, account)
    if not tz_name:
        return True, "no_timezone"
    if ZoneInfo is None:
        return True, "timezone_unavailable"

    try:
        now = datetime.now(ZoneInfo(tz_name))
        start_str = window.get("start")
        end_str = window.get("end")
        if not start_str or not end_str:
            return True, "window_incomplete"
        start_hour, start_minute = map(int, start_str.split(":"))
        end_hour, end_minute = map(int, end_str.split(":"))
        start_dt = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end_dt = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if start_dt <= now <= end_dt:
            return True, "within_window"
        return False, "outside_window"
    except Exception as exc:
        logger.warning("Window check failed for %s: %s", account_name, exc)
        return True, "window_check_failed"


def _feature_enabled(activity_schedule: Dict, key: str) -> Tuple[bool, str, Dict]:
    feature = (activity_schedule or {}).get(key, {}) or {}
    if not feature.get("enabled", False):
        return False, "disabled", feature
    if feature.get("require_manual_review", True) and not feature.get("approved", False):
        return False, "manual_approval_required", feature
    return True, "ok", feature


def _delay_between(min_seconds: int, max_seconds: int, dry_run: bool) -> None:
    delay = random.randint(min_seconds, max_seconds)
    if dry_run:
        logger.info("[dry-run] Would wait %ss between activities", delay)
        return
    logger.info("Waiting %ss between activities", delay)
    time.sleep(delay)


def _write_activity_log(payload: Dict) -> None:
    try:
        ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ACTIVITY_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception as exc:
        logger.warning("Failed to write activity log: %s", exc)


def _load_rollout_plan() -> Dict:
    plan_path = Path("config/rollout_plan.json")
    if not plan_path.exists():
        return {}
    try:
        return json.loads(plan_path.read_text())
    except Exception:
        return {}


def _get_phase_config(plan: Dict) -> Dict:
    current = str(plan.get("current_phase", "")).strip()
    phases = plan.get("phases", {}) if isinstance(plan.get("phases", {}), dict) else {}
    return phases.get(current, {}) if current else {}


def _send_alert(account_name: str, message: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    to_email = os.getenv("ALERT_EMAIL_TO")
    if not all([host, username, password, to_email]):
        return
    try:
        import smtplib

        subject = f"[Community Manager Alert] {account_name}"
        body = f"Subject: {subject}\n\n{message}\n"
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, [to_email], body)
    except Exception as exc:
        logger.warning("Failed to send alert email: %s", exc)


def _count_created_since(account_name: str, since: datetime) -> int:
    paths = [
        Path("scripts/subreddit_creation/history/created_subreddits.json"),
        Path("data/created_subreddits.json"),
    ]
    count = 0
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            entries = data.get("subreddits", [])
        else:
            entries = data
        for entry in entries:
            try:
                if entry.get("account") != account_name:
                    continue
                ts = datetime.fromisoformat(entry.get("timestamp", ""))
                if ts >= since:
                    count += 1
            except Exception:
                continue
    return count


def _run_creation(account: Dict, dry_run: bool, headless: bool, max_subreddits: Optional[int]) -> Dict:
    creator = SubredditCreator(
        account_name=account["name"],
        headless=headless,
        dry_run=dry_run,
    )
    max_to_create = max_subreddits or creator.profile_config.get("max_subreddits_per_day", 1)
    logger.info("Starting subreddit creation for %s (max=%s)", account["name"], max_to_create)
    started = datetime.now()
    creator.run(max_subreddits=int(max_to_create), headless=headless)
    created = _count_created_since(account["name"], started)
    return {"created": created, "max": int(max_to_create)}


def _run_moderation(account: Dict, dry_run: bool, headless: bool) -> Dict:
    manager = SeleniumModerationManager(
        account_name=account["name"],
        headless=headless,
        dry_run=dry_run,
    )
    logger.info("Starting moderation for %s", account["name"])
    results = manager.run_daily_moderation()
    manager.cleanup()
    summary = {"subreddits": 0, "total": 0, "approved": 0, "removed": 0, "ignored": 0}
    if isinstance(results, dict):
        summary["subreddits"] = len(results)
        for stats in results.values():
            if not isinstance(stats, dict):
                continue
            summary["total"] += stats.get("total_items", 0)
            summary["approved"] += stats.get("approved", 0)
            summary["removed"] += stats.get("removed", 0)
            summary["ignored"] += stats.get("ignored", 0)
    return summary


def _run_posting(account: Dict, dry_run: bool, headless: bool, queue_target: int) -> Dict:
    scheduler = MCRDSEPostScheduler(
        account_name=account["name"],
        headless=headless,
        dry_run=dry_run,
    )
    schedule = scheduler.load_schedule()
    generated = 0
    if len(schedule) < queue_target:
        to_generate = max(0, queue_target - len(schedule))
        if to_generate:
            logger.info("Generating %s scheduled posts for %s", to_generate, account["name"])
            generated_posts = scheduler.generate_scheduled_posts(to_generate, days_ahead=7)
            generated = len(generated_posts)
    logger.info("Processing due posts for %s", account["name"])
    posted = scheduler.process_due_posts()
    scheduler.cleanup()
    return {"generated": generated, "posted": posted}


def run_for_account(
    account: Dict,
    cfg: ConfigManager,
    dry_run: bool,
    headless: bool,
    respect_windows: bool,
    phase_id: Optional[str] = None,
    phase_name: Optional[str] = None,
) -> None:
    status_tracker = AccountStatusTracker()
    activity_schedule = cfg.activity_schedule or {}
    account_name = account.get("name")

    if status_tracker.should_skip_account(account_name):
        logger.info("Skipping %s due to account status", account_name)
        return

    if respect_windows:
        ok, reason = _within_window(activity_schedule, account, account_name)
        if not ok:
            logger.info("Skipping %s outside window (%s)", account_name, reason)
            return

    os.environ["SELENIUM_HEADLESS"] = "1" if headless else "0"

    creation_ok, creation_reason, creation_cfg = _feature_enabled(activity_schedule, "subreddit_creation")
    moderation_ok, moderation_reason, moderation_cfg = _feature_enabled(activity_schedule, "moderation")
    posting_ok, posting_reason, posting_cfg = _feature_enabled(activity_schedule, "post_scheduling")

    logger.info("Account %s: creation=%s, moderation=%s, posting=%s", account_name, creation_ok, moderation_ok, posting_ok)

    if creation_ok:
        status_before = status_tracker.get_account_status(account_name)
        max_subreddits = creation_cfg.get("max_total_subreddits") or creation_cfg.get("max_per_run")
        summary = _run_creation(account, dry_run or creation_cfg.get("dry_run", False), headless, max_subreddits)
        status_after = status_tracker.get_account_status(account_name)
        _write_activity_log(
            {
                "timestamp": datetime.now().isoformat(),
                "account": account_name,
                "activity": "subreddit_creation",
                "phase": phase_id,
                "phase_name": phase_name,
                "status_before": status_before,
                "status_after": status_after,
                "outcome": "ok",
                "summary": summary,
                "dry_run": dry_run,
            }
        )
        _delay_between(30, 90, dry_run)
    else:
        logger.info("Creation skipped for %s (%s)", account_name, creation_reason)

    if moderation_ok:
        status_before = status_tracker.get_account_status(account_name)
        summary = _run_moderation(account, dry_run or moderation_cfg.get("dry_run", False), headless)
        status_after = status_tracker.get_account_status(account_name)
        _write_activity_log(
            {
                "timestamp": datetime.now().isoformat(),
                "account": account_name,
                "activity": "moderation",
                "phase": phase_id,
                "phase_name": phase_name,
                "status_before": status_before,
                "status_after": status_after,
                "outcome": "ok",
                "summary": summary,
                "dry_run": dry_run,
            }
        )
        _delay_between(20, 60, dry_run)
    else:
        logger.info("Moderation skipped for %s (%s)", account_name, moderation_reason)

    if posting_ok:
        status_before = status_tracker.get_account_status(account_name)
        queue_target = posting_cfg.get("queue_target", 5)
        summary = _run_posting(account, dry_run or posting_cfg.get("dry_run", False), headless, int(queue_target))
        status_after = status_tracker.get_account_status(account_name)
        _write_activity_log(
            {
                "timestamp": datetime.now().isoformat(),
                "account": account_name,
                "activity": "post_scheduling",
                "phase": phase_id,
                "phase_name": phase_name,
                "status_before": status_before,
                "status_after": status_after,
                "outcome": "ok",
                "summary": summary,
                "dry_run": dry_run,
            }
        )
    else:
        logger.info("Posting skipped for %s (%s)", account_name, posting_reason)

    status_tracker.update_account_status(account_name, "active", {"activity": "community_manager"})
    final_status = status_tracker.get_account_status(account_name)
    if any(token in final_status for token in ("suspended", "banned", "restricted", "rate_limited")):
        _send_alert(account_name, f"Account status is {final_status} after community manager run.")


def main() -> None:
    cleanup_state()
    parser = argparse.ArgumentParser(description="Unified community manager runner")
    parser.add_argument("--account", help="Account name to run (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--respect-windows", action="store_true", help="Skip accounts outside their time window")
    args = parser.parse_args()

    cfg = ConfigManager().load_all()
    accounts = cfg.load_accounts_config() or []
    rollout_plan = _load_rollout_plan()
    phase_cfg = _get_phase_config(rollout_plan)

    if args.account:
        accounts = [acct for acct in accounts if acct.get("name") == args.account]
        if not accounts:
            logger.error("Account %s not found in config/accounts.json", args.account)
            sys.exit(1)
    else:
        accounts = [acct for acct in accounts if acct.get("night_scanner_enabled", True)]
        allowed_accounts = phase_cfg.get("allowed_accounts", [])
        if allowed_accounts:
            accounts = [acct for acct in accounts if acct.get("name") in allowed_accounts]

    if not accounts:
        logger.error("No accounts available to run")
        sys.exit(1)

    force_dry_run = bool(phase_cfg.get("force_dry_run", False))
    if force_dry_run:
        args.dry_run = True

    if phase_cfg:
        logger.info(
            "Rollout phase %s (%s)",
            rollout_plan.get("current_phase"),
            phase_cfg.get("name", "unknown"),
        )

    logger.info("Starting community manager for %s accounts", len(accounts))
    phase_id = str(rollout_plan.get("current_phase")) if rollout_plan.get("current_phase") is not None else None
    phase_name = phase_cfg.get("name")

    for account in accounts:
        try:
            # Apply per-phase conservative overrides
            if phase_cfg:
                if "max_subreddits_per_run" in phase_cfg:
                    cfg.activity_schedule.setdefault("subreddit_creation", {})["max_total_subreddits"] = phase_cfg[
                        "max_subreddits_per_run"
                    ]
                if "posting_queue_target" in phase_cfg:
                    cfg.activity_schedule.setdefault("post_scheduling", {})["queue_target"] = phase_cfg[
                        "posting_queue_target"
                    ]
            run_for_account(
                account,
                cfg,
                args.dry_run,
                args.headless,
                args.respect_windows,
                phase_id=phase_id,
                phase_name=phase_name,
            )
        except Exception as exc:
            logger.error("Community manager error for %s: %s", account.get("name"), exc)


if __name__ == "__main__":
    main()
