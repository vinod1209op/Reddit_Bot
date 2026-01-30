#!/usr/bin/env python3
"""
Update A/B metrics for posts in the schedule file.
"""
import argparse
import json
from pathlib import Path
from typing import Dict


def load_schedule(path: Path):
    if not path.exists():
        return []
    content = path.read_text().strip()
    if not content:
        return []
    return json.loads(content)


def save_schedule(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def update_metrics(post_id: str, metrics: Dict, schedule_path: Path) -> bool:
    schedule = load_schedule(schedule_path)
    updated = False
    for post in schedule:
        if post.get("id") == post_id:
            post.setdefault("metrics", {})
            post["metrics"].update(metrics)
            updated = True
            break
    if updated:
        save_schedule(schedule_path, schedule)
    return updated


def main():
    parser = argparse.ArgumentParser(description="Update A/B metrics for a post")
    parser.add_argument("--id", required=True, help="Post id in schedule file")
    parser.add_argument("--views", type=int, default=None)
    parser.add_argument("--upvotes", type=int, default=None)
    parser.add_argument("--comments", type=int, default=None)
    parser.add_argument("--retention", type=float, default=None)
    parser.add_argument("--crosspost", type=float, default=None)
    parser.add_argument(
        "--schedule",
        default="scripts/content_scheduling/schedule/post_schedule.json",
        help="Schedule file path",
    )
    args = parser.parse_args()

    metrics = {}
    for key in ("views", "upvotes", "comments", "retention", "crosspost"):
        val = getattr(args, key)
        if val is not None:
            metrics_key = "crosspost_effectiveness" if key == "crosspost" else key
            metrics[metrics_key] = val

    if not metrics:
        print("No metrics provided.")
        return 1

    updated = update_metrics(args.id, metrics, Path(args.schedule))
    if not updated:
        print("Post id not found.")
        return 2
    print("Metrics updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
