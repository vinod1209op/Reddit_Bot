"""
Purpose: Public wrapper for Selenium BrowserManager.
Constraints: Re-export only; no logic here.
"""

# Imports
from .utils.browser_manager import BrowserManager

__all__ = ["BrowserManager"]
