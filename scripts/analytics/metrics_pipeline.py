#!/usr/bin/env python3
"""
Generate analytics metrics from local data (no external calls).
"""
import json
from pathlib import Path
from datetime import datetime, timedelta


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _load_schedule():
    return _load_json(Path("scripts/content_scheduling/schedule/post_schedule.json"), [])


def _load_moderation():
    history_dir = Path("scripts/moderation/history")
    items = []
    for path in history_dir.glob("moderation_daily_*.json"):
        data = _load_json(path, {})
        if isinstance(data, dict):
            for stats in data.values():
                items.append(stats)
    return items


def _count_sources(text: str, keywords):
    text = (text or "").lower()
    return sum(1 for k in keywords if k in text)


def generate():
    config = _load_json(Path("config/analytics.json"), {})
    source_keywords = config.get("source_keywords", [])
    schedule = _load_schedule()
    moderation_items = _load_moderation()
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    posted = [p for p in schedule if p.get("status") == "posted"]
    posted_week = [p for p in posted if p.get("posted_at") and datetime.fromisoformat(p["posted_at"]) >= week_ago]

    # Growth metrics (proxy)
    growth = {
        "posts_week": len(posted_week),
        "posts_total": len(posted),
        "active_users_proxy": sum((p.get("metrics") or {}).get("comments", 0) for p in posted_week),
    }

    # Engagement metrics
    engagement = {
        "upvotes": sum((p.get("metrics") or {}).get("upvotes", 0) for p in posted_week),
        "comments": sum((p.get("metrics") or {}).get("comments", 0) for p in posted_week),
        "shares_proxy": sum(1 for p in posted_week if p.get("crosspost_from")),
    }

    # Quality metrics
    quality = {
        "avg_post_length": round(sum(len((p.get("content") or "")) for p in posted_week) / max(1, len(posted_week)), 2),
        "avg_source_citations": round(
            sum(_count_sources(p.get("content") or "", source_keywords) for p in posted_week) / max(1, len(posted_week)),
            2,
        ),
        "avg_discussion_depth": round(
            sum((p.get("metrics") or {}).get("comments", 0) for p in posted_week) / max(1, len(posted_week)),
            2,
        ),
    }

    # Health metrics
    moderation_total = sum(i.get("total_items", 0) for i in moderation_items)
    moderation_removed = sum(i.get("removed", 0) for i in moderation_items)
    health = {
        "moderation_load": moderation_total,
        "spam_rate": round((moderation_removed / moderation_total) if moderation_total else 0, 4),
        "user_satisfaction_proxy": round(
            sum(((p.get("metrics") or {}).get("upvotes", 0) or 0) for p in posted_week) / max(1, len(posted_week)),
            2,
        ),
    }

    report = {
        "generated_at": now.isoformat(),
        "growth": growth,
        "engagement": engagement,
        "quality": quality,
        "health": health,
    }

    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    Path("logs/analytics_report.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# Analytics Report",
        f"Generated: {report['generated_at']}",
        "",
        "## Growth",
        f"- Posts (week): {growth['posts_week']}",
        f"- Posts (total): {growth['posts_total']}",
        f"- Active users (proxy): {growth['active_users_proxy']}",
        "",
        "## Engagement",
        f"- Upvotes: {engagement['upvotes']}",
        f"- Comments: {engagement['comments']}",
        f"- Shares (proxy): {engagement['shares_proxy']}",
        "",
        "## Quality",
        f"- Avg post length: {quality['avg_post_length']}",
        f"- Avg source citations: {quality['avg_source_citations']}",
        f"- Avg discussion depth: {quality['avg_discussion_depth']}",
        "",
        "## Health",
        f"- Moderation load: {health['moderation_load']}",
        f"- Spam rate: {health['spam_rate']}",
        f"- User satisfaction (proxy): {health['user_satisfaction_proxy']}",
    ]
    Path("logs/analytics_report.md").write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    generate()
