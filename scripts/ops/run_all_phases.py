#!/usr/bin/env python3
"""
Interactive runner for major automation phases.
This does NOT perform live Reddit actions unless those scripts are configured to do so.
"""
import argparse
import subprocess
from pathlib import Path
from typing import List, Tuple


def _run(cmd: List[str]) -> None:
    print(f"\n>>> Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def _preflight() -> None:
    try:
        import pydantic  # noqa: F401
    except Exception:
        print("\nMissing dependency: pydantic")
        print("Run: pip install -r requirements.txt\n")

def _python_exec() -> str:
    venv_python = ".venv/bin/python"
    if Path(venv_python).exists():
        return venv_python
    return "python3"

def main() -> int:
    parser = argparse.ArgumentParser(description="Run all automation phases")
    parser.add_argument("--account", default="account4")
    args = parser.parse_args()

    _preflight()
    py = _python_exec()

    full_pipeline = [
        ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/runners/community_manager.py --account {args.account} --dry-run"],
        ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/content_discovery/content_discovery.py"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --replies --count 3\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --events --months 2\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --recognition\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --recruitment\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/analytics/metrics_pipeline.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/analytics/predictive_insights.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/sustainability/sustainable_growth.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/research/research_pipeline.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/research/research_portal_export.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/risk/risk_manager.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/recovery/disaster_recovery.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/compliance/compliance_tracker.py --check-tos --log --notes 'Manual run'\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/integration/ecosystem_export.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/integration/ecosystem_delivery.py\"],
    ]
    full_pipeline_live = [
        ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/runners/community_manager.py --account {args.account}"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/content_discovery/content_discovery.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --replies --count 3\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --events --months 2\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --recognition\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --recruitment\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/analytics/metrics_pipeline.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/analytics/predictive_insights.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/sustainability/sustainable_growth.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/research/research_pipeline.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/research/research_portal_export.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/risk/risk_manager.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/recovery/disaster_recovery.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/compliance/compliance_tracker.py --check-tos --log --notes 'Manual run'\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/integration/ecosystem_export.py\"],
        ["bash", "-lc", f\"PYTHONPATH=src:. {py} scripts/integration/ecosystem_delivery.py\"],
    ]

    menu: List[Tuple[str, List[str]]] = [
        ("Run full pipeline (safe dry-run)", ["__RUN_ALL__"]),
        ("Run full pipeline (live)", ["__RUN_ALL_LIVE__"]),
        ("Community manager (creation → moderation → posting)", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/runners/community_manager.py --account {args.account}"]),
        ("Content discovery", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/content_discovery/content_discovery.py"]),
        ("Engagement replies", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --replies --count 3"]),
        ("Engagement events", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --events --months 2"]),
        ("Recognition report", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --recognition"]),
        ("Research recruitment posts", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/engagement/engagement_program.py --recruitment"]),
        ("Analytics pipeline", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/analytics/metrics_pipeline.py"]),
        ("Predictive insights", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/analytics/predictive_insights.py"]),
        ("Sustainable growth plan", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/sustainability/sustainable_growth.py"]),
        ("Research reports", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/research/research_pipeline.py"]),
        ("Research portal export", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/research/research_portal_export.py"]),
        ("Risk management", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/risk/risk_manager.py"]),
        ("Disaster recovery + exports", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/recovery/disaster_recovery.py"]),
        ("Compliance check", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/compliance/compliance_tracker.py --check-tos --log --notes 'Manual run'"]),
        ("Ecosystem export + delivery", ["bash", "-lc", f"PYTHONPATH=src:. {py} scripts/integration/ecosystem_export.py && PYTHONPATH=src:. {py} scripts/integration/ecosystem_delivery.py"]),
    ]

    while True:
        print("\nChoose a phase to run:")
        for i, (label, _) in enumerate(menu, start=1):
            print(f"{i}) {label}")
        print(f"{len(menu) + 1}) Exit")
        choice = input(f"Select option (1-{len(menu) + 1}): ").strip()
        if not choice.isdigit():
            print("Invalid selection.")
            continue
        idx = int(choice)
        if idx == len(menu) + 1:
            break
        if 1 <= idx <= len(menu):
            cmd = menu[idx - 1][1]
            if cmd == ["__RUN_ALL__"]:
                for step in full_pipeline:
                    _run(step)
            elif cmd == ["__RUN_ALL_LIVE__"]:
                for step in full_pipeline_live:
                    _run(step)
            else:
                _run(cmd)
        else:
            print("Invalid selection.")

    print("\nExited.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
