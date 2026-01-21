"""
Purpose: Create Reddit API clients and fetch posts with fallbacks.
Constraints: API helpers only; no posting logic.
"""

# Imports
import sys
from typing import Iterable, Mapping, Optional

try:
    import praw
except ImportError:
    praw = None


# Helpers
def fetch_posts(reddit, subreddit_name: str, limit: int, fallback_posts: Iterable) -> Iterable:
    """
    Fetch posts from Reddit; on error, return fallback_posts.
    Returns an iterable (PRAW submissions or provided fallback).
    """
    try:
        subreddit = reddit.subreddit(subreddit_name)
        return subreddit.new(limit=limit)
    except Exception as exc:
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        return fallback_posts


def make_reddit_client(
    creds: Optional[Mapping[str, str]] = None,
    env_fallback: bool = True,
    timeout: int = 10,
    default_user_agent: str = "reddit-bot-research/1.0 (+contact)",
):
    """
    Create a PRAW Reddit client with consistent UA/timeout.
    If creds is None, falls back to environment variables when env_fallback is True.
    """
    if praw is None:
        raise ImportError("praw is not installed")
    c = creds or {}
    if env_fallback:
        import os

        def env_or(key, default=""):
            return c.get(key) or os.environ.get(key, default)

        client_id = env_or("REDDIT_CLIENT_ID")
        client_secret = env_or("REDDIT_CLIENT_SECRET")
        username = env_or("REDDIT_USERNAME")
        password = env_or("REDDIT_PASSWORD")
        user_agent = env_or("REDDIT_USER_AGENT", default_user_agent)
    else:
        client_id = c.get("client_id", "")
        client_secret = c.get("client_secret", "")
        username = c.get("username", "")
        password = c.get("password", "")
        user_agent = c.get("user_agent", default_user_agent)

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent or default_user_agent,
        requestor_kwargs={"timeout": timeout},
    )
