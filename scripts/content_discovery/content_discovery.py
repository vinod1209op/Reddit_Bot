"""
Local content discovery (no external fetch).
Reads a queue file and converts items into scheduled posts.
"""
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DiscoveryItem:
    title: str
    url: str
    summary: str
    source: str
    category: str


class ContentDiscovery:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()
        self.queue_path = Path(self.config.get("queue_path", "data/content_discovery_queue.json"))

    def _load_config(self) -> Dict:
        if not self.config_path.exists():
            return {"enabled": True, "queue_path": "data/content_discovery_queue.json"}
        try:
            return json.loads(self.config_path.read_text())
        except Exception:
            return {"enabled": True, "queue_path": "data/content_discovery_queue.json"}

    def load_queue(self) -> List[DiscoveryItem]:
        if not self.queue_path.exists():
            return []
        try:
            raw = json.loads(self.queue_path.read_text())
        except Exception:
            return []
        items = []
        for entry in raw:
            title = entry.get("title") or ""
            url = entry.get("url") or ""
            summary = entry.get("summary") or entry.get("abstract") or ""
            source = entry.get("source") or "unknown"
            category = entry.get("category") or "news"
            if title and summary:
                items.append(DiscoveryItem(title=title, url=url, summary=summary, source=source, category=category))
        return items

    def _discussion_questions(self, text: str) -> List[str]:
        if not text:
            return []
        prompts = [
            "What stood out to you most in these findings?",
            "How might this affect clinical practice or guidelines?",
            "What would you want to see studied next?",
        ]
        random.shuffle(prompts)
        return prompts[:3]

    def _build_post(self, item: DiscoveryItem) -> Dict:
        questions = self._discussion_questions(item.summary)
        questions_block = "\n".join([f"- {q}" for q in questions]) if questions else ""
        content = (
            f"{item.summary}\n\n"
            f"**Source:** {item.source}\n"
        )
        if item.url:
            content += f"**Link:** {item.url}\n"
        if questions_block:
            content += f"\n**Discussion prompts:**\n{questions_block}"
        return {
            "type": "news" if item.category == "news" else "resource",
            "title": item.title,
            "content": content.strip(),
            "metadata": {
                "source": item.source,
                "url": item.url,
                "category": item.category,
            },
        }

    def generate_posts_from_queue(self, scheduler, max_items: Optional[int] = None) -> int:
        if not self.config.get("enabled", True):
            return 0
        items = self.load_queue()
        if not items:
            return 0
        limit = max_items or int(self.config.get("max_items_per_run", 5))
        created = 0
        for item in items[:limit]:
            base = self._build_post(item)
            post = scheduler.generate_post_from_template(base["type"])
            ab_variants = scheduler._choose_ab_variants()
            title = base["title"]
            content = base["content"]
            if ab_variants.get("title_style"):
                title = scheduler._apply_title_variant(title, ab_variants["title_style"])
            if ab_variants.get("content_length"):
                content = scheduler._apply_length_variant(content, ab_variants["content_length"])
            cta_url = scheduler.config.get("cta_url")
            if ab_variants.get("media_inclusion"):
                content = scheduler._apply_media_variant(content, ab_variants["media_inclusion"], cta_url)
            cta_text = scheduler.config.get("cta_text", "Take the MCRDSE Movement Quiz")
            if cta_url:
                content += f"\n\nIf this topic resonates, {cta_text} at {cta_url}."
            post["title"] = title
            post["content"] = content
            post["ab_test"] = ab_variants
            post.setdefault("metadata", {}).update(base.get("metadata", {}))
            if ab_variants:
                scheduler._log_ab_event(post, "created")
            scheduler.schedule_post(post)
            created += 1
        return created
