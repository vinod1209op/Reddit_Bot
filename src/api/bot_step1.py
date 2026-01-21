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
from pathlib import Path
from typing import Iterable, List, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import praw
from dotenv import load_dotenv
from shared.config_manager import ConfigManager
from shared.api_utils import preview_text, fetch_posts


# Mock data used when Reddit API is unavailable or credentials are missing.
MOCK_POSTS: List[Mapping[str, str]] = [
    {
        "id": "mock1",
        "title": "Mock post about microdosing and anxiety",
        "score": 42,
        "body": "Curious if low-dose psilocybin affects anxiety; looking for general harm-reduction info.",
    },
    {
        "id": "mock2",
        "title": "Mock discussion on set and setting",
        "score": 23,
        "body": "People talk about mindset, environment, and taking breaks; no dosing details requested.",
    },
    {
        "id": "mock3",
        "title": "Mock question: how to stay safe exploring psychedelics?",
        "score": 7,
        "body": "Seeking general safety tips and resources; understand this is not medical advice.",
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
    config = ConfigManager().load_all()
    subreddits = config.bot_settings.get("subreddits") or config.default_subreddits
    subreddit_name = subreddits[0] if subreddits else "test"  # Safe test subreddit for read-only checks

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
        posts = fetch_posts(reddit, subreddit_name, limit=5, fallback_posts=MOCK_POSTS)
        print_posts(posts)
    except Exception as exc:
        # Any failure to authenticate or call the API drops to mock mode.
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        print(f"\nLatest posts from r/{subreddit_name}:")
        print_posts(MOCK_POSTS)


if __name__ == "__main__":
    main()
