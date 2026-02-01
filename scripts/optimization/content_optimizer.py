#!/usr/bin/env python3
"""
Lightweight content optimizer using local historical metrics.
No external ML dependencies; uses heuristic scoring.
"""
import json
import hashlib
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


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


class ContentOptimizer:
    def __init__(self, config_path: Path = Path("config/content_optimizer.json")):
        self.config = _load_json(config_path, {})
        self.enabled = bool(self.config.get("enabled", True))

    def _history(self):
        schedule = _load_json(Path("scripts/content_scheduling/schedule/post_schedule.json"), [])
        return [p for p in schedule if p.get("metrics")]

    def _aggregate_stats(self):
        history = self._history()
        by_type = {}
        by_sub = {}
        for p in history:
            m = p.get("metrics") or {}
            upvotes = m.get("upvotes") or 0
            comments = m.get("comments") or 0
            score = (upvotes * 1.0) + (comments * 1.5)
            ptype = p.get("type", "unknown")
            sub = p.get("subreddit", "unknown")
            by_type.setdefault(ptype, []).append(score)
            by_sub.setdefault(sub, []).append(score)
        avg_type = {k: (sum(v) / max(1, len(v))) for k, v in by_type.items()}
        avg_sub = {k: (sum(v) / max(1, len(v))) for k, v in by_sub.items()}
        return {"avg_type": avg_type, "avg_sub": avg_sub}

    def predict_engagement(self, post_data: dict) -> float:
        if not self.enabled:
            return 0.0
        stats = self._aggregate_stats()
        base = 1.0
        base += stats["avg_type"].get(post_data.get("type", "unknown"), 0) * 0.1
        base += stats["avg_sub"].get(post_data.get("subreddit", "unknown"), 0) * 0.1
        length = len(post_data.get("content", ""))
        base += min(0.5, length / 2000.0)
        if "?" in post_data.get("title", ""):
            base += 0.1
        return round(base, 3)

    def predict_risk(self, post_data: dict) -> float:
        text = (post_data.get("title", "") + " " + post_data.get("content", "")).lower()
        hits = sum(1 for k in self.config.get("risk_keywords", []) if k in text)
        return round(min(1.0, hits * 0.2), 2)

    def optimize_title(self, title: str, post_data: dict) -> str:
        variants = [
            title if title.endswith("?") else f"{title}?",
            f"What most people miss about {title}",
            title.replace(":", " —"),
        ]
        best = title
        best_score = -1
        for v in variants:
            score = self.predict_engagement({**post_data, "title": v})
            if score > best_score:
                best = v
                best_score = score
        return best

    def suggest_improvements(self, content: str) -> list:
        suggestions = []
        if len(content) < 200:
            suggestions.append("Add 1–2 paragraphs of context or sources.")
        if "http" not in content and "doi" not in content.lower():
            suggestions.append("Consider adding a source link or DOI.")
        if "\n- " not in content:
            suggestions.append("Add a short bullet list to improve readability.")
        return suggestions

    def template_id(self, post_type: str, title: str, content: str) -> str:
        return f"{post_type}:{_hash(title + '|' + content)}"


if __name__ == "__main__":
    optimizer = ContentOptimizer()
    print("Enabled:", optimizer.enabled)
