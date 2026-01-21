"""
STEP 2: Keyword filtering with the same safe fallback pattern.

What this script does:
- Loads .env values and tries to authenticate with Reddit.
- Scans a small batch of posts from safe subreddits.
- Prints only the posts whose title/body contain any of the defined keywords.
- If auth/network/API fails, it falls back to mock posts so filtering logic can be tested.
"""

import os
import sys
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import praw
from dotenv import load_dotenv
from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.utils.api_utils import normalize_post, matched_keywords, fetch_posts

# Mock data for offline/testing mode.
MOCK_POSTS: List[Mapping[str, str]] = [
    {
        "id": "mock1",
        "subreddit": "learnpython",
        "title": "Mock post asking for python help",
        "score": 10,
        "body": "Sample body mentioning python and a test script.",
    },
    {
        "id": "mock2",
        "subreddit": "learnpython",
        "title": "Mock post unrelated to keywords",
        "score": 5,
        "body": "This one should not match unless keywords change.",
    },
    {
        "id": "mock3",
        "subreddit": "learnpython",
        "title": "Need help debugging",
        "score": 8,
        "body": "Stuck on a problem; any python tips are welcome.",
    },
]


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


def scan_and_print(posts: Iterable, keywords: Sequence[str], default_subreddit: str) -> None:
    """Filter posts by keyword and print matches in a clear format."""
    for post in posts:
        info = normalize_post(post, default_subreddit)
        combined = f"{info['title']} {info['body']}".lower()
        hits = matched_keywords(combined, keywords)
        if not hits:
            continue

        print(
            f"[MATCH] ID: {info['id']}\n"
            f"Subreddit: r/{info['subreddit']}\n"
            f"Title: {info['title']}\n"
            f"Matched keywords: {hits}\n"
        )


def main() -> None:
    load_dotenv()
    config = ConfigManager().load_all()
    subreddits = config.bot_settings.get("subreddits") or config.default_subreddits
    keywords = config.bot_settings.get("keywords") or config.default_keywords
    forced_mock = os.getenv("MOCK_MODE") == "1"

    if forced_mock:
        print("MOCK_MODE is set; running with mock posts.")
        for subreddit_name in subreddits:
            print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(keywords)}")
            scan_and_print(MOCK_POSTS, keywords, subreddit_name)
        return

    try:
        reddit = get_reddit_client()
        user = reddit.user.me()
        print(f"Logged in as: {user}")
    except Exception as exc:
        # Any auth/HTTP failure triggers mock mode.
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        for subreddit_name in subreddits:
            print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(keywords)}")
            scan_and_print(MOCK_POSTS, keywords, subreddit_name)
        return

    # Happy path: fetch from Reddit, but each fetch still has its own fallback.
    for subreddit_name in subreddits:
        print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(keywords)}")
        posts = fetch_posts(reddit, subreddit_name, limit=50, fallback_posts=MOCK_POSTS)
        scan_and_print(posts, keywords, subreddit_name)


if __name__ == "__main__":
    main()
