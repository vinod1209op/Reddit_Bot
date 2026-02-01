#!/usr/bin/env python3
"""
Purpose: Scheduled multi-account scanner with human-like browsing behavior
         and advanced anti-detection measures.
"""

import argparse
import copy
import time
import random
import os
import sys
import json
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# Constants
ROOT = Path(__file__).resolve().parents[2]

from selenium.webdriver.common.by import By
from microdose_study_bot.reddit_selenium.utils.human_simulator import HumanSimulator
from microdose_study_bot.reddit_selenium.utils.engagement_actions import EngagementActions
from microdose_study_bot.reddit_selenium.utils.anti_detection.detection_evasion import DetectionEvasionCoordinator
from microdose_study_bot.reddit_selenium.login import LoginManager
from microdose_study_bot.reddit_selenium.utils.browser_manager import BrowserManager
from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.safety.policies import enforce_readonly_env
from microdose_study_bot.core.utils.http import get_with_retry
from microdose_study_bot.core.storage.state_cleanup import cleanup_state
from microdose_study_bot.core.storage.scan_store import (
    build_run_paths,
    build_run_scanned_path,
    load_seen,
    QUEUE_DEFAULT_PATH,
    SEEN_DEFAULT_PATH,
    SCANNED_DEFAULT_PATH,
)
from microdose_study_bot.core.utils.console_tee import enable_console_tee
from microdose_study_bot.core.utils.scan_shards import compute_scan_shard
from microdose_study_bot.core.utils.vpn_manager import VPNManager
from microdose_study_bot.core.logging import UnifiedLogger
from microdose_study_bot.core.rate_limiter import RateLimiter
from microdose_study_bot.core.account_status import AccountStatusTracker
from scripts.runners.session_scanner import run_session_scan

logger = UnifiedLogger(__name__).get_logger()

SUBREDDIT_COVERAGE_PATH = Path("logs/subreddit_coverage.json")
SUBREDDIT_COVERAGE_WINDOW_DAYS = 7

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

