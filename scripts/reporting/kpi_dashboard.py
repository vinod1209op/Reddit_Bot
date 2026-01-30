#!/usr/bin/env python3
"""
Generate a lightweight KPI dashboard from local logs and schedules.
"""
import json
from pathlib import Path
from datetime import datetime


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _count_posts(schedule):
    posted = [p for p in schedule if p.get("status") == "posted"]
    scheduled = [p for p in schedule if p.get("status") == "scheduled"]
    failed = [p for p in schedule if p.get("status") == "failed"]
    return {"posted": len(posted), "scheduled": len(scheduled), "failed": len(failed)}


def _ab_summary(schedule):
    rows = [p for p in schedule if p.get("ab_test")]
    with_metrics = [p for p in rows if (p.get("metrics") or {}).get("views")]
    return {"ab_posts": len(rows), "ab_with_metrics": len(with_metrics)}


def _moderation_summary():
    history_dir = Path("scripts/moderation/history")
    if not history_dir.exists():
        return {"daily_files": 0}
    files = list(history_dir.glob("moderation_daily_*.json"))
    return {"daily_files": len(files)}


def generate_dashboard():
    schedule_path = Path("scripts/content_scheduling/schedule/post_schedule.json")
    schedule = _load_json(schedule_path, [])
    post_counts = _count_posts(schedule)
    ab = _ab_summary(schedule)
    moderation = _moderation_summary()

    dashboard = {
        "generated_at": datetime.now().isoformat(),
        "posts": post_counts,
        "ab_tests": ab,
        "moderation": moderation,
    }

    out_json = Path("logs/kpi_dashboard.json")
    out_md = Path("logs/kpi_dashboard.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(dashboard, indent=2))

    lines = [
        "# KPI Dashboard",
        f"Generated: {dashboard['generated_at']}",
        "",
        "## Posting",
        f"- Posted: {post_counts['posted']}",
        f"- Scheduled: {post_counts['scheduled']}",
        f"- Failed: {post_counts['failed']}",
        "",
        "## A/B Testing",
        f"- A/B posts: {ab['ab_posts']}",
        f"- With metrics: {ab['ab_with_metrics']}",
        "",
        "## Moderation",
        f"- Daily moderation logs: {moderation['daily_files']}",
    ]
    out_md.write_text("\n".join(lines))
    return dashboard


if __name__ == "__main__":
    generate_dashboard()
