#!/usr/bin/env python3
"""
Enhanced night scanner with human-like behavior and multi-account support.
Runs in read-only mode during Pacific time windows.

Updated to use refactored BrowserManager and LoginManager classes.
"""

import time
import random
import json
import os
from datetime import datetime
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium_automation.utils.human_simulator import HumanSimulator
from selenium_automation.utils.engagement_actions import EngagementActions
from selenium_automation.login_manager import LoginManager
from selenium_automation.utils.browser_manager import BrowserManager
from shared.config_manager import ConfigManager
from shared.logger import UnifiedLogger

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
            headless = self.activity_config.get('headless', True)
            self.browser_manager = BrowserManager(headless=headless)
            
            # Get driver with undetected Chrome
            self.driver = self.browser_manager.create_driver(use_undetected=True)
            
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
            self.human_sim = HumanSimulator(self.driver)
            self.engagement = EngagementActions(self.driver, self.activity_config.get('safety_limits', {}))
            
            self.logger.info(f"Browser setup complete for {self.account.get('name', 'unknown')}")
            
        except Exception as e:
            self.logger.error(f"Failed to setup browser: {e}")
            raise
    
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
            
            # Load target subreddits
            config_manager = ConfigManager()
            subreddits = config_manager.load_json('config/subreddits.json')
            
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
            self.driver.get(f"https://www.reddit.com/r/{subreddit_name}")
            
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
            # Try multiple selectors for posts
            selectors = [
                '[data-test-id="post-container"]',
                'article',
                'shreddit-post',
                'div.Post'
            ]
            
            for selector in selectors:
                try:
                    posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if posts:
                        # Take a random post from top 10
                        post = random.choice(posts[:min(10, len(posts))])
                        
                        # Human-like reading sequence
                        if self.human_sim:
                            self.human_sim.read_post_sequence(post)
                        else:
                            # Fallback
                            self.browser_manager.safe_click(self.driver, post)
                            self.browser_manager.add_human_delay(3, 8)
                            self.driver.back()
                            self.browser_manager.add_human_delay(1, 2)
                        
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error viewing random post: {e}")
            return False
    
    def view_random_post_in_current_subreddit(self):
        """View a random post in the current subreddit"""
        try:
            posts = self.driver.find_elements(By.CSS_SELECTOR, '[data-test-id="post-container"]')
            if posts:
                post = random.choice(posts[:5])  # Only from top 5
                self.browser_manager.safe_click(self.driver, post)
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
            upvote_buttons = self.driver.find_elements(By.CSS_SELECTOR, '[aria-label="upvote"]')
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
            
            # This would need actual implementation
            # For now, just log that we would save
            self.logger.debug("Save action triggered (not implemented)")
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
            
            # This would need actual implementation
            # For now, just log that we would follow
            self.logger.debug("Follow action triggered (not implemented)")
            return False
            
        except Exception as e:
            self.logger.debug(f"Error following: {e}")
            return False
    
    def check_notifications(self):
        """Check notifications (if enabled)"""
        try:
            # Check if notifications checking is allowed
            if not self.activity_config.get('allow_notifications_check', True):
                return
            
            # Try to find notification bell
            notification_selectors = [
                '[aria-label="Open notifications"]',
                '[data-test-id="notification-button"]',
                'button[aria-label*="notification"]'
            ]
            
            for selector in notification_selectors:
                try:
                    bell = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if bell:
                        self.browser_manager.safe_click(self.driver, bell)
                        self.browser_manager.add_human_delay(2, 4)
                        
                        # Close notifications
                        self.driver.execute_script("document.activeElement.blur();")
                        self.browser_manager.add_human_delay(1, 2)
                        break
                except:
                    continue
                    
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
    def __init__(self):
        self.config_manager = ConfigManager()
        self.logger = UnifiedLogger("MultiAccountOrchestrator").get_logger()
        self.accounts = self.load_accounts()
        self.activity_config = self.config_manager.load_json('config/activity_schedule.json')
    
    def load_accounts(self):
        """Load accounts from config"""
        try:
            accounts = self.config_manager.load_json('config/accounts.json')
            
            # Load credentials from environment variables
            for account in accounts:
                email_var = account.get('email_env_var')
                password_var = account.get('password_env_var')
                
                if email_var:
                    account['email'] = os.getenv(email_var, '')
                if password_var:
                    account['password'] = os.getenv(password_var, '')
            
            return accounts
            
        except Exception as e:
            self.logger.error(f"Failed to load accounts: {e}")
            return []
    
    def run_rotation(self):
        """Run sessions for all accounts in rotation"""
        if not self.accounts:
            self.logger.error("No accounts configured")
            return
        
        for account in self.accounts:
            scanner = None
            try:
                self.logger.info(f"Starting session for {account.get('name', 'unknown')}")
                
                # Create scanner
                scanner = HumanizedNightScanner(account, self.activity_config)
                
                if not scanner.driver:
                    self.logger.error(f"Failed to create browser for {account.get('name')}")
                    continue
                
                # Login with cookies
                cookie_file = account.get('cookies_path', 'cookies.pkl')
                if scanner.login_manager and scanner.login_manager.login_with_cookies(cookie_file=cookie_file, headless=True):
                    self.logger.info(f"Logged in to {account.get('name')}")
                    
                    # Perform activity session
                    actions = scanner.perform_activity_session()
                    
                    if actions:
                        self.logger.info(f"Session completed for {account.get('name')}: {actions}")
                    
                    # Save cookies for next time
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


def check_time_window():
    """Check if current time is within scheduled windows"""
    try:
        from datetime import datetime

        tzinfo = None
        try:
            import pytz  # type: ignore

            tzinfo = pytz.timezone('America/Los_Angeles')
        except Exception:
            try:
                from zoneinfo import ZoneInfo

                tzinfo = ZoneInfo('America/Los_Angeles')
            except Exception:
                tzinfo = None

        current_time = datetime.now(tzinfo) if tzinfo else datetime.now()

        config_manager = ConfigManager()
        activity_config = config_manager.load_json('config/activity_schedule.json') or {}

        for window in activity_config.get('time_windows', []):
            start_time = datetime.strptime(window['start'], "%H:%M").time()
            end_time = datetime.strptime(window['end'], "%H:%M").time()
            
            # Handle overnight windows (end time < start time)
            if end_time < start_time:
                # Window spans midnight
                if current_time.time() >= start_time or current_time.time() <= end_time:
                    return True
            else:
                # Normal window
                if start_time <= current_time.time() <= end_time:
                    return True
        
        return False
        
    except Exception as e:
        print(f"Error checking time window: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Humanized Night Scanner")
    print("=" * 60)
    
    # Check time window
    if check_time_window():
        print("✓ In scheduled time window. Starting scanner...")
        
        try:
            orchestrator = MultiAccountOrchestrator()
            
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
