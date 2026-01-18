#!/usr/bin/env python3
"""
Enhanced night scanner with human-like behavior and multi-account support.
Runs in read-only mode during Pacific time windows.

Updated to use refactored BrowserManager and LoginManager classes.
"""

import argparse
import copy
import time
import random
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback for older Python
    ZoneInfo = None  # type: ignore

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from selenium.webdriver.common.by import By
from selenium_automation.utils.human_simulator import HumanSimulator
from selenium_automation.utils.engagement_actions import EngagementActions
from selenium_automation.login_manager import LoginManager
from selenium_automation.utils.browser_manager import BrowserManager
from shared.config_manager import ConfigManager
from shared.scan_store import (
    build_run_paths,
    build_run_scanned_path,
    load_seen,
    QUEUE_DEFAULT_PATH,
    SEEN_DEFAULT_PATH,
    SCANNED_DEFAULT_PATH,
)
from shared.console_tee import enable_console_tee
from shared.scan_shards import compute_scan_shard
from shared.logger import UnifiedLogger
from session_scanner import run_session_scan

ACTION_ALIASES = {
    "browse": "browse_subreddit",
    "scroll": "scroll_comments",
    "view_posts": "view_posts",
    "check_notifications": "check_notifications",
    "vote": "vote",
    "save": "save",
    "follow": "follow",
}
LOGIN_METHOD_ALIASES = {
    "cookies": "cookies_only",
    "cookie": "cookies_only",
    "cookies_only": "cookies_only",
    "cookie_only": "cookies_only",
    "google": "google_only",
    "google_only": "google_only",
    "oauth": "google_only",
    "oauth_only": "google_only",
    "cookies_then_google": "cookies_then_google",
    "auto": "cookies_then_google",
}


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def resolve_headless(activity_config: Dict[str, Any]) -> bool:
    headless = activity_config.get("headless")
    if headless is not None:
        return bool(headless)
    return _env_flag("SELENIUM_HEADLESS", True)


def resolve_use_undetected(activity_config: Dict[str, Any]) -> bool:
    use_undetected = activity_config.get("use_undetected")
    if use_undetected is not None:
        return bool(use_undetected)
    return _env_flag("SELENIUM_USE_UNDETECTED", True)


def normalize_action_names(actions: Any) -> List[str]:
    if isinstance(actions, str):
        actions = [a.strip() for a in actions.split(",") if a.strip()]
    if not isinstance(actions, list):
        return []
    normalized = []
    for action in actions:
        if not action:
            continue
        name = ACTION_ALIASES.get(str(action).strip(), str(action).strip())
        if name:
            normalized.append(name)
    return normalized


def normalize_login_method(value: Optional[str]) -> str:
    if not value:
        return "cookies_then_google"
    key = str(value).strip().lower()
    return LOGIN_METHOD_ALIASES.get(key, "cookies_then_google")


def in_time_window(current_time, start_time, end_time) -> bool:
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    return current_time >= start_time or current_time <= end_time


def parse_windows_arg(windows: str, tz_name: str) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for part in windows.split(","):
        part = part.strip()
        if not part or "-" not in part:
            continue
        start_s, end_s = part.split("-", 1)
        parsed.append(
            {
                "name": f"override_{start_s}_{end_s}",
                "start": start_s.strip(),
                "end": end_s.strip(),
                "timezone": tz_name,
            }
        )
    return parsed


