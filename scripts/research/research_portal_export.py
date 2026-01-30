#!/usr/bin/env python3
"""
Exports anonymized research summaries for a simple researcher portal.
"""
import argparse
import json
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


def export_portal(config: Dict, schedule: List[Dict]) -> Path:
    output_dir = Path(config.get("portal_export", {}).get("output_dir", "exports/research_portal"))
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now().isoformat(),
        "post_count": len(schedule),
        "subreddits": sorted({p.get("subreddit") for p in schedule if p.get("subreddit")}),
        "fields": [
            "id",
            "subreddit",
            "title",
            "type",
            "created_at",
            "scheduled_for",
            "posted_at",
            "quality_score",
        ],
        "posts": [],
    }
    for post in schedule:
        summary["posts"].append(
            {
                "id": post.get("id"),
                "subreddit": post.get("subreddit"),
                "title": post.get("title"),
                "type": post.get("type"),
                "created_at": post.get("created_at"),
                "scheduled_for": post.get("scheduled_for"),
                "posted_at": post.get("posted_at"),
                "quality_score": post.get("quality_score"),
            }
        )
    out = output_dir / "portal_export.json"
    out.write_text(json.dumps(summary, indent=2))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Research portal export")
    parser.add_argument("--config", default="config/research_pipeline.json")
    parser.add_argument("--schedule", default="scripts/content_scheduling/schedule/post_schedule.json")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})
    schedule = _load_json(Path(args.schedule), [])
    export_portal(config, schedule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
