"""
Cleanup helper to keep logs/ tidy.

Usage:
  python scripts/one_time/cleanup_logs.py --keep-days 7 --keep-max 10
Defaults to keep files modified within 7 days and also keep at most 10 most-recent,
deleting older ones. Skips CSVs if you want to keep data; tweak as needed.
"""
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path


def list_log_files(log_dir: Path):
    for path in log_dir.glob("**/*"):
        if path.is_file():
            yield path


def main():
    parser = argparse.ArgumentParser(description="Trim old log files.")
    parser.add_argument("--log-dir", default="logs", help="Log directory to clean.")
    parser.add_argument("--keep-days", type=int, default=7, help="Keep files modified within this many days.")
    parser.add_argument("--keep-max", type=int, default=10, help="Keep at most this many most-recent files.")
    parser.add_argument("--include-csv", action="store_true", help="Include CSVs in cleanup (defaults to skipping).")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        print(f"No log directory at {log_dir}")
        return

    cutoff = datetime.now() - timedelta(days=args.keep_days)
    files = list(list_log_files(log_dir))

    # Sort by mtime descending (newest first)
    files_sorted = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    kept = []
    removed = []
    for idx, path in enumerate(files_sorted):
        suffix = path.suffix.lower()
        if (not args.include_csv) and suffix == ".csv":
            kept.append(path)
            continue

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if idx < args.keep_max or mtime >= cutoff:
            kept.append(path)
        else:
            try:
                path.unlink()
                removed.append(path)
            except Exception as e:
                print(f"Could not remove {path}: {e}")

    print(f"Kept {len(kept)} files, removed {len(removed)} files.")
    if removed:
        for p in removed:
            print(f"Removed: {p}")


if __name__ == "__main__":
    main()
