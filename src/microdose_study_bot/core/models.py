"""
Purpose: Shared data models for cross-module communication.
Constraints: Data containers only; no logic.
"""

# Imports

from dataclasses import dataclass
from typing import Optional


# Public API
@dataclass
class ScanMatch:
    """Minimal representation of a matched Reddit post."""

    post_id: str
    title: str
    subreddit: str
    url: str
    matched_keywords: Optional[list[str]] = None
