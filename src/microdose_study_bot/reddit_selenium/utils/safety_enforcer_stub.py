"""
Purpose: Placeholder safety enforcement stub.
Constraints: Disabled by default; for local testing only.
"""

# Imports
import logging
import os
from typing import Dict, Optional

# Constants
logger = logging.getLogger(__name__)


# Public API
class SafetyEnforcerStub:
    """Minimal stub that allows all actions but warns."""

    def validate_action(self, action: str, details: Optional[Dict] = None) -> bool:
        if os.getenv("ALLOW_SAFETY_STUB", "0") != "1":
            raise RuntimeError(
                "SafetyEnforcerStub is non-production and disabled by default. "
                "Set ALLOW_SAFETY_STUB=1 only for local testing."
            )
        logger.warning(
            "SafetyEnforcerStub placeholder used for action '%s'; no checks enforced.",
            action,
        )
        return True