def get_active_window(activity_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    windows = activity_config.get("time_windows") or []
    if not isinstance(windows, list) or not windows:
        return None

    default_tz = activity_config.get("timezone") or "America/Los_Angeles"
    for window in windows:
        if not isinstance(window, dict):
            continue
        tz_name = window.get("timezone") or default_tz
        tzinfo = None
        if ZoneInfo:
            try:
                tzinfo = ZoneInfo(tz_name)
            except Exception:
                tzinfo = None
        now = datetime.now(tzinfo) if tzinfo else datetime.now()
        try:
            start_time = datetime.strptime(window["start"], "%H:%M").time()
            end_time = datetime.strptime(window["end"], "%H:%M").time()
        except Exception:
            continue

        if in_time_window(now.time(), start_time, end_time):
            window_copy = dict(window)
            window_copy.setdefault("timezone", tz_name)
            return window_copy

    return None


class HumanizedNightScanner:
    def __init__(self, account_config, activity_config):
        self.account = account_config
        self.activity_config = activity_config
        self.logger = UnifiedLogger(__name__).get_logger()
        
        # Initialize managers
        self.browser_manager = None
        self.login_manager = None
        self.driver = None
        self.human_sim = None
        self.engagement = None
        
        # Initialize browser with human-like settings
        self.setup_humanized_browser()
        
    def setup_humanized_browser(self):
        """Setup browser with randomized fingerprint using BrowserManager"""
        try:
            # Create BrowserManager with account-specific settings
            headless = resolve_headless(self.activity_config)
            use_undetected = resolve_use_undetected(self.activity_config)
            os.environ["USE_TOR_PROXY"] = "1"
            self.browser_manager = BrowserManager(headless=headless)
            
            # Get driver with optional undetected Chrome
            self.driver = self.browser_manager.create_driver(use_undetected=use_undetected)
            
            if not self.driver:
                self.logger.error("Failed to create driver")
                return
            
            # Set custom fingerprint from account config
            self.set_custom_fingerprint()
            
            # Create LoginManager
            self.login_manager = LoginManager()
            self.login_manager.driver = self.driver  # Set the driver we created
            self.login_manager.browser_manager = self.browser_manager  # Share browser manager
            
            # Initialize human simulator and engagement actions
            self.human_sim = HumanSimulator(self.driver, browser_manager=self.browser_manager)
            self.engagement = EngagementActions(self.driver, self.activity_config, browser_manager=self.browser_manager)
            
            self.logger.info(f"Browser setup complete for {self.account.get('name', 'unknown')}")
            
        except Exception as e:
            self.logger.error(f"Failed to setup browser: {e}")
            raise

    def _login_with_cookies(self, cookie_file: str) -> bool:
        if not self.login_manager:
            return False
        if not cookie_file:
            self.logger.warning("Cookie login skipped: missing cookie file path.")
            return False
        cookie_path = Path(cookie_file)
        if not cookie_path.exists():
            self.logger.warning(f"Cookie login skipped: file not found at {cookie_file}")
            return False
        headless = bool(self.browser_manager.headless) if self.browser_manager else True
        return self.login_manager.login_with_cookies(cookie_file=cookie_file, headless=headless)

    def _login_with_google(self, google_email: str, google_password: str) -> bool:
        if not self.login_manager:
            return False
        if not google_email or not google_password:
            self.logger.warning("Google OAuth skipped: missing email/password.")
            return False
        headless = bool(self.browser_manager.headless) if self.browser_manager else True
        if headless:
            self.logger.warning("Google OAuth in headless mode may fail; set headless=false for interactive login.")
        return self.login_manager.login_with_google(
            google_email=google_email,
            google_password=google_password,
            headless=headless,
        )

    def login(self, cookie_file: str, google_email: str, google_password: str, login_method: Optional[str] = None) -> bool:
        method = normalize_login_method(login_method)
        if method == "cookies_only":
            return self._login_with_cookies(cookie_file)
        if method == "google_only":
            return self._login_with_google(google_email, google_password)

        if self._login_with_cookies(cookie_file):
            return True
        return self._login_with_google(google_email, google_password)
    
    def set_custom_fingerprint(self):
        """Set custom browser fingerprint from account config"""
        try:
            # Get fingerprint settings from account config
            fingerprint = self.account.get('browser_fingerprint', {})
            
            # Set user agent if specified
            user_agent = fingerprint.get('user_agent')
            if user_agent and self.browser_manager:
                self.browser_manager.user_agents = [user_agent]
            
            # Set viewport if specified
            viewport = fingerprint.get('viewport')
            if viewport and self.driver:
                try:
                    width, height = map(int, viewport.split('x'))
                    self.driver.set_window_size(width, height)
                except:
                    pass
            
            # Apply additional randomization
            if self.browser_manager:
                self.browser_manager.randomize_fingerprint(self.driver)
                
        except Exception as e:
            self.logger.warning(f"Could not set custom fingerprint: {e}")
    
    def perform_activity_session(self):
        """Execute one session of human-like activity"""
        try:
            # Get session settings
            session_length = random.randint(
                self.activity_config['randomization']['session_length_minutes']['min'],
                self.activity_config['randomization']['session_length_minutes']['max']
            )
            
            start_time = time.time()
            actions_performed = {
                'votes': 0,
                'saves': 0,
                'follows': 0,
                'posts_viewed': 0,
                'subreddits_browsed': 0
            }
            
            # Load target subreddits (allow per-account sharding)
            subreddits = self.account.get("subreddits")
            if not isinstance(subreddits, list) or not subreddits:
                config_manager = ConfigManager()
                subreddits = config_manager.load_json('config/subreddits.json')
            if not isinstance(subreddits, list):
                subreddits = []
            
            self.logger.info(f"Starting {session_length} minute session for {self.account.get('name')}")
            
            while time.time() - start_time < session_length * 60:
                # Choose random activity based on mix
                activity = self.choose_random_activity()
                
                if activity == 'browse_subreddit':
                    if subreddits:
                        subreddit = random.choice(subreddits)
                        self.logger.info(f"Browsing r/{subreddit}")
                        self.browse_subreddit_humanly(subreddit)
                        actions_performed['subreddits_browsed'] += 1
                
                elif activity == 'view_posts':
                    self.view_random_posts()
                    actions_performed['posts_viewed'] += 1

                elif activity == 'scroll_comments':
                    self.scroll_comments()
                    
                elif activity == 'vote' and actions_performed['votes'] < self.activity_config['safety_limits']['max_votes_per_session']:
                    if self.safe_vote():
                        actions_performed['votes'] += 1
                        self.logger.debug(f"Voted (total: {actions_performed['votes']})")
                
                elif activity == 'save' and actions_performed['saves'] < self.activity_config['safety_limits']['max_saves_per_session']:
                    if self.safe_save():
                        actions_performed['saves'] += 1
                        self.logger.debug(f"Saved post (total: {actions_performed['saves']})")
                
                elif activity == 'follow' and actions_performed['follows'] < self.activity_config['safety_limits']['max_follows_per_session']:
                    if self.safe_follow():
                        actions_performed['follows'] += 1
                        self.logger.debug(f"Followed user (total: {actions_performed['follows']})")
                
                elif activity == 'check_notifications':
                    self.check_notifications()
                
                # Random delay between actions
                self.random_delay()
            
            self.logger.info(f"Session complete. Actions: {actions_performed}")
            return actions_performed
            
        except Exception as e:
            self.logger.error(f"Error during activity session: {e}")
            return None
    
    def browse_subreddit_humanly(self, subreddit_name):
        """Browse a subreddit with human-like behavior"""
        try:
            # Navigate to subreddit
            self.driver.get(f"https://old.reddit.com/r/{subreddit_name}")
            
            # Human-like delay
            self.browser_manager.add_human_delay(2, 4)
            
            # Random scrolling
            scrolls = random.randint(2, 5)
            for _ in range(scrolls):
                pixels = random.randint(300, 800)
                self.browser_manager.scroll_down(self.driver, pixels)
                self.browser_manager.add_human_delay(1, 3)
            
            # Occasionally view a post (30% chance)
            if random.random() > 0.7:
                self.view_random_post_in_current_subreddit()
            
        except Exception as e:
            self.logger.warning(f"Error browsing subreddit {subreddit_name}: {e}")
    
    def view_random_posts(self):
        """Find and view random posts on current page"""
        try:
            posts = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")
            if posts:
                post = random.choice(posts[:min(10, len(posts))])
                target = None
                for selector in ("a.title", "a.comments"):
                    try:
                        target = post.find_element(By.CSS_SELECTOR, selector)
                        break
                    except Exception:
                        continue
                target = target or post

                # Human-like reading sequence
                if self.human_sim:
                    self.human_sim.read_post_sequence(target)
                else:
                    # Fallback
                    self.browser_manager.safe_click(self.driver, target)
                    self.browser_manager.add_human_delay(3, 8)
                    self.driver.back()
                    self.browser_manager.add_human_delay(1, 2)
                
                return True
            return False
            
        except Exception as e:
            self.logger.debug(f"Error viewing random post: {e}")
            return False

    def scroll_comments(self):
        """Scroll through comments section if present"""
        try:
            if self.human_sim:
                self.human_sim.view_comments_section()
                return True
            # Fallback: simple scroll
            for _ in range(random.randint(2, 4)):
                if self.browser_manager and self.driver:
                    self.browser_manager.scroll_down(self.driver, random.randint(250, 600))
                    self.browser_manager.add_human_delay(0.8, 1.6)
            return True
        except Exception as e:
            self.logger.debug(f"Error scrolling comments: {e}")
            return False
    
    def view_random_post_in_current_subreddit(self):
        """View a random post in the current subreddit"""
        try:
            posts = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")
            if posts:
                post = random.choice(posts[:5])  # Only from top 5
                target = None
                for selector in ("a.title", "a.comments"):
                    try:
                        target = post.find_element(By.CSS_SELECTOR, selector)
                        break
                    except Exception:
                        continue
                target = target or post
                self.browser_manager.safe_click(self.driver, target)
                self.browser_manager.add_human_delay(3, 6)
                
                # Scroll through the post
                self.browser_manager.scroll_down(self.driver, random.randint(200, 600))
                self.browser_manager.add_human_delay(1, 2)
                
                # Go back
                self.driver.back()
                self.browser_manager.add_human_delay(1, 2)
                return True
        except Exception as e:
            self.logger.debug(f"Error viewing post: {e}")
        
        return False
    
    def safe_vote(self):
        """Safely upvote a random post (if enabled)"""
        try:
            # Check if voting is allowed in config
            if not self.activity_config.get('allow_voting', False):
                return False
            
            # Find upvote buttons
            upvote_buttons = self.driver.find_elements(By.CSS_SELECTOR, "div.thing div.arrow.up")
            upvote_buttons = [
                btn for btn in upvote_buttons
                if "upmod" not in (btn.get_attribute("class") or "")
            ]
            if upvote_buttons:
                # Random chance to vote (30%)
                if random.random() > 0.7:
                    button = random.choice(upvote_buttons[:3])  # Only from top 3
                    self.browser_manager.safe_click(self.driver, button)
                    self.browser_manager.add_human_delay(0.5, 1)
                    return True
        except Exception as e:
            self.logger.debug(f"Error voting: {e}")
        
        return False
    
    def safe_save(self):
        """Safely save a random post (if enabled)"""
        try:
            # Check if saving is allowed
            if not self.activity_config.get('allow_saving', False):
                return False
            if not self.engagement:
                return False

            posts = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")
            if not posts:
                return False
            random.shuffle(posts)
            for post in posts[:5]:
                if self.engagement.save_post(post):
                    self.browser_manager.add_human_delay(0.7, 1.4)
                    return True
            return False
            
        except Exception as e:
            self.logger.debug(f"Error saving: {e}")
            return False
    
    def safe_follow(self):
        """Safely follow a random user (if enabled)"""
        try:
            # Check if following is allowed
            if not self.activity_config.get('allow_following', False):
                return False
            if not self.engagement:
                return False

            author_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.thing a.author")
            authors = []
            for element in author_elements:
                name = (element.text or "").strip()
                if not name:
                    continue
                if name.lower() in ("[deleted]", "deleted"):
                    continue
                authors.append(name)
            if not authors:
                return False

            random.shuffle(authors)
            author = authors[0]
            current_url = ""
            try:
                current_url = self.driver.current_url
            except Exception:
                current_url = ""

            followed = self.engagement.follow_user(author)
            self.browser_manager.add_human_delay(1, 2)
            if current_url:
                self.driver.get(current_url)
                self.browser_manager.add_human_delay(1, 2)
            return followed
            
        except Exception as e:
            self.logger.debug(f"Error following: {e}")
            return False
    
    def check_notifications(self):
        """Check notifications (if enabled)"""
        try:
            # Check if notifications checking is allowed
            if not self.activity_config.get('allow_notifications_check', True):
                return
            self.driver.get("https://old.reddit.com/message/unread")
            self.browser_manager.add_human_delay(2, 4)
            self.driver.back()
            self.browser_manager.add_human_delay(1, 2)
                    
        except Exception as e:
            self.logger.debug(f"Error checking notifications: {e}")
    
    def random_delay(self):
        """Realistic delay between actions"""
        try:
            mean_delay = self.activity_config['randomization']['delay_between_actions']['mean_seconds']
            delay = random.expovariate(1.0 / mean_delay)
            delay = min(delay, self.activity_config['randomization']['delay_between_actions']['max_seconds'])
            delay = max(delay, self.activity_config['randomization']['delay_between_actions']['min_seconds'])
            
            if self.browser_manager:
                self.browser_manager.add_human_delay(delay, delay)  # Use min=max for exact delay
            else:
                time.sleep(delay)
                
        except Exception as e:
            # Fallback to random delay
            time.sleep(random.uniform(2, 5))
    
    def choose_random_activity(self):
        """Choose activity based on weighted distribution"""
        try:
            activities = list(self.activity_config['activity_mix'].keys())
            weights = list(self.activity_config['activity_mix'].values())
            return random.choices(activities, weights=weights)[0]
        except:
            # Default activities if config is wrong
            default_activities = ['browse_subreddit', 'view_posts', 'check_notifications']
            return random.choice(default_activities)
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if self.driver and self.browser_manager:
                self.browser_manager.close_driver(self.driver)
            elif self.driver:
                self.driver.quit()
        except:
            pass


class MultiAccountOrchestrator:
    def __init__(self, activity_config: Optional[Dict[str, Any]] = None, active_window: Optional[Dict[str, Any]] = None):
        self.config_manager = ConfigManager()
        self.logger = UnifiedLogger("MultiAccountOrchestrator").get_logger()
        self.base_activity_config = activity_config or self.config_manager.load_json('config/activity_schedule.json') or {}
        self.active_window = active_window
        self.scan_config = self.config_manager.load_all()
        self.scan_schedule = self.config_manager.load_json("config/schedule.json") or {}
        self.accounts = self.load_accounts()
        self.run_id = os.getenv("RUN_ID") or datetime.now().isoformat()
        _, self.run_queue_path, self.run_summary_path = build_run_paths(self.run_id)
        self.run_scanned_path = build_run_scanned_path(self.run_id)
        self.run_summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path = Path(os.getenv("SCAN_QUEUE_PATH", self.scan_schedule.get("queue_path", QUEUE_DEFAULT_PATH)))
        self.summary_path = Path(os.getenv("SCAN_SUMMARY_PATH", self.scan_schedule.get("summary_path", "logs/night_scan_summary.csv")))
        self.scanned_path = Path(os.getenv("SCANNED_POSTS_PATH", SCANNED_DEFAULT_PATH))
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen_path = Path(os.getenv("SEEN_POSTS_PATH", SEEN_DEFAULT_PATH))
        self.seen = set(load_seen(self.seen_path))
        self.scan_limit = int(os.getenv("SCAN_LIMIT", self.scan_schedule.get("limit", 25)))
        self.keywords = self.scan_config.bot_settings.get("keywords") or self.scan_config.default_keywords
        schedule_tz = self.scan_schedule.get("timezone") or "America/Los_Angeles"
        if self.active_window and self.active_window.get("timezone"):
            schedule_tz = self.active_window["timezone"]
        self.tz_name = schedule_tz
        if self.active_window and self.active_window.get("start") and self.active_window.get("end"):
            self.scan_window = f"{self.active_window['start']}-{self.active_window['end']}"
        else:
            self.scan_window = "manual"
    
    def load_accounts(self):
        """Load accounts from config"""
        try:
            accounts = self.config_manager.load_json('config/accounts.json')
            if not isinstance(accounts, list):
                accounts = []

            # Load credentials from environment variables
            for account in accounts:
                email_var = account.get('email_env_var')
                password_var = account.get('password_env_var')
                google_email_var = account.get('google_email_env_var') or email_var
                google_password_var = account.get('google_password_env_var') or password_var
                
                if email_var:
                    account['email'] = os.getenv(email_var, '')
                if password_var:
                    account['password'] = os.getenv(password_var, '')
                if google_email_var:
                    account['google_email'] = os.getenv(google_email_var, '')
                if google_password_var:
                    account['google_password'] = os.getenv(google_password_var, '')

            names_env = os.getenv("HUMANIZED_ACCOUNT_NAMES") or os.getenv("SCAN_ACCOUNT_NAMES") or ""
            names = {name.strip() for name in names_env.split(",") if name.strip()}
            if names:
                filtered = [account for account in accounts if account.get("name") in names]
                if not filtered:
                    self.logger.warning(f"No accounts matched HUMANIZED_ACCOUNT_NAMES={names_env}")
                else:
                    accounts = filtered

            return accounts
            
        except Exception as e:
            self.logger.error(f"Failed to load accounts: {e}")
            return []
    
    def _apply_profile(self, config: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
        if not profile_name:
            return config
        profiles = config.get("profiles", {})
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            return config

        merged = copy.deepcopy(config)
        for key in (
            "activity_mix",
            "randomization",
            "safety_limits",
            "allow_voting",
            "allow_saving",
            "allow_following",
            "allow_notifications_check",
            "headless",
            "use_undetected",
        ):
            if key in profile:
                override = profile[key]
                if isinstance(merged.get(key), dict) and isinstance(override, dict):
                    merged[key].update(override)
                else:
                    merged[key] = override
        return merged

    def _filter_activity_mix(self, config: Dict[str, Any]) -> Dict[str, Any]:
        base_mix = config.get("activity_mix", {})
        mix = dict(base_mix) if isinstance(base_mix, dict) else {}

        if not config.get("allow_voting", False):
            mix.pop("vote", None)
        if not config.get("allow_saving", False):
            mix.pop("save", None)
        if not config.get("allow_following", False):
            mix.pop("follow", None)
        if not config.get("allow_notifications_check", True):
            mix.pop("check_notifications", None)

        if self.active_window and self.active_window.get("actions"):
            allowed = set(normalize_action_names(self.active_window.get("actions", [])))
            if allowed:
                mix = {key: value for key, value in mix.items() if key in allowed}

        if not mix and isinstance(base_mix, dict):
            mix = dict(base_mix)

        config["activity_mix"] = mix
        return config

    def build_activity_config(self, profile_name: str) -> Dict[str, Any]:
        config = copy.deepcopy(self.base_activity_config) if self.base_activity_config else {}
        config = self._apply_profile(config, profile_name)
        config = self._filter_activity_mix(config)
        return config

    def run_rotation(self):
        """Run sessions for all accounts in rotation"""
        if not self.accounts:
            self.logger.error("No accounts configured")
            return

        total_accounts = len(self.accounts)
        for idx, account in enumerate(self.accounts):
            scanner = None
            try:
                self.logger.info(f"Starting session for {account.get('name', 'unknown')}")
                
                # Create scanner
                profile_name = account.get("activity_profile", "") or ""
                activity_config = self.build_activity_config(profile_name)
                scanner = HumanizedNightScanner(account, activity_config)
                
                if not scanner.driver:
                    self.logger.error(f"Failed to create browser for {account.get('name')}")
                    continue
                
                cookie_file = account.get('cookies_path', 'cookies.pkl')
                google_email = account.get('google_email', '')
                google_password = account.get('google_password', '')
                login_method = account.get("login_method") or activity_config.get("login_method") or "cookies_then_google"

                if scanner.login(cookie_file, google_email, google_password, login_method):
                    self.logger.info(f"Logged in to {account.get('name')}")
                    
                    # Perform activity session
                    actions = scanner.perform_activity_session()
                    
                    if actions:
                        self.logger.info(f"Session completed for {account.get('name')}: {actions}")

                    account_subreddits = account.get("subreddits") or (
                        self.scan_config.bot_settings.get("subreddits") or self.scan_config.default_subreddits
                    )

                    default_sort, default_time, default_offset = compute_scan_shard(idx, total_accounts)
                    sort = account.get("scan_sort") or default_sort
                    if "scan_time_range" in account:
                        time_range = account.get("scan_time_range") or ""
                    else:
                        time_range = default_time or ""
                    if "scan_page_offset" in account:
                        page_offset = int(account.get("scan_page_offset") or 0)
                    else:
                        page_offset = default_offset
                    self.logger.info(
                        f"Scan shard for {account.get('name', '')}: sort={sort}, time={time_range or 'none'}, page_offset={page_offset}"
                    )
                    self.logger.info(
                        f"Subreddits for {account.get('name', '')}: {', '.join(account_subreddits)}"
                    )
                    run_session_scan(
                        driver=scanner.driver,
                        browser_manager=scanner.browser_manager,
                        login_manager=scanner.login_manager,
                        config=self.scan_config,
                        subreddits=account_subreddits,
                        keywords=self.keywords,
                        limit=self.scan_limit,
                        queue_path=self.queue_path,
                        summary_path=self.summary_path,
                        run_queue_path=self.run_queue_path,
                        run_summary_path=self.run_summary_path,
                        scanned_path=self.scanned_path,
                        run_scanned_path=self.run_scanned_path,
                        seen=self.seen,
                        seen_path=self.seen_path,
                        run_id=self.run_id,
                        account=account.get("name", ""),
                        tz_name=self.tz_name,
                        scan_window=self.scan_window,
                        mode="selenium",
                        sort=sort,
                        time_range=time_range or "",
                        page_offset=page_offset,
                    )
                    
                    # Save cookies for next time
                    if scanner.login_manager and cookie_file:
                        scanner.login_manager.save_login_cookies(cookie_file)
                    
                else:
                    self.logger.warning(f"Could not login to {account.get('name')}")
                
                # Cleanup
                scanner.cleanup()
                
                # Wait between accounts (5-15 minutes)
                if account != self.accounts[-1]:  # Don't wait after last account
                    wait_time = random.randint(300, 900)
                    self.logger.info(f"Waiting {wait_time//60} minutes before next account")
                    time.sleep(wait_time)
                
            except Exception as e:
                self.logger.error(f"Error with account {account.get('name', 'unknown')}: {e}")
                if scanner:
                    scanner.cleanup()
                continue


def check_time_window(activity_config: Optional[Dict[str, Any]] = None) -> bool:
    """Check if current time is within scheduled windows."""
    try:
        config = activity_config or ConfigManager().load_json('config/activity_schedule.json') or {}
        return get_active_window(config) is not None
    except Exception as e:
        print(f"Error checking time window: {e}")
        return False


if __name__ == "__main__":
    enable_console_tee(os.getenv("CONSOLE_LOG_PATH", "logs/selenium_automation.log"))
    print("=" * 60)
    print("Humanized Night Scanner")
    print("=" * 60)

    parser = argparse.ArgumentParser(description="Humanized night scanner")
    parser.add_argument(
        "--windows",
        default=os.getenv("HUMANIZED_WINDOWS", ""),
        help="Override windows (HH:MM-HH:MM, comma-separated).",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("SCAN_TIMEZONE", "America/Los_Angeles"),
        help="IANA timezone name.",
    )
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Run regardless of schedule (sets window to 00:00-23:59).",
    )
    args = parser.parse_args()

    force_run_env = os.getenv("HUMANIZED_FORCE_RUN", "").lower() in ("1", "true", "yes")

    # Check time window
    os.environ["ENABLE_POSTING"] = "0"
    os.environ["USE_LLM"] = "0"

    config_manager = ConfigManager()
    activity_config = config_manager.load_json('config/activity_schedule.json') or {}
    if args.windows:
        activity_config["time_windows"] = parse_windows_arg(args.windows, args.timezone)
        activity_config["timezone"] = args.timezone

    if args.force_run or force_run_env:
        active_window = {
            "name": "force_run",
            "start": "00:00",
            "end": "23:59",
            "timezone": args.timezone,
        }
    else:
        active_window = get_active_window(activity_config)

    if active_window:
        print("✓ In scheduled time window. Starting scanner...")
        
        try:
            orchestrator = MultiAccountOrchestrator(
                activity_config=activity_config,
                active_window=active_window,
            )
            
            if orchestrator.accounts:
                print(f"Found {len(orchestrator.accounts)} accounts")
                orchestrator.run_rotation()
                print("✓ Rotation complete")
            else:
                print("✗ No accounts configured")
                
        except Exception as e:
            print(f"✗ Error running orchestrator: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("✗ Not in scheduled time window. Exiting.")
    
    print("=" * 60)
