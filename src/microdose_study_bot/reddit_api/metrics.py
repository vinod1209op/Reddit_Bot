"""
Purpose: Public wrapper for metrics workflow (step 4).
Constraints: Re-export only; no logic here.
"""

# Imports
from .bot_step4_metrics import main as run

__all__ = ["run"]
