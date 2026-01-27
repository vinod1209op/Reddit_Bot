#!/usr/bin/env python3
"""Validate core config files and exit non-zero on errors."""
import json
import sys
from pathlib import Path

REQUIRED = [
    Path("config/accounts.json"),
    Path("config/activity_schedule.json"),
    Path("config/subreddit_creation.json"),
    Path("config/post_scheduling.json"),
]


def main() -> int:
    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        print(f"Missing config files: {missing}")
        return 1

    errors = []
    for path in REQUIRED:
        try:
            json.loads(path.read_text())
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    if errors:
        print("Config parse errors:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("All required config files are present and valid JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
