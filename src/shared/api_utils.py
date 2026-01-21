import csv
import sys
from pathlib import Path
from textwrap import shorten
from typing import Iterable, Mapping, Sequence, List, Any, Optional

try:
    import praw
except ImportError:
    praw = None


def preview_text(text: str, width: int = 200) -> str:
    """Return a single-line preview of text, trimmed to width."""
    if not text:
        return "(no body text)"
    sanitized = " ".join(text.split())
    return shorten(sanitized, width=width, placeholder="...")


def normalize_post(post: Any, default_subreddit: str) -> Mapping[str, Any]:
    """Convert either a PRAW submission or a dict into a consistent mapping."""
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


def append_log(path: Path, row: Mapping[str, Any], header: Sequence[str]) -> None:
    """Append a row to a CSV log, creating headers on first write."""
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


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
