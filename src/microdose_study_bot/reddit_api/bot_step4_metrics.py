"""
Purpose: Collect engagement metrics for previously posted comments.
Constraints: Read-only; no replies or posting.
"""

# Imports

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

# Constants
PROJECT_ROOT = Path(__file__).resolve().parents[2]

import praw
import prawcore
from dotenv import load_dotenv


LOG_PATH = Path("bot_logs.csv")
METRICS_PATH = Path("bot_metrics.csv")


# Helpers
def get_reddit_client() -> praw.Reddit:
    """Create a Reddit client using environment variables. Errors bubble up to be handled in main."""
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "reddit-bot-research/1.0 (+contact)"),
        requestor_kwargs={"timeout": 10},
    )


def read_log_rows(path: Path) -> Iterable[Dict[str, str]]:
    """Yield log rows from bot_logs.csv."""
    if not path.exists():
        print(f"No log file found at {path}. Nothing to check.")
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def sanitize_comment_id(raw_id: str) -> str:
    """Strip a leading t1_ prefix if present."""
    return raw_id.replace("t1_", "") if raw_id else ""


def append_metrics(row: Dict[str, str]) -> None:
    """Append a metrics row to bot_metrics.csv, creating headers on first write."""
    header = [
        "timestamp_checked_utc",
        "run_id",
        "subreddit",
        "post_id",
        "comment_id",
        "title",
        "matched_keywords",
        "score",
        "replies_count",
        "error",
    ]
    file_exists = METRICS_PATH.exists()
    with METRICS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def fetch_metrics(reddit: praw.Reddit, comment_id: str) -> Dict[str, int]:
    """Fetch score and reply count for a comment, handling API errors gracefully."""
    try:
        comment = reddit.comment(id=comment_id)
        comment.refresh()  # Refresh to ensure latest score/replies
        # Shallow count of replies; replace_more could be expensive, so skip it by default.
        replies_count = len(comment.replies)
        return {"score": comment.score, "replies_count": replies_count, "error": ""}
    except prawcore.exceptions.PrawcoreException as exc:
        return {"score": "", "replies_count": "", "error": f"PRAW error: {exc}"}
    except Exception as exc:
        return {"score": "", "replies_count": "", "error": f"Unexpected error: {exc}"}


# Public API
def main() -> None:
    load_dotenv()

    if os.getenv("MOCK_MODE") == "1":
        print("MOCK_MODE is set; skipping API checks and exiting.")
        return

    try:
        reddit = get_reddit_client()
        user = reddit.user.me()
        print(f"Authenticated as: {user}")
    except Exception as exc:
        print(f"Failed to authenticate to Reddit: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = list(read_log_rows(LOG_PATH))
    if not rows:
        print("No log rows to process.")
        return

    for row in rows:
        if row.get("posted", "").lower() != "true":
            continue
        comment_id = sanitize_comment_id(row.get("comment_id", ""))
        if not comment_id:
            continue

        metrics = fetch_metrics(reddit, comment_id)
        metrics_row = {
            "timestamp_checked_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": row.get("run_id", ""),
            "subreddit": row.get("subreddit", ""),
            "post_id": row.get("post_id", ""),
            "comment_id": comment_id,
            "title": row.get("title", ""),
            "matched_keywords": row.get("matched_keywords", ""),
            "score": metrics["score"],
            "replies_count": metrics["replies_count"],
            "error": metrics["error"],
        }
        append_metrics(metrics_row)
        print(
            f"Checked comment {comment_id}: score={metrics['score']} replies={metrics['replies_count']} "
            f"{'(error logged)' if metrics['error'] else ''}"
        )


if __name__ == "__main__":
    main()
