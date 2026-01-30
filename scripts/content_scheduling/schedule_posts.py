#!/usr/bin/env python3
"""
MCRDSE Post Scheduler
Schedule and automate posts across MCRDSE subreddits
"""

import json
import time
import logging
import random
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
try:
    import schedule  # optional; used only for future cron helpers
except Exception:  # pragma: no cover
    schedule = None
import threading
from microdose_study_bot.reddit_selenium.automation_base import RedditAutomationBase
from microdose_study_bot.core.logging import UnifiedLogger
from microdose_study_bot.core.storage.state_cleanup import cleanup_state
from microdose_study_bot.core.storage.idempotency_store import (
    IDEMPOTENCY_DEFAULT_PATH,
    build_post_key,
    can_attempt,
    mark_attempt,
    mark_failure,
    mark_success,
)

logger = UnifiedLogger("PostScheduler").get_logger()

class MCRDSEPostScheduler(RedditAutomationBase):
    """Schedule and post content to MCRDSE subreddits using Selenium"""
    
    def __init__(self, account_name="account1", headless=True, dry_run=False, session=None, owns_session=True):
        """
        Initialize post scheduler
        
        Args:
            account_name: Which Reddit account to use
            headless: Run browser in background
        """
        os.environ["SELENIUM_HEADLESS"] = "1" if headless else "0"
        self.account_name = account_name
        self.headless = headless
        super().__init__(account_name=account_name, dry_run=dry_run, session=session, owns_session=owns_session)
        self.config = self.load_config()
        self.schedule_file = Path("scripts/content_scheduling/schedule/post_schedule.json")
        self.legacy_schedule_file = Path("data/post_schedule.json")
        self.post_templates = self.load_templates()
        self.is_running = False
        self.scheduler_thread = None
        self.ab_log_path = Path("logs/ab_tests.jsonl")
        self.optimizer = self._load_optimizer()
        
    def load_config(self) -> Dict:
        """Load scheduler configuration"""
        config_path = Path("config/post_scheduling.json")
        
        file_config = {}
        if config_path.exists():
            try:
                file_config = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Config file corrupted, using defaults")
        
        # Default configuration
        default_config = {
            "posting_settings": {
                "max_posts_per_day": 5,
                "max_posts_per_week": 15,
                "min_time_between_posts_minutes": 60,
                "time_windows": ["09:00-12:00", "18:00-21:00"],
                "optimal_posting_times": [
                    {"time": "09:00", "weight": 10},
                    {"time": "12:00", "weight": 8},
                    {"time": "15:00", "weight": 6},
                    {"time": "18:00", "weight": 7},
                    {"time": "21:00", "weight": 9}
                ],
                "avoid_posting_times": [
                    "02:00-05:00",  # Late night
                    "13:00-14:00"   # Lunch time
                ]
            },
            "content_strategy": {
                "daily_themes": {
                    "Monday": "Research Review",
                    "Tuesday": "Toolkit & Resources",
                    "Wednesday": "Community Support",
                    "Thursday": "Science & Studies",
                    "Friday": "Future & Innovation",
                    "Saturday": "Personal Experiences",
                    "Sunday": "Weekly Reflection"
                },
                "theme_post_types": {
                    "Research Review": ["resource", "news"],
                    "Toolkit & Resources": ["resource"],
                    "Community Support": ["discussion", "question"],
                    "Science & Studies": ["news", "discussion"],
                    "Future & Innovation": ["discussion", "question"],
                    "Personal Experiences": ["experience", "discussion"],
                    "Weekly Reflection": ["discussion", "question"]
                },
                "content_mix": {
                    "discussion": 30,
                    "question": 25,
                    "resource": 20,
                    "experience": 15,
                    "news": 10
                },
                "min_post_length": 100,
                "max_post_length": 5000
            },
            "subreddit_distribution": {
                "primary_focus": ["MCRDSE_Research", "MicrodosingScience"],
                "secondary_focus": ["PsychedelicTherapy", "PlantMedicineCommunity"],
                "crosspost_to": ["microdosing", "psychonaut", "nootropics"],
                "crosspost_delay_minutes": 30
            },
            "safety_settings": {
                "randomize_post_times": True,
                "jitter_minutes": 15,
                "use_human_typing": True,
                "add_typos_chance": 0.05,
                "random_delays_between_actions": True,
                "verify_post_success": True,
                "retry_failed_posts": True,
                "max_retries": 3
            },
            "automation_settings": {
                "check_schedule_interval_minutes": 5,
                "cleanup_old_schedule_days": 30,
                "backup_schedule_days": 7,
                "log_all_actions": True,
                "send_alerts_on_failure": False
            },
            "ab_testing": {
                "enabled": False,
                "experiments": {
                    "title_style": ["question", "statement", "curiosity_gap"],
                    "post_timing": ["morning", "afternoon", "evening"],
                    "content_length": ["short", "medium", "long"],
                    "media_inclusion": ["text_only", "link"]
                }
            }
        }

        # Start with defaults and merge in file config (preserve CTA even if posting_settings missing)
        config = default_config.copy()
        if isinstance(file_config, dict):
            config.update({k: v for k, v in file_config.items() if k not in ("posting_settings", "content_strategy", "subreddit_distribution", "safety_settings", "automation_settings")})
            for section in ("posting_settings", "content_strategy", "subreddit_distribution", "safety_settings", "automation_settings"):
                if isinstance(file_config.get(section), dict):
                    config[section] = {**config.get(section, {}), **file_config.get(section, {})}
        profiles = file_config.get("profiles", {}) if isinstance(file_config, dict) else {}
        profile_name = (self.activity_schedule or {}).get("post_scheduling", {}).get("profile") or "low_frequency"
        profile_config = profiles.get(profile_name, {}) if profiles else {}

        if profile_config:
            config["posting_settings"]["max_posts_per_day"] = profile_config.get(
                "max_posts_per_day", config["posting_settings"]["max_posts_per_day"]
            )
            if "max_posts_per_week" in profile_config:
                config["posting_settings"]["max_posts_per_week"] = profile_config["max_posts_per_week"]
            if "time_windows" in profile_config:
                config["posting_settings"]["time_windows"] = profile_config["time_windows"]
            if "content_mix" in profile_config:
                config["content_strategy"]["content_mix"] = profile_config["content_mix"]

        # Merge in feature-level overrides from activity_schedule.json
        post_feature = (self.activity_schedule or {}).get("post_scheduling", {})
        if isinstance(post_feature, dict):
            if "max_posts_per_day" in post_feature:
                config["posting_settings"]["max_posts_per_day"] = post_feature["max_posts_per_day"]
            if "max_posts_per_week" in post_feature:
                config["posting_settings"]["max_posts_per_week"] = post_feature["max_posts_per_week"]
            window = post_feature.get("schedule_window_local")
            if isinstance(window, dict) and window.get("start") and window.get("end"):
                config["posting_settings"]["time_windows"] = [f"{window['start']}-{window['end']}"]

        # Save default config if missing
        if not config_path.exists():
            config_path.parent.mkdir(exist_ok=True, parents=True)
            config_path.write_text(json.dumps(file_config or {"profiles": {"low_frequency": {
                "max_posts_per_day": 2,
                "content_mix": config["content_strategy"]["content_mix"],
                "time_windows": config["posting_settings"]["time_windows"]
            }}}, indent=2))
            logger.info(f"Created default config at {config_path}")

        return config

    def _load_optimizer(self):
        try:
            from scripts.optimization.content_optimizer import ContentOptimizer
            return ContentOptimizer()
        except Exception:
            return None
    
    def load_templates(self) -> Dict:
        """Load post templates"""
        templates_path = Path("scripts/content_scheduling/templates/post_templates.json")
        
        if templates_path.exists():
            try:
                return json.loads(templates_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Template file corrupted, using defaults")
        
        # Default templates
        default_templates = {
            "discussion": {
                "templates": [
                    {
                        "title": "What are your thoughts on {topic}?",
                        "content": "I've been thinking about {topic} recently and wanted to get the community's perspective.\n\n**Some questions to consider:**\n- What has your experience been with {topic}?\n- What research have you seen on this topic?\n- How do you approach {topic} in practice?\n\nLet's have a thoughtful discussion!",
                        "variables": {
                            "topic": [
                                "microdosing protocols",
                                "psychedelic integration",
                                "harm reduction practices",
                                "neuroplasticity research",
                                "therapeutic applications"
                            ]
                        }
                    },
                    {
                        "title": "Discussion: The future of {field}",
                        "content": "Where do you see {field} heading in the next 5-10 years?\n\n**Discussion points:**\n1. Current trends and developments\n2. Potential breakthroughs on the horizon\n3. Challenges that need addressing\n4. How we can contribute as a community\n\nShare your insights and predictions!",
                        "variables": {
                            "field": [
                                "psychedelic therapy",
                                "microdosing research",
                                "consciousness studies",
                                "mental health treatment"
                            ]
                        }
                    }
                ]
            },
            "question": {
                "templates": [
                    {
                        "title": "Question about {topic} for experienced practitioners",
                        "content": "I'm curious about {topic} and would appreciate insights from those with experience.\n\n**My specific questions:**\n1. What are the key considerations for {topic}?\n2. What resources would you recommend for learning more?\n3. What common misconceptions should I be aware of?\n\nThanks in advance for your wisdom!",
                        "variables": {
                            "topic": [
                                "starting a microdosing protocol",
                                "psychedelic integration practices",
                                "combining meditation with microdosing",
                                "tracking neuroplasticity changes"
                            ]
                        }
                    }
                ]
            },
            "resource": {
                "templates": [
                    {
                        "title": "Resource Collection: {topic}",
                        "content": "I've compiled some helpful resources about {topic} that might benefit the community.\n\n**Resources included:**\n- Research papers and studies\n- Educational articles\n- Community guidelines\n- Safety information\n\nFeel free to add your own recommendations in the comments!",
                        "variables": {
                            "topic": [
                                "microdosing safety",
                                "psychedelic research methods",
                                "neuroplasticity exercises",
                                "integration techniques"
                            ]
                        }
                    }
                ]
            },
            "experience": {
                "templates": [
                    {
                        "title": "My experience with {topic} - What I've learned",
                        "content": "I wanted to share my personal journey with {topic} in case it helps others.\n\n**Background:** {background}\n\n**Key insights:**\n1. {insight1}\n2. {insight2}\n3. {insight3}\n\n**Advice for others:**\n- {advice1}\n- {advice2}\n\n*Remember: This is my personal experience. Yours may differ.*",
                        "variables": {
                            "topic": [
                                "microdosing for creativity",
                                "psychedelic therapy",
                                "mindfulness practices",
                                "personal growth work"
                            ],
                            "background": [
                                "Seeking alternatives for mental wellness",
                                "Exploring consciousness expansion",
                                "Looking for sustainable self-improvement"
                            ],
                            "insight1": [
                                "Patience is more important than intensity",
                                "Set and setting matter immensely",
                                "Integration is where real change happens"
                            ],
                            "insight2": [
                                "Small consistent steps yield better results",
                                "Community support makes a huge difference",
                                "Documenting experiences helps with insights"
                            ],
                            "insight3": [
                                "Balance is key to sustainable practice",
                                "Individual responses vary significantly",
                                "Education reduces risk and increases benefit"
                            ],
                            "advice1": [
                                "Start low and go slow",
                                "Keep a detailed journal",
                                "Find a supportive community"
                            ],
                            "advice2": [
                                "Consult professionals when in doubt",
                                "Listen to your body and mind",
                                "Focus on integration over experience"
                            ]
                        }
                    }
                ]
            },
            "news": {
                "templates": [
                    {
                        "title": "News Update: {development} in psychedelic research",
                        "content": "There's been an interesting development in psychedelic research that I wanted to share.\n\n**What's happening:**\n{summary}\n\n**Why it matters:**\n{significance}\n\n**Sources & further reading:**\n- [Link to study/article]\n- [Related research]\n\nWhat are your thoughts on this development?",
                        "variables": {
                            "development": [
                                "New clinical trial results",
                                "Policy changes affecting research",
                                "Breakthrough in understanding mechanisms",
                                "Innovative therapeutic approaches"
                            ],
                            "summary": [
                                "A recent study published in a major journal shows promising results",
                                "Regulatory changes are opening new avenues for research",
                                "Scientists have discovered new insights into how psychedelics work",
                                "New therapeutic protocols are showing significant benefits"
                            ],
                            "significance": [
                                "This could lead to new treatment options",
                                "It represents progress in destigmatization",
                                "It deepens our scientific understanding",
                                "It may influence future research directions"
                            ]
                        }
                    }
                ]
            }
        }
        
        # Save default templates
        templates_path.parent.mkdir(exist_ok=True, parents=True)
        templates_path.write_text(json.dumps(default_templates, indent=2))
        logger.info(f"Created default templates at {templates_path}")
        
        return default_templates

    def load_network_config(self) -> Dict:
        path = Path("config/subreddit_network.json")
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _log_ab_event(self, post: Dict, event: str, extra: Optional[Dict] = None) -> None:
        payload = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "post_id": post.get("id"),
            "subreddit": post.get("subreddit"),
            "title": post.get("title"),
            "type": post.get("type"),
            "ab_test": post.get("ab_test", {}),
            "crosspost_from": post.get("crosspost_from"),
            "post_url": post.get("post_url"),
        }
        if extra:
            payload.update(extra)
        try:
            self.ab_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ab_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _pick_theme_for_date(self, dt: datetime) -> Optional[str]:
        themes = self.config.get("content_strategy", {}).get("daily_themes", {})
        if not themes:
            return None
        return themes.get(dt.strftime("%A"))

    def _select_post_type_for_theme(self, theme: Optional[str]) -> Optional[str]:
        mapping = self.config.get("content_strategy", {}).get("theme_post_types", {})
        if not theme or not isinstance(mapping, dict):
            return None
        choices = mapping.get(theme, [])
        if not choices:
            return None
        return random.choice(choices)

    def _choose_ab_variants(self) -> Dict[str, str]:
        ab = self.config.get("ab_testing", {})
        if not ab.get("enabled"):
            return {}
        variants = {}
        experiments = ab.get("experiments") or {}
        weights_cfg = ab.get("weights") or {}
        for key, opts in experiments.items():
            if isinstance(opts, list) and opts:
                weights = None
                if isinstance(weights_cfg.get(key), dict):
                    weights = [weights_cfg[key].get(opt, 1.0) for opt in opts]
                if weights:
                    variants[key] = random.choices(opts, weights=weights, k=1)[0]
                else:
                    variants[key] = random.choice(opts)
        return variants

    def _apply_title_variant(self, title: str, variant: str) -> str:
        if variant == "question":
            if title.endswith("?"):
                return title
            return f"{title}?"
        if variant == "curiosity_gap":
            return f"What most people miss about {title}"
        if variant == "statement":
            return title
        return title

    def _apply_seo_title_keywords(self, title: str) -> str:
        keywords = self.config.get("seo_title_keywords", [])
        if not keywords:
            return title
        if random.random() > 0.5:
            return title
        keyword = random.choice(keywords)
        if keyword.lower() in title.lower():
            return title
        return f"{title} — {keyword}"

    def _apply_length_variant(self, content: str, variant: str) -> str:
        if variant == "short":
            parts = [p for p in content.split("\n\n") if p.strip()]
            return "\n\n".join(parts[:2]) if parts else content
        if variant == "long":
            extra = (
                "\n\nDiscussion prompts:\n"
                "- What stood out to you most?\n"
                "- What would you want to see studied next?\n"
                "- How does this connect to your experience or research focus?"
            )
            return content + extra
        return content

    def _apply_media_variant(self, content: str, variant: str, cta_url: Optional[str]) -> str:
        if variant in ("link", "links") and cta_url and cta_url not in content:
            return content + f"\n\nRelated link: {cta_url}"
        return content

    def _apply_timing_variant(self, scheduled: datetime, variant: str) -> datetime:
        windows = {
            "morning": ("09:00", "11:00"),
            "afternoon": ("12:00", "15:00"),
            "evening": ("18:00", "21:00"),
        }
        if variant not in windows:
            return scheduled
        start_str, end_str = windows[variant]
        start_hour, start_minute = map(int, start_str.split(":"))
        end_hour, end_minute = map(int, end_str.split(":"))
        base = scheduled
        start_dt = base.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end_dt = base.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        total_minutes = max(1, int((end_dt - start_dt).total_seconds() / 60))
        offset = random.randint(0, total_minutes)
        return start_dt + timedelta(minutes=offset)

    def _related_subreddits(self, subreddit: str) -> List[str]:
        network = self.load_network_config()
        cross = network.get("cross_promotion", {})
        related_map = cross.get("related_map", {})
        related = list(related_map.get(subreddit, []))
        if related:
            return related
        categories = network.get("categories", {})
        for group in categories.values():
            if isinstance(group, list) and subreddit in group:
                return [s for s in group if s != subreddit]
        return []

    def _generate_crosspost_posts(self, post: Dict, max_crossposts: Optional[int] = None) -> List[Dict]:
        if post.get("type") == "digest" or post.get("crosspost_from"):
            return []
        network = self.load_network_config()
        cross = network.get("cross_promotion", {})
        max_cp = int(max_crossposts or cross.get("max_crossposts", 0) or 0)
        if max_cp <= 0:
            return []
        related = self._related_subreddits(post.get("subreddit", ""))
        if not related:
            return []
        random.shuffle(related)
        selected = related[:max_cp]
        delay_minutes = int(
            self.config.get("subreddit_distribution", {}).get("crosspost_delay_minutes", 30)
        )
        base_time = datetime.fromisoformat(post["scheduled_for"])
        crossposts = []
        for i, subreddit in enumerate(selected):
            cp = dict(post)
            cp["id"] = f"cross_{int(time.time())}_{random.randint(1000, 9999)}"
            cp["subreddit"] = subreddit
            cp["crosspost_from"] = post.get("subreddit")
            cp["title"] = post["title"]
            cp["content"] = (
                f"Cross-posted from r/{post.get('subreddit')} (original context below).\n\n"
                f"{post['content']}"
            )
            cp["scheduled_for"] = (base_time + timedelta(minutes=delay_minutes * (i + 1))).isoformat()
            cp["status"] = "scheduled"
            cp["created_at"] = datetime.now().isoformat()
            crossposts.append(cp)
        return crossposts
    
    def load_schedule(self) -> List[Dict]:
        """Load scheduled posts from file"""
        schedule_data = []
        schedule_exists = self.schedule_file.exists()
        if schedule_exists:
            try:
                content = self.schedule_file.read_text().strip()
                if not content:
                    return []
                schedule_data = json.loads(content)
            except json.JSONDecodeError:
                logger.error("Schedule file corrupted, attempting recovery")
                # Try legacy schedule even if primary exists
                try:
                    if self.legacy_schedule_file.exists():
                        with open(self.legacy_schedule_file, 'r') as f:
                            schedule_data = json.load(f)
                            return schedule_data or []
                except json.JSONDecodeError:
                    logger.error("Legacy schedule file also corrupted")
                # Try most recent backup
                backup_dir = Path("scripts/content_scheduling/schedule/backups")
                if backup_dir.exists():
                    backups = sorted(backup_dir.glob("schedule_backup_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                    for path in backups[:5]:
                        try:
                            schedule_data = json.loads(path.read_text())
                            logger.warning("Recovered schedule from backup: %s", path)
                            return schedule_data or []
                        except Exception:
                            continue
                logger.error("Schedule recovery failed; starting with empty schedule")

        # Fall back to legacy schedule only if primary schedule file is missing
        if not schedule_exists and self.legacy_schedule_file.exists():
            try:
                with open(self.legacy_schedule_file, 'r') as f:
                    schedule_data = json.load(f)
            except json.JSONDecodeError:
                logger.error("Legacy schedule file corrupted, starting with empty schedule")

        return schedule_data or []
    
    def save_schedule(self, schedule_data: List[Dict]):
        """Save schedule to file"""
        self.schedule_file.parent.mkdir(exist_ok=True, parents=True)
        
        # Backup old schedule
        if self.schedule_file.exists():
            backup_dir = Path("scripts/content_scheduling/schedule/backups")
            backup_dir.mkdir(exist_ok=True, parents=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"schedule_backup_{timestamp}.json"
            with open(self.schedule_file, 'r') as src, open(backup_file, 'w') as dst:
                dst.write(src.read())
        
        # Save new schedule
        with open(self.schedule_file, 'w') as f:
            json.dump(schedule_data, f, indent=2, default=str)

        # Save legacy copy
        self.legacy_schedule_file.parent.mkdir(exist_ok=True, parents=True)
        with open(self.legacy_schedule_file, 'w') as f:
            json.dump(schedule_data, f, indent=2, default=str)
        
        logger.info(f"Schedule saved with {len(schedule_data)} posts")
    
    def generate_post_from_template(self, post_type: str, subreddit: str = None) -> Dict:
        """Generate a post from templates"""
        if post_type not in self.post_templates:
            post_type = random.choice(list(self.post_templates.keys()))
        
        template_group = self.post_templates[post_type]
        template = random.choice(template_group["templates"])
        template_id = template.get("template_id")
        template_ai_assisted = template.get("ai_assisted")
        
        # Fill variables
        title = template["title"]
        content = template["content"]
        
        for var_name, options in template.get("variables", {}).items():
            replacement = random.choice(options)
            title = title.replace(f"{{{var_name}}}", replacement)
            content = content.replace(f"{{{var_name}}}", replacement)
        
        # Apply A/B variants (before CTA)
        ab_variants = self._choose_ab_variants()
        if ab_variants.get("title_style"):
            title = self._apply_title_variant(title, ab_variants["title_style"])
        title = self._apply_seo_title_keywords(title)
        if ab_variants.get("content_length"):
            content = self._apply_length_variant(content, ab_variants["content_length"])
        
        # Optional ML/heuristic optimization
        if self.optimizer and getattr(self.optimizer, "enabled", False):
            title = self.optimizer.optimize_title(title, {"type": post_type, "content": content, "subreddit": subreddit or ""})
            suggestions = self.optimizer.suggest_improvements(content)
            if suggestions:
                content += "\n\nSuggestions:\n" + "\n".join([f"- {s}" for s in suggestions[:2]])

        # Select subreddit if not specified
        if not subreddit:
            subreddit = self.select_subreddit_for_post(post_type)
        
        # Generate scheduled time
        scheduled_time = self.generate_scheduled_time()
        if ab_variants.get("post_timing"):
            scheduled_time = self._apply_timing_variant(scheduled_time, ab_variants["post_timing"])

        # Apply media inclusion variants (CTA can act as link)
        cta_url = self.config.get("cta_url")
        if ab_variants.get("media_inclusion"):
            content = self._apply_media_variant(content, ab_variants["media_inclusion"], cta_url)

        # Add CTA if configured (inline URL in sentence)
        cta_text = self.config.get("cta_text", "Take the MCRDSE Movement Quiz")
        if cta_url:
            content += f"\n\nIf this topic resonates, {cta_text} at {cta_url}."
        else:
            if random.random() < 0.3:  # 30% chance
                content += "\n\nFor research-based resources, check out the MCRDSE research portal."
        quality_score = min(1.0, max(0.0, len(content) / 500.0))
        
        if template_ai_assisted is None:
            ai_assisted_default = self.config.get("ai_assisted_default", True)
        else:
            ai_assisted_default = bool(template_ai_assisted)
        post = {
            "id": f"post_{int(time.time())}_{random.randint(1000, 9999)}",
            "type": post_type,
            "subreddit": subreddit,
            "title": title,
            "content": content,
            "ai_assisted": bool(ai_assisted_default),
            "status": "scheduled",
            "created_at": datetime.now().isoformat(),
            "scheduled_for": scheduled_time.isoformat(),
            "account": self.account_name,
            "attempts": 0,
            "last_attempt": None,
            "posted_at": None,
            "post_url": None,
            "error": None,
            "quality_score": round(quality_score, 2),
            "ab_test": ab_variants,
            "metrics": {
                "views": None,
                "upvotes": None,
                "comments": None,
                "retention": None,
                "crosspost_effectiveness": None,
            },
        }
        if self.optimizer and getattr(self.optimizer, "enabled", False):
            post["template_id"] = template_id or self.optimizer.template_id(post_type, title, content)
            post["predicted_engagement"] = self.optimizer.predict_engagement(post)
            post["predicted_risk"] = self.optimizer.predict_risk(post)

        if ab_variants:
            self._log_ab_event(post, "created")
        
        return post
    
    def select_subreddit_for_post(self, post_type: str) -> str:
        """Select appropriate subreddit for post type"""
        primary = self.config.get("subreddit_distribution", {}).get("primary_focus", [])
        secondary = self.config.get("subreddit_distribution", {}).get("secondary_focus", [])
        crosspost = self.config.get("subreddit_distribution", {}).get("crosspost_to", [])
        moderated = (
            self.status_tracker.status_data.get(self.account_name, {})
            .get("subreddits", {})
            .get("moderated", [])
        )
        fallback = self.config_manager.bot_settings.get("subreddits", [])

        if moderated and random.random() < 0.6:
            return random.choice(moderated)
        if primary and random.random() < 0.7:
            return random.choice(primary)
        if secondary and random.random() < 0.8:
            return random.choice(secondary)
        if crosspost:
            return random.choice(crosspost)
        if fallback:
            return random.choice(fallback)
        return "microdosing"
    
    def generate_scheduled_time(self) -> datetime:
        """Generate a scheduled time based on optimal posting times"""
        now = datetime.now()

        windows = self.config.get("posting_settings", {}).get("time_windows") or []
        if windows:
            start_str, end_str = random.choice(windows).split("-")
            start_hour, start_minute = map(int, start_str.split(":"))
            end_hour, end_minute = map(int, end_str.split(":"))
            start_dt = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            end_dt = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            if start_dt <= now <= end_dt:
                window_start = now
                window_end = end_dt
            else:
                window_start = start_dt if now < start_dt else start_dt + timedelta(days=1)
                window_end = end_dt if now < start_dt else end_dt + timedelta(days=1)
            total_minutes = max(1, int((window_end - window_start).total_seconds() / 60))
            offset = random.randint(0, total_minutes)
            scheduled = window_start + timedelta(minutes=offset)
        else:
            optimal_times = self.config["posting_settings"]["optimal_posting_times"]
            weights = [t["weight"] for t in optimal_times]
            times = [t["time"] for t in optimal_times]
            selected_time_str = random.choices(times, weights=weights, k=1)[0]
            hour, minute = map(int, selected_time_str.split(":"))
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if scheduled <= now:
                scheduled += timedelta(days=1)

        if self.config["safety_settings"]["randomize_post_times"]:
            jitter = random.randint(
                -self.config["safety_settings"]["jitter_minutes"],
                self.config["safety_settings"]["jitter_minutes"]
            )
            scheduled += timedelta(minutes=jitter)

        avoid_times = self.config["posting_settings"]["avoid_posting_times"]
        for avoid_range in avoid_times:
            start_str, end_str = avoid_range.split("-")
            start_hour, start_minute = map(int, start_str.split(":"))
            end_hour, end_minute = map(int, end_str.split(":"))
            avoid_start = scheduled.replace(hour=start_hour, minute=start_minute)
            avoid_end = scheduled.replace(hour=end_hour, minute=end_minute)
            if avoid_end < avoid_start:
                avoid_end += timedelta(days=1)
            if avoid_start <= scheduled <= avoid_end:
                scheduled = avoid_end + timedelta(minutes=30)

        return scheduled
    
    def setup_browser(self):
        """Setup Selenium browser with anti-detection measures"""
        try:
            if self.driver:
                return True
            self._setup_browser()
            logger.info("Browser setup complete (base)")
            return True
        except Exception as e:
            logger.error(f"Failed to setup browser: {e}")
            return False
    
    def login_with_cookies(self) -> bool:
        """Login to Reddit using saved cookies"""
        try:
            if self.logged_in:
                return True
            result = self._login_with_fallback()
            return result.success
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def _find_first(self, selectors: List[Tuple[str, str]], wait_seconds: int = 6):
        """Return the first visible element matching any selector."""
        for by, value in selectors:
            try:
                element = WebDriverWait(self.driver, wait_seconds).until(
                    EC.presence_of_element_located((by, value))
                )
                if element and element.is_displayed():
                    return element
            except Exception:
                continue
        return None

    def _find_by_id_deep(self, element_id: str):
        """Find element by id, including inside shadow roots."""
        try:
            return self.driver.execute_script(
                """
                const targetId = arguments[0];
                function findByIdDeep(root) {
                  if (!root) return null;
                  if (root.querySelector) {
                    const direct = root.querySelector('#' + targetId);
                    if (direct) return direct;
                  }
                  const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
                  for (const node of nodes) {
                    if (node.shadowRoot) {
                      const found = findByIdDeep(node.shadowRoot);
                      if (found) return found;
                    }
                  }
                  return null;
                }
                return findByIdDeep(document);
                """,
                element_id,
            )
        except Exception:
            return None

    def _query_selector_deep(self, selector: str):
        """Find first element matching selector, including inside shadow roots."""
        try:
            return self.driver.execute_script(
                """
                const sel = arguments[0];
                function findDeep(root) {
                  if (!root) return null;
                  if (root.querySelector) {
                    const direct = root.querySelector(sel);
                    if (direct) return direct;
                  }
                  const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
                  for (const node of nodes) {
                    if (node.shadowRoot) {
                      const found = findDeep(node.shadowRoot);
                      if (found) return found;
                    }
                  }
                  return null;
                }
                return findDeep(document);
                """,
                selector,
            )
        except Exception:
            return None
    
    def human_typing(self, element, text: str):
        """Simulate human typing with random delays and occasional typos"""
        if not self.config["safety_settings"]["use_human_typing"]:
            element.send_keys(text)
            return
        
        # Add occasional typos
        if random.random() < self.config["safety_settings"]["add_typos_chance"]:
            # Insert a typo (miss a letter or swap letters)
            if len(text) > 5:
                typo_pos = random.randint(1, len(text) - 2)
                text = text[:typo_pos] + text[typo_pos+1:]  # Remove a letter
        
        for char in text:
            element.send_keys(char)
            # Random delay between keystrokes (50-150ms)
            time.sleep(random.uniform(0.05, 0.15))

    
    def submit_post(self, post_data: Dict) -> Tuple[bool, Optional[str]]:
        """Submit a post to Reddit using Selenium"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Skipping submit_post execution")
                return True, "dry_run"
            subreddit = post_data["subreddit"]
            title = post_data["title"]
            content = post_data["content"]
            if post_data.get("crosspost_from"):
                require_manual = bool(
                    self.config.get("subreddit_distribution", {}).get("crosspost_requires_manual", False)
                )
                if require_manual:
                    if self.headless:
                        logger.warning("Crosspost requires manual approval in headless mode; skipping.")
                        return False, "crosspost_manual_required"
                    input(f"Approve crosspost to r/{subreddit} from r/{post_data['crosspost_from']} and press Enter...")
            if os.getenv("BYPASS_POSTING_LIMITS", "").strip().lower() not in ("1", "true", "yes"):
                if not self.status_tracker.can_perform_action(
                    self.account_name,
                    "posting",
                    subreddit=subreddit,
                    daily_limit=self.config["posting_settings"]["max_posts_per_day"],
                ):
                    logger.info(f"Posting limited for {self.account_name}; skipping r/{subreddit}")
                    return False, "posting_limited"
            limits = (self.activity_schedule or {}).get("rate_limits", {})
            if os.getenv("BYPASS_POSTING_LIMITS", "").strip().lower() not in ("1", "true", "yes"):
                allowed, wait_seconds = self.rate_limiter.check_rate_limit(
                    self.account_name, "submit_post", limits
                )
                if not allowed:
                    self.status_tracker.set_cooldown(self.account_name, "posting", wait_seconds)
                    logger.info(f"Rate limited for posting; wait {wait_seconds}s")
                    return False, "rate_limited"
            
            idem_path = Path(os.getenv("IDEMPOTENCY_PATH", IDEMPOTENCY_DEFAULT_PATH))
            post_key = build_post_key(post_data)
            if post_key and not can_attempt(idem_path, post_key):
                logger.info("Idempotency skip: post already attempted/sent")
                return False, "idempotent_skip"

            logger.info(f"Submitting post to r/{subreddit}: {title[:50]}...")
            mark_attempt(idem_path, post_key, {"subreddit": subreddit, "title": title})
            
            # Navigate to modern submit page (new Reddit only)
            submit_url = f"https://www.reddit.com/r/{subreddit}/submit"
            self.driver.get(submit_url)
            time.sleep(3)
            
            # Check for CAPTCHA (strict element-based check to avoid false positives)
            def _captcha_present() -> Tuple[bool, str]:
                try:
                    selectors = [
                        "iframe[src*='recaptcha']",
                        "iframe[src*='hcaptcha']",
                        "div.g-recaptcha",
                        "div.h-captcha",
                        "[id*='captcha' i]",
                        "[class*='captcha' i]",
                        "input[name*='captcha' i]",
                    ]
                    for sel in selectors:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in elements:
                            try:
                                if el.is_displayed():
                                    return True, f"selector:{sel}"
                            except Exception:
                                continue
                except Exception:
                    pass
                return False, ""

            captcha_found, captcha_reason = _captcha_present()
            if captcha_found:
                logger.error("CAPTCHA detected! (%s)", captcha_reason)
                # Short wait + refresh loop before prompting (iframe sometimes clears)
                for attempt in range(2):
                    time.sleep(2)
                    self.driver.refresh()
                    time.sleep(2)
                    captcha_found, captcha_reason = _captcha_present()
                    if not captcha_found:
                        break
                if not self.headless:
                    input("Please solve CAPTCHA and press Enter...")
                    time.sleep(3)
                    still_found, still_reason = _captcha_present()
                    if still_found:
                        logger.error("CAPTCHA still present after manual solve (%s)", still_reason)
                        return False, "captcha_unresolved"
                else:
                    return False, "CAPTCHA detected in headless mode"
            
            # Ensure Text tab selected (modern UI only)
            try:
                text_tab = self._find_first(
                    [
                        (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'text')]"),
                    ],
                    wait_seconds=3,
                )
                if text_tab:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", text_tab)
                    text_tab.click()
                    time.sleep(0.8)
            except Exception:
                logger.warning("Could not find text tab in modern Reddit UI")
            
            # Enter title (modern UI only)
            title_field = self._find_first(
                [
                    (By.CSS_SELECTOR, "faceplate-textarea-input[name='title']"),
                    (By.CSS_SELECTOR, "#post-composer__title faceplate-textarea-input[name='title']"),
                ],
                wait_seconds=10,
            )
            if not title_field:
                return False, "title_field_not_found"
            try:
                self.driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    title_field,
                    title,
                )
            except Exception:
                title_field.send_keys(title)
            time.sleep(1)
            
            # Switch to Markdown editor (modern UI)
            try:
                more_options = self._find_first(
                    [
                        (By.CSS_SELECTOR, "button[aria-label='More options']"),
                    ],
                    wait_seconds=3,
                )
                if not more_options:
                    more_options = self._query_selector_deep("button[aria-label='More options']")
                if more_options:
                    try:
                        more_options.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", more_options)
                    time.sleep(0.5)
                else:
                    logger.warning("Markdown toggle: More options button not found")
                # Click "Switch to Markdown" in the dropdown (shadow DOM)
                self.driver.execute_script(
                    """
                    function findDeepAll(root, selector, acc) {
                      if (!root) return;
                      if (root.querySelectorAll) {
                        root.querySelectorAll(selector).forEach(n => acc.push(n));
                      }
                      const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
                      for (const node of nodes) {
                        if (node.shadowRoot) findDeepAll(node.shadowRoot, selector, acc);
                      }
                    }
                    const acc = [];
                    findDeepAll(document, 'rpl-menu-item', acc);
                    for (const item of acc) {
                      const txt = (item.textContent || '').trim();
                      if (txt.includes('Switch to Markdown')) {
                        item.click();
                        break;
                      }
                    }
                    """
                )
                # Confirm Markdown editor is visible
                for _ in range(5):
                    visible = self.driver.execute_script(
                        """
                        const comp = document.querySelector('shreddit-markdown-composer');
                        if (!comp || !comp.shadowRoot) return false;
                        const header = comp.shadowRoot.querySelector('div .text-secondary-weak');
                        const text = header ? header.textContent || '' : '';
                        return text.includes('Markdown Editor');
                        """
                    )
                    if visible:
                        break
                    time.sleep(0.5)
                time.sleep(0.2)
            except Exception:
                logger.warning("Could not switch to Markdown editor")

            # Enter content (Markdown editor)
            try:
                textarea = None
                for _ in range(8):
                    textarea = self.driver.execute_script(
                        """
                        const comp = document.querySelector('shreddit-markdown-composer');
                        if (!comp) return null;
                        if (!comp.shadowRoot) return null;
                        return comp.shadowRoot.querySelector('textarea[part=\"textarea-input\"]');
                        """
                    )
                    if textarea:
                        break
                    time.sleep(0.5)
                if not textarea:
                    textarea = self._query_selector_deep("textarea[part='textarea-input']")
                if not textarea:
                    # Try light DOM inside markdown composer (if any)
                    textarea = self.driver.execute_script(
                        """
                        const comp = document.querySelector('shreddit-markdown-composer');
                        if (!comp) return null;
                        return comp.querySelector('textarea[part=\"textarea-input\"]');
                        """
                    )
                if not textarea:
                    exists = self.driver.execute_script(
                        """
                        const comp = document.querySelector('shreddit-markdown-composer');
                        if (!comp) return 'composer_missing';
                        return comp.shadowRoot ? 'composer_shadow_ok' : 'composer_shadow_missing';
                        """
                    )
                    counts = self.driver.execute_script(
                        """
                        function countDeep(root, selector) {
                          let count = 0;
                          if (root && root.querySelectorAll) {
                            count += root.querySelectorAll(selector).length;
                          }
                          const nodes = root && root.querySelectorAll ? root.querySelectorAll('*') : [];
                          for (const node of nodes) {
                            if (node.shadowRoot) {
                              count += countDeep(node.shadowRoot, selector);
                            }
                          }
                          return count;
                        }
                        return {
                          markdown_composers: countDeep(document, 'shreddit-markdown-composer'),
                          textarea_parts: countDeep(document, \"textarea[part='textarea-input']\"),
                        };
                        """
                    )
                    logger.error(
                        "Markdown editor: textarea not found after retries (%s, counts=%s)",
                        exists,
                        counts,
                    )
                    if exists == "composer_missing" and not self.headless:
                        try:
                            input("Markdown editor not found. Please switch to Markdown manually, then press Enter...")
                        except Exception:
                            pass
                        # Retry once after manual switch
                        textarea = self._query_selector_deep("textarea[part='textarea-input']")
                        if textarea:
                            logger.info("Markdown editor: textarea found after manual switch")
                        else:
                            logger.warning("Markdown editor still missing; falling back to rich-text editor")
                    if not textarea:
                        # Fallback to rich-text editor if markdown is unavailable
                        rt_field = self._find_first(
                            [
                                (By.CSS_SELECTOR, "shreddit-composer#post-composer_bodytext [contenteditable='true'][role='textbox']"),
                            ],
                            wait_seconds=5,
                        )
                        if rt_field:
                            try:
                                rt_field.click()
                                self.human_typing(rt_field, content)
                            except Exception:
                                self.driver.execute_script("arguments[0].innerText = arguments[1];", rt_field, content)
                            time.sleep(1)
                            return True, "fallback_richtext"
                    return False, "content_field_not_found"
                self.driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    textarea,
                    content,
                )
                time.sleep(1)
            except Exception:
                logger.error("Markdown editor: failed to set content")
                return False, "content_field_not_found"
            
            # Add flair if required (modern UI only)
            try:
                flair_open_button = self._find_first(
                    [
                        (By.CSS_SELECTOR, "#reddit-post-flair-button"),
                    ],
                    wait_seconds=2,
                )
                if flair_open_button:
                    flair_open_button.click()
                    time.sleep(1)
                    flair_map = {
                        "discussion": "Research Discussion",
                        "question": "Question",
                        "resource": "Resource Share",
                        "experience": "Personal Experience",
                        "news": "Community News",
                        "ai_assisted": "AI-Assisted",
                    }
                    if post_data.get("ai_assisted", True):
                        preferred = flair_map.get("ai_assisted")
                    else:
                        preferred = flair_map.get(post_data.get("type", ""), "")
                    chosen = False
                    if preferred:
                        try:
                            option = self._find_first(
                                [
                                    (By.XPATH, f"//faceplate-radio-input[.//span[contains(normalize-space(.), '{preferred}')]]"),
                                ],
                                wait_seconds=2,
                            )
                            if option:
                                option.click()
                                chosen = True
                        except Exception:
                            pass
                    if not chosen:
                        flair_options = self.driver.find_elements(
                            By.XPATH,
                            "//faceplate-radio-input[not(@id='post-flair-radio-input-no-flair')]",
                        )
                        flair_options = [f for f in flair_options if f.is_displayed()]
                        if flair_options:
                            random.choice(flair_options).click()
                            chosen = True
                    if chosen:
                        time.sleep(1)
                        apply_btn = self._find_first(
                            [
                                (By.CSS_SELECTOR, "#post-flair-modal-apply-button"),
                            ],
                            wait_seconds=2,
                        )
                        if apply_btn:
                            apply_btn.click()
                            time.sleep(1)
            except Exception:
                logger.debug("Could not add flair, continuing anyway")
            
            # Submit (modern UI only)
            submit_button = self._find_first(
                [
                    (By.CSS_SELECTOR, "#inner-post-submit-button"),
                    (By.CSS_SELECTOR, "#submit-post-button"),
                ],
                wait_seconds=5,
            )
            if not submit_button:
                submit_button = self._find_by_id_deep("inner-post-submit-button")
            if not submit_button:
                submit_button = self._find_by_id_deep("submit-post-button")
            if not submit_button:
                return False, "submit_button_not_found"
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_button)
            except Exception:
                pass
            try:
                submit_button.click()
            except Exception:
                try:
                    self.driver.execute_script(
                        "const host = document.querySelector('#submit-post-button');"
                        "const btn = host && host.shadowRoot ? host.shadowRoot.querySelector('#inner-post-submit-button') : null;"
                        "if (btn) btn.click();",
                    )
                except Exception:
                    pass
            time.sleep(5)
            
            def _success_from_page() -> bool:
                try:
                    toast_text = self.driver.execute_script(
                        """
                        const nodes = Array.from(document.querySelectorAll('[role="alert"], faceplate-toast, .toast, .Toast'));
                        return nodes.map(n => (n.textContent || '')).join(' ').toLowerCase();
                        """
                    )
                    if isinstance(toast_text, str) and ("post" in toast_text and ("submitted" in toast_text or "posted" in toast_text)):
                        return True
                except Exception:
                    pass
                return False

            success = False
            post_url = self.driver.current_url
            for _ in range(10):
                post_url = self.driver.current_url
                if "comments" in post_url:
                    success = True
                    break
                if _success_from_page():
                    success = True
                    break
                time.sleep(2)

            if success:
                logger.info(f"Post successful: {post_url}")
                self.rate_limiter.record_action(self.account_name, "submit_post")
                self.status_tracker.record_post_activity(
                    self.account_name, subreddit, post_data.get("type", "unknown"), True,
                    daily_limit=self.config["posting_settings"]["max_posts_per_day"]
                )
                if post_key:
                    mark_success(idem_path, post_key, {"post_url": post_url})
                return True, post_url

            # Check for errors
            page_text = self.driver.page_source.lower()
            error_messages = [
                "try again later",
                "you're doing that too much",
                "rate limit",
                "something went wrong",
                "please try again"
            ]
            
            for error in error_messages:
                if error in page_text:
                    logger.error(f"Post failed: {error}")
                    self.status_tracker.record_post_activity(
                        self.account_name, subreddit, post_data.get("type", "unknown"), False,
                        daily_limit=self.config["posting_settings"]["max_posts_per_day"]
                    )
                    if "rate" in error:
                        self.status_tracker.update_account_status(
                            self.account_name, "rate_limited", {"reason": error}
                        )
                    if post_key:
                        mark_failure(idem_path, post_key, error=error)
                    return False, error
            
            current_url = self.driver.current_url
            if current_url != submit_url:
                logger.warning("Post result unclear; URL changed. Assuming success.")
                self.rate_limiter.record_action(self.account_name, "submit_post")
                self.status_tracker.record_post_activity(
                    self.account_name, subreddit, post_data.get("type", "unknown"), True,
                    daily_limit=self.config["posting_settings"]["max_posts_per_day"]
                )
                if post_key:
                    mark_success(idem_path, post_key, {"post_url": current_url, "assumed": True})
                return True, current_url

            logger.error("Post failed for unknown reason (no error markers, no success markers)")
            logger.info("Post submit debug: url=%s", current_url)
            self.status_tracker.record_post_activity(
                self.account_name, subreddit, post_data.get("type", "unknown"), False,
                daily_limit=self.config["posting_settings"]["max_posts_per_day"]
            )
            if post_key:
                mark_failure(idem_path, post_key, error="unknown")
            return False, "Unknown error"
            
        except Exception as e:
            logger.error(f"Error submitting post: {e}")
            self.status_tracker.record_post_activity(
                self.account_name, post_data.get("subreddit", "unknown"), post_data.get("type", "unknown"), False,
                daily_limit=self.config["posting_settings"]["max_posts_per_day"]
            )
            try:
                idem_path = Path(os.getenv("IDEMPOTENCY_PATH", IDEMPOTENCY_DEFAULT_PATH))
                post_key = build_post_key(post_data)
                if post_key:
                    mark_failure(idem_path, post_key, error=str(e))
            except Exception:
                pass
            return False, str(e)
    
    def schedule_post(self, post_data: Dict):
        """Add a post to the schedule"""
        schedule_data = self.load_schedule()

        if not self._can_schedule_more_posts(schedule_data):
            logger.warning("Posting limits reached; skipping schedule")
            return None
        
        # Set status to scheduled if not already
        post_data["status"] = "scheduled"
        post_data["created_at"] = datetime.now().isoformat()
        
        # Add to schedule
        schedule_data.append(post_data)
        
        # Save schedule
        self.save_schedule(schedule_data)
        
        logger.info(f"Scheduled post for {post_data['scheduled_for']} to r/{post_data['subreddit']}")
        return post_data
    
    def generate_scheduled_posts(self, num_posts: int = 5, days_ahead: int = 7):
        """Generate and schedule multiple posts"""
        logger.info(f"Generating {num_posts} posts scheduled over next {days_ahead} days")
        
        posts = []
        schedule_data = self.load_schedule()
        for i in range(num_posts):
            if not self._can_schedule_more_posts(schedule_data):
                logger.warning("Posting limits reached; stopping generation")
                break
            # Determine post type based on content mix
            post_types = list(self.config["content_strategy"]["content_mix"].keys())
            weights = list(self.config["content_strategy"]["content_mix"].values())
            post_type = random.choices(post_types, weights=weights, k=1)[0]
            
            # Generate post
            scheduled_time = self.generate_scheduled_time()
            theme = self._pick_theme_for_date(scheduled_time)
            themed_type = self._select_post_type_for_theme(theme)
            if themed_type:
                post_type = themed_type
            post = self.generate_post_from_template(post_type)
            if theme:
                post["theme"] = theme
            
            # Schedule at appropriate time (spread out over days)
            days_offset = random.randint(0, days_ahead - 1)
            scheduled_time = datetime.fromisoformat(post["scheduled_for"])
            scheduled_time += timedelta(days=days_offset)
            
            # Random time within day
            hour = random.randint(9, 21)  # 9 AM to 9 PM
            minute = random.randint(0, 59)
            post["scheduled_for"] = scheduled_time.replace(hour=hour, minute=minute).isoformat()
            
            posts.append(post)
            schedule_data.append(post)

            for cp in self._generate_crosspost_posts(post):
                posts.append(cp)
                schedule_data.append(cp)
        
        self.save_schedule(schedule_data)
        
        logger.info(f"Generated and scheduled {len(posts)} posts")
        return posts

    def seed_subreddit_content(self, subreddit: str, count: int, days: int = 30) -> List[Dict]:
        """Seed a subreddit with scheduled content over a window."""
        posts = []
        schedule_data = self.load_schedule()
        for _ in range(count):
            if not self._can_schedule_more_posts(schedule_data):
                break
            post_types = list(self.config["content_strategy"]["content_mix"].keys())
            weights = list(self.config["content_strategy"]["content_mix"].values())
            post_type = random.choices(post_types, weights=weights, k=1)[0]
            scheduled_time = self.generate_scheduled_time()
            theme = self._pick_theme_for_date(scheduled_time)
            themed_type = self._select_post_type_for_theme(theme)
            if themed_type:
                post_type = themed_type
            post = self.generate_post_from_template(post_type, subreddit=subreddit)
            if theme:
                post["theme"] = theme
            days_offset = random.randint(0, max(1, days) - 1)
            scheduled_time = datetime.fromisoformat(post["scheduled_for"])
            scheduled_time += timedelta(days=days_offset)
            post["scheduled_for"] = scheduled_time.isoformat()
            post["seeded"] = True
            posts.append(post)
            schedule_data.append(post)
            for cp in self._generate_crosspost_posts(post):
                cp["seeded"] = True
                posts.append(cp)
                schedule_data.append(cp)
        self.save_schedule(schedule_data)
        return posts

    def seed_network_content(
        self,
        count_per_subreddit: Optional[int] = None,
        days: int = 30,
        subreddits: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        network = self.load_network_config()
        if not network.get("enabled"):
            return {}
        categories = network.get("categories", {})
        cross = network.get("cross_promotion", {})
        count = count_per_subreddit or int(network.get("seed_posts_per_subreddit", 10))
        seeded = {}
        target = set([s for s in (subreddits or []) if s])
        for group in categories.values():
            if not isinstance(group, list):
                continue
            for subreddit in group:
                if target and subreddit not in target:
                    continue
                posts = self.seed_subreddit_content(subreddit, count=count, days=days)
                seeded[subreddit] = len(posts)
                # Optional weekly digest for hubs
                if cross.get("weekly_digest") and subreddit in categories.get("primary_hubs", []):
                    digest = self.generate_weekly_digest(subreddit, related=group)
                    if digest:
                        self.schedule_post(digest)
        return seeded

    def run_content_discovery(self, max_items: Optional[int] = None) -> int:
        """Generate scheduled posts from local discovery queue (no external fetch)."""
        try:
            from scripts.content_discovery.content_discovery import ContentDiscovery
        except Exception as exc:
            logger.error("Content discovery module missing: %s", exc)
            return 0
        discovery = ContentDiscovery(config_path=Path("config/content_discovery.json"))
        return discovery.generate_posts_from_queue(self, max_items=max_items)

    def generate_ab_report(self, limit: int = 100) -> Dict[str, Any]:
        """Create a summary of A/B performance from the schedule file."""
        schedule = self.load_schedule()
        rows = []
        for post in schedule:
            ab = post.get("ab_test") or {}
            metrics = post.get("metrics") or {}
            if not ab:
                continue
            views = metrics.get("views") or 0
            upvotes = metrics.get("upvotes") or 0
            comments = metrics.get("comments") or 0
            cross = metrics.get("crosspost_effectiveness") or 0
            if views:
                upvote_rate = round((upvotes / views) * 100, 2)
            else:
                upvote_rate = None
            row = {
                "id": post.get("id"),
                "subreddit": post.get("subreddit"),
                "title": post.get("title"),
                "type": post.get("type"),
                "ab_test": ab,
                "views": views,
                "upvotes": upvotes,
                "comments": comments,
                "upvote_rate_per_100": upvote_rate,
                "crosspost_effectiveness": cross,
            }
            rows.append(row)
        rows = rows[:limit]
        summary = {"total_ab_posts": len(rows), "rows": rows}
        report_json = Path("logs/ab_test_report.json")
        report_md = Path("logs/ab_test_report.md")
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(summary, indent=2))
        lines = ["# A/B Test Report", f"Total A/B posts: {len(rows)}", ""]
        for r in rows:
            lines.append(
                f"- {r['id']} | r/{r['subreddit']} | upvote/100 views: {r['upvote_rate_per_100']} | comments: {r['comments']} | ab: {r['ab_test']}"
            )
        report_md.write_text("\n".join(lines))
        return summary

    def generate_kpi_dashboard(self) -> Dict[str, Any]:
        try:
            from scripts.reporting.kpi_dashboard import generate_dashboard
        except Exception as exc:
            logger.error("KPI dashboard module missing: %s", exc)
            return {}
        return generate_dashboard()

    def schedule_weekly_digest(self, weeks_ahead: int = 4) -> int:
        """Schedule weekly digests for primary hubs."""
        network = self.load_network_config()
        if not network.get("enabled"):
            return 0
        categories = network.get("categories", {})
        hubs = categories.get("primary_hubs", []) if isinstance(categories.get("primary_hubs", []), list) else []
        if not hubs:
            return 0
        count = 0
        now = datetime.now()
        for hub in hubs:
            for w in range(weeks_ahead):
                scheduled_time = now + timedelta(days=7 * (w + 1))
                digest = self.generate_weekly_digest(hub, related=hubs)
                if not digest:
                    continue
                digest["scheduled_for"] = scheduled_time.isoformat()
                self.schedule_post(digest)
                count += 1
        return count

    def schedule_ab_title_variations(self, post_type: str, subreddit: Optional[str] = None, variations: int = 3) -> List[Dict]:
        """Create multiple scheduled posts with different title variants."""
        posts = []
        base = self.generate_post_from_template(post_type, subreddit=subreddit)
        base_id = base.get("id")
        for _ in range(max(1, variations)):
            variant = self._choose_ab_variants()
            title = base["title"]
            if variant.get("title_style"):
                title = self._apply_title_variant(title, variant["title_style"])
            title = self._apply_seo_title_keywords(title)
            post = dict(base)
            post["id"] = f"ab_{int(time.time())}_{random.randint(1000, 9999)}"
            post["title"] = title
            post["ab_test"] = variant
            post["ab_group"] = base_id
            self.schedule_post(post)
            posts.append(post)
        return posts

    def generate_weekly_digest(self, subreddit: str, related: Optional[List[str]] = None) -> Optional[Dict]:
        related = related or []
        items = "\n".join([f"- r/{name}" for name in related if name != subreddit][:5])
        title = "Weekly Digest: Network highlights and threads"
        content = (
            "Here is a quick weekly roundup from across the network.\n\n"
            "## Related communities\n"
            f"{items if items else '- r/' + subreddit}\n\n"
            "Share the best discussions you’ve seen this week in the comments."
        )
        scheduled_time = self.generate_scheduled_time()
        return {
            "id": f"digest_{int(time.time())}_{random.randint(1000, 9999)}",
            "type": "digest",
            "subreddit": subreddit,
            "title": title,
            "content": content,
            "status": "scheduled",
            "created_at": datetime.now().isoformat(),
            "scheduled_for": scheduled_time.isoformat(),
            "account": self.account_name,
            "attempts": 0,
            "last_attempt": None,
            "posted_at": None,
            "post_url": None,
            "error": None,
            "quality_score": 0.6,
        }
    
    def check_due_posts(self) -> List[Dict]:
        """Check for posts that are due to be posted"""
        schedule_data = self.load_schedule()
        now = datetime.now()
        
        due_posts = []
        for post in schedule_data:
            if post.get("account") and post.get("account") != self.account_name:
                continue
            if post["status"] != "scheduled":
                continue
            
            try:
                scheduled_time = datetime.fromisoformat(post["scheduled_for"])
                
                # Check if post is due (within next 5 minutes or past due)
                if scheduled_time <= now + timedelta(minutes=5):
                    due_posts.append(post)
            except (ValueError, KeyError):
                logger.warning(f"Invalid scheduled time in post {post.get('id', 'unknown')}")
                continue
        
        return due_posts
    
    def process_due_posts(self):
        """Process all due posts"""
        due_posts = self.check_due_posts()
        
        if not due_posts:
            logger.debug("No posts due for posting")
            return 0
        
        logger.info(f"Found {len(due_posts)} posts due for posting")
        
        if self.dry_run:
            logger.info("[dry-run] Would process %s due posts", len(due_posts))
            return len(due_posts)

        # Setup browser if needed
        if not self.driver:
            if not self.setup_browser():
                logger.error("Failed to setup browser")
                return 0
            
            if not self.login_with_cookies():
                logger.error("Failed to login")
                return 0
        
        success_count = 0
        for post in due_posts:
            try:
                # Update attempt count
                post["attempts"] = post.get("attempts", 0) + 1
                post["last_attempt"] = datetime.now().isoformat()
                
                # Submit post
                action_result = self.execute_safely(
                    lambda: self.submit_post(post),
                    action_name="submit_post",
                    max_retries=self.config["safety_settings"]["max_retries"],
                )
                raw_result = action_result.result
                if isinstance(raw_result, tuple) and len(raw_result) >= 2:
                    success, result = raw_result[0], raw_result[1]
                else:
                    success, result = action_result.success, raw_result
                
                if success:
                    post["status"] = "posted"
                    post["posted_at"] = datetime.now().isoformat()
                    post["post_url"] = result
                    post["error"] = None
                    success_count += 1
                    logger.info(f"Successfully posted: {post['title'][:50]}...")
                    self._log_ab_event(post, "submitted", {"result": "success"})
                else:
                    post["error"] = result
                    
                    # Check if we should retry
                    max_retries = self.config["safety_settings"]["max_retries"]
                    if post["attempts"] < max_retries and self.config["safety_settings"]["retry_failed_posts"]:
                        # Reschedule for later (15 minutes to 2 hours)
                        delay_minutes = random.randint(15, 120)
                        new_time = datetime.now() + timedelta(minutes=delay_minutes)
                        post["scheduled_for"] = new_time.isoformat()
                        post["status"] = "scheduled"
                        logger.info(f"Rescheduled post for retry in {delay_minutes} minutes")
                    else:
                        post["status"] = "failed"
                        logger.error(f"Post failed after {post['attempts']} attempts: {result}")
                
                # Save schedule after each post
                self.update_post_in_schedule(post)
                
                # Delay between posts
                delay = random.randint(
                    self.config["posting_settings"]["min_time_between_posts_minutes"],
                    self.config["posting_settings"]["min_time_between_posts_minutes"] * 2
                )
                logger.info(f"Waiting {delay} minutes before next post...")
                time.sleep(delay * 60)
                
            except Exception as e:
                logger.error(f"Error processing post {post.get('id', 'unknown')}: {e}")
                post["error"] = str(e)
                post["status"] = "failed"
                self.update_post_in_schedule(post)
                continue
        
        return success_count
    
    def update_post_in_schedule(self, updated_post: Dict):
        """Update a post in the schedule"""
        schedule_data = self.load_schedule()
        
        for i, post in enumerate(schedule_data):
            if post.get("id") == updated_post.get("id"):
                schedule_data[i] = updated_post
                break
        
        self.save_schedule(schedule_data)
    
    def cleanup_old_schedule(self):
        """Clean up old posts from schedule"""
        schedule_data = self.load_schedule()
        
        cutoff_days = self.config["automation_settings"]["cleanup_old_schedule_days"]
        cutoff_date = datetime.now() - timedelta(days=cutoff_days)
        
        new_schedule = []
        removed_count = 0
        
        for post in schedule_data:
            try:
                # Keep posts that are scheduled for future
                scheduled_time = datetime.fromisoformat(post["scheduled_for"])
                if scheduled_time > cutoff_date:
                    new_schedule.append(post)
                else:
                    # Keep failed posts for debugging if they failed recently
                    if post.get("status") == "failed":
                        if "last_attempt" in post:
                            last_attempt = datetime.fromisoformat(post["last_attempt"])
                            if last_attempt > cutoff_date:
                                new_schedule.append(post)
                                continue
                    removed_count += 1
            except:
                # Keep posts with invalid dates for manual review
                new_schedule.append(post)
        
        if removed_count > 0:
            self.save_schedule(new_schedule)
            logger.info(f"Cleaned up {removed_count} old posts from schedule")
        
        return removed_count

    def _get_recent_post_counts(self) -> Dict[str, int]:
        entry = self.status_tracker.status_data.get(self.account_name, {})
        posts = entry.get("activity_stats", {}).get("posts", [])
        now = datetime.now()
        day_count = 0
        week_count = 0
        for item in posts:
            try:
                ts = datetime.fromisoformat(item.get("timestamp", ""))
            except Exception:
                continue
            if not item.get("success"):
                continue
            if ts.date() == now.date():
                day_count += 1
            if (now - ts).days < 7:
                week_count += 1
        return {"today": day_count, "week": week_count}

    def _can_schedule_more_posts(self, schedule_data: List[Dict]) -> bool:
        if self.status_tracker.should_skip_account(self.account_name):
            return False
        remaining = self.status_tracker.get_cooldown_remaining(self.account_name, "posting")
        if remaining and remaining > 0:
            return False
        limits = self.config.get("posting_settings", {})
        max_day = limits.get("max_posts_per_day", 1)
        max_week = limits.get("max_posts_per_week", 7)
        counts = self._get_recent_post_counts()
        scheduled_today = 0
        scheduled_week = 0
        now = datetime.now()
        for post in schedule_data:
            if post.get("status") not in ("scheduled", "processing"):
                continue
            try:
                scheduled_time = datetime.fromisoformat(post.get("scheduled_for", ""))
            except Exception:
                continue
            if scheduled_time.date() == now.date():
                scheduled_today += 1
            if (scheduled_time - now).days < 7:
                scheduled_week += 1

        total_today = counts["today"] + scheduled_today
        total_week = counts["week"] + scheduled_week
        if total_today >= max_day:
            return False
        if total_week >= max_week:
            return False
        return True
    
    def run_scheduler_daemon(self):
        """Run the scheduler as a daemon (continuous operation)"""
        logger.info("Starting scheduler daemon...")
        self.is_running = True
        
        # Setup browser
        if not self.setup_browser():
            logger.error("Failed to setup browser, exiting daemon")
            return
        
        if not self.login_with_cookies():
            logger.error("Failed to login, exiting daemon")
            return
        
        try:
            while self.is_running:
                try:
                    # Process due posts
                    success_count = self.process_due_posts()
                    
                    # Cleanup old schedule
                    self.cleanup_old_schedule()
                    
                    # Log status
                    if success_count > 0:
                        logger.info(f"Posted {success_count} posts this cycle")
                    
                    # Wait before next check
                    check_interval = self.config["automation_settings"]["check_schedule_interval_minutes"]
                    logger.debug(f"Waiting {check_interval} minutes before next check...")
                    
                    # Wait, but check for stop signal periodically
                    for _ in range(check_interval * 6):  # Check every 10 seconds
                        if not self.is_running:
                            break
                        time.sleep(10)
                    
                except Exception as e:
                    logger.error(f"Error in scheduler daemon cycle: {e}")
                    time.sleep(60)  # Wait a minute before retrying
        
        except KeyboardInterrupt:
            logger.info("Scheduler daemon stopped by user")
        finally:
            if self.driver:
                self.cleanup()
            self.is_running = False
    
    def start_daemon(self):
        """Start the scheduler daemon in a separate thread"""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.scheduler_thread = threading.Thread(target=self.run_scheduler_daemon)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        logger.info("Scheduler daemon started in background")
    
    def stop_daemon(self):
        """Stop the scheduler daemon"""
        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=30)
        logger.info("Scheduler daemon stopped")
    
    def view_schedule(self, status_filter: str = None, days_ahead: int = 7):
        """View the current schedule"""
        schedule_data = self.load_schedule()
        now = datetime.now()
        future_cutoff = now + timedelta(days=days_ahead)
        
        filtered_posts = []
        for post in schedule_data:
            if status_filter and post.get("status") != status_filter:
                continue
            
            try:
                scheduled_time = datetime.fromisoformat(post["scheduled_for"])
                if scheduled_time > future_cutoff:
                    continue
            except:
                pass
            
            filtered_posts.append(post)
        
        # Sort by scheduled time
        filtered_posts.sort(key=lambda x: x.get("scheduled_for", ""))
        
        return filtered_posts
    
    def get_schedule_summary(self) -> Dict:
        """Get summary statistics of the schedule"""
        schedule_data = self.load_schedule()
        
        summary = {
            "total": len(schedule_data),
            "by_status": {},
            "by_subreddit": {},
            "by_type": {},
            "next_post": None
        }
        
        next_post_time = None
        next_post = None
        
        for post in schedule_data:
            # Count by status
            status = post.get("status", "unknown")
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
            
            # Count by subreddit
            subreddit = post.get("subreddit", "unknown")
            summary["by_subreddit"][subreddit] = summary["by_subreddit"].get(subreddit, 0) + 1
            
            # Count by type
            post_type = post.get("type", "unknown")
            summary["by_type"][post_type] = summary["by_type"].get(post_type, 0) + 1
            
            # Find next scheduled post
            if status == "scheduled":
                try:
                    scheduled_time = datetime.fromisoformat(post["scheduled_for"])
                    if next_post_time is None or scheduled_time < next_post_time:
                        next_post_time = scheduled_time
                        next_post = post
                except:
                    pass
        
        summary["next_post"] = next_post
        
        return summary

def main():
    """Command-line interface"""
    import argparse
    cleanup_state()
    
    parser = argparse.ArgumentParser(description="MCRDSE Post Scheduler - Selenium Version")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--generate", type=int, help="Generate N posts and schedule them")
    parser.add_argument("--seed-network", action="store_true", help="Seed network subreddits with scheduled posts")
    parser.add_argument("--seed-count", type=int, help="Seed count per subreddit (overrides network config)")
    parser.add_argument("--seed-days", type=int, default=30, help="Days to spread seeded posts across")
    parser.add_argument("--schedule", action="store_true", help="Schedule a specific post (interactive)")
    parser.add_argument("--post-now", action="store_true", help="Post immediately (bypass schedule)")
    parser.add_argument("--view", action="store_true", help="View schedule")
    parser.add_argument("--summary", action="store_true", help="Show schedule summary")
    parser.add_argument("--start-daemon", action="store_true", help="Start scheduler daemon")
    parser.add_argument("--stop-daemon", action="store_true", help="Stop scheduler daemon")
    parser.add_argument("--process", action="store_true", help="Process due posts once")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup old schedule")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--validate-only", action="store_true", help="Validate configs/accounts and exit")
    parser.add_argument("--days", type=int, default=7, help="Days ahead to view/generate for")
    
    args = parser.parse_args()
    
    logger.info("\n" + "="*60)
    logger.info("MCRDSE Post Scheduler")
    logger.info("="*60)
    
    # Initialize scheduler
    scheduler = MCRDSEPostScheduler(
        account_name=args.account,
        headless=args.headless,
        dry_run=args.dry_run,
    )
    logger.info(f"Validation summary: {scheduler.run_validations()}")
    enabled, reason = scheduler.is_feature_enabled("post_scheduling")
    if not enabled:
        logger.info(f"Post scheduling disabled ({reason}); exiting.")
        scheduler.cleanup()
        return

    if args.validate_only:
        logger.info(f"Validation summary: {scheduler.run_validations()}")
        scheduler.cleanup()
        return
    
    # Handle commands
    if args.generate:
        logger.info(f"\nGenerating {args.generate} posts...")
        posts = scheduler.generate_scheduled_posts(args.generate, args.days)
        logger.info(f"✓ Generated {len(posts)} posts")
        
        # Show what was generated
        for i, post in enumerate(posts, 1):
            scheduled_time = datetime.fromisoformat(post["scheduled_for"])
            logger.info(f"  {i}. r/{post['subreddit']} - {post['type']} - {scheduled_time.strftime('%Y-%m-%d %H:%M')}")
    
    elif args.schedule:
        logger.info("\nInteractive post scheduling")
        
        # Get post details
        post_type = input("Post type (discussion/question/resource/experience/news): ").strip().lower()
        if post_type not in scheduler.post_templates:
            post_type = "discussion"
        
        subreddit = input("Subreddit (press Enter for auto-select): ").strip()
        if not subreddit:
            subreddit = None
        
        # Generate post
        post = scheduler.generate_post_from_template(post_type, subreddit)
        
        # Show preview
        logger.info(f"\nPost preview:")
        logger.info(f"Title: {post['title']}")
        logger.info(f"Type: {post['type']}")
        logger.info(f"Subreddit: r/{post['subreddit']}")
        logger.info(f"Scheduled for: {post['scheduled_for']}")
        logger.info(f"\nContent preview:\n{post['content'][:200]}...")
        
        confirm = input("\nSchedule this post? (yes/no): ").strip().lower()
        if confirm == "yes":
            scheduler.schedule_post(post)
            logger.info("✓ Post scheduled")
        else:
            logger.info("Post cancelled")
    
    elif args.post_now:
        logger.info("\nPosting immediately...")
        if args.dry_run:
            logger.info("[dry-run] Skipping browser setup/login and submit")
            post_type = input("Post type (discussion/question/resource/experience/news): ").strip().lower() or "discussion"
            subreddit = input("Subreddit: ").strip()
            post = scheduler.generate_post_from_template(post_type, subreddit)
            logger.info(f"[dry-run] Would post to r/{post['subreddit']}: {post['title']}")
            return
        
        # Setup browser
        if not scheduler.setup_browser():
            logger.info("❌ Failed to setup browser")
            return
        
        if not scheduler.login_with_cookies():
            logger.info("❌ Login failed")
            scheduler.cleanup()
            return
        
        # Generate a post
        post_type = input("Post type (discussion/question/resource/experience/news): ").strip().lower() or "discussion"
        subreddit = input("Subreddit: ").strip()
        
        post = scheduler.generate_post_from_template(post_type, subreddit)
        post["scheduled_for"] = datetime.now().isoformat()
        
        # Post immediately
        success, result = scheduler.submit_post(post)
        
        if success:
            logger.info(f"✓ Post successful: {result}")
        else:
            logger.info(f"❌ Post failed: {result}")
        
        if scheduler.driver:
            scheduler.cleanup()
    
    elif args.view:
        logger.info("\nCurrent Schedule:")
        posts = scheduler.view_schedule(days_ahead=args.days)
        
        if not posts:
            logger.info("No posts scheduled")
        else:
            for i, post in enumerate(posts, 1):
                try:
                    scheduled_time = datetime.fromisoformat(post["scheduled_for"])
                    time_str = scheduled_time.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = post.get("scheduled_for", "Unknown")
                
                status = post.get("status", "unknown")
                status_icon = {
                    "scheduled": "⏰",
                    "posted": "✓",
                    "failed": "❌",
                    "processing": "🔄"
                }.get(status, "?")
                
                logger.info(f"{status_icon} {i}. r/{post.get('subreddit', '?')} - {post.get('type', '?')}")
                logger.info(f"   Title: {post.get('title', '?')[:60]}...")
                logger.info(f"   Time: {time_str} | Status: {status}")
                
                if post.get("error"):
                    logger.info(f"   Error: {post['error'][:80]}...")
                logger.info()
    
    elif args.summary:
        logger.info("\nSchedule Summary:")
        summary = scheduler.get_schedule_summary()
        
        logger.info(f"Total posts: {summary['total']}")
        logger.info(f"\nBy status:")
        for status, count in summary['by_status'].items():
            logger.info(f"  {status}: {count}")
        
        logger.info(f"\nBy subreddit:")
        for subreddit, count in summary['by_subreddit'].items():
            logger.info(f"  r/{subreddit}: {count}")
        
        logger.info(f"\nBy type:")
        for post_type, count in summary['by_type'].items():
            logger.info(f"  {post_type}: {count}")
        
        if summary['next_post']:
            next_time = datetime.fromisoformat(summary['next_post']['scheduled_for'])
            logger.info(f"\nNext post: {next_time.strftime('%Y-%m-%d %H:%M')}")
            logger.info(f"  r/{summary['next_post']['subreddit']} - {summary['next_post']['title'][:50]}...")
    
    elif args.start_daemon:
        if args.dry_run:
            logger.info("[dry-run] Skipping daemon start")
            return
        logger.info("\nStarting scheduler daemon...")
        scheduler.start_daemon()
        logger.info("Daemon started. Press Ctrl+C to stop.")
        
        try:
            while scheduler.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nStopping daemon...")
            scheduler.stop_daemon()
    
    elif args.stop_daemon:
        logger.info("\nStopping scheduler daemon...")
        scheduler.stop_daemon()
        logger.info("Daemon stopped")
    
    elif args.process:
        logger.info("\nProcessing due posts...")
        if not args.dry_run:
            # Setup browser
            if not scheduler.setup_browser():
                logger.info("❌ Failed to setup browser")
                return
            
            if not scheduler.login_with_cookies():
                logger.info("❌ Login failed")
                scheduler.cleanup()
                return
        
        success_count = scheduler.process_due_posts()
        logger.info(f"✓ Posted {success_count} posts")
        
        if scheduler.driver:
            scheduler.cleanup()
    
    elif args.cleanup:
        logger.info("\nCleaning up old schedule...")
        removed = scheduler.cleanup_old_schedule()
        logger.info(f"✓ Removed {removed} old posts")
    
    elif args.seed_network:
        logger.info("\nSeeding network content...")
        seeded = scheduler.seed_network_content(count_per_subreddit=args.seed_count, days=args.seed_days)
        logger.info(f"✓ Seeded {len(seeded)} subreddits")
        for sub, count in list(seeded.items())[:10]:
            logger.info(f"  r/{sub}: {count} posts")

    else:
        # Interactive mode
        logger.info("\nInteractive Mode")
        logger.info("1. Generate and schedule posts")
        logger.info("2. View schedule")
        logger.info("3. View summary")
        logger.info("4. Post immediately")
        logger.info("5. Start scheduler daemon")
        logger.info("6. Process due posts now")
        logger.info("7. Cleanup old schedule")
        logger.info("8. Exit")
        
        choice = input("\nSelect option (1-8): ").strip()
        
        if choice == "1":
            count = input("How many posts to generate? (default 5): ").strip()
            count = int(count) if count.isdigit() else 5
            days = input("Schedule over how many days? (default 7): ").strip()
            days = int(days) if days.isdigit() else 7
            
            posts = scheduler.generate_scheduled_posts(count, days)
            logger.info(f"\n✓ Generated {len(posts)} posts")
        
        elif choice == "2":
            posts = scheduler.view_schedule()
            if posts:
                for i, post in enumerate(posts[:10], 1):  # Show first 10
                    time_str = datetime.fromisoformat(post["scheduled_for"]).strftime("%m/%d %H:%M")
                    logger.info(f"{i}. [{post['type']}] r/{post['subreddit']}: {post['title'][:40]}... ({time_str})")
                if len(posts) > 10:
                    logger.info(f"... and {len(posts) - 10} more")
            else:
                logger.info("No posts scheduled")
        
        elif choice == "3":
            summary = scheduler.get_schedule_summary()
            logger.info(f"\nTotal: {summary['total']}")
            logger.info("Status breakdown:")
            for status, count in summary['by_status'].items():
                logger.info(f"  {status}: {count}")
        
        elif choice == "4":
            logger.info("\nThis will post immediately (bypass schedule).")
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm == "yes":
                # Re-run with post-now flag
                import sys
                sys.argv = [sys.argv[0], "--post-now", "--account", args.account]
                if args.headless:
                    sys.argv.append("--headless")
                main()
        
        elif choice == "5":
            logger.info("\nStarting daemon in background...")
            scheduler.start_daemon()
            input("\nDaemon started. Press Enter to return to menu (daemon continues)...")
        
        elif choice == "6":
            logger.info("\nProcessing due posts...")
            # Setup browser temporarily
            if scheduler.setup_browser() and scheduler.login_with_cookies():
                success = scheduler.process_due_posts()
                logger.info(f"✓ Posted {success} posts")
                scheduler.cleanup()
            else:
                logger.info("❌ Failed to setup/login")
        
        elif choice == "7":
            removed = scheduler.cleanup_old_schedule()
            logger.info(f"✓ Removed {removed} old posts")
        
        else:
            logger.info("Exiting")
    
    logger.info("\n" + "="*60)
    logger.info("Post scheduler complete!")
    logger.info("="*60)

if __name__ == "__main__":
    main()
