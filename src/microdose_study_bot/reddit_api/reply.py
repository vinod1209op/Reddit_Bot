"""
Purpose: Public wrapper for reply drafting workflow (step 3).
Constraints: Re-export only; no logic here.
"""

# Imports
from .bot_step3_replies import main as run

__all__ = ["run"]
