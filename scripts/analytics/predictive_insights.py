#!/usr/bin/env python3
"""
Generate simple predictive insights from local history.
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


def _load_schedule():
    return _load_json(Path("scripts/content_scheduling/schedule/post_schedule.json"), [])


def _extract_topics(text: str, keywords):
    text = (text or "").lower()
    return [k for k in keywords if k in text]


def generate():
    config = _load_json(Path("config/analytics.json"), {})
    keywords = config.get("topic_keywords", [])
    min_samples = int(config.get("min_samples_for_time_opt", 5))
    schedule = _load_schedule()
    posted = [p for p in schedule if p.get("status") == "posted" and p.get("posted_at")]

    topic_counts = {}
    hour_counts = {}
    for p in posted:
        text = f"{p.get('title','')} {p.get('content','')}"
        for topic in _extract_topics(text, keywords):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        try:
            hour = datetime.fromisoformat(p["posted_at"]).hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        except Exception:
            continue

    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    optimal_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    insights = {
        "generated_at": datetime.now().isoformat(),
        "top_topics": top_topics,
        "optimal_hours": optimal_hours if len(posted) >= min_samples else [],
        "forecast": {
            "trend_basis": "posts_per_week proxy",
            "next_week_posts_estimate": len(posted) // max(1, 4)
        },
    }

    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    Path("logs/predictive_insights.json").write_text(json.dumps(insights, indent=2))

    lines = [
        "# Predictive Insights",
        f"Generated: {insights['generated_at']}",
        "",
        "## Top Topics",
    ]
    for topic, count in top_topics:
        lines.append(f"- {topic}: {count}")
    lines.append("")
    lines.append("## Optimal Posting Hours (proxy)")
    for hour, count in insights["optimal_hours"]:
        lines.append(f"- {hour}:00 (count {count})")
    Path("logs/predictive_insights.md").write_text("\n".join(lines))
    return insights


if __name__ == "__main__":
    generate()
