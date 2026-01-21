"""
Purpose: Public wrapper for keyword scan workflow (step 2).
Constraints: Re-export only; no logic here.
"""

# Imports
from .bot_step2_keywords import main as run

__all__ = ["run"]
