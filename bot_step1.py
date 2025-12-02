"""
STEP 1: Basic connection with a safe fallback to mock data.

What this script does:
- Loads .env values (Reddit credentials) using python-dotenv.
- Tries to authenticate with Reddit and prints the logged-in username.
- Fetches the latest 5 posts from a safe test subreddit (r/learnpython) and prints a short summary.
- If any auth/network/API issue occurs, it falls back to mock posts so the flow is still testable.
"""

import os
import sys
from textwrap import shorten
from typing import Iterable, List, Mapping

import praw
import prawcore
from dotenv import load_dotenv


# Mock data used when Reddit API is unavailable or credentials are missing.
MOCK_POSTS: List[Mapping[str, str]] = [
    {
        "id": "mock1",
        "title": "Mock post about anxiety and focus",
        "score": 42,
        "body": "Sample body text about managing focus and being mindful of limits.",
    },
    {
        "id": "mock2",
        "title": "Mock discussion on healthy study habits",
        "score": 23,
        "body": "People report that breaks, sleep, and hydration help more than supplements.",
    },
    {
        "id": "mock3",
        "title": "Mock question: what is mindfulness?",
        "score": 7,
        "body": "Mindfulness is paying attention on purpose, in the present moment, without judgment.",
    },
]


def preview_text(text: str, width: int = 200) -> str:
    """Return a single-line preview of the post body."""
    if not text:
        return "(no body text)"
    sanitized = " ".join(text.split())
    return shorten(sanitized, width=width, placeholder="...")


def get_reddit_client() -> praw.Reddit:
    """Create a Reddit client using environment variables. Errors bubble up to be handled in main."""
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )


def fetch_posts(reddit: praw.Reddit, subreddit_name: str, limit: int = 5) -> Iterable:
    """
    Try to fetch posts from Reddit. Any API/auth errors trigger a mock fallback.
    Returning an iterable keeps the print loop simple.
    """
    try:
        subreddit = reddit.subreddit(subreddit_name)
        return subreddit.new(limit=limit)
    except (prawcore.exceptions.PrawcoreException, KeyError) as exc:
        # KeyError can happen if env vars are missing; treat it like an auth issue.
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        return MOCK_POSTS
    except Exception as exc:
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return MOCK_POSTS


def print_posts(posts: Iterable) -> None:
    """Print posts in a consistent, compact format."""
    for post in posts:
        # Handle both PRAW submissions and dict-based mock posts.
        title = getattr(post, "title", None) or post.get("title", "")
        post_id = getattr(post, "id", None) or post.get("id", "")
        score = getattr(post, "score", None) or post.get("score", 0)
        body = getattr(post, "selftext", None) or post.get("body", "")

        body_preview = preview_text(body)
        print(
            f"- {title}\n"
            f"  ID: {post_id} | Score: {score}\n"
            f"  Preview: {body_preview}\n"
        )


def main() -> None:
    load_dotenv()

    forced_mock = os.getenv("MOCK_MODE") == "1"
    subreddit_name = "learnpython"  # Safe test subreddit for read-only checks

    if forced_mock:
        print("MOCK_MODE is set; running with mock posts.")
        print(f"\nLatest posts from r/{subreddit_name}:")
        print_posts(MOCK_POSTS)
        return

    try:
        reddit = get_reddit_client()
        user = reddit.user.me()
        print(f"Logged in as: {user}")
        print(f"\nLatest posts from r/{subreddit_name}:")
        posts = fetch_posts(reddit, subreddit_name, limit=5)
        print_posts(posts)
    except Exception as exc:
        # Any failure to authenticate or call the API drops to mock mode.
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        print(f"\nLatest posts from r/{subreddit_name}:")
        print_posts(MOCK_POSTS)


if __name__ == "__main__":
    main()
