#!/usr/bin/env python3
"""
Unified CLI entrypoint with subcommands.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(rel_path: str, args: list[str]) -> int:
    script_path = REPO_ROOT / rel_path
    if not script_path.exists():
        print(f"Script not found: {script_path}")
        return 1
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(prog="reddit-bot", description="Reddit automation CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run read-only scanner")
    scan.add_argument("args", nargs=argparse.REMAINDER)

    hscan = sub.add_parser("humanized-scan", help="Run humanized scanner")
    hscan.add_argument("args", nargs=argparse.REMAINDER)

    moderation = sub.add_parser("moderation", help="Run moderation manager")
    moderation.add_argument("args", nargs=argparse.REMAINDER)

    schedule = sub.add_parser("schedule", help="Run post scheduler")
    schedule.add_argument("args", nargs=argparse.REMAINDER)

    community = sub.add_parser("community-manager", help="Run community manager")
    community.add_argument("args", nargs=argparse.REMAINDER)

    reports = sub.add_parser("reports", help="Generate reports")
    reports_sub = reports.add_subparsers(dest="report", required=True)
    reports_acc = reports_sub.add_parser("account", help="Weekly account report")
    reports_comm = reports_sub.add_parser("community", help="Weekly community report")

    args, unknown = parser.parse_known_args()
    passthrough = []
    for item in unknown:
        if item == "--":
            continue
        passthrough.append(item)

    if args.command == "scan":
        return _run_script("scripts/runners/night_scanner.py", args.args + passthrough)
    if args.command == "humanized-scan":
        return _run_script("scripts/runners/humanized_night_scanner.py", args.args + passthrough)
    if args.command == "moderation":
        return _run_script("scripts/moderation/manage_moderation.py", args.args + passthrough)
    if args.command == "schedule":
        return _run_script("scripts/content_scheduling/schedule_posts.py", args.args + passthrough)
    if args.command == "community-manager":
        return _run_script("scripts/runners/community_manager.py", args.args + passthrough)
    if args.command == "reports":
        if args.report == "account":
            return _run_script("scripts/weekly_account_report.py", [])
        if args.report == "community":
            return _run_script("scripts/weekly_community_report.py", [])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
