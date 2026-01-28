"""
Purpose: Lightweight in-process metrics collection with JSON snapshots.
Constraints: No external dependencies; file-based output only.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Optional


class MetricsCollector:
    """Thread-safe metrics collector with rolling rate windows."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._totals: Dict[str, int] = defaultdict(int)
        self._errors: Dict[str, int] = defaultdict(int)
        self._timestamps: Dict[str, Deque[float]] = defaultdict(deque)

    def record(self, name: str, success: bool = True) -> None:
        now = time.time()
        with self._lock:
            self._totals[name] += 1
            if not success:
                self._errors[name] += 1
            dq = self._timestamps[name]
            dq.append(now)
            self._prune(dq, now)

    def record_error(self, name: str = "error") -> None:
        self.record(name, success=False)

    def record_post_attempt(self, success: bool = True) -> None:
        self.record("post_attempt", success=success)

    def snapshot(self) -> Dict[str, object]:
        now = time.time()
        with self._lock:
            rates = {
                name: self._rate(dq, now)
                for name, dq in self._timestamps.items()
            }
            return {
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "uptime_seconds": int(now - self._start_time),
                "window_seconds": self.window_seconds,
                "totals": dict(self._totals),
                "errors": dict(self._errors),
                "rates_per_min": rates,
            }

    def write_snapshot(self, path: Path) -> None:
        payload = self.snapshot()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _prune(self, dq: Deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

    def _rate(self, dq: Deque[float], now: float) -> float:
        self._prune(dq, now)
        if self.window_seconds <= 0:
            return 0.0
        return round((len(dq) / self.window_seconds) * 60.0, 3)


_GLOBAL_METRICS: Optional[MetricsCollector] = None
_GLOBAL_LOCK = threading.Lock()


def get_metrics() -> MetricsCollector:
    global _GLOBAL_METRICS
    with _GLOBAL_LOCK:
        if _GLOBAL_METRICS is None:
            _GLOBAL_METRICS = MetricsCollector()
        return _GLOBAL_METRICS
