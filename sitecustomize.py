"""Ensure src/ is on sys.path when running from repo root."""

from __future__ import annotations

import sys
from pathlib import Path


def _add_path(path: Path) -> None:
    resolved = str(path.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

_add_path(ROOT)
if SRC.exists():
    _add_path(SRC)
