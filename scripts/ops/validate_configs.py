from microdose_study_bot.core.logging import UnifiedLogger
logger = UnifiedLogger('ValidateConfigs').get_logger()
#!/usr/bin/env python3
"""Validate core config files and exit non-zero on errors."""
import json
import sys
from pathlib import Path

REQUIRED = [
    Path("config/activity_schedule.json"),
    Path("config/subreddit_creation.json"),
    Path("config/post_scheduling.json"),
]

OPTIONAL = [
    Path("config/accounts.json"),
]


def main() -> int:
    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        logger.info(f"Missing config files: {missing}")
        return 1

    errors = []
    for path in REQUIRED:
        try:
            json.loads(path.read_text())
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    if errors:
        logger.info("Config parse errors:")
        for err in errors:
            logger.info(f"- {err}")
        return 1

    optional_missing = [str(p) for p in OPTIONAL if not p.exists()]
    if optional_missing:
        logger.info(f"Optional config files missing (ok): {optional_missing}")

    logger.info("All required config files are present and valid JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())