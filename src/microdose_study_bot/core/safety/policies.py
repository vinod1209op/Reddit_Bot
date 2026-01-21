"""
Purpose: Central safety policies and enforcement helpers.
Constraints: Policy definitions only; no automation side effects.
"""

# Imports
import os
from typing import Dict

# Constants
DEFAULT_REPLY_RULES: Dict[str, object] = {
    "min_sentences": 2,
    "max_sentences": 5,
    "requires_human_approval": True,
    "allow_autopost": False,
}

# Public API
def enforce_readonly_env() -> None:
    """Force read-only behavior for scheduled runners."""
    os.environ["ENABLE_POSTING"] = "0"
    os.environ["USE_LLM"] = "0"
