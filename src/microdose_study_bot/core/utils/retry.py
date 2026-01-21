"""
Purpose: Simple retry helper with exponential backoff.
Constraints: Utility only; callers decide which exceptions are retriable.
"""

# Imports
import random
import time
from typing import Callable, Iterable, Optional, TypeVar

T = TypeVar("T")


# Public API
def retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    jitter: float = 0.2,
    exceptions: Iterable[type[Exception]] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> T:
    """Retry a callable with exponential backoff and optional jitter."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except tuple(exceptions) as exc:  # type: ignore[arg-type]
            last_exc = exc
            if attempt >= attempts:
                break
            if on_retry:
                on_retry(attempt, exc)
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay += random.uniform(0, jitter)
            time.sleep(delay)
    raise last_exc if last_exc else RuntimeError("retry: failed without exception")
