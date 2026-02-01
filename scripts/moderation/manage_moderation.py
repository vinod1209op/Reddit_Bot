#!/usr/bin/env python3
"""
MCRDSE Subreddit Moderation Manager
"""

import json
import sys
import time
import logging
import random
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from microdose_study_bot.reddit_selenium.automation_base import RedditAutomationBase
from microdose_study_bot.core.logging import UnifiedLogger

# Setup logging
logger = UnifiedLogger("ModerationManager").get_logger()

class SeleniumModerationManager(RedditAutomationBase):
    """Selenium-based moderation manager for MCRDSE subreddits"""
    
    def __init__(self, account_name="account1", headless=True, dry_run=False, session=None, owns_session=True):
        """
        Initialize moderation manager with Selenium
        
        Args:
            account_name: Which Reddit account to use (from config/accounts.json)
            headless: Run browser in background
        """
        os.environ["SELENIUM_HEADLESS"] = "1" if headless else "0"
        self.account_name = account_name
        self.headless = headless
        super().__init__(account_name=account_name, dry_run=dry_run, session=session, owns_session=owns_session)
        self.config = self.load_config()
        self.moderation_templates = self._load_moderation_templates()
        self.governance = self._load_governance_config()
        self.moderation_stats = {}
        self.activity_limits = self._load_activity_limits()
        self.moderation_ui_mode = "old"
        self.moderation_urls_used = []
        self.profile_map = {}
        
        # Load account-specific settings
        self.account_config = self.account

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

    def _set_field_value(self, element, value: str) -> bool:
        """Set input/textarea value with JS fallback for old Reddit forms."""
        try:
            element.clear()
            element.send_keys(value)
            return True
        except Exception:
            try:
                self.driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
                    element,
                    value,
                )
                return True
            except Exception:
                return False

    def _sanitize_wiki_text(self, value: str) -> str:
        """
        Reddit wiki rejects some unicode (e.g., emoji). Keep it ASCII-only to
        avoid YAML parse errors and silent save failures.
        """
        if value is None:
            return ""
        try:
            return value.encode("ascii", "ignore").decode("ascii")
        except Exception:
            return ""

    def _click_first(self, selectors: List[Tuple[str, str]], wait_seconds: int = 6) -> bool:
        """Click the first visible element that matches any selector."""
        element = self._find_first(selectors, wait_seconds=wait_seconds)
        if not element:
            return False
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)
            element.click()
            return True
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False
        
    def load_config(self) -> Dict:
        """Load moderation configuration"""
        config_path = Path("scripts/moderation/config/moderation_config.json")
        
        file_config = {}
        if config_path.exists():
            try:
                file_config = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Config file corrupted, using defaults")
        
        # Default configuration
        default_config = {
            "moderation": {
                "auto_approve_trusted_users": True,
                "trusted_authors": [],
                "remove_spam_keywords": ["buy", "sell", "vendor", "price", "dm me"],
                "remove_self_harm_keywords": ["suicide", "kill myself", "end my life"],
                "require_flair": True,
                "min_post_length": 50,
                "max_posts_per_hour": 3,
                "max_comments_per_hour": 10,
                "queue_processing_limit": 10,
                "conservative_mode": True
            },
            "flairs": {
                "post_flairs": [
                    {"name": "Research Discussion", "color": "#0DD3BB"},
                    {"name": "Personal Experience", "color": "#FFB000"},
                    {"name": "Scientific Study", "color": "#46D160"},
                    {"name": "Question", "color": "#FFD635"},
                    {"name": "Resource Share", "color": "#0079D3"},
                    {"name": "Community News", "color": "#FF4500"},
                    {"name": "Meta Discussion", "color": "#7E53C1"}
                ],
                "user_flairs": [
                    {"name": "Researcher", "color": "#0DD3BB"},
                    {"name": "Therapist", "color": "#FFB000"},
                    {"name": "Educator", "color": "#46D160"},
                    {"name": "Student", "color": "#FFD635"},
                    {"name": "Advocate", "color": "#0079D3"},
                    {"name": "MCRDSE Team", "color": "#FF4500"}
                ]
            },
            "automod_templates": {
                "basic": """---
# Basic AutoModerator rules for MCRDSE communities
type: submission
author:
    account_age: "< 24 hours"
    combined_karma: "< 10"
action: filter
action_reason: "New account/low karma"

type: submission
title+body (includes): ["buy", "sell", "vendor", "price", "dm me"]
action: filter
action_reason: "Potential sourcing"

type: submission
title+body (includes): ["suicide", "kill myself", "end my life"]
action: report
action_reason: "Self-harm concerns"

type: comment
author:
    account_age: "< 7 days"
    comment_karma: "< 5"
action: filter
action_reason: "New user comment"
---
""",
                "advanced": """---
# Advanced AutoModerator rules for MCRDSE communities
# Spam protection
type: any
author:
    account_age: "< 24 hours"
    combined_karma: "< 10"
action: filter
action_reason: "New account/low karma"

# Sourcing prevention
type: any
title+body (includes): ["buy", "sell", "vendor", "dealer", "price", "\\$", "ship"]
action: filter
action_reason: "Potential sourcing"

# Medical advice prevention
type: any
title+body (includes): ["prescribe", "diagnose", "treatment", "cure", "you should take"]
action: filter
action_reason: "Potential medical advice"

# Self-harm detection
type: any
title+body (includes): ["suicide", "kill myself", "want to die", "end my life"]
action: report
action_reason: "Self-harm concerns"
modmail: "Self-harm content detected: {{permalink}}"

# Welcome new users
type: comment
author:
    comment_karma: "< 10"
    account_age: "< 7 days"
message: |
    Welcome to our community! Please review our guidelines.

# Quality control
type: submission
body (regex): '^\\s*[\\s\\S]{0,49}\\s*$'
action: filter
action_reason: "Post too short"
message: |
    Your post appears to be very short. Please add more content.
---
"""
            },
            "subreddit_rules": [
                "All posts must be research-focused or evidence-based",
                "No sourcing or discussion of acquiring substances",
                "No medical advice - share experiences, not prescriptions",
                "Be respectful to all community members",
                "Practice harm reduction in all discussions",
                "Cite sources when making factual claims",
                "Use appropriate post flair for your content",
                "No spam, self-promotion, or low-effort content"
            ],
            "scheduled_tasks": {
                "check_queue_interval_minutes": 60,
                "daily_report_time": "22:00",
                "weekly_cleanup_day": "Sunday"
            }
        }
        
        # Save default config
        if not config_path.exists():
            config_path.parent.mkdir(exist_ok=True, parents=True)
            config_path.write_text(json.dumps(default_config, indent=2))
            logger.info(f"Created default config at {config_path}")
        
        if file_config and isinstance(file_config, dict):
            return {**default_config, **file_config}
        return default_config

    def _load_moderation_templates(self) -> Dict:
        path = Path("config/moderation_templates.json")
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _load_governance_config(self) -> Dict:
        path = Path("config/community_governance.json")
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _load_activity_limits(self) -> Dict:
        if os.getenv("BYPASS_MODERATION_LIMITS", "").strip().lower() in ("1", "true", "yes"):
            return {
                "max_actions_per_run": 9999,
                "auto_remove_reported": True,
                "remove_spam": True,
                "notify_on_flags": False,
            }
        moderation_feature = (self.activity_schedule or {}).get("moderation", {})
        limits = {
            "max_actions_per_run": moderation_feature.get("max_actions_per_run", 10),
            "auto_remove_reported": moderation_feature.get("auto_remove_reported", False),
            "remove_spam": moderation_feature.get("remove_spam", True),
            "notify_on_flags": moderation_feature.get("notify_on_flags", True),
        }
        return limits
    
    def load_account_config(self) -> Dict:
        """Load account-specific configuration"""
        accounts_path = Path("config/accounts.json")
        if accounts_path.exists():
            try:
                accounts = json.loads(accounts_path.read_text())
                for account in accounts:
                    if account.get("name") == self.account_name:
                        return account
            except:
                pass
        
        # Return default if not found
        return {
            "name": self.account_name,
            "cookies_path": f"data/cookies_{self.account_name}.pkl"
        }

    def verify_moderator_status(self, subreddit_name: str) -> bool:
        if self.dry_run:
            logger.info("[dry-run] Skipping moderator verification")
            return True
        try:
            if not self.driver:
                return False
            self.driver.get(f"https://old.reddit.com/r/{subreddit_name}/about/moderators")
            time.sleep(2)
            page = self.driver.page_source.lower()
            username = (self.account_config or {}).get("username") or self.account_name
            return username.lower() in page
        except Exception as exc:
            logger.warning(f"Moderator verification failed: {exc}")
            return False
    
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

    def _can_moderate(self, subreddit_name: str) -> bool:
        if os.getenv("BYPASS_MODERATION_LIMITS", "").strip().lower() in ("1", "true", "yes"):
            return True
        if self.status_tracker.should_skip_account(self.account_name):
            return False
        if os.getenv("BYPASS_MODERATOR_CHECK", "").strip().lower() not in ("1", "true", "yes"):
            if not self.verify_moderator_status(subreddit_name):
                return False
        if os.getenv("BYPASS_MODERATION_COOLDOWN", "").strip().lower() not in ("1", "true", "yes"):
            remaining = self.status_tracker.get_cooldown_remaining(self.account_name, "moderation")
            if remaining and remaining > 0:
                return False
        return True
    
    def navigate_to_subreddit(self, subreddit_name: str, section: str = "") -> bool:
        """Navigate to a specific subreddit section"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Skipping navigation to r/%s/%s", subreddit_name, section)
                return True
            base_url = f"https://old.reddit.com/r/{subreddit_name}"
            if section:
                base_url += f"/{section}"
            
            self.moderation_urls_used.append(base_url)
            logger.info("Using old Reddit URL: %s", base_url)
            self.driver.get(base_url)
            time.sleep(3)
            
            # Check if we have access
            if "you are not allowed to do that" in self.driver.page_source.lower():
                logger.error(f"No moderator access to r/{subreddit_name}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to r/{subreddit_name}: {e}")
            return False
    
    def setup_automoderator(self, subreddit_name: str, template: str = "basic") -> bool:
        """Setup AutoModerator rules via wiki"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would set up AutoModerator for r/%s", subreddit_name)
                return True
            # Check view URL first to determine if page exists
            view_url = f"https://old.reddit.com/r/{subreddit_name}/wiki/config/automoderator"
            self.moderation_urls_used.append(view_url)
            logger.info("Using old Reddit URL: %s", view_url)
            self.driver.get(view_url)
            time.sleep(2)
            if "wiki is disabled" in self.driver.page_source.lower():
                logger.warning("Wiki is disabled; enable wiki in subreddit settings first")
                return False

            if "page \"config/automoderator\" was not found" in self.driver.page_source.lower():
                # Go directly to create page flow (old Reddit)
                create_url = f"https://old.reddit.com/r/{subreddit_name}/wiki/create/config/automoderator"
                self.moderation_urls_used.append(create_url)
                logger.info("Using old Reddit URL: %s", create_url)
                self.driver.get(create_url)
                time.sleep(2)
            else:
                # Page exists; go to edit URL
                edit_url = f"https://old.reddit.com/r/{subreddit_name}/wiki/edit/config/automoderator"
                self.moderation_urls_used.append(edit_url)
                logger.info("Using old Reddit URL: %s", edit_url)
                self.driver.get(edit_url)
                time.sleep(2)
            
            # Get automod content from config (sanitized)
            base_content = self.config["automod_templates"].get(template, self.config["automod_templates"]["basic"])
            advanced = self.config.get("advanced_automod_rules", {})
            extra_blocks = []
            for key in ("quality_enforcement", "conversation_starter", "resource_suggestions"):
                block = advanced.get(key)
                if block:
                    extra_blocks.append(block.strip())
            transparency = self.config.get("transparency_templates", {})
            for key in ("automation_notice", "opt_out_ack"):
                block = transparency.get(key)
                if block:
                    extra_blocks.append(block.strip())
            automod_content = base_content
            if extra_blocks:
                automod_content = base_content.rstrip() + "\n\n" + "\n\n".join(extra_blocks) + "\n"
            automod_content = self._sanitize_wiki_text(automod_content)
            
            # Find textarea and insert rules
            textarea = self._find_first(
                [
                    (By.NAME, "content"),
                    (By.ID, "wiki_page_content"),
                    (By.CSS_SELECTOR, "textarea[name='content']"),
                    (By.CSS_SELECTOR, "textarea"),
                ],
                wait_seconds=10,
            )
            if not textarea:
                # Fallback: pick the largest visible textarea
                try:
                    textareas = [t for t in self.driver.find_elements(By.TAG_NAME, "textarea") if t.is_displayed()]
                    if textareas:
                        textarea = sorted(
                            textareas,
                            key=lambda t: (t.size.get("height", 0) * t.size.get("width", 0)),
                            reverse=True,
                        )[0]
                except Exception:
                    textarea = None
            if not textarea:
                logger.error("AutoModerator textarea not found on old Reddit page")
                return False

            # If existing matches desired, skip
            existing_val = (textarea.get_attribute("value") or "").strip()
            if existing_val == automod_content.strip():
                logger.info("AutoModerator content already up to date; skipping write")
                return True

            textarea.clear()
            if not self._set_field_value(textarea, automod_content):
                logger.error("Failed to set AutoModerator content")
                return False
            time.sleep(2)

            # Optional: fill revision reason if present
            try:
                reason_input = self._find_first(
                    [
                        (By.NAME, "reason"),
                        (By.NAME, "reasonforrevision"),
                        (By.CSS_SELECTOR, "input[name*='reason']"),
                    ],
                    wait_seconds=1,
                )
                if reason_input:
                    self._set_field_value(reason_input, "initial automod setup")
            except Exception:
                pass

            # Save
            save_button = self._find_first(
                [
                    (By.CSS_SELECTOR, "#wiki_save_button"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.CSS_SELECTOR, "input[name='save']"),
                    (By.CSS_SELECTOR, "input[value='save page']"),
                    (By.XPATH, "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                    (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                ]
            )
            if save_button:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", save_button)
                    time.sleep(0.2)
                    save_button.click()
                except Exception:
                    try:
                        self.driver.execute_script("arguments[0].click();", save_button)
                    except Exception:
                        pass
            else:
                logger.warning("AutoModerator save button not found on old UI page")
            time.sleep(3)

            # Single verification pass: ensure page exists once after save
            view_url = f"https://old.reddit.com/r/{subreddit_name}/wiki/config/automoderator"
            self.moderation_urls_used.append(view_url)
            logger.info("Using old Reddit URL: %s", view_url)
            self.driver.get(view_url)
            time.sleep(2)
            if "page \"config/automoderator\" was not found" in self.driver.page_source.lower():
                logger.warning("AutoModerator page not found after save (url=%s title=%s)", self.driver.current_url, self.driver.title)
                return False

            logger.info(f"AutoModerator configured for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up AutoModerator for r/{subreddit_name}: {e}")
            return False
    
    def setup_post_flairs(self, subreddit_name: str) -> bool:
        """Setup post flairs for the subreddit"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would set up post flairs for r/%s", subreddit_name)
                return True
            if not self.navigate_to_subreddit(subreddit_name, "about/flair"):
                logger.error(f"Cannot access flair settings for r/{subreddit_name}")
                return False
            
            # Switch to link flair (post flair) section
            self._click_first(
                [
                    (By.CSS_SELECTOR, "a[href$='link_templates']"),
                    (By.CSS_SELECTOR, "a[href*='link_templates']"),
                    (By.CSS_SELECTOR, "a[href$='link_flair']"),
                    (By.CSS_SELECTOR, "a[href*='link_flair']"),
                    (By.XPATH, "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'post flair')]"),
                    (By.XPATH, "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'link flair')]"),
                ]
            )
            time.sleep(2)
            
            # Get flairs from config
            flairs = self.config["flairs"]["post_flairs"]
            existing_names = set(
                (el.get_attribute("value") or "").strip().lower()
                for el in self.driver.find_elements(By.NAME, "text")
                if (el.get_attribute("value") or "").strip()
            )
            
            for flair in flairs:
                if flair["name"].strip().lower() in existing_names:
                    continue
                try:
                    def find_link_form_with_empty():
                        for f in self.driver.find_elements(By.CSS_SELECTOR, "form"):
                            try:
                                flair_type = f.find_element(By.NAME, "flair_type").get_attribute("value")
                                if (flair_type or "").upper() != "LINK_FLAIR":
                                    continue
                                text_inputs = f.find_elements(By.NAME, "text")
                                for inp in text_inputs:
                                    if not (inp.get_attribute("value") or "").strip():
                                        return f, inp
                            except Exception:
                                continue
                        # Fallback: empty template container
                        try:
                            empty_row = self.driver.find_element(By.ID, "empty-link-flair-template")
                            empty_form = empty_row.find_element(By.CSS_SELECTOR, "form")
                            empty_text = empty_form.find_element(By.NAME, "text")
                            if not (empty_text.get_attribute("value") or "").strip():
                                return empty_form, empty_text
                        except Exception:
                            pass
                        return None, None

                    # Re-find LINK_FLAIR form each time (page refreshes on save)
                    link_form, empty_text = find_link_form_with_empty()
                    if not link_form or not empty_text:
                        # Reload templates page once to get a fresh blank row
                        self.driver.get(f"https://old.reddit.com/r/{subreddit_name}/about/flair#link_templates")
                        time.sleep(2)
                        link_form, empty_text = find_link_form_with_empty()
                    if not link_form or not empty_text:
                        raise NoSuchElementException("No empty flair text input found")

                    if not self._set_field_value(empty_text, flair["name"]):
                        raise NoSuchElementException("Failed to set flair text")
                    time.sleep(0.3)

                    # Best-effort CSS class/color (old UI uses CSS class)
                    css_inputs = link_form.find_elements(By.NAME, "css_class")
                    if css_inputs:
                        self._set_field_value(css_inputs[-1], flair.get("css_class", "").strip())
                    time.sleep(0.3)

                    # Save row (old UI submits the templates form)
                    try:
                        submit_btn = link_form.find_element(By.XPATH, ".//button[@type='submit'] | .//input[@type='submit']")
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
                        submit_btn.click()
                        time.sleep(1)
                        # Wait briefly for page to refresh
                        time.sleep(1)
                    except Exception:
                        try:
                            save_in_row = self._find_first(
                                [
                                    (By.XPATH, ".//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                                    (By.XPATH, ".//input[@type='submit' or @type='button'][contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                                ],
                                wait_seconds=1,
                            )
                            if save_in_row:
                                save_in_row.click()
                                time.sleep(0.5)
                        except Exception:
                            pass
                
                except Exception as e:
                    logger.warning(f"Error creating flair '{flair['name']}': {e}")
                    continue
            
            # Click save button at bottom
            save_clicked = self._click_first(
                [
                    (By.CSS_SELECTOR, "button.save-button"),
                    (By.CSS_SELECTOR, "button.saveoptions"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                ]
            )
            if save_clicked:
                time.sleep(2)
            
            logger.info(f"Created {len(flairs)} post flairs for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up post flairs for r/{subreddit_name}: {e}")
            return False
    
    def setup_user_flairs(self, subreddit_name: str) -> bool:
        """Setup user flairs for the subreddit"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would set up user flairs for r/%s", subreddit_name)
                return True
            if not self.navigate_to_subreddit(subreddit_name, "about/flair"):
                logger.error(f"Cannot access flair settings for r/{subreddit_name}")
                return False
            
            # Switch to user flair section
            self._click_first(
                [
                    (By.CSS_SELECTOR, "a[href$='user_templates']"),
                    (By.CSS_SELECTOR, "a[href*='user_templates']"),
                    (By.CSS_SELECTOR, "a[href$='user_flair']"),
                    (By.CSS_SELECTOR, "a[href*='user_flair']"),
                    (By.XPATH, "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'user flair')]"),
                ]
            )
            time.sleep(2)
            
            # Get flairs from config
            flairs = self.config["flairs"]["user_flairs"]
            existing_names = set(
                (el.get_attribute("value") or "").strip().lower()
                for el in self.driver.find_elements(By.NAME, "text")
                if (el.get_attribute("value") or "").strip()
            )

            for flair in flairs:
                if flair["name"].strip().lower() in existing_names:
                    continue
                try:
                    def find_user_form_with_empty():
                        for f in self.driver.find_elements(By.CSS_SELECTOR, "form"):
                            try:
                                flair_type = f.find_element(By.NAME, "flair_type").get_attribute("value")
                                if (flair_type or "").upper() != "USER_FLAIR":
                                    continue
                                text_inputs = f.find_elements(By.NAME, "text")
                                for inp in text_inputs:
                                    if not (inp.get_attribute("value") or "").strip():
                                        return f, inp
                            except Exception:
                                continue
                        try:
                            empty_row = self.driver.find_element(By.ID, "empty-user-flair-template")
                            empty_form = empty_row.find_element(By.CSS_SELECTOR, "form")
                            empty_text = empty_form.find_element(By.NAME, "text")
                            if not (empty_text.get_attribute("value") or "").strip():
                                return empty_form, empty_text
                        except Exception:
                            pass
                        return None, None

                    # Re-find USER_FLAIR form each time (page refreshes on save)
                    user_form, empty_text = find_user_form_with_empty()
                    if not user_form or not empty_text:
                        self.driver.get(f"https://old.reddit.com/r/{subreddit_name}/about/flair#user_templates")
                        time.sleep(2)
                        user_form, empty_text = find_user_form_with_empty()
                    if not user_form or not empty_text:
                        raise NoSuchElementException("No empty user flair text input found")

                    if not self._set_field_value(empty_text, flair["name"]):
                        raise NoSuchElementException("Failed to set user flair text")
                    time.sleep(0.3)

                    css_inputs = user_form.find_elements(By.NAME, "css_class")
                    if css_inputs:
                        self._set_field_value(css_inputs[-1], flair.get("css_class", "").strip())
                    time.sleep(0.3)

                    # Save row (old UI submits the templates form)
                    try:
                        submit_btn = user_form.find_element(By.XPATH, ".//button[@type='submit'] | .//input[@type='submit']")
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
                        submit_btn.click()
                        time.sleep(1)
                        time.sleep(1)
                    except Exception:
                        try:
                            save_in_row = self._find_first(
                                [
                                    (By.XPATH, ".//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                                    (By.XPATH, ".//input[@type='submit' or @type='button'][contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                                ],
                                wait_seconds=1,
                            )
                            if save_in_row:
                                save_in_row.click()
                                time.sleep(0.5)
                        except Exception:
                            pass
                
                except Exception as e:
                    logger.warning(f"Error creating user flair '{flair['name']}': {e}")
                    continue
            
            # Click save button at bottom
            save_clicked = self._click_first(
                [
                    (By.CSS_SELECTOR, "button.save-button"),
                    (By.CSS_SELECTOR, "button.saveoptions"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                ]
            )
            if save_clicked:
                time.sleep(2)
            
            logger.info(f"Created {len(flairs)} user flairs for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up user flairs for r/{subreddit_name}: {e}")
            return False

    def setup_wiki_pages(self, subreddit_name: str) -> bool:
        """Create or update basic wiki pages for SEO/discoverability."""
        seo = self._load_seo_config()
        default = seo.get("default", {})
        specific = seo.get(subreddit_name, {})
        pages = specific.get("wiki_pages") or default.get("wiki_pages") or {}
        if not pages:
            return True
        if self.dry_run:
            logger.info("[dry-run] Would update wiki pages for r/%s", subreddit_name)
            return True
        ok = True
        for page, content in pages.items():
            try:
                edit_url = f"https://old.reddit.com/r/{subreddit_name}/wiki/edit/{page}"
                self.driver.get(edit_url)
                time.sleep(2)
                textarea = self._find_first(
                    [
                        (By.CSS_SELECTOR, "textarea#content"),
                        (By.CSS_SELECTOR, "textarea[name='content']"),
                        (By.CSS_SELECTOR, "textarea"),
                    ],
                    wait_seconds=3,
                )
                if not textarea:
                    logger.warning("Wiki textarea not found for %s", page)
                    ok = False
                    continue
                textarea.clear()
                textarea.send_keys(content)
                saved = self._click_first(
                    [
                        (By.CSS_SELECTOR, "button[type='submit']"),
                        (By.CSS_SELECTOR, "input[type='submit']"),
                        (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                    ],
                    wait_seconds=2,
                )
                if not saved:
                    logger.warning("Wiki save button not found for %s", page)
                    ok = False
                time.sleep(1)
            except Exception as exc:
                logger.warning("Wiki update failed for %s: %s", page, exc)
                ok = False
        return ok
    
    def setup_subreddit_rules(self, subreddit_name: str) -> bool:
        """Setup subreddit rules"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would set up rules for r/%s", subreddit_name)
                return True
            if not self.navigate_to_subreddit(subreddit_name, "about/rules"):
                logger.error(f"Cannot access rules settings for r/{subreddit_name}")
                return False
            
            rules = self.config["subreddit_rules"]

            # Collect existing short names so we don't duplicate
            existing_names = set()
            try:
                existing_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[name*='short'], input[name*='title']")
                for inp in existing_inputs:
                    val = (inp.get_attribute("value") or "").strip().lower()
                    if val:
                        existing_names.add(val)
                # New UI sometimes shows rule chips/text
                for label in self.driver.find_elements(By.CSS_SELECTOR, ".rule-name, .RuleCard__title, .rule-title"):
                    text = (label.text or "").strip().lower()
                    if text:
                        existing_names.add(text)
            except Exception:
                pass
            
            for i, rule_text in enumerate(rules, 1):
                if rule_text.strip().lower() in existing_names:
                    continue
                try:
                    # Click "Add rule" button (old or new UI)
                    add_clicked = self._click_first(
                        [
                            (By.CSS_SELECTOR, "button.subreddit-rule-add-button"),
                            (By.CSS_SELECTOR, "button.add-rule"),
                            (By.CSS_SELECTOR, "a.add-rule"),
                            (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add a rule')]"),
                            (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add rule')]"),
                            (By.XPATH, "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add a rule')]"),
                        ]
                    )
                    time.sleep(1)

                    # New UI rules editor (form already visible)
                    short_name = self._find_first(
                        [
                            (By.XPATH, "//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'short name')]/following::input[1]"),
                            (By.XPATH, "//input[contains(@aria-label,'Short name')]"),
                            (By.CSS_SELECTOR, "input[name*='short']"),
                        ],
                        wait_seconds=2,
                    )
                    if short_name:
                        self._set_field_value(short_name, rule_text[:100])
                        time.sleep(0.2)
                        reason_input = self._find_first(
                            [
                                (By.XPATH, "//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'violation')]/following::input[1]"),
                                (By.XPATH, "//input[contains(@aria-label,'Violation')]"),
                                (By.CSS_SELECTOR, "input[name*='reason']"),
                            ],
                            wait_seconds=2,
                        )
                        if reason_input:
                            self._set_field_value(reason_input, f"Violates rule {i}")
                        desc_input = self._find_first(
                            [
                                (By.XPATH, "//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'full description')]/following::textarea[1]"),
                                (By.CSS_SELECTOR, "textarea[name*='description']"),
                                (By.CSS_SELECTOR, "textarea"),
                            ],
                            wait_seconds=2,
                        )
                        if desc_input:
                            self._set_field_value(desc_input, rule_text)

                        # Save rule (green check / save button)
                        saved = self._click_first(
                            [
                                (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                                (By.XPATH, "//button[contains(@aria-label,'Save')]"),
                                (By.XPATH, "//button[contains(@aria-label,'Add rule')]"),
                                (By.CSS_SELECTOR, "button[aria-label*='save' i]"),
                                (By.CSS_SELECTOR, "button[title*='save' i]"),
                                (By.CSS_SELECTOR, "button.subreddit-rule-submit-button"),
                            ],
                            wait_seconds=2,
                        )
                        if not saved:
                            # Fallback: click the last visible button in the rule editor container (green check)
                            try:
                                container = desc_input.find_element(By.XPATH, "./ancestor::form[1]")
                                try:
                                    debug_buttons = []
                                    for b in container.find_elements(By.TAG_NAME, "button"):
                                        debug_buttons.append({
                                            "text": (b.text or "").strip(),
                                            "aria": b.get_attribute("aria-label") or "",
                                            "title": b.get_attribute("title") or "",
                                            "class": b.get_attribute("class") or "",
                                            "displayed": bool(b.is_displayed()),
                                        })
                                    logger.info("Rule editor buttons: %s", debug_buttons)
                                except Exception:
                                    pass
                                buttons = [b for b in container.find_elements(By.TAG_NAME, "button") if b.is_displayed()]
                                if buttons:
                                    try:
                                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", buttons[-1])
                                        buttons[-1].click()
                                        saved = True
                                    except Exception:
                                        self.driver.execute_script("arguments[0].click();", buttons[-1])
                                        saved = True
                            except Exception:
                                pass
                        if not saved:
                            raise NoSuchElementException("Rule save button not found")
                        time.sleep(1)
                        continue

                    # Old UI rule rows
                    rule_rows = self.driver.find_elements(By.CSS_SELECTOR, ".rule-row, .rule, tr.rule")
                    new_row = rule_rows[-1] if rule_rows else None

                    if new_row:
                        text_input = self._find_first(
                            [
                                (By.CSS_SELECTOR, "input.rule-input"),
                                (By.CSS_SELECTOR, "input[name*='short']"),
                                (By.CSS_SELECTOR, "input[name*='title']"),
                                (By.CSS_SELECTOR, "input[type='text']"),
                            ],
                            wait_seconds=3,
                        )
                        if text_input:
                            self._set_field_value(text_input, rule_text[:100])
                        time.sleep(0.5)

                        reason_input = self._find_first(
                            [
                                (By.CSS_SELECTOR, "input.reason-input"),
                                (By.CSS_SELECTOR, "input[name*='reason']"),
                                (By.CSS_SELECTOR, "input[name*='violation']"),
                            ],
                            wait_seconds=2,
                        )
                        if reason_input:
                            self._set_field_value(reason_input, f"Violates rule {i}")
                        time.sleep(0.5)

                        desc_input = self._find_first(
                            [
                                (By.CSS_SELECTOR, "textarea"),
                                (By.CSS_SELECTOR, "textarea[name*='description']"),
                                (By.CSS_SELECTOR, "textarea[name*='long']"),
                            ],
                            wait_seconds=1,
                        )
                        if desc_input:
                            self._set_field_value(desc_input, rule_text)
                
                except Exception as e:
                    logger.warning(f"Error adding rule {i}: {e}")
                    continue
            
            # Click save button
            save_clicked = self._click_first(
                [
                    (By.CSS_SELECTOR, "button.save-rules"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                ]
            )
            if save_clicked:
                time.sleep(2)
                logger.info(f"Rules saved for r/{subreddit_name}")
            else:
                logger.warning("Could not find save button, rules may not have been saved")
            
            logger.info(f"Added {len(rules)} rules for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up rules for r/{subreddit_name}: {e}")
            return False
    
    def configure_subreddit_settings(self, subreddit_name: str) -> bool:
        """Configure basic subreddit settings"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would configure settings for r/%s", subreddit_name)
                return True
            if not self.navigate_to_subreddit(subreddit_name, "about/edit"):
                logger.error(f"Cannot access edit settings for r/{subreddit_name}")
                return False
            
            changes_made = False

            try:
                # Allow images
                images_checkbox = self.driver.find_element(By.NAME, "allow_images")
                if not images_checkbox.is_selected():
                    images_checkbox.click()
                    time.sleep(0.5)
                    changes_made = True
            except:
                pass
            
            try:
                # Allow videos
                videos_checkbox = self.driver.find_element(By.NAME, "allow_videos")
                if not videos_checkbox.is_selected():
                    videos_checkbox.click()
                    time.sleep(0.5)
                    changes_made = True
            except:
                pass
            
            try:
                # Set to public
                public_radio = self.driver.find_element(By.CSS_SELECTOR, "input[value='public']")
                if not public_radio.is_selected():
                    public_radio.click()
                    time.sleep(0.5)
                    changes_made = True
            except:
                pass

            # Ensure wiki is enabled (needed for AutoModerator)
            try:
                wiki_radio = self._find_first(
                    [
                        (By.CSS_SELECTOR, "input[name='wikimode'][value='mod']"),
                        (By.CSS_SELECTOR, "input[name='wikimode'][value='any']"),
                        (By.CSS_SELECTOR, "input[name='wikimode'][value='0']"),
                    ],
                    wait_seconds=2,
                )
                if wiki_radio and not wiki_radio.is_selected():
                    wiki_radio.click()
                    time.sleep(0.2)
                    changes_made = True
            except Exception:
                pass
            
            if changes_made:
                save_clicked = self._click_first(
                    [
                        (By.CSS_SELECTOR, "button[type='submit']"),
                        (By.CSS_SELECTOR, "input[type='submit']"),
                        (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                        (By.XPATH, "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]"),
                    ],
                    wait_seconds=2,
                )
                if save_clicked:
                    time.sleep(3)
                    logger.info(f"Settings saved for r/{subreddit_name}")
                else:
                    logger.warning("Could not find save button")
            else:
                logger.info(f"No setting changes needed for r/{subreddit_name}; skipping save")
            
            logger.info(f"Configured minimal settings for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring settings for r/{subreddit_name}: {e}")
            return False

    def refresh_sidebar_network_links(self, subreddit_names: List[str]) -> Dict[str, bool]:
        results = {}
        for subreddit_name in subreddit_names:
            try:
                if not self.navigate_to_subreddit(subreddit_name, "about/edit"):
                    logger.error("Cannot access edit settings for r/%s", subreddit_name)
                    results[subreddit_name] = False
                    continue
                sidebar_field = self.driver.find_element(By.ID, "description")
                current_sidebar = sidebar_field.get_attribute("value") or ""
                updated_sidebar = self._append_network_links(current_sidebar, subreddit_name)
                if updated_sidebar != current_sidebar:
                    sidebar_field.clear()
                    sidebar_field.send_keys(updated_sidebar)
                    time.sleep(0.5)
                    self._click_first(
                        [
                            (By.CSS_SELECTOR, "button[type='submit']"),
                            (By.CSS_SELECTOR, "input[type='submit']"),
                        ],
                        wait_seconds=2,
                    )
                    time.sleep(2)
                results[subreddit_name] = True
            except Exception as exc:
                logger.error("Sidebar refresh failed for r/%s: %s", subreddit_name, exc)
                results[subreddit_name] = False
        return results
    
    def generate_sidebar_content(self, subreddit_name: str) -> str:
        """Generate sidebar content for subreddit"""
        base = f"""**Welcome to r/{subreddit_name}!**

## About This Community
This is a research-focused community for evidence-based discussions about psychedelic microdosing, mental health, and consciousness studies.

## Community Guidelines
1. Be respectful and kind to all members
2. No sourcing or discussion of acquiring substances
3. Share experiences, not medical advice
4. Practice harm reduction principles
5. Cite sources when discussing research

## Resources
- [MCRDSE Research Portal](https://mcrdse.com/research)
- [Safety Guidelines](https://mcrdse.com/safety)
- [Academic Studies](https://mcrdse.com/studies)

## Disclaimer
This community is for educational purposes only. Not medical advice.

---
*Part of the MCRDSE network - Advancing psychedelic research and education.*"""
        return self._append_network_links(base, subreddit_name)

    def _append_network_links(self, sidebar: str, subreddit_name: str) -> str:
        try:
            path = Path("config/subreddit_network.json")
            if not path.exists():
                return sidebar
            network = json.loads(path.read_text())
            if not network.get("enabled"):
                return sidebar
            if "## Network Links" in sidebar:
                return sidebar
            cross = network.get("cross_promotion", {})
            related_map = cross.get("related_map", {})
            links_per = int(cross.get("links_per_sidebar", 3))
            related = related_map.get(subreddit_name, [])
            if not related:
                return sidebar
            related = related[:links_per]
            links = "\n".join([f"- r/{name}" for name in related])
            return sidebar + "\n\n## Network Links\n" + links
        except Exception:
            return sidebar

    def _load_seo_config(self) -> Dict:
        path = Path("config/seo/subreddit_seo.json")
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _apply_seo_description(self, subreddit_name: str, description: str) -> str:
        seo = self._load_seo_config()
        default = seo.get("default", {})
        specific = seo.get(subreddit_name, {})
        desc_keywords = (specific.get("description_keywords") or default.get("description_keywords") or [])[:6]
        if not desc_keywords:
            return description
        keyword_line = "Keywords: " + ", ".join(desc_keywords)
        if keyword_line.lower() in (description or "").lower():
            return description
        return f"{(description or '').strip()} {keyword_line}".strip()

    def _apply_seo_sidebar(self, subreddit_name: str, sidebar: str) -> str:
        seo = self._load_seo_config()
        default = seo.get("default", {})
        specific = seo.get(subreddit_name, {})
        side_keywords = (specific.get("sidebar_keywords") or default.get("sidebar_keywords") or [])[:8]
        if not side_keywords:
            return sidebar
        if "## Keywords" in (sidebar or ""):
            return sidebar
        sidebar = (sidebar or "").rstrip()
        sidebar += "\n\n## Keywords\n" + "\n".join([f"- {kw}" for kw in side_keywords])
        return sidebar
    
    def _process_queue_items(self, subreddit_name: str) -> Dict:
        if self.dry_run:
            logger.info("[dry-run] Would process queue items for r/%s", subreddit_name)
            return {
                "subreddit": subreddit_name,
                "timestamp": datetime.now().isoformat(),
                "total_items": 0,
                "approved": 0,
                "removed": 0,
                "ignored": 0,
                "processed_items": [],
            }
        stats = {
            "subreddit": subreddit_name,
            "timestamp": datetime.now().isoformat(),
            "total_items": 0,
            "approved": 0,
            "removed": 0,
            "ignored": 0,
            "processed_items": [],
        }

        queue_items = self.driver.find_elements(By.CSS_SELECTOR, ".thing")
        if self.config.get("quality_scoring", {}).get("enabled"):
            scored = []
            for item in queue_items:
                try:
                    score = self._score_item_from_element(item)
                except Exception:
                    score = 0.0
                scored.append((score, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            queue_items = [i for _s, i in scored]
        max_items = self.config["moderation"].get("queue_processing_limit", 10)
        max_items = min(max_items, self.activity_limits.get("max_actions_per_run", max_items))

        for item in queue_items[:max_items]:
            try:
                item_stats = self.process_queue_item(item, subreddit_name)
                stats["total_items"] += 1

                if item_stats["action"] == "approved":
                    stats["approved"] += 1
                elif item_stats["action"] == "removed":
                    stats["removed"] += 1
                else:
                    stats["ignored"] += 1

                stats["processed_items"].append(item_stats)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Error processing queue item: {e}")
                continue

        logger.info(f"Processed {stats['total_items']} items in r/{subreddit_name} queue")
        return stats

    def check_moderation_queue(self, subreddit_name: str) -> Dict:
        """Check and process moderation queue"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/modqueue"):
                logger.error(f"Cannot access mod queue for r/{subreddit_name}")
                return {}
            return self._process_queue_items(subreddit_name)
        except Exception as e:
            logger.error(f"Error checking moderation queue for r/{subreddit_name}: {e}")
            return {}
    
    def process_queue_item(self, item_element, subreddit_name: str) -> Dict:
        """Process a single queue item"""
        item_info = {
            "type": "unknown",
            "title": "",
            "author": "",
            "reason": "",
            "action": "ignored",
            "timestamp": datetime.now().isoformat(),
            "subreddit": subreddit_name,
        }
        
        try:
            # Get item type (post or comment)
            if "comment" in item_element.get_attribute("class"):
                item_info["type"] = "comment"
            else:
                item_info["type"] = "post"
            
            # Get title/author
            try:
                title_elem = item_element.find_element(By.CSS_SELECTOR, "a.title")
                item_info["title"] = title_elem.text[:100]
            except:
                pass
            
            try:
                author_elem = item_element.find_element(By.CSS_SELECTOR, ".author")
                item_info["author"] = author_elem.text
            except:
                pass
            
            # Get report reason
            try:
                reason_elem = item_element.find_element(By.CSS_SELECTOR, ".report-reason")
                item_info["reason"] = reason_elem.text
            except:
                pass

            # Optional: extract body and comment count
            item_info["body"] = self._extract_body_text(item_element)
            item_info["comment_count"] = self._extract_comment_count(item_element)

            # Quality scoring
            if self.config.get("quality_scoring", {}).get("enabled"):
                item_info["scores"] = self._score_item(item_info)
                item_info["priority"] = self._priority_from_scores(item_info["scores"])
                if self._should_escalate(item_info):
                    item_info["priority"] = "escalate"
            
            # Analyze content
            should_remove = self.should_remove_item(item_element, item_info)
            can_auto_approve = self._can_auto_approve(item_info)
            
            # Take action conservatively
            if should_remove:
                self.remove_item(item_element)
                item_info["action"] = "removed"
            elif can_auto_approve and not self.config["moderation"].get("conservative_mode", True):
                self.approve_item(item_element)
                item_info["action"] = "approved"
            elif can_auto_approve and self.config["moderation"].get("conservative_mode", True):
                # Conservative: approve only if trusted
                if item_info.get("author") in self.config["moderation"].get("trusted_authors", []):
                    self.approve_item(item_element)
                    item_info["action"] = "approved"
                else:
                    item_info["action"] = "ignored"
            else:
                item_info["action"] = "ignored"

            # Template suggestion (no auto-comment; for mod use)
            item_info["template_suggestion"] = self._pick_moderation_template(item_info)
            # Transparency log for significant actions
            if item_info["action"] in ("approved", "removed") or item_info.get("priority") == "escalate":
                self._write_transparency_log(item_info)

            self.status_tracker.record_moderation_activity(
                self.account_name,
                item_info.get("subreddit", "unknown"),
                item_info["action"],
                item_info["action"] in ("approved", "removed"),
            )
            
        except Exception as e:
            logger.warning(f"Error in process_queue_item: {e}")
        
        return item_info

    def _extract_body_text(self, item_element) -> str:
        selectors = [
            ".usertext-body",
            ".md",
            "div[data-test-id='post-content']",
        ]
        for sel in selectors:
            try:
                el = item_element.find_element(By.CSS_SELECTOR, sel)
                text = (el.text or "").strip()
                if text:
                    return text[:1000]
            except Exception:
                continue
        return ""

    def _extract_comment_count(self, item_element) -> int:
        try:
            links = item_element.find_elements(By.CSS_SELECTOR, "a.comments, a[href*='/comments/']")
            for link in links:
                text = (link.text or "").lower()
                for token in text.split():
                    if token.isdigit():
                        return int(token)
        except Exception:
            pass
        return 0

    def _score_content_quality(self, item_info: Dict) -> float:
        text = (item_info.get("title", "") + " " + item_info.get("body", "")).strip()
        length = len(text)
        min_len = int(self.config.get("quality_scoring", {}).get("min_quality_length", 120))
        length_score = min(1.0, max(0.0, length / max(min_len, 1)))

        # Readability proxy: average sentence length
        sentences = [s for s in text.replace("\n", " ").split(".") if s.strip()]
        avg_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
        readability = 1.0 if avg_len <= 20 else 0.7 if avg_len <= 30 else 0.4

        # Source presence
        source_keywords = self.config.get("quality_scoring", {}).get("source_keywords", [])
        has_source = any(k.lower() in text.lower() for k in source_keywords)
        source_score = 1.0 if has_source else 0.4

        return round((0.5 * length_score) + (0.3 * readability) + (0.2 * source_score), 2)

    def _score_user_trust(self, item_info: Dict) -> float:
        author = item_info.get("author", "")
        trusted = self.config["moderation"].get("trusted_authors", [])
        if author and author in trusted:
            return 0.9
        reason = (item_info.get("reason") or "").lower()
        if "new account" in reason or "low karma" in reason:
            return 0.2
        return 0.4

    def _score_discussion_health(self, item_info: Dict) -> float:
        comments = item_info.get("comment_count", 0) or 0
        if comments >= 15:
            return 0.9
        if comments >= 5:
            return 0.6
        if comments >= 1:
            return 0.4
        return 0.2

    def _score_item(self, item_info: Dict) -> Dict[str, float]:
        qs = self._score_content_quality(item_info)
        us = self._score_user_trust(item_info)
        ds = self._score_discussion_health(item_info)
        weights = self.config.get("quality_scoring", {}).get("weights", {})
        score = (
            qs * float(weights.get("content_quality", 0.4))
            + us * float(weights.get("user_trust", 0.3))
            + ds * float(weights.get("discussion_health", 0.3))
        )
        return {"content_quality": qs, "user_trust": us, "discussion_health": ds, "overall": round(score, 2)}

    def _score_item_from_element(self, item_element) -> float:
        info = {
            "title": "",
            "body": "",
            "reason": "",
            "author": "",
            "comment_count": 0,
        }
        try:
            info["title"] = (item_element.find_element(By.CSS_SELECTOR, "a.title").text or "")[:100]
        except Exception:
            pass
        try:
            info["author"] = (item_element.find_element(By.CSS_SELECTOR, ".author").text or "")
        except Exception:
            pass
        try:
            info["reason"] = (item_element.find_element(By.CSS_SELECTOR, ".report-reason").text or "")
        except Exception:
            pass
        info["body"] = self._extract_body_text(item_element)
        info["comment_count"] = self._extract_comment_count(item_element)
        return self._score_item(info)["overall"]

    def _priority_from_scores(self, scores: Dict[str, float]) -> str:
        thresholds = self.config.get("quality_scoring", {}).get("priority_thresholds", {})
        high = float(thresholds.get("high", 0.7))
        medium = float(thresholds.get("medium", 0.45))
        overall = scores.get("overall", 0.0)
        if overall >= high:
            return "high"
        if overall >= medium:
            return "medium"
        return "low"

    def _pick_moderation_template(self, item_info: Dict) -> str:
        if not self.moderation_templates:
            return ""
        reason = (item_info.get("reason") or "").lower()
        if "low detail" in reason or "short" in reason:
            pool = self.moderation_templates.get("quality_enforcement", [])
        elif "sourcing" in reason:
            pool = self.moderation_templates.get("resource_suggestions", [])
        else:
            pool = self.moderation_templates.get("conversation_starter", []) or self.moderation_templates.get("default", [])
        return random.choice(pool) if pool else ""

    def _should_escalate(self, item_info: Dict) -> bool:
        conflict = self.governance.get("conflict_resolution", {})
        keywords = [k.lower() for k in conflict.get("auto_escalation_keywords", [])]
        severe = [k.lower() for k in conflict.get("severe_keywords", [])]
        text = " ".join(
            [
                (item_info.get("title") or ""),
                (item_info.get("body") or ""),
                (item_info.get("reason") or ""),
            ]
        ).lower()
        if any(k in text for k in severe):
            return True
        hits = sum(1 for k in keywords if k in text)
        threshold = int(conflict.get("escalation_threshold", 1))
        return hits >= threshold

    def _write_transparency_log(self, item_info: Dict) -> None:
        conflict = self.governance.get("conflict_resolution", {})
        if not conflict.get("public_log_enabled", True):
            return
        out_dir = Path("logs")
        out_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": item_info.get("timestamp"),
            "subreddit": item_info.get("subreddit"),
            "title": item_info.get("title"),
            "author": item_info.get("author"),
            "action": item_info.get("action"),
            "reason": item_info.get("reason"),
            "priority": item_info.get("priority"),
        }
        # JSONL
        with (out_dir / "moderation_transparency.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Markdown summary
        md = out_dir / "moderation_transparency.md"
        if not md.exists():
            md.write_text("# Moderation Transparency Log\n\n")
        with md.open("a", encoding="utf-8") as f:
            f.write(
                f"- {entry['timestamp']} | r/{entry['subreddit']} | {entry['action']} | {entry['title']}\n"
            )
    
    def should_remove_item(self, item_element, item_info: Dict) -> bool:
        """Determine if an item should be removed"""
        content = ""
        
        try:
            # Get content text
            if item_info["type"] == "post":
                # Try to get post content
                try:
                    content_elem = item_element.find_element(By.CSS_SELECTOR, ".md")
                    content = content_elem.text.lower()
                except:
                    content = item_info.get("title", "").lower()
            else:
                # For comments
                try:
                    content_elem = item_element.find_element(By.CSS_SELECTOR, ".md")
                    content = content_elem.text.lower()
                except:
                    pass
        except:
            pass
        
        # Check against removal criteria
        removal_keywords = self.config["moderation"]["remove_spam_keywords"] + \
                          self.config["moderation"]["remove_self_harm_keywords"]
        
        for keyword in removal_keywords:
            if keyword.lower() in content:
                return True
        
        # Check for new account/low karma (simplified)
        try:
            # This would require parsing user info, which is complex
            # For now, we'll trust AutoModerator's filtering
            pass
        except:
            pass
        
        return False

    def _can_auto_approve(self, item_info: Dict) -> bool:
        if not self.config["moderation"].get("auto_approve_trusted_users", True):
            return False
        trusted = self.config["moderation"].get("trusted_authors", [])
        return item_info.get("author") in trusted
    
    def approve_item(self, item_element):
        """Approve a queue item"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would approve item")
                return
            # Find approve button
            approve_button = item_element.find_element(By.CSS_SELECTOR, "button.approve")
            approve_button.click()
            time.sleep(0.5)
        except:
            logger.warning("Could not find approve button")
    
    def remove_item(self, item_element):
        """Remove a queue item"""
        try:
            if self.dry_run:
                logger.info("[dry-run] Would remove item")
                return
            # Find remove button
            remove_button = item_element.find_element(By.CSS_SELECTOR, "button.remove")
            remove_button.click()
            time.sleep(0.5)
            
            # Sometimes there's a removal reason dropdown
            try:
                removal_reason = Select(item_element.find_element(By.CSS_SELECTOR, "select.remove-reason"))
                removal_reason.select_by_index(1)  # Select first reason
                time.sleep(0.5)
            except:
                pass
            
            # Confirm removal
            try:
                confirm_button = item_element.find_element(By.CSS_SELECTOR, "button.confirm-remove")
                confirm_button.click()
                time.sleep(0.5)
            except:
                pass
            
        except:
            logger.warning("Could not find remove button")
    
    def setup_complete_moderation(self, subreddit_name: str) -> bool:
        """Complete moderation setup for a subreddit"""
        if not self._can_moderate(subreddit_name):
            logger.info(f"Moderation limited for {self.account_name}; skipping r/{subreddit_name}")
            return False
        logger.info(f"Starting complete moderation setup for r/{subreddit_name}")
        
        steps = [
            ("Configure settings", self.configure_subreddit_settings),
            ("Setup AutoModerator", self.setup_automoderator),
            ("Setup post flairs", self.setup_post_flairs),
            ("Setup user flairs", self.setup_user_flairs),
            ("Setup rules", self.setup_subreddit_rules)
        ]
        
        success_count = 0
        for step_name, step_function in steps:
            try:
                logger.info(f"  Starting: {step_name}")
                result = self.execute_safely(
                    lambda: step_function(subreddit_name),
                    max_retries=2,
                    login_required=True,
                    action_name="moderation_action",
                )
                if result.success and result.result:
                    success_count += 1
                    logger.info(f"  ✓ {step_name} completed")
                    self.status_tracker.record_moderation_activity(
                        self.account_name, subreddit_name, step_name, True
                    )
                else:
                    logger.warning(f"  ✗ {step_name} failed")
                    self.status_tracker.record_moderation_activity(
                        self.account_name, subreddit_name, step_name, False
                    )
                
                # Delay between steps
                time.sleep(3)
                
            except Exception as e:
                logger.error(f"Error in {step_name}: {e}")
        
        logger.info(f"Completed {success_count}/{len(steps)} setup steps for r/{subreddit_name}")
        all_old = all("old.reddit.com" in url for url in self.moderation_urls_used) if self.moderation_urls_used else True
        logger.info("Moderation UI mode: %s (old-only=%s)", self.moderation_ui_mode, all_old)
        return success_count >= 3  # Require at least 3 successful steps

    def check_spam_queue(self, subreddit_name: str) -> Dict:
        """Check and process spam queue"""
        if not self.activity_limits.get("remove_spam", True):
            return {}
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/spam"):
                logger.error(f"Cannot access spam queue for r/{subreddit_name}")
                return {}
            return self._process_queue_items(subreddit_name)
        except Exception as exc:
            logger.error(f"Error checking spam queue for r/{subreddit_name}: {exc}")
            return {}

    def check_reported_queue(self, subreddit_name: str) -> Dict:
        """Check and process reported queue"""
        if not self.activity_limits.get("auto_remove_reported", False):
            return {}
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/reports"):
                logger.error(f"Cannot access reports for r/{subreddit_name}")
                return {}
            return self._process_queue_items(subreddit_name)
        except Exception as exc:
            logger.error(f"Error checking reports for r/{subreddit_name}: {exc}")
            return {}
    
    def run_daily_moderation(self, subreddit_names: List[str] = None):
        """Run daily moderation tasks for specified subreddits"""
        if subreddit_names is None:
            # Get subreddits from tracking file
            subreddit_names = self.get_managed_subreddits()
        
        logger.info(f"Starting daily moderation for {len(subreddit_names)} subreddits")
        
        results = {}
        for subreddit in subreddit_names:
            logger.info(f"Processing r/{subreddit}")
            if not self._can_moderate(subreddit):
                logger.info(f"No moderator access for r/{subreddit}; skipping")
                continue
            
            queue_result = self.execute_safely(
                lambda: self.check_moderation_queue(subreddit),
                max_retries=2,
                login_required=True,
                action_name="moderation_action",
            )
            queue_stats = queue_result.result if queue_result.success else None
            results[subreddit] = queue_stats
            self.status_tracker.record_moderation_activity(
                self.account_name, subreddit, "daily_moderation", bool(queue_result.success)
            )

            if self.activity_limits.get("remove_spam", True):
                self.execute_safely(
                    lambda: self.check_spam_queue(subreddit),
                    max_retries=1,
                    login_required=True,
                    action_name="moderation_action",
                )
            if self.activity_limits.get("auto_remove_reported", False):
                self.execute_safely(
                    lambda: self.check_reported_queue(subreddit),
                    max_retries=1,
                    login_required=True,
                    action_name="moderation_action",
                )
            
            # Delay between subreddits
            time.sleep(5)
        
        # Save results
        daily_file = Path(f"scripts/moderation/history/moderation_daily_{datetime.now().strftime('%Y%m%d')}.json")
        daily_file.parent.mkdir(exist_ok=True, parents=True)
        daily_file.write_text(json.dumps(results, indent=2))
        
        logger.info(f"Daily moderation complete. Results saved to {daily_file}")
        return results
    
    def get_managed_subreddits(self) -> List[str]:
        """Get list of subreddits we manage"""
        tracking_file = Path("data/created_subreddits.json")
        if tracking_file.exists():
            try:
                data = json.loads(tracking_file.read_text())
                if isinstance(data, list):
                    return [sub.get("subreddit") for sub in data if isinstance(sub, dict) and sub.get("subreddit")]
                return [sub.get("subreddit") for sub in data.get("subreddits", []) if isinstance(sub, dict) and sub.get("subreddit")]
            except:
                pass

        # Fallback to configured subreddits
        configured = self.config_manager.bot_settings.get("subreddits", [])
        if configured:
            return configured
        
        # Fallback: prompt user
        if not self.headless:
            subreddits_input = input("Enter subreddit names (comma-separated): ")
            return [s.strip() for s in subreddits_input.split(",") if s.strip()]
        
        return []
    
    def setup_all_moderation(self):
        """Setup moderation for all managed subreddits"""
        subreddits = self.get_managed_subreddits()
        
        if not subreddits:
            logger.error("No subreddits found to manage")
            return
        
        logger.info(f"Setting up moderation for {len(subreddits)} subreddits")
        
        results = {}
        for subreddit in subreddits:
            success = self.setup_complete_moderation(subreddit)
            results[subreddit] = {"success": success}
            time.sleep(5)  # Delay between subreddits
        
        # Save setup results
        setup_file = Path(f"scripts/moderation/history/moderation_setup_{datetime.now().strftime('%Y%m%d')}.json")
        setup_file.parent.mkdir(exist_ok=True, parents=True)
        setup_file.write_text(json.dumps(results, indent=2))
        
        logger.info(f"Setup complete. Results saved to {setup_file}")
        return results

def main():
    """Command-line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCRDSE Selenium Moderation Manager")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--subreddit", help="Subreddit to manage")
    parser.add_argument("--all", action="store_true", help="Manage all MCRDSE subreddits")
    parser.add_argument("--setup", action="store_true", help="Setup moderation")
    parser.add_argument("--daily", action="store_true", help="Run daily moderation tasks")
    parser.add_argument("--queue", action="store_true", help="Check moderation queue")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--watch", action="store_true", help="Auto-restart on code/config changes (interactive mode)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--validate-only", action="store_true", help="Validate configs/accounts and exit")
    
    args = parser.parse_args()
    
    logger.info("\n" + "="*60)
    logger.info("MCRDSE Selenium Moderation Manager")
    logger.info("="*60)
    
    # Initialize manager
    manager = SeleniumModerationManager(
        account_name=args.account,
        headless=args.headless,
        dry_run=args.dry_run,
    )
    logger.info(f"Validation summary: {manager.run_validations()}")
    enabled, reason = manager.is_feature_enabled("moderation")
    if not enabled:
        logger.info(f"Moderation disabled ({reason}); exiting.")
        manager.cleanup()
        return

    if args.validate_only:
        logger.info(f"Validation summary: {manager.run_validations()}")
        manager.cleanup()
        return
    
    # Setup browser and login
    if not args.dry_run:
        logger.info("Setting up browser...")
        if not manager.setup_browser():
            logger.info("❌ Failed to setup browser")
            return
        
        logger.info("Logging in to Reddit...")
        if not manager.login_with_cookies():
            logger.info("❌ Login failed")
            manager.cleanup()
            return
    else:
        logger.info("[dry-run] Skipping browser setup/login")
    
    logger.info("✅ Ready")
    
    # Determine action
    if args.setup:
        if args.subreddit:
            logger.info(f"\nSetting up moderation for r/{args.subreddit}...")
            success = manager.setup_complete_moderation(args.subreddit)
            logger.info(f"✅ Setup {'complete' if success else 'partially complete'}")
        elif args.all:
            logger.info("\nSetting up moderation for all subreddits...")
            manager.setup_all_moderation()
        else:
            logger.info("Please specify --subreddit or --all")
    
    elif args.daily:
        logger.info("\nRunning daily moderation tasks...")
        if args.subreddit:
            manager.run_daily_moderation([args.subreddit])
        elif args.all:
            manager.run_daily_moderation()
        else:
            logger.info("Please specify --subreddit or --all")
    
    elif args.queue:
        logger.info("\nChecking moderation queue...")
        if args.subreddit:
            stats_result = manager.execute_safely(
                lambda: manager.check_moderation_queue(args.subreddit),
                max_retries=1,
                login_required=False,
                action_name="moderation_action",
            )
            stats = stats_result.result if stats_result.success else None
            if stats:
                logger.info(f"\nQueue stats for r/{args.subreddit}:")
                logger.info(f"  Total items: {stats.get('total_items', 0)}")
                logger.info(f"  Approved: {stats.get('approved', 0)}")
                logger.info(f"  Removed: {stats.get('removed', 0)}")
                logger.info(f"  Ignored: {stats.get('ignored', 0)}")
        else:
            logger.info("Please specify --subreddit")
    
    elif args.interactive or not any([args.setup, args.daily, args.queue]):
        # Interactive mode (loop until exit)
        watch_paths = []
        if getattr(args, "watch", False):
            watch_paths = [
                Path("scripts/moderation/manage_moderation.py"),
                Path("scripts/moderation/config/moderation_config.json"),
                Path("config/accounts.json"),
            ]
        watch_state = {}

        def _snapshot_watch_state():
            state = {}
            for p in watch_paths:
                try:
                    state[str(p)] = p.stat().st_mtime
                except Exception:
                    continue
            return state

        def _restart_if_changed():
            if not watch_paths:
                return
            nonlocal watch_state
            current = _snapshot_watch_state()
            if watch_state and current != watch_state:
                logger.info("Detected changes in watched files; restarting...")
                os.execv(sys.executable, [sys.executable] + sys.argv)
            watch_state = current

        if watch_paths:
            watch_state = _snapshot_watch_state()

        while True:
            _restart_if_changed()
            logger.info("\nInteractive Mode")
            logger.info("1. Setup moderation for a subreddit")
            logger.info("2. Run daily moderation tasks")
            logger.info("3. Check moderation queue")
            logger.info("4. Setup all subreddits")
            logger.info("5. Exit")
            
            choice = input("\nSelect option (1-5): ").strip()
            
            if choice == "1":
                subreddit = input("Enter subreddit name: ").strip()
                if subreddit:
                    success = manager.setup_complete_moderation(subreddit)
                    logger.info(f"Setup {'complete' if success else 'partially complete'}")
                _restart_if_changed()
            
            elif choice == "2":
                subreddit = input("Enter subreddit name (or press Enter for all): ").strip()
                if subreddit:
                    manager.run_daily_moderation([subreddit])
                else:
                    manager.run_daily_moderation()
                _restart_if_changed()
            
            elif choice == "3":
                subreddit = input("Enter subreddit name: ").strip()
                if subreddit:
                    stats = manager.check_moderation_queue(subreddit)
                    if stats:
                        logger.info(f"\nQueue stats:")
                        logger.info(f"  Total: {stats.get('total_items', 0)}")
                        logger.info(f"  Approved: {stats.get('approved', 0)}")
                        logger.info(f"  Removed: {stats.get('removed', 0)}")
                _restart_if_changed()
            
            elif choice == "4":
                confirm = input("Setup moderation for ALL MCRDSE subreddits? (yes/no): ").strip()
                if confirm.lower() == "yes":
                    manager.setup_all_moderation()
                _restart_if_changed()
            
            elif choice == "5":
                break
    
    # Cleanup
    manager.cleanup()
    
    logger.info("\n" + "="*60)
    logger.info("Moderation management complete!")
    logger.info("="*60)

if __name__ == "__main__":
    main()
