#!/usr/bin/env python3
"""
Generate a long-term sustainability plan report from config.
"""
import json
from datetime import datetime
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


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _load_optional(path: Path) -> Dict:
    try:
        if path.exists():
            content = path.read_text().strip()
            return json.loads(content) if content else {}
    except Exception:
        return {}
    return {}


def build_report(config: Dict) -> Dict[str, str]:
    now = datetime.now().isoformat()
    analytics = _load_optional(Path("logs/analytics_report.json"))
    risk = _load_optional(Path("logs/risk_report.json"))
    compliance = _load_optional(Path("logs/tos_review_status.json"))
    report = [
        "# Long-Term Sustainability Plan",
        f"Generated: {now}",
        "",
        "## Financial Model Exploration",
        "### Community-Supported Model",
    ]
    community = config.get("financial_model", {}).get("community_supported", {})
    for note in community.get("notes", []):
        report.append(f"- {note}")
    report.extend(["", "### Research Funding"])
    funding = config.get("financial_model", {}).get("research_funding", {})
    for key, items in funding.items():
        label = key.replace("_", " ").title()
        report.append(f"- {label}: {', '.join(items)}")

    report.extend(["", "## Governance Evolution"])
    phases = config.get("governance_evolution", {}).get("phases", [])
    for phase in phases:
        report.append(f"- Phase {phase.get('id')}: {phase.get('name')} ({phase.get('status')})")
    report.extend(["", "Handoff triggers:"])
    for trigger in config.get("governance_evolution", {}).get("handoff_triggers", []):
        report.append(f"- {trigger}")

    report.extend(["", "## Exit Strategy Planning"])
    exit_cfg = config.get("exit_strategy", {})
    report.append("### Platform-Agnostic Architecture")
    for key, val in exit_cfg.get("platform_agnostic", {}).items():
        report.append(f"- {key.replace('_', ' ')}: {bool(val)}")
    report.append("")
    report.append("### Community Migration Protocol")
    report.append(f"- Targets: {', '.join(exit_cfg.get('migration_protocol', {}).get('targets', []))}")
    for step in exit_cfg.get("migration_protocol", {}).get("steps", []):
        report.append(f"- {step}")

    report.extend(["", "## Current Indicators (Most Recent)"])
    if analytics:
        report.append("- Analytics report: available")
    else:
        report.append("- Analytics report: not found")
    if risk:
        report.append("- Risk report: available")
    else:
        report.append("- Risk report: not found")
    if compliance:
        report.append("- Compliance status: available")
    else:
        report.append("- Compliance status: not found")

    out_md = "logs/long_term_sustainability.md"
    out_json = "logs/long_term_sustainability.json"
    _write_text(Path(out_md), "\n".join(report))
    Path(out_json).write_text(json.dumps(config, indent=2))
    return {"md": out_md, "json": out_json}


def main() -> int:
    config = _load_json(Path("config/long_term_sustainability.json"), {})
    build_report(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
