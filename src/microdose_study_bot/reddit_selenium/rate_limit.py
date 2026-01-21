"""
Purpose: Public wrapper for Selenium rate limiting.
Constraints: Re-export only; no logic here.
"""

# Imports
from .utils.rate_limiter import RateLimiter

__all__ = ["RateLimiter"]
