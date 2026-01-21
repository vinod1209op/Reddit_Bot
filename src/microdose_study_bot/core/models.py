"""Shared data models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScanMatch:
    """Minimal representation of a matched Reddit post."""

    post_id: str
    title: str
    subreddit: str
    url: str
    matched_keywords: Optional[list[str]] = None
