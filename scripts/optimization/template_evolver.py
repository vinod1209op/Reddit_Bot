#!/usr/bin/env python3
"""
Retire underperforming templates and suggest updates based on history.
"""
import json
from pathlib import Path


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def evolve():
    cfg = _load_json(Path("config/content_optimizer.json"), {})
    schedule = _load_json(Path("scripts/content_scheduling/schedule/post_schedule.json"), [])
    templates_path = Path("scripts/content_scheduling/templates/post_templates.json")
    templates = _load_json(templates_path, {})

    scores = {}
    for p in schedule:
        tid = p.get("template_id")
        if not tid:
            continue
        metrics = p.get("metrics") or {}
        score = (metrics.get("upvotes", 0) * 1.0) + (metrics.get("comments", 0) * 1.5)
        scores.setdefault(tid, []).append(score)

    avg_scores = {k: sum(v) / max(1, len(v)) for k, v in scores.items()}
    retire_threshold = float(cfg.get("retire_threshold", 0.35))

    for ptype, group in templates.items():
        for t in group.get("templates", []):
            tid = t.get("template_id")
            if not tid:
                continue
            score = avg_scores.get(tid, 1.0)
            if score < retire_threshold:
                t["disabled"] = True

    templates_path.write_text(json.dumps(templates, indent=2))
    return {"retired": [k for k, v in avg_scores.items() if v < retire_threshold]}


if __name__ == "__main__":
    print(evolve())
