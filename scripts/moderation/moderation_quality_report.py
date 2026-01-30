#!/usr/bin/env python3
"""
Generate a moderation quality report from recent moderation history files.
"""
import json
from pathlib import Path
from datetime import datetime


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def generate():
    history_dir = Path("scripts/moderation/history")
    files = sorted(history_dir.glob("moderation_daily_*.json"), reverse=True)
    if not files:
        return {}
    data = _load_json(files[0], {})
    items = data.get("processed_items") or []

    scored = [i for i in items if (i.get("scores") or {}).get("overall") is not None]
    scored_sorted = sorted(scored, key=lambda x: x.get("scores", {}).get("overall", 0), reverse=True)
    top = scored_sorted[:10]
    low = scored_sorted[-10:] if scored_sorted else []

    report = {
        "generated_at": datetime.now().isoformat(),
        "source_file": str(files[0]),
        "total_items": len(items),
        "scored_items": len(scored),
        "top_priority": top,
        "low_priority": low,
    }

    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    Path("logs/moderation_quality_report.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# Moderation Quality Report",
        f"Generated: {report['generated_at']}",
        f"Source: {report['source_file']}",
        f"Total items: {report['total_items']}",
        f"Scored items: {report['scored_items']}",
        "",
        "## Top Priority (by score)",
    ]
    for item in top:
        score = item.get("scores", {}).get("overall")
        lines.append(f"- {item.get('subreddit')} | {item.get('title')} | score: {score}")
    lines.append("")
    lines.append("## Low Priority (by score)")
    for item in low:
        score = item.get("scores", {}).get("overall")
        lines.append(f"- {item.get('subreddit')} | {item.get('title')} | score: {score}")
    Path("logs/moderation_quality_report.md").write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    generate()
