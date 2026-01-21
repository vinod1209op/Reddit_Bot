"""
Purpose: Append structured rows to CSV logs.
Constraints: Storage helper only; no business logic.
"""

# Imports
import csv
from pathlib import Path
from typing import Mapping, Sequence, Any


# Helpers
def append_log(path: Path, row: Mapping[str, Any], header: Sequence[str]) -> None:
    """Append a row to a CSV log, creating headers on first write."""
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
