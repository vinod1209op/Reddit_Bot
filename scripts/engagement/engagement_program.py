#!/usr/bin/env python3
"""
Engagement program automation helpers (comments, events, recognition).
"""
import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from scripts.content_scheduling.schedule_posts import MCRDSEPostScheduler


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _next_nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    first = datetime(year, month, 1)
    days_ahead = (weekday - first.weekday()) % 7
    target = first + timedelta(days=days_ahead + 7 * (n - 1))
    return target


def _weekday_index(name: str) -> int:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names.index(name)


class EngagementProgram:
    def __init__(self, config_path: Path = Path("config/engagement_program.json")):
        self.config = _load_json(config_path, {})
        self.reply_templates = _load_json(Path("config/engagement_reply_templates.json"), {})

    def generate_comment_replies(self, count: int = 3, category: Optional[str] = None) -> List[str]:
        strategy = self.config.get("comment_strategy", {}).get("types", {})
        categories = list(strategy.keys()) or list(self.reply_templates.keys())
        if not categories:
            return []
        bot_prefix = self.config.get("bot_prefix", "")
        replies = []
        for _ in range(count):
            if category:
                chosen = category
            else:
                weights = [strategy.get(c, {}).get("weight", 1.0) for c in categories]
                chosen = random.choices(categories, weights=weights, k=1)[0]
            pool = self.reply_templates.get(chosen) or self.reply_templates.get("default", [])
            if pool:
                reply = random.choice(pool)
                if bot_prefix and not reply.startswith(bot_prefix):
                    reply = f"{bot_prefix}{reply}"
                replies.append(reply)
        return replies

    def schedule_monthly_events(self, scheduler: MCRDSEPostScheduler, subreddits: List[str], months_ahead: int = 2) -> int:
        events = self.config.get("monthly_events", {})
        if not events:
            return 0
        count = 0
        today = datetime.now()
        for m in range(months_ahead + 1):
            target_month = (today.month - 1 + m) % 12 + 1
            target_year = today.year + ((today.month - 1 + m) // 12)
            for key, evt in events.items():
                weekday = _weekday_index(evt.get("weekday", "Wednesday"))
                week_of_month = int(evt.get("week_of_month", 1))
                date = _next_nth_weekday(target_year, target_month, weekday, week_of_month)
                for subreddit in subreddits:
                    post = scheduler.generate_post_from_template("discussion", subreddit=subreddit)
                    post["title"] = evt["title"].format(
                        paper="Selected Paper",
                        guest="Invited Researcher",
                        month=date.strftime("%B"),
                    )
                    post["content"] = evt["content"].format(
                        paper="Selected Paper",
                        guest="Invited Researcher",
                        month=date.strftime("%B"),
                    )
                    post["type"] = "event"
                    post["scheduled_for"] = date.replace(hour=12, minute=0).isoformat()
                    scheduler.schedule_post(post)
                    count += 1
        return count

    def schedule_research_recruitment(
        self,
        scheduler: MCRDSEPostScheduler,
        subreddits: List[str],
        templates_path: Path = Path("config/research_recruitment_templates.json"),
    ) -> int:
        templates = _load_json(templates_path, {})
        variants = templates.get("templates") or []
        template = random.choice(variants) if variants else templates.get("default") or {}
        if not template:
            return 0
        count = 0
        for subreddit in subreddits:
            post = scheduler.generate_post_from_template("discussion", subreddit=subreddit)
            post["title"] = template.get("title", post["title"])
            post["content"] = template.get("content", post["content"])
            post["type"] = "research_recruitment"
            scheduler.schedule_post(post)
            count += 1
        return count

    def generate_recognition_report(self, schedule_path: Path, output_dir: Path = Path("logs")) -> Dict:
        schedule = _load_json(schedule_path, [])
        featured = []
        for post in schedule:
            metrics = post.get("metrics") or {}
            comments = metrics.get("comments") or 0
            upvotes = metrics.get("upvotes") or 0
            if comments or upvotes:
                featured.append(
                    {
                        "id": post.get("id"),
                        "subreddit": post.get("subreddit"),
                        "title": post.get("title"),
                        "comments": comments,
                        "upvotes": upvotes,
                    }
                )
        featured = sorted(featured, key=lambda r: (r["comments"], r["upvotes"]), reverse=True)[:10]
        report = {
            "generated_at": datetime.now().isoformat(),
            "featured_posts": featured,
            "recognition": self.config.get("recognition", {}),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "recognition_report.json").write_text(json.dumps(report, indent=2))
        lines = [
            "# Recognition Report",
            f"Generated: {report['generated_at']}",
            "",
            "## Featured Posts",
        ]
        for item in featured:
            lines.append(f"- r/{item['subreddit']} | {item['title']} | comments: {item['comments']} | upvotes: {item['upvotes']}")
        (output_dir / "recognition_report.md").write_text("\n".join(lines))
        return report


def main():
    parser = argparse.ArgumentParser(description="Engagement program utilities")
    parser.add_argument("--replies", action="store_true", help="Generate comment replies")
    parser.add_argument("--events", action="store_true", help="Schedule monthly events")
    parser.add_argument("--recognition", action="store_true", help="Generate recognition report")
    parser.add_argument("--recruitment", action="store_true", help="Schedule research recruitment posts")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--months", type=int, default=2)
    parser.add_argument("--account", default="account4")
    parser.add_argument("--subreddits", nargs="*", default=["MindWellBeing", "ClinicalMicrodosingHu", "Mental_Health_Hub"])
    parser.add_argument("--queue", action="store_true", help="Write generated replies to a local queue file")
    parser.add_argument("--queue-path", default="data/engagement_reply_queue.json")
    args = parser.parse_args()

    program = EngagementProgram()
    if args.replies:
        replies = program.generate_comment_replies(count=args.count)
        if args.queue:
            queue_path = Path(args.queue_path)
            existing = _load_json(queue_path, [])
            for r in replies:
                existing.append(
                    {
                        "generated_at": datetime.now().isoformat(),
                        "reply": r,
                        "source": "template",
                        "status": "draft",
                    }
                )
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue_path.write_text(json.dumps(existing, indent=2))
            print(f"Wrote {len(replies)} replies to {queue_path}")
        else:
            for r in replies:
                print(f"- {r}")
    if args.events:
        scheduler = MCRDSEPostScheduler(account_name=args.account, headless=True, dry_run=True)
        count = program.schedule_monthly_events(scheduler, args.subreddits, months_ahead=args.months)
        print(f"Scheduled {count} event posts.")
    if args.recruitment:
        scheduler = MCRDSEPostScheduler(account_name=args.account, headless=True, dry_run=True)
        count = program.schedule_research_recruitment(scheduler, args.subreddits)
        print(f"Scheduled {count} recruitment posts.")
    if args.recognition:
        report = program.generate_recognition_report(
            Path("scripts/content_scheduling/schedule/post_schedule.json")
        )
        print(f"Recognition report generated with {len(report.get('featured_posts', []))} items.")


if __name__ == "__main__":
    raise SystemExit(main())
