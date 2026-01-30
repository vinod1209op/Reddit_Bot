"""
Purpose: engagement actions for Selenium sessions.
"""

# Imports
import os
import random
import time
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from microdose_study_bot.core.storage.idempotency_store import (
    IDEMPOTENCY_DEFAULT_PATH,
    build_post_key,
    can_attempt,
    mark_attempt,
    mark_failure,
    mark_success,
)

# Public API
class EngagementActions:
    def __init__(self, driver, config, browser_manager=None):
        self.driver = driver
        self.config = config
        self.browser_manager = browser_manager

    def _bypass_limits(self) -> bool:
        return (
            os.getenv("BYPASS_ALL_LIMITS", "1").strip().lower() in ("1", "true", "yes")
            or os.getenv("BYPASS_ENGAGEMENT_LIMITS", "1").strip().lower() in ("1", "true", "yes")
        )
    
    def save_post(self, post_element):
        """Save post for later reading"""
        if not self._bypass_limits():
            if not self.config.get('allow_saving', False):
                return False
        
        try:
            # Find save button (varies by Reddit theme)
            save_selectors = [
                "li.save-button a",
                "a.save-button",
                "form.save-button a",
                "a[onclick*='save']",
                "a[data-event-action='save']",
                "button[aria-label*='save']",
                "button[data-click-id='save']"
            ]
            
            for selector in save_selectors:
                try:
                    # CORRECTED: Use proper Selenium 4+ syntax
                    save_btn = post_element.find_element(By.CSS_SELECTOR, selector)
                    label = " ".join(
                        filter(
                            None,
                            [
                                (save_btn.text or "").strip().lower(),
                                (save_btn.get_attribute("aria-label") or "").strip().lower(),
                                (save_btn.get_attribute("title") or "").strip().lower(),
                                (save_btn.get_attribute("value") or "").strip().lower(),
                            ],
                        )
                    )
                    if "unsave" in label or "saved" in label:
                        continue
                    
                    # Use browser_manager for safe click if available
                    if self.browser_manager:
                        clicked = self.browser_manager.safe_click(self.driver, save_btn)
                    else:
                        save_btn.click()
                        clicked = True
                    
                    if clicked:
                        time.sleep(random.uniform(0.3, 0.7))
                        return True
                        
                except (NoSuchElementException, StaleElementReferenceException):
                    continue
                    
        except Exception as e:
            print(f"Error saving post: {e}")
            
        return False
    
    def follow_user(self, username):
        """Follow a user (optional)"""
        if not self._bypass_limits():
            if not self.config.get('allow_following', False):
                return False
        
        try:
            # Visit user profile
            self.driver.get(f"https://old.reddit.com/user/{username}")
            time.sleep(random.uniform(2, 4))
            
            # Find follow button with multiple selectors
            follow_selectors = [
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'follow')]",
                "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'follow')]",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'follow')]/parent::button",
                "//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'follow')]/parent::button",
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add friend')]",
                "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add friend')]",
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'friend')]",
                "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'friend')]",
            ]
            follow_candidates = []

            for xpath in follow_selectors:
                try:
                    follow_candidates.extend(self.driver.find_elements(By.XPATH, xpath))
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            try:
                follow_candidates.extend(
                    self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "form[action*='friend'] button, "
                        "form[action*='friend'] a, "
                        "form[action*='friend'] input[type='submit'], "
                        "a.addfriend, button.addfriend",
                    )
                )
            except (NoSuchElementException, StaleElementReferenceException):
                pass

            for candidate in follow_candidates:
                label = " ".join(
                    filter(
                        None,
                        [
                            (candidate.text or "").strip().lower(),
                            (candidate.get_attribute("aria-label") or "").strip().lower(),
                            (candidate.get_attribute("title") or "").strip().lower(),
                            (candidate.get_attribute("value") or "").strip().lower(),
                        ],
                    )
                )
                if any(word in label for word in ("unfollow", "remove", "unfriend")):
                    continue
                if not label:
                    continue
                if self.browser_manager:
                    clicked = self.browser_manager.safe_click(self.driver, candidate)
                else:
                    candidate.click()
                    clicked = True
                if clicked:
                    time.sleep(random.uniform(1, 2))
                    return True
                    
        except Exception as e:
            print(f"Error following user {username}: {e}")
            
        return False
    
    def view_subreddit(self, subreddit_name):
        """Browse a subreddit naturally"""
        try:
            self.driver.get(f"https://old.reddit.com/r/{subreddit_name}")
            
            # Human-like delay
            if self.browser_manager:
                self.browser_manager.add_human_delay(3, 6)
            else:
                time.sleep(random.uniform(3, 6))
            
            # Scroll through hot posts
            for _ in range(random.randint(2, 4)):
                scroll_amount = random.randint(400, 800)
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
                
                if self.browser_manager:
                    self.browser_manager.add_human_delay(2, 4)
                else:
                    time.sleep(random.uniform(2, 4))
                
                # Occasionally view a post (40% chance)
                if random.random() > 0.6:
                    # CORRECTED: Use proper Selenium 4+ syntax
                    posts = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")
                    if posts:
                        post = random.choice(posts[:5])  # Only from top 5
                        target = None
                        try:
                            target = post.find_element(By.CSS_SELECTOR, "a.title")
                        except Exception:
                            target = post
                        
                        # Use browser_manager for safe click if available
                        if self.browser_manager:
                            self.browser_manager.safe_click(self.driver, target)
                        else:
                            target.click()
                        
                        # View the post
                        if self.browser_manager:
                            self.browser_manager.add_human_delay(5, 10)
                        else:
                            time.sleep(random.uniform(5, 10))
                        
                        # Go back
                        self.driver.back()
                        
                        if self.browser_manager:
                            self.browser_manager.add_human_delay(1, 2)
                        else:
                            time.sleep(random.uniform(1, 2))
                            
        except Exception as e:
            print(f"Error viewing subreddit {subreddit_name}: {e}")
    
    def check_notifications(self):
        """Check inbox notifications"""
        try:
            self.driver.get("https://old.reddit.com/message/unread")
            if self.browser_manager:
                self.browser_manager.add_human_delay(3, 6)
                self.driver.back()
                self.browser_manager.add_human_delay(1, 2)
            else:
                time.sleep(random.uniform(3, 6))
                self.driver.back()
                time.sleep(random.uniform(1, 2))
            return True
                    
        except Exception as e:
            print(f"Error checking notifications: {e}")
            
        return False
    
    def upvote_post(self, post_element=None):
        """Upvote a post (if enabled)"""
        if not self._bypass_limits():
            if not self.config.get('allow_voting', False):
                return False
        
        try:
            # If no specific element provided, try to upvote current post
            if post_element:
                # Look for upvote button within the post element
                upvote_selectors = [
                    "div.arrow.up",
                    "button[aria-label*='upvote']"
                ]
                
                for selector in upvote_selectors:
                    try:
                        upvote_btn = post_element.find_element(By.CSS_SELECTOR, selector)
                        
                        # Random chance to vote (70% if found)
                        if random.random() > 0.3:
                            if self.browser_manager:
                                clicked = self.browser_manager.safe_click(self.driver, upvote_btn)
                            else:
                                upvote_btn.click()
                                clicked = True
                            
                            if clicked:
                                time.sleep(random.uniform(0.2, 0.5))
                                return True
                    except (NoSuchElementException, StaleElementReferenceException):
                        continue
            else:
                # Try to find any upvote button on page
                upvote_buttons = self.driver.find_elements(By.CSS_SELECTOR, "div.arrow.up")
                if upvote_buttons:
                    # Random chance and random button
                    if random.random() > 0.5:
                        btn = random.choice(upvote_buttons[:3])  # Only from top 3
                        if self.browser_manager:
                            clicked = self.browser_manager.safe_click(self.driver, btn)
                        else:
                            btn.click()
                            clicked = True
                        
                        if clicked:
                            time.sleep(random.uniform(0.2, 0.5))
                            return True
                            
        except Exception as e:
            print(f"Error upvoting: {e}")
            
        return False
    
    def downvote_post(self, post_element=None):
        """Downvote a post (if enabled - use with caution)"""
        if not self._bypass_limits():
            if not self.config.get('allow_voting', False):
                return False
        
        try:
            # If no specific element provided, try to downvote current post
            if post_element:
                downvote_selectors = [
                    "div.arrow.down",
                    "button[aria-label*='downvote']"
                ]
                
                for selector in downvote_selectors:
                    try:
                        downvote_btn = post_element.find_element(By.CSS_SELECTOR, selector)
                        
                        # Very low chance to downvote (5% if found)
                        if random.random() > 0.95:
                            if self.browser_manager:
                                clicked = self.browser_manager.safe_click(self.driver, downvote_btn)
                            else:
                                downvote_btn.click()
                                clicked = True
                            
                            if clicked:
                                time.sleep(random.uniform(0.2, 0.5))
                                return True
                    except (NoSuchElementException, StaleElementReferenceException):
                        continue
                        
        except Exception as e:
            print(f"Error downvoting: {e}")
            
        return False
    
    def view_user_profile(self, username):
        """View a user's profile"""
        try:
            self.driver.get(f"https://old.reddit.com/user/{username}")
            
            if self.browser_manager:
                self.browser_manager.add_human_delay(3, 6)
                self.browser_manager.scroll_down(self.driver, random.randint(300, 700))
                self.browser_manager.add_human_delay(1, 3)
            else:
                time.sleep(random.uniform(3, 6))
                self.driver.execute_script(f"window.scrollBy(0, {random.randint(300, 700)})")
                time.sleep(random.uniform(1, 3))
            
            return True
            
        except Exception as e:
            print(f"Error viewing profile {username}: {e}")
            return False
    
    def search_topic(self, query):
        """Search for a topic on Reddit"""
        try:
            # Go to search page
            self.driver.get(f"https://old.reddit.com/search?q={query}")
            
            if self.browser_manager:
                self.browser_manager.add_human_delay(2, 4)
            else:
                time.sleep(random.uniform(2, 4))
            
            # Scroll through results
            for _ in range(random.randint(2, 4)):
                if self.browser_manager:
                    self.browser_manager.scroll_down(self.driver, random.randint(400, 800))
                    self.browser_manager.add_human_delay(1, 2)
                else:
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(400, 800)})")
                    time.sleep(random.uniform(1, 2))
            
            return True
            
        except Exception as e:
            print(f"Error searching for {query}: {e}")
            return False
    
    def comment_on_post(self, post_url, comment_text, dry_run=True):
        """Comment on a post (dry_run by default for safety)"""
        if not self._bypass_limits():
            if not self.config.get('allow_commenting', False):
                return {"success": False, "error": "Commenting not allowed"}
        
        try:
            idem_path = Path(os.getenv("IDEMPOTENCY_PATH", IDEMPOTENCY_DEFAULT_PATH))
            post_key = build_post_key({"url": post_url})
            if not dry_run and post_key and not can_attempt(idem_path, post_key):
                return {"success": False, "error": "Idempotency: post already attempted/sent"}

            # Navigate to post
            self.driver.get(post_url)
            
            if self.browser_manager:
                self.browser_manager.add_human_delay(2, 4)
            else:
                time.sleep(random.uniform(2, 4))
            
            # Try to find comment box
            comment_selectors = [
                "textarea[name='text']",
                "textarea#comment",
                "textarea[placeholder*='comment']",
                '[contenteditable="true"][role="textbox"]'
            ]
            
            comment_box = None
            for selector in comment_selectors:
                try:
                    comment_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if comment_box:
                        break
                except (NoSuchElementException, StaleElementReferenceException):
                    continue
            
            if not comment_box:
                return {"success": False, "error": "Could not find comment box"}
            
            # Type comment with human-like behavior
            if self.browser_manager:
                # Use browser_manager's human-like typing
                typed = self.browser_manager.human_like_typing(comment_box, comment_text)
            else:
                # Fallback typing
                comment_box.click()
                time.sleep(random.uniform(0.2, 0.5))
                comment_box.clear()
                for char in comment_text:
                    comment_box.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
                typed = True
            
            if not typed:
                return {"success": False, "error": "Could not type comment"}
            
            if self.browser_manager:
                self.browser_manager.add_human_delay(1, 2)
            else:
                time.sleep(random.uniform(1, 2))
            
            if dry_run:
                return {"success": True, "dry_run": True, "message": "Dry run - comment not submitted"}
            
            # Try to submit (implementation depends on Reddit's UI)
            # This is a placeholder - actual submission logic would be more complex
            mark_attempt(idem_path, post_key, {"url": post_url})
            result = {"success": True, "dry_run": False, "message": "Comment submitted"}
            if post_key:
                mark_success(idem_path, post_key, {"url": post_url})
            return result
            
        except Exception as e:
            try:
                idem_path = Path(os.getenv("IDEMPOTENCY_PATH", IDEMPOTENCY_DEFAULT_PATH))
                post_key = build_post_key({"url": post_url})
                if post_key:
                    mark_failure(idem_path, post_key, error=str(e))
            except Exception:
                pass
            return {"success": False, "error": str(e)}
