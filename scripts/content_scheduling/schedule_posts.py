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
import schedule
import threading
from microdose_study_bot.reddit_selenium.automation_base import RedditAutomationBase

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/post_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MCRDSEPostScheduler(RedditAutomationBase):
    """Schedule and post content to MCRDSE subreddits using Selenium"""
    
    def __init__(self, account_name="account1", headless=True, dry_run=False):
        """
        Initialize post scheduler
        
        Args:
            account_name: Which Reddit account to use
            headless: Run browser in background
        """
        os.environ["SELENIUM_HEADLESS"] = "1" if headless else "0"
        self.account_name = account_name
        self.headless = headless
        super().__init__(account_name=account_name, dry_run=dry_run)
        self.config = self.load_config()
        self.schedule_file = Path("scripts/content_scheduling/schedule/post_schedule.json")
        self.post_templates = self.load_templates()
        self.is_running = False
        self.scheduler_thread = None
        
    def load_config(self) -> Dict:
        """Load scheduler configuration"""
        config_path = Path("config/post_scheduling.json")
        
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Config file corrupted, using defaults")
        
        # Default configuration
        default_config = {
            "posting_settings": {
                "max_posts_per_day": 5,
                "min_time_between_posts_minutes": 60,
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
            }
        }
        
        # Save default config
        config_path.parent.mkdir(exist_ok=True, parents=True)
        config_path.write_text(json.dumps(default_config, indent=2))
        logger.info(f"Created default config at {config_path}")
        
        return default_config
    
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
    
    def load_schedule(self) -> List[Dict]:
        """Load scheduled posts from file"""
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error("Schedule file corrupted, starting with empty schedule")
                return []
        return []
    
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
        
        logger.info(f"Schedule saved with {len(schedule_data)} posts")
    
    def generate_post_from_template(self, post_type: str, subreddit: str = None) -> Dict:
        """Generate a post from templates"""
        if post_type not in self.post_templates:
            post_type = random.choice(list(self.post_templates.keys()))
        
        template_group = self.post_templates[post_type]
        template = random.choice(template_group["templates"])
        
        # Fill variables
        title = template["title"]
        content = template["content"]
        
        for var_name, options in template.get("variables", {}).items():
            replacement = random.choice(options)
            title = title.replace(f"{{{var_name}}}", replacement)
            content = content.replace(f"{{{var_name}}}", replacement)
        
        # Add MCRDSE reference (subtle)
        if random.random() < 0.3:  # 30% chance
            content += "\n\n*For research-based resources, check out the MCRDSE research portal.*"
        
        # Select subreddit if not specified
        if not subreddit:
            subreddit = self.select_subreddit_for_post(post_type)
        
        # Generate scheduled time
        scheduled_time = self.generate_scheduled_time()
        quality_score = min(1.0, max(0.0, len(content) / 500.0))
        
        post = {
            "id": f"post_{int(time.time())}_{random.randint(1000, 9999)}",
            "type": post_type,
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
            "quality_score": round(quality_score, 2)
        }
        
        return post
    
    def select_subreddit_for_post(self, post_type: str) -> str:
        """Select appropriate subreddit for post type"""
        primary = self.config["subreddit_distribution"]["primary_focus"]
        secondary = self.config["subreddit_distribution"]["secondary_focus"]
        
        # Weighted selection
        if random.random() < 0.7:  # 70% chance for primary
            return random.choice(primary)
        else:
            return random.choice(secondary)
    
    def generate_scheduled_time(self) -> datetime:
        """Generate a scheduled time based on optimal posting times"""
        now = datetime.now()
        
        # Get optimal times
        optimal_times = self.config["posting_settings"]["optimal_posting_times"]
        
        # Weighted random selection
        weights = [t["weight"] for t in optimal_times]
        times = [t["time"] for t in optimal_times]
        
        selected_time_str = random.choices(times, weights=weights, k=1)[0]
        
        # Parse time
        hour, minute = map(int, selected_time_str.split(":"))
        
        # Schedule for today or tomorrow
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If time has passed today, schedule for tomorrow
        if scheduled <= now:
            scheduled += timedelta(days=1)
        
        # Add random jitter
        if self.config["safety_settings"]["randomize_post_times"]:
            jitter = random.randint(
                -self.config["safety_settings"]["jitter_minutes"],
                self.config["safety_settings"]["jitter_minutes"]
            )
            scheduled += timedelta(minutes=jitter)
        
        # Check avoid times
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
                # Move to next available time
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
            if not self.status_tracker.can_perform_action(
                self.account_name, "posting", subreddit=subreddit, daily_limit=self.config["posting_settings"]["max_posts_per_day"]
            ):
                logger.info(f"Posting limited for {self.account_name}; skipping r/{subreddit}")
                return False, "posting_limited"
            limits = (self.activity_schedule or {}).get("rate_limits", {})
            allowed, wait_seconds = self.rate_limiter.check_rate_limit(
                self.account_name, "submit_post", limits
            )
            if not allowed:
                self.status_tracker.set_cooldown(self.account_name, "posting", wait_seconds)
                logger.info(f"Rate limited for posting; wait {wait_seconds}s")
                return False, "rate_limited"
            
            logger.info(f"Submitting post to r/{subreddit}: {title[:50]}...")
            
            # Navigate to submit page
            submit_url = f"https://old.reddit.com/r/{subreddit}/submit"
            self.driver.get(submit_url)
            time.sleep(3)
            
            # Check for CAPTCHA
            if "captcha" in self.driver.page_source.lower():
                logger.error("CAPTCHA detected!")
                if not self.headless:
                    input("Please solve CAPTCHA and press Enter...")
                    time.sleep(3)
                else:
                    return False, "CAPTCHA detected in headless mode"
            
            # Select text post
            try:
                text_button = self.driver.find_element(By.CSS_SELECTOR, "input[value='self']")
                text_button.click()
                time.sleep(1)
            except:
                logger.warning("Could not find text post button, continuing anyway")
            
            # Enter title
            title_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='title']"))
            )
            title_field.clear()
            self.human_typing(title_field, title)
            time.sleep(1)
            
            # Enter content
            content_field = self.driver.find_element(By.CSS_SELECTOR, "textarea[name='text']")
            content_field.clear()
            self.human_typing(content_field, content)
            time.sleep(2)
            
            # Add flair if required
            try:
                flair_button = self.driver.find_element(By.CSS_SELECTOR, ".flairselector-btn")
                flair_button.click()
                time.sleep(1)
                
                # Select a random flair
                flair_options = self.driver.find_elements(By.CSS_SELECTOR, ".flairselector-item")
                if flair_options:
                    random.choice(flair_options).click()
                    time.sleep(1)
            except:
                logger.debug("Could not add flair, continuing anyway")
            
            # Submit
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_button.click()
            time.sleep(5)
            
            # Check if post was successful
            if "comments" in self.driver.current_url:
                post_url = self.driver.current_url
                logger.info(f"Post successful: {post_url}")
                self.rate_limiter.record_action(self.account_name, "submit_post")
                self.status_tracker.record_post_activity(
                    self.account_name, subreddit, post_data.get("type", "unknown"), True,
                    daily_limit=self.config["posting_settings"]["max_posts_per_day"]
                )
                return True, post_url
            else:
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
                        return False, error
                
                logger.error("Post failed for unknown reason")
                self.status_tracker.record_post_activity(
                    self.account_name, subreddit, post_data.get("type", "unknown"), False,
                    daily_limit=self.config["posting_settings"]["max_posts_per_day"]
                )
                return False, "Unknown error"
            
        except Exception as e:
            logger.error(f"Error submitting post: {e}")
            self.status_tracker.record_post_activity(
                self.account_name, post_data.get("subreddit", "unknown"), post_data.get("type", "unknown"), False,
                daily_limit=self.config["posting_settings"]["max_posts_per_day"]
            )
            return False, str(e)
    
    def schedule_post(self, post_data: Dict):
        """Add a post to the schedule"""
        schedule_data = self.load_schedule()
        
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
        for i in range(num_posts):
            # Determine post type based on content mix
            post_types = list(self.config["content_strategy"]["content_mix"].keys())
            weights = list(self.config["content_strategy"]["content_mix"].values())
            post_type = random.choices(post_types, weights=weights, k=1)[0]
            
            # Generate post
            post = self.generate_post_from_template(post_type)
            
            # Schedule at appropriate time (spread out over days)
            days_offset = random.randint(0, days_ahead - 1)
            scheduled_time = datetime.fromisoformat(post["scheduled_for"])
            scheduled_time += timedelta(days=days_offset)
            
            # Random time within day
            hour = random.randint(9, 21)  # 9 AM to 9 PM
            minute = random.randint(0, 59)
            post["scheduled_for"] = scheduled_time.replace(hour=hour, minute=minute).isoformat()
            
            posts.append(post)
        
        # Add to schedule
        schedule_data = self.load_schedule()
        schedule_data.extend(posts)
        self.save_schedule(schedule_data)
        
        logger.info(f"Generated and scheduled {len(posts)} posts")
        return posts
    
    def check_due_posts(self) -> List[Dict]:
        """Check for posts that are due to be posted"""
        schedule_data = self.load_schedule()
        now = datetime.now()
        
        due_posts = []
        for post in schedule_data:
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
                success, result = self.submit_post(post)
                
                if success:
                    post["status"] = "posted"
                    post["posted_at"] = datetime.now().isoformat()
                    post["post_url"] = result
                    post["error"] = None
                    success_count += 1
                    logger.info(f"Successfully posted: {post['title'][:50]}...")
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
    
    parser = argparse.ArgumentParser(description="MCRDSE Post Scheduler - Selenium Version")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--generate", type=int, help="Generate N posts and schedule them")
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
    
    print("\n" + "="*60)
    print("MCRDSE Post Scheduler")
    print("="*60)
    
    # Initialize scheduler
    scheduler = MCRDSEPostScheduler(
        account_name=args.account,
        headless=args.headless,
        dry_run=args.dry_run,
    )
    logger.info(f"Validation summary: {scheduler.run_validations()}")
    enabled, reason = scheduler.is_feature_enabled("post_scheduling")
    if not enabled:
        print(f"Post scheduling disabled ({reason}); exiting.")
        scheduler.cleanup()
        return

    if args.validate_only:
        print(f"Validation summary: {scheduler.run_validations()}")
        scheduler.cleanup()
        return
    
    # Handle commands
    if args.generate:
        print(f"\nGenerating {args.generate} posts...")
        posts = scheduler.generate_scheduled_posts(args.generate, args.days)
        print(f"✓ Generated {len(posts)} posts")
        
        # Show what was generated
        for i, post in enumerate(posts, 1):
            scheduled_time = datetime.fromisoformat(post["scheduled_for"])
            print(f"  {i}. r/{post['subreddit']} - {post['type']} - {scheduled_time.strftime('%Y-%m-%d %H:%M')}")
    
    elif args.schedule:
        print("\nInteractive post scheduling")
        
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
        print(f"\nPost preview:")
        print(f"Title: {post['title']}")
        print(f"Type: {post['type']}")
        print(f"Subreddit: r/{post['subreddit']}")
        print(f"Scheduled for: {post['scheduled_for']}")
        print(f"\nContent preview:\n{post['content'][:200]}...")
        
        confirm = input("\nSchedule this post? (yes/no): ").strip().lower()
        if confirm == "yes":
            scheduler.schedule_post(post)
            print("✓ Post scheduled")
        else:
            print("Post cancelled")
    
    elif args.post_now:
        print("\nPosting immediately...")
        if args.dry_run:
            print("[dry-run] Skipping browser setup/login and submit")
            post_type = input("Post type (discussion/question/resource/experience/news): ").strip().lower() or "discussion"
            subreddit = input("Subreddit: ").strip()
            post = scheduler.generate_post_from_template(post_type, subreddit)
            print(f"[dry-run] Would post to r/{post['subreddit']}: {post['title']}")
            return
        
        # Setup browser
        if not scheduler.setup_browser():
            print("❌ Failed to setup browser")
            return
        
        if not scheduler.login_with_cookies():
            print("❌ Login failed")
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
            print(f"✓ Post successful: {result}")
        else:
            print(f"❌ Post failed: {result}")
        
        if scheduler.driver:
            scheduler.cleanup()
    
    elif args.view:
        print("\nCurrent Schedule:")
        posts = scheduler.view_schedule(days_ahead=args.days)
        
        if not posts:
            print("No posts scheduled")
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
                
                print(f"{status_icon} {i}. r/{post.get('subreddit', '?')} - {post.get('type', '?')}")
                print(f"   Title: {post.get('title', '?')[:60]}...")
                print(f"   Time: {time_str} | Status: {status}")
                
                if post.get("error"):
                    print(f"   Error: {post['error'][:80]}...")
                print()
    
    elif args.summary:
        print("\nSchedule Summary:")
        summary = scheduler.get_schedule_summary()
        
        print(f"Total posts: {summary['total']}")
        print(f"\nBy status:")
        for status, count in summary['by_status'].items():
            print(f"  {status}: {count}")
        
        print(f"\nBy subreddit:")
        for subreddit, count in summary['by_subreddit'].items():
            print(f"  r/{subreddit}: {count}")
        
        print(f"\nBy type:")
        for post_type, count in summary['by_type'].items():
            print(f"  {post_type}: {count}")
        
        if summary['next_post']:
            next_time = datetime.fromisoformat(summary['next_post']['scheduled_for'])
            print(f"\nNext post: {next_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"  r/{summary['next_post']['subreddit']} - {summary['next_post']['title'][:50]}...")
    
    elif args.start_daemon:
        if args.dry_run:
            print("[dry-run] Skipping daemon start")
            return
        print("\nStarting scheduler daemon...")
        scheduler.start_daemon()
        print("Daemon started. Press Ctrl+C to stop.")
        
        try:
            while scheduler.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping daemon...")
            scheduler.stop_daemon()
    
    elif args.stop_daemon:
        print("\nStopping scheduler daemon...")
        scheduler.stop_daemon()
        print("Daemon stopped")
    
    elif args.process:
        print("\nProcessing due posts...")
        if not args.dry_run:
            # Setup browser
            if not scheduler.setup_browser():
                print("❌ Failed to setup browser")
                return
            
            if not scheduler.login_with_cookies():
                print("❌ Login failed")
                scheduler.cleanup()
                return
        
        success_count = scheduler.process_due_posts()
        print(f"✓ Posted {success_count} posts")
        
        if scheduler.driver:
            scheduler.cleanup()
    
    elif args.cleanup:
        print("\nCleaning up old schedule...")
        removed = scheduler.cleanup_old_schedule()
        print(f"✓ Removed {removed} old posts")
    
    else:
        # Interactive mode
        print("\nInteractive Mode")
        print("1. Generate and schedule posts")
        print("2. View schedule")
        print("3. View summary")
        print("4. Post immediately")
        print("5. Start scheduler daemon")
        print("6. Process due posts now")
        print("7. Cleanup old schedule")
        print("8. Exit")
        
        choice = input("\nSelect option (1-8): ").strip()
        
        if choice == "1":
            count = input("How many posts to generate? (default 5): ").strip()
            count = int(count) if count.isdigit() else 5
            days = input("Schedule over how many days? (default 7): ").strip()
            days = int(days) if days.isdigit() else 7
            
            posts = scheduler.generate_scheduled_posts(count, days)
            print(f"\n✓ Generated {len(posts)} posts")
        
        elif choice == "2":
            posts = scheduler.view_schedule()
            if posts:
                for i, post in enumerate(posts[:10], 1):  # Show first 10
                    time_str = datetime.fromisoformat(post["scheduled_for"]).strftime("%m/%d %H:%M")
                    print(f"{i}. [{post['type']}] r/{post['subreddit']}: {post['title'][:40]}... ({time_str})")
                if len(posts) > 10:
                    print(f"... and {len(posts) - 10} more")
            else:
                print("No posts scheduled")
        
        elif choice == "3":
            summary = scheduler.get_schedule_summary()
            print(f"\nTotal: {summary['total']}")
            print("Status breakdown:")
            for status, count in summary['by_status'].items():
                print(f"  {status}: {count}")
        
        elif choice == "4":
            print("\nThis will post immediately (bypass schedule).")
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm == "yes":
                # Re-run with post-now flag
                import sys
                sys.argv = [sys.argv[0], "--post-now", "--account", args.account]
                if args.headless:
                    sys.argv.append("--headless")
                main()
        
        elif choice == "5":
            print("\nStarting daemon in background...")
            scheduler.start_daemon()
            input("\nDaemon started. Press Enter to return to menu (daemon continues)...")
        
        elif choice == "6":
            print("\nProcessing due posts...")
            # Setup browser temporarily
            if scheduler.setup_browser() and scheduler.login_with_cookies():
                success = scheduler.process_due_posts()
                print(f"✓ Posted {success} posts")
                scheduler.cleanup()
            else:
                print("❌ Failed to setup/login")
        
        elif choice == "7":
            removed = scheduler.cleanup_old_schedule()
            print(f"✓ Removed {removed} old posts")
        
        else:
            print("Exiting")
    
    print("\n" + "="*60)
    print("Post scheduler complete!")
    print("="*60)

if __name__ == "__main__":
    main()
