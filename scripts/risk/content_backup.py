#!/usr/bin/env python3
"""
Snapshot key content files for recovery.
"""
import json
import shutil
from pathlib import Path
from datetime import datetime


def _load_config():
    path = Path("config/risk_management.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def backup():
    cfg = _load_config()
    paths = cfg.get("backup", {}).get("content_backup_paths", [])
    if not paths:
        return []
    out_dir = Path("logs/content_backups") / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in paths:
        src = Path(p)
        if not src.exists():
            continue
        dest = out_dir / src.name
        shutil.copy2(src, dest)
        copied.append(str(dest))
    return copied


if __name__ == "__main__":
    files = backup()
    print(f"Backed up {len(files)} files.")
