"""
Purpose: Simple in-memory rate limiter for automation actions.
Constraints: No network I/O; purely local tracking.
"""

from __future__ import annotations

import time
import random
import os
from typing import Dict, List, Tuple


class RateLimiter:
    def __init__(self):
        self.activity_log: Dict[str, Dict[str, List[float]]] = {}

    def _bypass_limits(self, action: str) -> bool:
        if os.getenv("BYPASS_ALL_LIMITS", "1").strip().lower() in ("1", "true", "yes"):
            return True
        if os.getenv("BYPASS_ENGAGEMENT_LIMITS", "1").strip().lower() in ("1", "true", "yes"):
            return str(action).lower() in {"comment", "reply", "vote", "follow", "save", "message"}
        return False

    def _log(self, account_name: str, action: str) -> List[float]:
        return self.activity_log.setdefault(account_name, {}).setdefault(action, [])

    def record_action(self, account_name: str, action: str) -> None:
        self._log(account_name, action).append(time.time())

    def check_rate_limit(
        self,
        account_name: str,
        action: str,
        limits_config: Dict[str, Dict[str, int]],
    ) -> Tuple[bool, int]:
        """
        Returns (allowed, wait_seconds).
        limits_config expects:
          { action: { per_hour: int, per_day: int, per_week: int, jitter_seconds: int } }
        """
        if self._bypass_limits(action):
            return True, 0

        if not limits_config or action not in limits_config:
            return True, 0

        limits = limits_config.get(action, {})
        now = time.time()
        timestamps = self._log(account_name, action)

        per_hour = limits.get("per_hour")
        per_day = limits.get("per_day")
        per_week = limits.get("per_week")
        jitter = int(limits.get("jitter_seconds", 0) or 0)

        def _count_since(seconds: int) -> int:
            cutoff = now - seconds
            return len([ts for ts in timestamps if ts >= cutoff])

        if per_hour and _count_since(3600) >= per_hour:
            return False, 3600 + (random.randint(-jitter, jitter) if jitter else 0)
        if per_day and _count_since(86400) >= per_day:
            return False, 86400 + (random.randint(-jitter, jitter) if jitter else 0)
        if per_week and _count_since(604800) >= per_week:
            return False, 604800 + (random.randint(-jitter, jitter) if jitter else 0)

        return True, 0
