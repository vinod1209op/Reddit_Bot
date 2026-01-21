import os
from typing import Optional, Tuple


DEFAULT_SHARDS = (
    ("new", None),
    ("top", "day"),
    ("top", "week"),
    ("top", "month"),
    ("top", "year"),
    ("top", "all"),
    ("hot", None),
    ("rising", None),
)


def compute_scan_shard(index: int, total: int) -> Tuple[str, Optional[str], int]:
    """Return (sort, time_range, page_offset) for a given account index."""
    if total <= 1:
        return "new", None, 0

    sort, time_range = DEFAULT_SHARDS[index % len(DEFAULT_SHARDS)]
    max_page_offset = int(os.getenv("SCAN_PAGE_OFFSET_MAX", "3"))
    page_offset = min(index, max_page_offset)
    return sort, time_range, page_offset
