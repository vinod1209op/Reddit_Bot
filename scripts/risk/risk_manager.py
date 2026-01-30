#!/usr/bin/env python3
"""
Risk management report for scale safety and compliance.
"""
import json
from pathlib import Path
from datetime import datetime


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _load_schedule():
    return _load_json(Path("scripts/content_scheduling/schedule/post_schedule.json"), [])


def _load_status():
    return _load_json(Path("data/account_status.json"), {})

def _load_quality_report():
    return _load_json(Path("logs/moderation_quality_report.json"), {})


def _load_config():
    return _load_json(Path("config/risk_management.json"), {})


def _unique_ratio(items):
    if not items:
        return 1.0
    return len(set(items)) / max(1, len(items))


def generate():
    cfg = _load_config()
    schedule = _load_schedule()
    status = _load_status()
    quality = _load_quality_report()
    posted = [p for p in schedule if p.get("status") in ("posted", "scheduled")]

    # Activity dispersion
    account_counts = {}
    for p in posted:
        acc = p.get("account") or "unknown"
        account_counts[acc] = account_counts.get(acc, 0) + 1
    total = sum(account_counts.values())
    max_share = max([c / total for c in account_counts.values()]) if total else 0

    # Content variation
    titles = [p.get("title", "") for p in posted]
    contents = [p.get("content", "")[:200] for p in posted]
    title_ratio = _unique_ratio(titles)
    content_ratio = _unique_ratio(contents)

    # Behavior randomization (proxy)
    randomization = {
        "random_timing": True,
        "human_typing": True,
    }

    report = {
        "generated_at": datetime.now().isoformat(),
        "activity_dispersion": {
            "account_counts": account_counts,
            "max_share": round(max_share, 3),
            "max_share_limit": cfg.get("activity_dispersion", {}).get("max_account_share", 0.6),
        },
        "content_variation": {
            "unique_title_ratio": round(title_ratio, 3),
            "unique_content_ratio": round(content_ratio, 3),
            "min_unique_title_ratio": cfg.get("content_variation", {}).get("min_unique_title_ratio", 0.7),
            "min_unique_content_ratio": cfg.get("content_variation", {}).get("min_unique_content_ratio", 0.6),
        },
        "behavior_randomization": randomization,
        "backup": cfg.get("backup", {}),
        "compliance_monitoring": cfg.get("compliance_monitoring", {}),
        "moderation_quality": quality,
        "account_cooldowns": status,
    }

    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    Path("logs/risk_management_report.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# Risk Management Report",
        f"Generated: {report['generated_at']}",
        "",
        "## Activity Dispersion",
        f"- Account distribution: {report['activity_dispersion']['account_counts']}",
        f"- Max account share: {report['activity_dispersion']['max_share']}",
        "",
        "## Content Variation",
        f"- Unique title ratio: {report['content_variation']['unique_title_ratio']}",
        f"- Unique content ratio: {report['content_variation']['unique_content_ratio']}",
        "",
        "## Backup Pool",
        f"- Accounts: {report['backup'].get('account_backup_pool', [])}",
        "",
        "## Moderation Quality (latest)",
        f"- Scored items: {quality.get('scored_items', 0)}",
        "",
        "## Account Cooldowns",
        f"- Raw: {list(status.keys()) if status else []}",
    ]
    Path("logs/risk_management_report.md").write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    generate()
