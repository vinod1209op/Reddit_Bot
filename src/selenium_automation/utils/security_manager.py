"""
Placeholder security manager.

Currently no security checks are enforced; this stub exists to avoid silent failures
when imported. Extend with real checks before using in production.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SecurityManager:
    """Minimal stub that allows all actions but warns."""

    def validate_action(self, action: str, details: Optional[Dict] = None) -> bool:
        logger.warning(
            "SecurityManager placeholder used for action '%s'; no checks enforced.",
            action,
        )
        return True
