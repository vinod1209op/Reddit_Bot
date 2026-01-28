from microdose_study_bot.core.logging import UnifiedLogger
logger = UnifiedLogger('WeeklyCommunityReport').get_logger()
#!/usr/bin/env python3
"""
Generate a weekly community management report.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _parse_ts(value: str):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _count_created_subreddits(since: datetime) -> int:
    paths = [
        Path("scripts/subreddit_creation/history/created_subreddits.json"),
        Path("data/created_subreddits.json"),
    ]
    count = 0
    for path in paths:
        data = _load_json(path)
        if not data:
            continue
        entries = data.get("subreddits", []) if isinstance(data, dict) else data
        for entry in entries:
            ts = _parse_ts(entry.get("timestamp", ""))
            if ts and ts >= since:
                count += 1
    return count


def _count_posts(since: datetime) -> Dict[str, int]:
    schedule = _load_json(Path("data/post_schedule.json")) or []
    counts = {"scheduled": 0, "posted": 0}
    for entry in schedule:
        created = _parse_ts(entry.get("created_at", ""))
        posted = _parse_ts(entry.get("posted_at", ""))
        if created and created >= since:
            counts["scheduled"] += 1
        if posted and posted >= since:
            counts["posted"] += 1
    return counts


def _count_moderation_actions(since: datetime) -> Dict[str, int]:
    history_dir = Path("scripts/moderation/history")
    summary = {"total": 0, "approved": 0, "removed": 0, "ignored": 0}
    if not history_dir.exists():
        return summary
    for path in history_dir.glob("moderation_daily_*.json"):
        data = _load_json(path)
        if not data:
            continue
        for stats in data.values():
            ts = _parse_ts(stats.get("timestamp", ""))
            if not ts or ts < since:
                continue
            summary["total"] += stats.get("total_items", 0)
            summary["approved"] += stats.get("approved", 0)
            summary["removed"] += stats.get("removed", 0)
            summary["ignored"] += stats.get("ignored", 0)
    return summary


def _account_cooldowns() -> Dict[str, Dict[str, str]]:
    data = _load_json(Path("data/account_status.json")) or {}
    results = {}
    for account, info in data.items():
        cooldowns = info.get("cooldowns", {})
        if cooldowns:
            results[account] = cooldowns
    return results


def main() -> None:
    now = datetime.now()
    since = now - timedelta(days=7)
    created_count = _count_created_subreddits(since)
    post_counts = _count_posts(since)
    moderation_counts = _count_moderation_actions(since)
    cooldowns = _account_cooldowns()

    report_md = Path("logs/weekly_community_report.md")
    report_json = Path("logs/weekly_community_report.json")
    report_md.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Weekly Community Report",
        "",
        f"- Window: {since.date()} → {now.date()}",
        f"- Subreddits created: {created_count}",
        f"- Posts scheduled: {post_counts['scheduled']}",
        f"- Posts posted: {post_counts['posted']}",
        f"- Moderation actions: {moderation_counts['total']} (approved {moderation_counts['approved']}, removed {moderation_counts['removed']}, ignored {moderation_counts['ignored']})",
        "",
        "## Account cooldowns",
    ]
    if cooldowns:
        for account, values in cooldowns.items():
            lines.append(f"- {account}: {values}")
    else:
        lines.append("- None")

    report_md.write_text("\n".join(lines) + "\n")

    report_json.write_text(
        json.dumps(
            {
                "window_start": since.isoformat(),
                "window_end": now.isoformat(),
                "created_subreddits": created_count,
                "posts_scheduled": post_counts["scheduled"],
                "posts_posted": post_counts["posted"],
                "moderation": moderation_counts,
                "cooldowns": cooldowns,
            },
            indent=2,
        )
    )

    logger.info(f"Saved {report_md}")
    logger.info(f"Saved {report_json}")


if __name__ == "__main__":
    main()