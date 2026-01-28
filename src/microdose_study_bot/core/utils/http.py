"""
Purpose: HTTP helpers with retry/backoff.
Constraints: No business logic; callers handle response validation.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

from microdose_study_bot.core.utils.retry import retry


def request_with_retry(
    method: str,
    url: str,
    *,
    retry_on_status: Optional[set[int]] = None,
    attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter: Optional[float] = None,
    **kwargs,
) -> requests.Response:
    retry_on_status = retry_on_status or {500, 502, 503, 504}
    attempts = attempts or int(os.getenv("HTTP_RETRY_ATTEMPTS", "3"))
    base_delay = base_delay if base_delay is not None else float(os.getenv("HTTP_RETRY_BASE_DELAY", "0.5"))
    max_delay = max_delay if max_delay is not None else float(os.getenv("HTTP_RETRY_MAX_DELAY", "5.0"))
    jitter = jitter if jitter is not None else float(os.getenv("HTTP_RETRY_JITTER", "0.2"))

    def _do_request():
        resp = requests.request(method, url, **kwargs)
        if resp.status_code in retry_on_status:
            raise RuntimeError(f"Retryable HTTP status: {resp.status_code}")
        return resp

    return retry(
        _do_request,
        attempts=attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
    )


def get_with_retry(url: str, **kwargs) -> requests.Response:
    return request_with_retry("GET", url, **kwargs)


def post_with_retry(url: str, **kwargs) -> requests.Response:
    return request_with_retry("POST", url, **kwargs)


def put_with_retry(url: str, **kwargs) -> requests.Response:
    return request_with_retry("PUT", url, **kwargs)


def patch_with_retry(url: str, **kwargs) -> requests.Response:
    return request_with_retry("PATCH", url, **kwargs)
