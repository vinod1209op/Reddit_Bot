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
from typing import Iterable, List, Mapping, Sequence

import praw
import prawcore
from dotenv import load_dotenv


SUBREDDITS: Sequence[str] = ["learnpython"]  # Swap to wellness subs later.
KEYWORDS: Sequence[str] = ["test", "python", "help"]  # Swap to wellness-related terms later.

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
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )


def fetch_posts(reddit: praw.Reddit, subreddit_name: str, limit: int = 50) -> Iterable:
    """Fetch posts from Reddit; on error, return mock posts."""
    try:
        subreddit = reddit.subreddit(subreddit_name)
        return subreddit.new(limit=limit)
    except (prawcore.exceptions.PrawcoreException, KeyError) as exc:
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        return MOCK_POSTS
    except Exception as exc:
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return MOCK_POSTS


def normalize_post(post, default_subreddit: str) -> Mapping[str, str]:
    """Convert either a PRAW submission or a mock dict into a consistent mapping."""
    return {
        "id": getattr(post, "id", None) or post.get("id", ""),
        "subreddit": getattr(post, "subreddit", None) or post.get("subreddit", default_subreddit),
        "title": getattr(post, "title", None) or post.get("title", ""),
        "score": getattr(post, "score", None) or post.get("score", 0),
        "body": getattr(post, "selftext", None) or post.get("body", ""),
    }


def matched_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    """Return a list of keywords that appear in the text (case-insensitive)."""
    haystack = text.lower()
    return [kw for kw in keywords if kw.lower() in haystack]


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
    forced_mock = os.getenv("MOCK_MODE") == "1"

    if forced_mock:
        print("MOCK_MODE is set; running with mock posts.")
        for subreddit_name in SUBREDDITS:
            print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(KEYWORDS)}")
            scan_and_print(MOCK_POSTS, KEYWORDS, subreddit_name)
        return

    try:
        reddit = get_reddit_client()
        user = reddit.user.me()
        print(f"Logged in as: {user}")
    except Exception as exc:
        # Any auth/HTTP failure triggers mock mode.
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        for subreddit_name in SUBREDDITS:
            print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(KEYWORDS)}")
            scan_and_print(MOCK_POSTS, KEYWORDS, subreddit_name)
        return

    # Happy path: fetch from Reddit, but each fetch still has its own fallback.
    for subreddit_name in SUBREDDITS:
        print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(KEYWORDS)}")
        posts = fetch_posts(reddit, subreddit_name, limit=50)
        scan_and_print(posts, KEYWORDS, subreddit_name)


if __name__ == "__main__":
    main()
