#!/usr/bin/env python3
"""
Compliance utilities: ToS review reminders and compliance log writer.
"""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def write_compliance_log(
    config: Dict,
    actor: str,
    action: str,
    context: str,
    notes: str,
    reviewer: str = "",
    decision: str = "",
    evidence: str = "",
    scope: str = "",
) -> Path:
    log_path = Path(config.get("compliance_log", {}).get("log_path", "logs/compliance_log.jsonl"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "reviewer": reviewer,
        "actor": actor,
        "action": action,
        "context": context,
        "decision": decision,
        "evidence": evidence,
        "scope": scope,
        "notes": notes,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return log_path


def check_tos_review(config: Dict) -> Dict:
    tracker = config.get("tos_tracker", {})
    last = tracker.get("last_reviewed")
    freq_days = int(tracker.get("review_frequency_days", 30))
    now = datetime.now()
    due = True
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            due = now >= (last_dt + timedelta(days=freq_days))
        except Exception:
            due = True
    report = {
        "checked_at": now.isoformat(),
        "due_for_review": due,
        "sources": tracker.get("sources", []),
        "last_reviewed": last,
        "review_frequency_days": freq_days,
    }
    _write_json(Path("logs/tos_review_status.json"), report)
    return report


def mark_tos_reviewed(config: Dict) -> None:
    config = dict(config)
    config.setdefault("tos_tracker", {})["last_reviewed"] = datetime.now().isoformat()
    _write_json(Path("config/compliance.json"), config)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compliance tracker")
    parser.add_argument("--config", default="config/compliance.json")
    parser.add_argument("--check-tos", action="store_true")
    parser.add_argument("--mark-tos-reviewed", action="store_true")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--actor", default="automation")
    parser.add_argument("--action", default="review")
    parser.add_argument("--context", default="compliance")
    parser.add_argument("--notes", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--decision", default="")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--scope", default="")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})

    if args.check_tos:
        report = check_tos_review(config)
        print(json.dumps(report, indent=2))

    if args.mark_tos_reviewed:
        mark_tos_reviewed(config)

    if args.log:
        path = write_compliance_log(
            config,
            args.actor,
            args.action,
            args.context,
            args.notes,
            reviewer=args.reviewer,
            decision=args.decision,
            evidence=args.evidence,
            scope=args.scope,
        )
        print(f"Wrote compliance log to {path}")

    if not (args.check_tos or args.mark_tos_reviewed or args.log):
        check_tos_review(config)
        write_compliance_log(
            config,
            "automation",
            "daily_check",
            "compliance",
            "Automated compliance check executed.",
            decision="ok",
            scope="weekly",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
