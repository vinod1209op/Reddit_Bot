"""
Purpose: Normalize Reddit content and match keywords.
Constraints: Pure helpers only; no side effects.
"""

# Imports
from textwrap import shorten
from typing import Mapping, Sequence, List, Any


# Helpers
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