# Mapping from scanner activities to detection evasion action types
ACTIVITY_TO_ACTION_TYPE = {
    'browse_subreddit': 'browse',
    'view_posts': 'view',
    'scroll_comments': 'scroll',
    'vote': 'vote',
    'save': 'save',
    'follow': 'follow',
    'check_notifications': 'navigation',
    'login': 'login',
    'tor_rotation': 'navigation'
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

def _rate_from_config(value: Any, default_min: float, default_max: float) -> float:
    if isinstance(value, dict):
        try:
            min_val = float(value.get("min", default_min))
            max_val = float(value.get("max", default_max))
            min_val = max(0.0, min(min_val, 1.0))
            max_val = max(min_val, min(max_val, 1.0))
            return random.uniform(min_val, max_val)
        except Exception:
            return random.uniform(default_min, default_max)
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    return random.uniform(default_min, default_max)

def _jitter_activity_mix(
    base_mix: Dict[str, float],
    jitter_pct: float = 0.5,
    floor: float = 1.0,
) -> Dict[str, float]:
    """Randomize activity weights heavily while preserving available actions."""
    if not base_mix:
        return {}
    jitter_pct = max(0.0, float(jitter_pct))
    randomized: Dict[str, float] = {}
    for key, weight in base_mix.items():
        try:
            w = float(weight)
        except Exception:
            w = 0.0
        jitter = random.uniform(1.0 - jitter_pct, 1.0 + jitter_pct)
        randomized[key] = max(floor, w * jitter)
    return randomized

def in_time_window(current_time, start_time, end_time) -> bool:
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    return current_time >= start_time or current_time <= end_time

def _vpn_enabled() -> bool:
    if not _env_flag("USE_VPN", False):
        return False
    if _env_flag("CI", False) and not _env_flag("USE_VPN_IN_CI", False):
        return False
    return True

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

def _load_subreddit_coverage(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}

def _save_subreddit_coverage(path: Path, coverage: Dict[str, str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(coverage, f, indent=2)
    except Exception:
        pass

def _days_since(timestamp: Optional[str]) -> int:
    if not timestamp:
        return 9999
    try:
        last = datetime.fromisoformat(timestamp)
        delta = datetime.utcnow() - last.replace(tzinfo=None)
        return max(int(delta.total_seconds() // 86400), 0)
    except Exception:
        return 9999

def select_subreddits_for_run(
    subreddits: Sequence[str],
    coverage: Dict[str, str],
    window_days: int,
) -> List[str]:
    if not subreddits:
        return []

    unique = [s for s in subreddits if s]
    if not unique:
        return []

    max_per_run = random.randint(1, len(unique))

    must_include = []
    for sub in unique:
        days = _days_since(coverage.get(sub))
        if days >= window_days:
            must_include.append(sub)

    if len(must_include) > max_per_run:
        must_include = random.sample(must_include, k=max_per_run)

    remaining = [s for s in unique if s not in must_include]
    weighted = []
    for sub in remaining:
        days = _days_since(coverage.get(sub))
        weight = 1.0 + min(days, window_days)
        key = random.random() ** (1.0 / weight)
        weighted.append((key, sub))
    weighted.sort(reverse=True)
    take = max(0, max_per_run - len(must_include))
    selected = must_include + [sub for _, sub in weighted[:take]]
    random.shuffle(selected)
    return selected

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
        self.rate_limiter = RateLimiter()
        
        # Track session state
        self.session_start_time = None
        self.action_count = 0
        self.last_tor_rotation_time = None
        
        # Initialize browser with human-like settings
        self.setup_humanized_browser()
        self.humanization_metrics = {
            'navigation_errors': 0,
            'tor_rotations': 0,
            'mouse_movements': 0
        }

        # Initialize Detection Evasion Coordinator
        self.detection_evasion = DetectionEvasionCoordinator(
            account_name=self.account.get('name', 'unknown'),
            account_config=self.account,
            activity_config=self.activity_config
        )
        
        self.logger.info(f"HumanizedNightScanner initialized for {self.account.get('name', 'unknown')} with anti-detection measures")
    
    def setup_humanized_browser(self):
        """Setup browser with randomized fingerprint using BrowserManager"""
        try:
            # Create BrowserManager with account-specific settings
            headless = resolve_headless(self.activity_config)
            use_undetected = resolve_use_undetected(self.activity_config)
            if self.account.get("use_tor_proxy") is not False:
                os.environ["USE_TOR_PROXY"] = "1"
            tor_port = self.account.get("tor_socks_port")
            if tor_port:
                os.environ["TOR_SOCKS_PORT"] = str(tor_port)
                self._log_tor_exit_ip(tor_port)
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
            self.login_manager.driver = self.driver
            self.login_manager.browser_manager = self.browser_manager
            
            # Initialize human simulator and engagement actions
            self.human_sim = HumanSimulator(self.driver, browser_manager=self.browser_manager)
            self.engagement = EngagementActions(self.driver, self.activity_config, browser_manager=self.browser_manager)
            
            self.logger.info(f"Browser setup complete for {self.account.get('name', 'unknown')}")
            
        except Exception as e:
            self.logger.error(f"Failed to setup browser: {e}")
            raise

    def _log_tor_exit_ip(self, tor_port: int) -> Optional[str]:
        """Log Tor exit IP for the given port and return it."""
        account_name = self.account.get("name", "unknown")
        proxy_url = f"socks5h://127.0.0.1:{tor_port}"
        try:
            response = get_with_retry(
                "https://check.torproject.org/api/ip",
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=10,
            )
            response.raise_for_status()
            ip = response.json().get("IP", "unknown")
            self.logger.info(f"🌐 Tor exit for {account_name} (port {tor_port}): {ip}")
            return ip
        except Exception as exc:
            self.logger.warning(
                f"Tor exit lookup failed for {account_name} (port {tor_port}): {exc}"
            )
            return None

    def rotate_tor_circuit(self):
        """Send NEWNYM command to Tor control port to get new IP"""
        tor_port = self.account.get("tor_socks_port")
        if not tor_port:
            return False
        
        control_port = tor_port + 100
        account_name = self.account.get("name", "unknown")
        
        self.logger.info(f"🔄 Rotating Tor circuit for {account_name}...")
        before_ip = self._log_tor_exit_ip(tor_port)
        
        try:
            tor_data_dir = os.getenv("TOR_DATA_DIR", f"/tmp/tor_{tor_port}")
            cookie_file = os.path.join(tor_data_dir, "control_auth_cookie")
            
            if not os.path.exists(cookie_file):
                self.logger.warning(f"Tor control cookie not found at {cookie_file}")
                return False
            
            with open(cookie_file, "rb") as f:
                cookie_hex = f.read().hex()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect(("127.0.0.1", control_port))
            
            sock.send(f"AUTHENTICATE {cookie_hex}\r\n".encode())
            response = sock.recv(1024).decode()
            
            if "250" not in response:
                self.logger.error(f"Tor authentication failed: {response}")
                sock.close()
                return False
            
            sock.send(b"SIGNAL NEWNYM\r\n")
            response = sock.recv(1024).decode()
            
            if "250" not in response:
                self.logger.error(f"Tor NEWNYM failed: {response}")
                sock.close()
                return False
            
            sock.close()
            self.logger.info(f"✅ NEWNYM requested for {account_name}")
            
            time.sleep(5)
            
            after_ip = self._log_tor_exit_ip(tor_port)
            if before_ip and after_ip:
                if before_ip == after_ip:
                    self.logger.warning(
                        f"⚠️ Tor IP unchanged for {account_name}: {before_ip}"
                    )
                else:
                    self.logger.info(
                        f"✅ Tor IP changed for {account_name}: {before_ip} -> {after_ip}"
                    )
            else:
                self.logger.info(f"✅ Tor circuit rotated for {account_name}")
            
            self.last_tor_rotation_time = time.time()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to rotate Tor circuit: {e}")
            return False

    def should_rotate_tor(self) -> bool:
        """Determine if we should rotate Tor circuit based on config and randomness"""
        tor_port = self.account.get("tor_socks_port")
        if not tor_port:
            return False
        
        humanization_config = self.activity_config.get("humanization", {})
        if not humanization_config.get("enable_tor_rotation", True):
            return False

        if self.session_start_time:
            if time.time() - self.session_start_time < 600:
                return False
        
        min_interval_minutes = float(humanization_config.get("tor_rotation_interval_minutes", 10) or 10)
        min_interval_seconds = max(600.0, min_interval_minutes * 60.0)
        if self.last_tor_rotation_time:
            time_since_last = time.time() - self.last_tor_rotation_time
            if time_since_last < min_interval_seconds:
                return False
        
        chance = _rate_from_config(
            humanization_config.get("tor_rotation_chance_per_action"),
            0.10,
            0.15,
        )
        if random.random() < chance:
            return True
        
        if self.action_count > 0 and self.action_count % 20 == 0:
            return True
        
        return False

    def _login_with_cookies(self, cookie_file: str):
        """Login with cookies and return (success, status) tuple."""
        if not self.login_manager:
            return False, "login_manager_not_initialized"
        if not cookie_file:
            self.logger.warning("Cookie login skipped: missing cookie file path.")
            return False, "missing_cookie_file"
        
        cookie_path = Path(cookie_file)
        if not cookie_path.exists():
            self.logger.warning(f"Cookie login skipped: file not found at {cookie_file}")
            return False, "cookie_file_not_found"
        
        headless = bool(self.browser_manager.headless) if self.browser_manager else True
        return self.login_manager.login_with_cookies(cookie_file=cookie_file, headless=headless)

    def _login_with_google(self, google_email: str, google_password: str):
        """Login with Google and return (success, status) tuple."""
        if not self.login_manager:
            return False, "login_manager_not_initialized"
        if not google_email or not google_password:
            self.logger.warning("Google OAuth skipped: missing email/password.")
            return False, "missing_credentials"
        
        headless = bool(self.browser_manager.headless) if self.browser_manager else True
        if headless:
            self.logger.warning("Google OAuth in headless mode may fail; set headless=false for interactive login.")
        
        return self.login_manager.login_with_google(
            google_email=google_email,
            google_password=google_password,
            headless=headless,
        )

    def login(self, cookie_file: str, google_email: str, google_password: str, login_method: Optional[str] = None):
        """
        Login using specified method and return (success, status) tuple.
        """
        method = normalize_login_method(login_method)
        
        # Record login action with anti-detection system
        if self.detection_evasion:
            self.detection_evasion.record_action("login", {
                "method": method,
                "timestamp": datetime.now().isoformat()
            })
        
        if method == "cookies_only":
            success, status = self._login_with_cookies(cookie_file)
        elif method == "google_only":
            success, status = self._login_with_google(google_email, google_password)
        else:
            success, status = self._login_with_cookies(cookie_file)
            if not success and status != "active":
                self.logger.info(f"Cookie login failed ({status}), trying Google fallback...")
                success, status = self._login_with_google(google_email, google_password)
        
        account_name = self.account.get('name', 'unknown')
        if success:
            self.logger.info(f"✅ Login successful for {account_name}, status: {status}")
        else:
            self.logger.warning(f"❌ Login failed for {account_name}, status: {status}")
        
        return success, status
    
    def set_custom_fingerprint(self):
        """Set custom browser fingerprint from account config"""
        try:
            fingerprint = self.account.get('browser_fingerprint', {})
            
            user_agent = fingerprint.get('user_agent')
            if user_agent and self.browser_manager:
                self.browser_manager.user_agents = [user_agent]
            
            viewport = fingerprint.get('viewport')
            if viewport and self.driver:
                try:
                    width, height = map(int, viewport.split('x'))
                    self.driver.set_window_size(width, height)
                except:
                    pass
            
            if self.browser_manager:
                self.browser_manager.randomize_fingerprint(self.driver)
                
        except Exception as e:
            self.logger.warning(f"Could not set custom fingerprint: {e}")
    
    def perform_activity_session(self) -> Optional[Dict[str, Any]]:
        """Execute one session of human-like activity with anti-detection measures."""
        try:
            # Get session settings
            session_length = random.randint(
                self.activity_config['randomization']['session_length_minutes']['min'],
                self.activity_config['randomization']['session_length_minutes']['max']
            )

            # Heavily randomize activity weights per session
            base_mix = self.activity_config.get("activity_mix", {})
            if isinstance(base_mix, dict) and base_mix:
                jitter_pct = random.uniform(0.35, 0.75)
                self.activity_config["activity_mix"] = _jitter_activity_mix(base_mix, jitter_pct=jitter_pct)
            
            # Start anti-detection session
            if not self.detection_evasion.start_session():
                self.logger.info("Session skipped (vacation or other anti-detection measure)")
                return None
            
            self.session_start_time = time.time()
            self.action_count = 0
            
            actions_performed = {
                'votes': 0,
                'saves': 0,
                'follows': 0,
                'posts_viewed': 0,
                'subreddits_browsed': 0,
                'navigation_errors': 0,
                'tor_rotations': 0
            }
            rate_limits = self.activity_config.get("rate_limits", {})
            
            # Load target subreddits
            subreddits = self.account.get("subreddits")
            if not isinstance(subreddits, list) or not subreddits:
                config_manager = ConfigManager()
                subreddits = config_manager.load_json('config/subreddits.json')
            if not isinstance(subreddits, list):
                subreddits = []
            
            self.logger.info(f"Starting {session_length} minute session for {self.account.get('name')} with anti-detection measures")
            
            while time.time() - self.session_start_time < session_length * 60:
                # Check if we should rotate Tor circuit
                if self.should_rotate_tor():
                    if self.rotate_tor_circuit():
                        actions_performed['tor_rotations'] += 1
                        self.humanization_metrics['tor_rotations'] += 1
                        # Record Tor rotation action
                        self.detection_evasion.record_action("tor_rotation", {
                            "success": True,
                            "timestamp": datetime.now().isoformat()
                        })
                
                # Choose random activity based on mix
                activity = self.choose_random_activity()
                action_type = ACTIVITY_TO_ACTION_TYPE.get(activity, 'wait')
                
                # Get behavior parameters for this action
                behavior = self.detection_evasion.get_behavior_for_action(action_type)
                
                humanization_config = self.activity_config.get("humanization", {})
                mouse_chance = _rate_from_config(
                    humanization_config.get("mouse_movement_chance"),
                    0.40,
                    0.60,
                )
                
                # Apply behavior-based mouse movement
                if self.human_sim and random.random() < mouse_chance:
                    mouse_intensity = behavior.get("mouse_intensity", "medium")
                    self.human_sim.human_mouse_movement(intensity=mouse_intensity)
                
                # Perform the activity with behavior parameters
                activity_success = False
                activity_details = {}
                
                if activity == 'browse_subreddit':
                    if subreddits:
                        subreddit = random.choice(subreddits)
                        self.logger.info(f"Browsing r/{subreddit}")
                        scroll_distance = self.browse_subreddit_humanly(subreddit, behavior)
                        activity_details = {
                            "subreddit": subreddit,
                            "scroll_distance": scroll_distance,
                            "click_speed": behavior.get("click_speed", "normal")
                        }
                        actions_performed['subreddits_browsed'] += 1
                        activity_success = True
                
                elif activity == 'view_posts':
                    scroll_distance = self.view_random_posts(behavior)
                    activity_details = {
                        "scroll_distance": scroll_distance,
                        "click_speed": behavior.get("click_speed", "normal")
                    }
                    actions_performed['posts_viewed'] += 1
                    activity_success = True

                elif activity == 'scroll_comments':
                    scroll_distance = self.scroll_comments(behavior)
                    activity_details = {
                        "scroll_distance": scroll_distance
                    }
                    activity_success = True
                    
                elif activity == 'vote' and actions_performed['votes'] < self.activity_config['safety_limits']['max_votes_per_session']:
                    allowed, _wait = self.rate_limiter.check_rate_limit(
                        self.account.get("name", "account"), "vote", rate_limits
                    )
                    if allowed:
                        vote_success = self.safe_vote(behavior)
                        if vote_success:
                            self.rate_limiter.record_action(self.account.get("name", "account"), "vote")
                            actions_performed['votes'] += 1
                            activity_details = {
                                "click_speed": behavior.get("click_speed", "normal"),
                                "engagement_chance": behavior.get("engagement_chance", 0.3)
                            }
                            self.logger.debug(f"Voted (total: {actions_performed['votes']})")
                            activity_success = True
                
                elif activity == 'save' and actions_performed['saves'] < self.activity_config['safety_limits']['max_saves_per_session']:
                    allowed, _wait = self.rate_limiter.check_rate_limit(
                        self.account.get("name", "account"), "save", rate_limits
                    )
                    if allowed and self.engagement:
                        save_success = self.safe_save()
                        if save_success:
                            self.rate_limiter.record_action(self.account.get("name", "account"), "save")
                            actions_performed['saves'] += 1
                            activity_details = {
                                "click_speed": behavior.get("click_speed", "normal")
                            }
                            self.logger.debug(f"Saved post (total: {actions_performed['saves']})")
                            activity_success = True
                
                elif activity == 'follow' and actions_performed['follows'] < self.activity_config['safety_limits']['max_follows_per_session']:
                    allowed, _wait = self.rate_limiter.check_rate_limit(
                        self.account.get("name", "account"), "follow", rate_limits
                    )
                    if allowed and self.engagement:
                        follow_success = self.safe_follow()
                        if follow_success:
                            self.rate_limiter.record_action(self.account.get("name", "account"), "follow")
                            actions_performed['follows'] += 1
                            self.logger.debug(f"Followed user (total: {actions_performed['follows']})")
                            activity_success = True
                
                elif activity == 'check_notifications':
                    self.check_notifications()
                    activity_success = True
                
                # Record action with anti-detection system
                if activity_success:
                    self.detection_evasion.record_action(action_type, activity_details)
                    self.action_count += 1
                
                # Simulate navigation error
                nav_error_chance = _rate_from_config(
                    humanization_config.get("navigation_error_rate"),
                    0.08,
                    0.12,
                )
                if self.human_sim and random.random() < nav_error_chance:
                    if self.human_sim.simulate_navigation_error(self.driver):
                        actions_performed['navigation_errors'] += 1
                        # Record navigation error
                        self.detection_evasion.record_action("navigation_error", {
                            "type": "simulated_error",
                            "timestamp": datetime.now().isoformat()
                        })
                
                # Get Markov chain delay for next action
                delay = self.detection_evasion.get_session_delay(action_type)
                time.sleep(delay)
            
            # End anti-detection session
            analysis = self.detection_evasion.end_session(success=True)
            
            # Log anti-detection analysis
            if analysis:
                risk_level = analysis.get("overall_risk", "unknown")
                self.logger.info(f"📊 Anti-detection analysis: {risk_level.upper()} risk")
                
                if risk_level in ["high", "critical"]:
                    self.logger.warning("⚠️ High risk patterns detected!")
                    for suggestion in analysis.get("suggestions", []):
                        self.logger.info(f"  💡 {suggestion}")
            
            # Combine session results
            session_results = actions_performed.copy()
            if analysis:
                session_results["anti_detection_analysis"] = analysis
            
            self.logger.info(f"📊 Session complete. Actions: {actions_performed}")
            return session_results
            
        except Exception as e:
            self.logger.error(f"Error during activity session: {e}")
            # End session with failure
            if self.detection_evasion:
                self.detection_evasion.end_session(success=False)
            return None
    
    def browse_subreddit_humanly(self, subreddit_name: str, behavior: Dict[str, Any]) -> int:
        """Browse a subreddit with human-like behavior and anti-detection measures."""
        total_scroll = 0
        try:
            # Navigate to subreddit
            self.driver.get(f"https://old.reddit.com/r/{subreddit_name}")
            
            # Use Markov chain delay
            delay = self.detection_evasion.get_session_delay("navigation")
            time.sleep(delay)
            
            # Get scroll pattern from behavior
            scroll_pattern = behavior.get("scroll_pattern", "smooth")
            click_speed = behavior.get("click_speed", "normal")
            
            # Random scrolling with behavior-based parameters
            scrolls = random.randint(2, 5)
            for _ in range(scrolls):
                # Get scroll distance from behavior or random
                if scroll_pattern == "smooth":
                    pixels = random.randint(400, 900)
                elif scroll_pattern == "jerky":
                    pixels = random.randint(600, 1200)
                else:  # reader
                    pixels = random.randint(200, 500)
                
                self.browser_manager.scroll_down(self.driver, pixels)
                total_scroll += pixels
                
                # Use Markov chain delay
                delay = self.detection_evasion.get_session_delay("scroll")
                time.sleep(delay)
            
            # Mouse wander with behavior-based intensity
            if self.human_sim and random.random() < 0.5:
                mouse_intensity = behavior.get("mouse_intensity", "medium")
                self.human_sim.mouse_wander(duration_seconds=random.uniform(1, 3))
            
            # Occasionally view a post
            if random.random() > 0.7:
                self.view_random_post_in_current_subreddit(behavior)
            
            return total_scroll
            
        except Exception as e:
            self.logger.warning(f"Error browsing subreddit {subreddit_name}: {e}")
            return total_scroll
    
    def view_random_posts(self, behavior: Dict[str, Any]) -> int:
        """Find and view random posts on current page with anti-detection measures."""
        total_scroll = 0
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

                # Human-like reading sequence with behavior-based mouse movement
                if self.human_sim:
                    mouse_intensity = behavior.get("mouse_intensity", "medium")
                    self.human_sim.human_mouse_movement(target, intensity=mouse_intensity)
                    
                    # Get reading time from behavior
                    read_time_factor = 1.0
                    if behavior.get("engagement_rate", 0.3) > 0.5:  # Enthusiastic readers read longer
                        read_time_factor = 1.5
                    
                    self.human_sim.read_post_sequence(target, read_time_factor)
                else:
                    # Fallback
                    self.browser_manager.safe_click(self.driver, target)
                    delay = self.detection_evasion.get_session_delay("view")
                    time.sleep(delay)
                    self.driver.back()
                    delay = self.detection_evasion.get_session_delay("navigation")
                    time.sleep(delay)
                
                # Scroll after viewing
                scroll_distance = random.randint(200, 600)
                self.browser_manager.scroll_down(self.driver, scroll_distance)
                total_scroll += scroll_distance
                
                return total_scroll
            return total_scroll
            
        except Exception as e:
            self.logger.debug(f"Error viewing random post: {e}")
            return total_scroll

    def scroll_comments(self, behavior: Dict[str, Any]) -> int:
        """Scroll through comments section with anti-detection measures."""
        total_scroll = 0
        try:
            if self.human_sim:
                scroll_pattern = behavior.get("scroll_pattern", "smooth")
                
                # Adjust scroll based on pattern
                if scroll_pattern == "smooth":
                    scrolls = random.randint(2, 4)
                    for _ in range(scrolls):
                        pixels = random.randint(300, 600)
                        self.browser_manager.scroll_down(self.driver, pixels)
                        total_scroll += pixels
                        delay = self.detection_evasion.get_session_delay("scroll")
                        time.sleep(delay)
                else:
                    # Use human simulator's method
                    self.human_sim.view_comments_section()
                    total_scroll = random.randint(400, 800)
                
                return total_scroll
            
            # Fallback: simple scroll
            for _ in range(random.randint(2, 4)):
                if self.browser_manager and self.driver:
                    pixels = random.randint(250, 600)
                    self.browser_manager.scroll_down(self.driver, pixels)
                    total_scroll += pixels
                    delay = self.detection_evasion.get_session_delay("scroll")
                    time.sleep(delay)
            return total_scroll
        except Exception as e:
            self.logger.debug(f"Error scrolling comments: {e}")
            return total_scroll
    
    def view_random_post_in_current_subreddit(self, behavior: Dict[str, Any]) -> bool:
        """View a random post in the current subreddit with anti-detection measures."""
        try:
            posts = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")
            if posts:
                post = random.choice(posts[:5])
                target = None
                for selector in ("a.title", "a.comments"):
                    try:
                        target = post.find_element(By.CSS_SELECTOR, selector)
                        break
                    except Exception:
                        continue
                target = target or post
                
                # Add mouse movement with behavior-based intensity
                if self.human_sim:
                    mouse_intensity = behavior.get("mouse_intensity", "medium")
                    self.human_sim.human_mouse_movement(target, intensity=mouse_intensity)
                
                self.browser_manager.safe_click(self.driver, target)
                delay = self.detection_evasion.get_session_delay("view")
                time.sleep(delay)
                
                # Scroll through the post
                pixels = random.randint(200, 600)
                self.browser_manager.scroll_down(self.driver, pixels)
                delay = self.detection_evasion.get_session_delay("scroll")
                time.sleep(delay)
                
                # Mouse wander with behavior-based frequency
                if self.human_sim and random.random() < behavior.get("engagement_rate", 0.3):
                    self.human_sim.mouse_wander()
                
                # Go back
                self.driver.back()
                delay = self.detection_evasion.get_session_delay("navigation")
                time.sleep(delay)
                return True
        except Exception as e:
            self.logger.debug(f"Error viewing post: {e}")
        
        return False
    
    def safe_vote(self, behavior: Dict[str, Any]) -> bool:
        """Safely upvote a random post with anti-detection behavior."""
        try:
            if not self.activity_config.get('allow_voting', False):
                return False
            
            upvote_buttons = self.driver.find_elements(By.CSS_SELECTOR, "div.thing div.arrow.up")
            upvote_buttons = [
                btn for btn in upvote_buttons
                if "upmod" not in (btn.get_attribute("class") or "")
            ]
            if upvote_buttons:
                # Use engagement rate from behavior
                engagement_rate = behavior.get("engagement_rate", 0.3)
                if random.random() > (1 - engagement_rate):
                    button = random.choice(upvote_buttons[:3])
                    
                    # Add mouse movement with behavior-based intensity
                    if self.human_sim:
                        mouse_intensity = behavior.get("mouse_intensity", "low")
                        self.human_sim.human_mouse_movement(button, intensity=mouse_intensity)
                    
                    self.browser_manager.safe_click(self.driver, button)
                    delay = self.detection_evasion.get_session_delay("vote")
                    time.sleep(delay)
                    return True
        except Exception as e:
            self.logger.debug(f"Error voting: {e}")
        
        return False
    
    def safe_save(self) -> bool:
        """Safely save a random post (if enabled)."""
        try:
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
                    delay = self.detection_evasion.get_session_delay("save")
                    time.sleep(delay)
                    return True
            return False
            
        except Exception as e:
            self.logger.debug(f"Error saving: {e}")
            return False
    
    def safe_follow(self) -> bool:
        """Safely follow a random user (if enabled)."""
        try:
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
            delay = self.detection_evasion.get_session_delay("follow")
            time.sleep(delay)
            if current_url:
                self.driver.get(current_url)
                delay = self.detection_evasion.get_session_delay("navigation")
                time.sleep(delay)
            return followed
            
        except Exception as e:
            self.logger.debug(f"Error following: {e}")
            return False
    
    def check_notifications(self):
        """Check notifications (if enabled)."""
        try:
            if not self.activity_config.get('allow_notifications_check', True):
                return
            self.driver.get("https://old.reddit.com/message/unread")
            delay = self.detection_evasion.get_session_delay("navigation")
            time.sleep(delay)
            self.driver.back()
            delay = self.detection_evasion.get_session_delay("navigation")
            time.sleep(delay)
                    
        except Exception as e:
            self.logger.debug(f"Error checking notifications: {e}")
    
    def choose_random_activity(self) -> str:
        """Choose activity based on weighted distribution."""
        try:
            mix = self.activity_config.get("activity_mix", {})
            activities = list(mix.keys())
            weights = list(mix.values())
            if activities and random.random() < 0.1:
                # Occasionally ignore weights to break patterns
                return random.choice(activities)
            return random.choices(activities, weights=weights)[0]
        except:
            # Default activities if config is wrong
            default_activities = ['browse_subreddit', 'view_posts', 'check_notifications']
            return random.choice(default_activities)
    
    def cleanup(self):
        """Cleanup resources."""
        try:
            # Get anti-detection status report before cleanup
            if self.detection_evasion:
                report = self.detection_evasion.get_status_report()
                self.logger.info(f"Anti-detection status before cleanup: {report.get('current_state', {})}")
            
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

        self.subreddit_coverage = _load_subreddit_coverage(SUBREDDIT_COVERAGE_PATH)
        
        # Initialize account status tracker
        self.status_tracker = AccountStatusTracker()
        self.logger.info(f"Account status tracker initialized. Tracking {len(self.status_tracker.status_data)} accounts")

    def load_accounts(self):
        """Load accounts from config."""
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
        
        # Add default humanization settings if not present
        if "humanization" not in config:
            config["humanization"] = {
                "enable_mouse_movement": True,
                "enable_navigation_errors": True,
                "enable_tor_rotation": True,
                "mouse_movement_intensity": "medium",
                "navigation_error_rate": 0.05,
                "mouse_wander_frequency": 0.3
            }
        
        # Ensure security evolution config is present
        if "security_evolution" not in config:
            config["security_evolution"] = {
                "enabled": True,
                "config_path": "config/security_evolution.json"
            }
        
        return config

    def handle_login_status(self, account_name: str, success: bool, status: str) -> bool:
        """
        Handle login status and take appropriate action.
        Returns True if scanning should proceed, False otherwise.
        """
        details = {
            "success": success,
            "status": status,
            "run_id": self.run_id,
            "scan_window": self.scan_window
        }
        
        self.status_tracker.update_account_status(account_name, status, details)
        
        if success:
            if status == "active":
                self.logger.info(f"✅ Account {account_name} is active, proceeding with scan")
                return True
            elif status == "captcha":
                self.logger.warning(f"🔒 Account {account_name} has CAPTCHA but login succeeded. Proceeding carefully.")
                return True
            else:
                self.logger.info(f"Account {account_name} login successful with status: {status}")
                return True
        
        self.logger.warning(f"❌ Login failed for {account_name} with status: {status}")
        
        if status == "suspended":
            self.logger.error(f"🚨 ACCOUNT SUSPENDED: {account_name}. Skipping all future scans.")
            return False
        elif status == "rate_limited":
            self.logger.warning(f"⏳ Account {account_name} is rate limited. Skipping for 24 hours.")
            return False
        elif status == "captcha":
            self.logger.warning(f"🔒 CAPTCHA detected for {account_name}. Skipping for 6 hours.")
            return False
        elif status == "security_check":
            self.logger.warning(f"🛡️ Security check required for {account_name}. Manual intervention needed.")
            return False
        elif status in ["no_cookies", "cookie_file_not_found", "missing_cookie_file"]:
            self.logger.warning(f"🍪 No valid cookies for {account_name}. Trying Google login or manual refresh needed.")
            return False
        elif status == "login_manager_not_initialized":
            self.logger.error(f"🔧 Login manager not initialized for {account_name}. Browser setup issue.")
            return False
        else:
            self.logger.warning(f"⚠️ Unknown login failure for {account_name}: {status}")
            return False

    def run_rotation(self):
        """Run sessions for all accounts in rotation with anti-detection measures."""
        if not self.accounts:
            self.logger.error("No accounts configured")
            return

        total_accounts = len(self.accounts)
        active_accounts = 0
        skipped_accounts = 0
        
        report = self.status_tracker.get_status_report()
        self.logger.info(f"📊 Account Status Report:")
        self.logger.info(f"   Total accounts: {report['total_accounts']}")
        self.logger.info(f"   Active: {report['active']}")
        self.logger.info(f"   Suspended: {report['suspended']}")
        self.logger.info(f"   Rate limited: {report['rate_limited']}")
        self.logger.info(f"   CAPTCHA required: {report['captcha']}")
        
        for idx, account in enumerate(self.accounts):
            account_name = account.get('name', 'unknown')
            
            if self.status_tracker.should_skip_account(account_name):
                self.logger.info(f"⏭️ Skipping account {account_name} due to previous status")
                skipped_accounts += 1
                continue
            
            scanner = None
            try:
                self.logger.info(f"🚀 Starting session for {account_name} ({idx+1}/{total_accounts}) with anti-detection measures")

                if _vpn_enabled():
                    location = account.get("vpn_location") or os.getenv("VPN_LOCATION", "").strip()
                    if location:
                        try:
                            vpn_info = VPNManager().connect_to_vpn(location)
                            self.logger.info(f"VPN connected for {account_name}: {vpn_info}")
                        except Exception as exc:
                            self.logger.warning(f"VPN connection failed for {account_name}: {exc}")
                
                profile_name = account.get("activity_profile", "") or ""
                activity_config = self.build_activity_config(profile_name)

                config_manager = ConfigManager()
                global_subreddits = config_manager.load_json('config/subreddits.json')
                if not isinstance(global_subreddits, list):
                    global_subreddits = []
                base_subreddits = global_subreddits
                account_subreddits = select_subreddits_for_run(
                    base_subreddits,
                    self.subreddit_coverage,
                    window_days=SUBREDDIT_COVERAGE_WINDOW_DAYS,
                )
                account["subreddits"] = account_subreddits

                scanner = HumanizedNightScanner(account, activity_config)
                
                if not scanner.driver:
                    self.logger.error(f"Failed to create browser for {account_name}")
                    self.status_tracker.update_account_status(account_name, "error", {"error": "browser_creation_failed"})
                    continue
                
                cookie_file = account.get('cookies_path', 'data/cookies_account1.pkl')
                google_email = account.get('google_email', '')
                google_password = account.get('google_password', '')
                login_method = account.get("login_method") or activity_config.get("login_method") or "cookies_then_google"

                # Login and handle status
                success, status = scanner.login(cookie_file, google_email, google_password, login_method)
                
                should_proceed = self.handle_login_status(account_name, success, status)
                
                if should_proceed:
                    self.logger.info(f"✅ Logged in to {account_name}, proceeding with activities")
                    active_accounts += 1
                    
                    # Perform activity session with anti-detection
                    actions = scanner.perform_activity_session()
                    
                    if actions:
                        self.logger.info(f"🎉 Session completed for {account_name}: {actions}")
                        
                        # Log anti-detection status
                        if scanner.detection_evasion:
                            status_report = scanner.detection_evasion.get_status_report()
                            risk_level = status_report.get("patterns", {}).get("last_risk_level", "unknown")
                            self.logger.info(f"🛡️ Anti-detection status for {account_name}: {risk_level} risk")

                    # Run session scan
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
                        f"📊 Scan shard for {account_name}: sort={sort}, time={time_range or 'none'}, page_offset={page_offset}"
                    )
                    self.logger.info(
                        f"🔍 Subreddits for {account_name}: {', '.join(account_subreddits)}"
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
                        account=account_name,
                        tz_name=self.tz_name,
                        scan_window=self.scan_window,
                        mode="selenium",
                        sort=sort,
                        time_range=time_range or "",
                        page_offset=page_offset,
                    )
                    
                    # Save cookies
                    if scanner.login_manager and cookie_file:
                        scanner.login_manager.save_login_cookies(cookie_file)

                    # Update subreddit coverage
                    for subreddit in account_subreddits:
                        self.subreddit_coverage[subreddit] = datetime.utcnow().isoformat()
                    _save_subreddit_coverage(SUBREDDIT_COVERAGE_PATH, self.subreddit_coverage)
                    
                else:
                    self.logger.warning(f"⏸️ Skipping scan for {account_name} due to login status")
                    skipped_accounts += 1
                
                scanner.cleanup()
                
                # Wait between accounts with anti-detection delay simulation
                if idx < len(self.accounts) - 1:
                    wait_time = random.randint(300, 900)
                    self.logger.info(f"⏳ Waiting {wait_time//60} minutes before next account")
                    time.sleep(wait_time)
                
            except Exception as e:
                self.logger.error(f"❌ Error with account {account_name}: {e}")
                self.status_tracker.update_account_status(account_name, "error", {"error": str(e), "traceback": "see logs"})
                if scanner:
                    scanner.cleanup()
                continue
        
        self.logger.info(f"📈 Rotation Complete:")
        self.logger.info(f"   Total accounts: {total_accounts}")
        self.logger.info(f"   Active sessions: {active_accounts}")
        self.logger.info(f"   Skipped accounts: {skipped_accounts}")
        
        final_report = self.status_tracker.get_status_report()
        report_file = Path("logs/account_status_report.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, 'w') as f:
            json.dump(final_report, f, indent=2)
        
        self.logger.info(f"📄 Account status report saved to {report_file}")

def check_time_window(activity_config: Optional[Dict[str, Any]] = None) -> bool:
    """Check if current time is within scheduled windows."""
    try:
        config = activity_config or ConfigManager().load_json('config/activity_schedule.json') or {}
        return get_active_window(config) is not None
    except Exception as e:
        logger.info(f"Error checking time window: {e}")
        return False

if __name__ == "__main__":
    enforce_readonly_env()
    cleanup_state()
    enable_console_tee(os.getenv("CONSOLE_LOG_PATH", "logs/selenium_automation.log"))
    logger.info("=" * 60)
    logger.info("Humanized Night Scanner with Anti-Detection Measures")
    logger.info("=" * 60)

    parser = argparse.ArgumentParser(description="Humanized night scanner with anti-detection")
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
        logger.info("✓ In scheduled time window. Starting scanner with anti-detection...")
        
        try:
            orchestrator = MultiAccountOrchestrator(
                activity_config=activity_config,
                active_window=active_window,
            )
            
            if orchestrator.accounts:
                logger.info(f"Found {len(orchestrator.accounts)} accounts")
                orchestrator.run_rotation()
                logger.info("✓ Rotation complete with anti-detection measures")
            else:
                logger.info("✗ No accounts configured")
                
        except Exception as e:
            logger.info(f"✗ Error running orchestrator: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.info("✗ Not in scheduled time window. Exiting.")
    
    logger.info("=" * 60)