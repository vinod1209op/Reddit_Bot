#!/usr/bin/env python3
"""
Ecosystem integration exports for Reddit <-> MCRDSE platform workflows.
Produces JSON/MD bundles for blog, Discord, and newsletter tooling.
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


def _save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _score_post(post: Dict) -> float:
    metrics = post.get("metrics") or {}
    return (metrics.get("comments") or 0) * 0.6 + (metrics.get("upvotes") or 0) * 0.4 + (post.get("quality_score") or 0)


def build_exports(config: Dict, schedule: List[Dict]) -> Dict[str, str]:
    exports = config.get("exports", {})
    max_items = int(config.get("recommendations", {}).get("max_items", 5))
    now = datetime.now().isoformat()

    sorted_posts = sorted(schedule, key=_score_post, reverse=True)
    top_posts = sorted_posts[:max_items]

    reddit_to_blog = [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "subreddit": p.get("subreddit"),
            "summary": (p.get("content") or "")[:280],
            "post_url": p.get("post_url"),
        }
        for p in top_posts
    ]
    blog_to_reddit = [
        {
            "title": f"New MCRDSE research: {p.get('title') or 'Update'}",
            "summary": "New research summary available on the MCRDSE platform.",
            "target_subreddit": p.get("subreddit"),
            "source_url": "",
        }
        for p in top_posts
    ]

    digest_lines = [
        "# Weekly Digest (Draft)",
        f"Generated: {now}",
        "",
        "## Top Discussions",
    ]
    for p in top_posts:
        digest_lines.append(f"- {p.get('title')} (r/{p.get('subreddit')})")

    discord_payload = {
        "generated_at": now,
        "messages": [
            {
                "title": p.get("title"),
                "subreddit": p.get("subreddit"),
                "url": p.get("post_url"),
            }
            for p in top_posts
        ],
    }

    newsletter_payload = {
        "generated_at": now,
        "highlights": [
            {"title": p.get("title"), "summary": (p.get("content") or "")[:180], "url": p.get("post_url")}
            for p in top_posts
        ],
    }

    out_paths = {
        "reddit_to_blog": exports.get("reddit_to_blog", "exports/ecosystem/reddit_to_blog.json"),
        "blog_to_reddit": exports.get("blog_to_reddit", "exports/ecosystem/blog_to_reddit.json"),
        "weekly_digest": exports.get("weekly_digest", "exports/ecosystem/weekly_digest.md"),
        "discord_payload": exports.get("discord_payload", "exports/ecosystem/discord_payload.json"),
        "newsletter_payload": exports.get("newsletter_payload", "exports/ecosystem/newsletter_payload.json"),
    }

    Path(out_paths["reddit_to_blog"]).parent.mkdir(parents=True, exist_ok=True)
    Path(out_paths["blog_to_reddit"]).parent.mkdir(parents=True, exist_ok=True)
    Path(out_paths["discord_payload"]).parent.mkdir(parents=True, exist_ok=True)
    Path(out_paths["newsletter_payload"]).parent.mkdir(parents=True, exist_ok=True)

    Path(out_paths["reddit_to_blog"]).write_text(json.dumps(reddit_to_blog, indent=2))
    Path(out_paths["blog_to_reddit"]).write_text(json.dumps(blog_to_reddit, indent=2))
    _save_text(Path(out_paths["weekly_digest"]), "\n".join(digest_lines))
    Path(out_paths["discord_payload"]).write_text(json.dumps(discord_payload, indent=2))
    Path(out_paths["newsletter_payload"]).write_text(json.dumps(newsletter_payload, indent=2))

    return out_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Ecosystem integration exports")
    parser.add_argument("--config", default="config/ecosystem_integration.json")
    parser.add_argument("--schedule", default="scripts/content_scheduling/schedule/post_schedule.json")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})
    schedule = _load_json(Path(args.schedule), [])
    build_exports(config, schedule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
