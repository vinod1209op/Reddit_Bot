#!/usr/bin/env python3
"""
Generate engagement reply candidates from templates.
"""
import argparse
import json
import random
from pathlib import Path


def load_templates(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def load_config(path: Path):
    if not path.exists():
        return {}
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else {}
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Generate engagement replies from templates")
    parser.add_argument("--category", default="default", help="Template category")
    parser.add_argument("--count", type=int, default=3, help="Number of replies")
    parser.add_argument("--templates", default="config/engagement_reply_templates.json")
    parser.add_argument("--config", default="config/engagement_program.json")
    args = parser.parse_args()

    templates = load_templates(Path(args.templates))
    config = load_config(Path(args.config))
    bot_prefix = config.get("bot_prefix", "")
    pool = templates.get(args.category) or templates.get("default") or []
    if not pool:
        print("No templates found.")
        return 1
    replies = random.sample(pool, k=min(args.count, len(pool)))
    for r in replies:
        if bot_prefix and not r.startswith(bot_prefix):
            r = f"{bot_prefix}{r}"
        print(f"- {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
