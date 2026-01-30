#!/usr/bin/env python3
"""
Anonymized research pipeline based on internal automation data.
Generates health, discourse, and trends reports without user identifiers.
"""
import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _tokenize(text: str) -> List[str]:
    return [t.strip(".,!?;:()[]").lower() for t in text.split() if t.strip()]


def analyze_topics(posts: List[Dict], topic_map: Dict[str, List[str]]) -> Dict[str, int]:
    counts = Counter()
    for post in posts:
        text = f"{post.get('title','')} {post.get('content','')}"
        tokens = set(_tokenize(text))
        for topic, keywords in topic_map.items():
            if any(k.lower() in tokens or k.lower() in text.lower() for k in keywords):
                counts[topic] += 1
    return dict(counts)

def analyze_journey(posts: List[Dict], journey_cfg: Dict) -> Dict[str, int]:
    stages = journey_cfg.get("stages", [])
    signals = journey_cfg.get("signals", {})
    counts = {stage: 0 for stage in stages}
    for post in posts:
        text = f"{post.get('title','')} {post.get('content','')}".lower()
        for stage in stages:
            keywords = signals.get(stage, [])
            if any(k.lower() in text for k in keywords):
                counts[stage] += 1
    return counts


def compute_health_metrics(posts: List[Dict]) -> Dict:
    if not posts:
        return {"avg_quality": 0, "avg_comments": 0, "avg_upvotes": 0}
    total_quality = 0
    total_comments = 0
    total_upvotes = 0
    for post in posts:
        total_quality += post.get("quality_score") or 0
        metrics = post.get("metrics") or {}
        total_comments += metrics.get("comments") or 0
        total_upvotes += metrics.get("upvotes") or 0
    count = len(posts)
    return {
        "avg_quality": round(total_quality / count, 3),
        "avg_comments": round(total_comments / count, 3),
        "avg_upvotes": round(total_upvotes / count, 3),
    }


def build_reports(posts: List[Dict], config: Dict) -> Dict[str, str]:
    topic_map = config.get("topics", {})
    topic_counts = analyze_topics(posts, topic_map)
    journey_counts = analyze_journey(posts, config.get("journey_metrics", {}))
    health = compute_health_metrics(posts)
    now = datetime.now().isoformat()

    monthly = [
        "# Monthly Community Health Report",
        f"Generated: {now}",
        "",
        "## Engagement Averages (Anonymized)",
        f"- Avg quality score: {health['avg_quality']}",
        f"- Avg comments: {health['avg_comments']}",
        f"- Avg upvotes: {health['avg_upvotes']}",
        "",
        "## Topic Activity (count of posts)",
    ]
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        monthly.append(f"- {topic}: {count}")
    if journey_counts:
        monthly.extend(["", "## User Journey Signals (count of posts)"])
        for stage, count in journey_counts.items():
            monthly.append(f"- {stage}: {count}")

    quarterly = [
        "# Quarterly Psychedelic Discourse Analysis",
        f"Generated: {now}",
        "",
        "## Observed Topics",
    ]
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        quarterly.append(f"- {topic}: {count} posts in schedule data")
    quarterly.append("")
    quarterly.append("## Notes")
    quarterly.append("- This report uses only internal scheduled content metadata.")

    yearly = [
        "# Yearly Trends in Microdosing Conversations",
        f"Generated: {now}",
        "",
        "## Topic Frequency Snapshot",
    ]
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        yearly.append(f"- {topic}: {count}")
    yearly.append("")
    yearly.append("## Method")
    yearly.append("- Aggregated, anonymized metadata only.")

    paths = config.get("reporting", {})
    monthly_path = paths.get("monthly_health_report", "logs/research_monthly_health.md")
    quarterly_path = paths.get("quarterly_discourse_report", "logs/research_quarterly_discourse.md")
    yearly_path = paths.get("yearly_trends_report", "logs/research_yearly_trends.md")

    _save_text(Path(monthly_path), "\n".join(monthly))
    _save_text(Path(quarterly_path), "\n".join(quarterly))
    _save_text(Path(yearly_path), "\n".join(yearly))

    return {
        "monthly": monthly_path,
        "quarterly": quarterly_path,
        "yearly": yearly_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Research pipeline (anonymized)")
    parser.add_argument("--config", default="config/research_pipeline.json")
    parser.add_argument("--schedule", default="scripts/content_scheduling/schedule/post_schedule.json")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})
    posts = _load_json(Path(args.schedule), [])
    build_reports(posts, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
