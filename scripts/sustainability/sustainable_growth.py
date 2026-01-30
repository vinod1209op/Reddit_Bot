#!/usr/bin/env python3
"""
Sustainable growth planning utilities.
Generates a plan for network effects, evangelist program, and resource allocation.
"""
import argparse
import json
from datetime import datetime, timedelta
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


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _score_posts(posts: List[Dict], weights: Dict) -> float:
    upvotes = 0
    comments = 0
    views = 0
    for post in posts:
        metrics = post.get("metrics") or {}
        upvotes += metrics.get("upvotes") or 0
        comments += metrics.get("comments") or 0
        views += metrics.get("views") or 0
    if not posts:
        return 0.0
    avg_upvotes = upvotes / len(posts)
    avg_comments = comments / len(posts)
    avg_views = views / len(posts)
    return (
        avg_upvotes * weights.get("upvotes", 0.5)
        + avg_comments * weights.get("comments", 0.4)
        + avg_views * weights.get("views", 0.1)
    )


def _next_event_date(days: int, hour: int) -> datetime:
    now = datetime.now()
    target = now + timedelta(days=days)
    return target.replace(hour=hour, minute=0, second=0, microsecond=0)


def build_plan(config: Dict, schedule: List[Dict], network: Dict) -> Dict:
    resources = config.get("resource_optimization", {})
    min_posts = int(resources.get("min_posts_for_scoring", 5))
    weights = resources.get("weights", {})

    posts_by_sub = {}
    for post in schedule:
        sub = post.get("subreddit")
        if not sub:
            continue
        posts_by_sub.setdefault(sub, []).append(post)

    scored = []
    for sub, posts in posts_by_sub.items():
        score = _score_posts(posts, weights)
        scored.append({"subreddit": sub, "score": round(score, 3), "posts": len(posts)})

    scored.sort(key=lambda item: item["score"], reverse=True)
    focus_limit = int(resources.get("max_focus_subreddits", 2))
    pause_limit = int(resources.get("max_pause_subreddits", 1))
    focus_threshold = float(resources.get("focus_threshold", 0.6))
    pause_threshold = float(resources.get("pause_threshold", 0.2))

    focus = [s for s in scored if s["posts"] >= min_posts and s["score"] >= focus_threshold][:focus_limit]
    pause = [s for s in reversed(scored) if s["posts"] >= min_posts and s["score"] <= pause_threshold][:pause_limit]
    maintain = [s for s in scored if s not in focus and s not in pause]

    related_map = network.get("related_map", {})
    journey = [{"from": key, "to": related_map.get(key, [])} for key in related_map.keys()]

    events_cfg = config.get("network_events", {})
    events = []
    for key, evt in events_cfg.items():
        date = _next_event_date(int(evt.get("cadence_days", 30)), int(evt.get("hour", 12)))
        events.append(
            {
                "key": key,
                "title": evt.get("title"),
                "date": date.isoformat(),
                "subreddits": network.get("subreddits", []),
            }
        )

    evangelist = config.get("evangelist_program", {})
    plan = {
        "generated_at": datetime.now().isoformat(),
        "resource_allocation": {
            "focus": focus,
            "maintain": maintain,
            "pause": pause,
            "min_posts_for_scoring": min_posts,
        },
        "user_journey_paths": journey,
        "network_events": events,
        "evangelist_program": evangelist,
    }
    return plan


def write_schedule_events(schedule_path: Path, plan: Dict, account: str) -> int:
    if not schedule_path.exists():
        schedule = []
    else:
        schedule = _load_json(schedule_path, [])
    created = 0
    for event in plan.get("network_events", []):
        for subreddit in event.get("subreddits", []):
            post = {
                "id": f"event_{int(datetime.now().timestamp())}_{subreddit}",
                "type": "event",
                "subreddit": subreddit,
                "title": event.get("title"),
                "content": "Network event scheduled. See details in the plan.",
                "status": "scheduled",
                "created_at": datetime.now().isoformat(),
                "scheduled_for": event.get("date"),
                "account": account,
                "attempts": 0,
                "last_attempt": None,
                "posted_at": None,
                "post_url": None,
                "error": None,
                "ai_assisted": False,
            }
            schedule.append(post)
            created += 1
    schedule_path.parent.mkdir(parents=True, exist_ok=True)
    schedule_path.write_text(json.dumps(schedule, indent=2))
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Sustainable growth planning")
    parser.add_argument("--config", default="config/sustainable_growth.json")
    parser.add_argument("--network", default="config/subreddit_network.json")
    parser.add_argument("--schedule", default="scripts/content_scheduling/schedule/post_schedule.json")
    parser.add_argument("--write-schedule", action="store_true")
    parser.add_argument("--account", default="account4")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})
    network = _load_json(Path(args.network), {})
    schedule = _load_json(Path(args.schedule), [])
    plan = build_plan(config, schedule, network)

    _write_json(Path("logs/sustainable_growth_plan.json"), plan)
    lines = [
        "# Sustainable Growth Plan",
        f"Generated: {plan['generated_at']}",
        "",
        "## Resource Allocation",
    ]
    for label in ("focus", "maintain", "pause"):
        lines.append(f"### {label.title()}")
        for item in plan["resource_allocation"].get(label, []):
            lines.append(f"- r/{item['subreddit']} | score: {item['score']} | posts: {item['posts']}")
        if not plan["resource_allocation"].get(label):
            lines.append("- None")
    lines.extend(["", "## Network Events"])
    for evt in plan.get("network_events", []):
        lines.append(f"- {evt['title']} on {evt['date']} | subs: {', '.join(evt.get('subreddits', []))}")
    lines.extend(["", "## User Journey Paths"])
    for path in plan.get("user_journey_paths", []):
        lines.append(f"- {path['from']} -> {', '.join(path.get('to', []))}")
    lines.extend(["", "## Evangelist Program"])
    evangelist = plan.get("evangelist_program", {})
    if evangelist:
        lines.append(f"- Min comments: {evangelist.get('min_comments')}")
        lines.append(f"- Min upvotes: {evangelist.get('min_upvotes')}")
        lines.append(f"- Min days active: {evangelist.get('min_days_active')}")
        lines.append(f"- Flair: {evangelist.get('flair_name')}")
    Path("logs").mkdir(parents=True, exist_ok=True)
    Path("logs/sustainable_growth_plan.md").write_text("\n".join(lines))

    if args.write_schedule:
        created = write_schedule_events(Path(args.schedule), plan, args.account)
        print(f"Wrote {created} scheduled event posts.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
