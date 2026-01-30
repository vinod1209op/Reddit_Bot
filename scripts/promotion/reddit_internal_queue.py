#!/usr/bin/env python3
"""
Generate Reddit internal promotion queue entries for /r/newreddits and /r/findareddit.
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


def _load_seo():
    return _load_json(Path("config/seo/subreddit_seo.json"), {})


def generate():
    cfg = _load_json(Path("config/reddit_internal_promo.json"), {})
    if not cfg.get("enabled", True):
        return {}
    subs = cfg.get("subreddits", [])
    seo = _load_seo()
    default = seo.get("default", {})
    items = []
    for sub in subs[: int(cfg.get("max_items", 5))]:
        specific = seo.get(sub, {})
        desc_keywords = (specific.get("description_keywords") or default.get("description_keywords") or [])[:4]
        title_keywords = (specific.get("title_keywords") or default.get("title_keywords") or [])[:3]
        summary = (
            f"r/{sub} focuses on " + ", ".join(title_keywords or ["research"]) +
            ". Keywords: " + ", ".join(desc_keywords or ["microdosing", "psychedelic research"])
        )
        items.append({"subreddit": sub, "summary": summary})

    out = {
        "generated_at": datetime.now().isoformat(),
        "items": items,
        "targets": cfg.get("targets", {}),
    }
    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    Path("logs/reddit_internal_queue.json").write_text(json.dumps(out, indent=2))
    lines = ["# Reddit Internal Promotion Queue", f"Generated: {out['generated_at']}", ""]
    for item in items:
        lines.append(f"- {item['subreddit']}: {item['summary']}")
    Path("logs/reddit_internal_queue.md").write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    generate()
