"""Smoke test package."""

import os
import sys


def _add_repo_paths() -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    src_root = os.path.join(repo_root, "src")
    for path in (repo_root, src_root):
        if path and path not in sys.path:
            sys.path.insert(0, path)


_add_repo_paths()
