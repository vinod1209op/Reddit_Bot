#!/usr/bin/env python3
"""
Export cross-platform promotion queues from scheduled/posted posts.
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


def _load_config():
    return _load_json(Path("config/cross_platform_promo.json"), {})


def _make_twitter(text: str, max_len: int) -> str:
    text = text.replace("\n", " ")
    return text[:max_len]


def export():
    cfg = _load_config()
    if not cfg.get("enabled", True):
        return {}
    schedule = _load_schedule()
    statuses = set(cfg.get("include_statuses", ["posted"]))
    posts = [p for p in schedule if p.get("status") in statuses]
    posts = posts[: int(cfg.get("max_items", 10))]
    output_dir = Path("logs")
    output_dir.mkdir(parents=True, exist_ok=True)

    twitter_lines = []
    discord_lines = []
    newsletter_lines = ["# Weekly Digest", f"Generated: {datetime.now().isoformat()}", ""]
    blog_lines = ["# Blog Queue", f"Generated: {datetime.now().isoformat()}", ""]
    promo_items = []

    for post in posts:
        title = post.get("title") or ""
        subreddit = post.get("subreddit") or ""
        url = post.get("post_url") or ""
        base = f"{title} (r/{subreddit})"
        twitter_lines.append(_make_twitter(base + (f" {url}" if url else ""), cfg["channels"]["twitter"]["max_len"]))
        discord_lines.append(f"{base}\n{url}".strip())
        newsletter_lines.append(f"- **{title}** (r/{subreddit}) {url}".strip())
        blog_lines.append(f"- {title} — expand into a full post. {url}".strip())
        promo_items.append({"title": title, "subreddit": subreddit, "url": url})

    Path("logs/twitter_queue.txt").write_text("\n".join(twitter_lines))
    Path("logs/discord_queue.txt").write_text("\n\n".join(discord_lines))
    Path("logs/newsletter_digest.md").write_text("\n".join(newsletter_lines))
    Path("logs/blog_queue.md").write_text("\n".join(blog_lines))
    Path("logs/promo_queue.json").write_text(json.dumps(promo_items, indent=2))
    return {"count": len(promo_items)}


if __name__ == "__main__":
    export()
