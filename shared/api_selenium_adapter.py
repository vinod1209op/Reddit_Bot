"""
Adapter that allows using either PRAW API or Selenium methods
"""
import os
import sys
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

# Add project root to path to ensure imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.safety_checker import SafetyChecker
from shared.api_utils import make_reddit_client

def _structured_error(message: str, code: str = "error", extra: Dict[str, Any] = None) -> Dict[str, Any]:
    """Return a consistent error payload."""
    payload = {"success": False, "error": message, "code": code}
    if extra:
        payload.update(extra)
    return payload

class RedditBotAdapter:
    """Unified interface for both PRAW and Selenium"""
    
    def __init__(self, config):
        self.config = config
        self.mode = config.bot_settings.get("mode", "selenium")
        self.logger = None
        self.praw_client = None
        self.selenium_bot = None
        self.has_api_functions = False
        try:
            from selenium_automation.utils.rate_limiter import RateLimiter
            self.rate_limiter = RateLimiter(config_file=str(project_root / "config" / "rate_limits.json"))
            # Align limits with loaded config if available
            if getattr(config, "rate_limits", None):
                self.rate_limiter.limits = config.rate_limits
        except Exception:
            self.rate_limiter = None
        # Safety checker for content/rate parity
        try:
            self.safety_checker = SafetyChecker(config)
        except Exception:
            self.safety_checker = None
        
        # Set environment variables for API mode
        if self.mode == "api":
            os.environ.update({
                'REDDIT_CLIENT_ID': config.api_creds.get("client_id", ""),
                'REDDIT_CLIENT_SECRET': config.api_creds.get("client_secret", ""),
                'REDDIT_USERNAME': config.api_creds.get("username", ""),
                'REDDIT_PASSWORD': config.api_creds.get("password", ""),
                'REDDIT_USER_AGENT': config.api_creds.get("user_agent", "bot:microdosing_research:v1.0"),
                'ENABLE_POSTING': '1' if config.bot_settings.get("enable_posting", False) else '0',
                'MOCK_MODE': '1' if config.bot_settings.get("mock_mode", False) else '0'
            })
    
    def setup(self) -> bool:
        """Setup based on selected mode"""
        if self.mode == "api":
            return self.setup_api_mode()
        else:
            return self.setup_selenium_mode()
    
    def setup_api_mode(self) -> bool:
        """Initialize PRAW-based bot"""
        try:
            # Import PRAW modules
            import praw
            self.has_api_functions = False
            
            # Validate credentials
            creds = self.config.api_creds
            missing_creds = []
            for key in ["client_id", "client_secret", "username", "password"]:
                if not creds.get(key):
                    missing_creds.append(key)
            
            if missing_creds:
                raise ValueError(f"Missing API credentials: {missing_creds}")
            
            # Create PRAW client
            self.praw_client = make_reddit_client(
                creds=creds,
                env_fallback=False,
            )
            
            # Test connection
            user = self.praw_client.user.me()
            print(f"✓ API Mode: Connected as {user}")
            
            return True
            
        except Exception as e:
            print(f"✗ API Mode setup failed: {e}")
            print("Falling back to Selenium mode...")
            self.mode = "selenium"
            return self.setup_selenium_mode()
    
    def setup_selenium_mode(self) -> bool:
        """Initialize Selenium-based bot"""
        try:
            from selenium_automation.main import RedditAutomation
            
            self.selenium_bot = RedditAutomation(config=self.config)
            self.selenium_bot.setup()
            
            if self.selenium_bot.login():
                print("✓ Selenium Mode: Connected")
                return True
            else:
                print("✗ Selenium login failed")
                return False
                
        except Exception as e:
            print(f"✗ Selenium setup failed: {e}")
            return False
    
    def find_posts_by_keywords(self, subreddit: str = None, keywords: List[str] = None, 
                               limit: int = 20) -> List[Dict[str, Any]]:
        """Find posts using selected method"""
        if self.mode == "api":
            return self.find_posts_api(subreddit, keywords, limit)
        else:
            return self.find_posts_selenium(subreddit, keywords, limit)
    
    def find_posts_api(self, subreddit: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
        """Use PRAW to find posts"""
        try:
            return self._find_posts_direct_praw(subreddit, keywords, limit)
            
        except Exception as e:
            print(f"API search error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _find_posts_direct_praw(self, subreddit: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
        """Direct PRAW search as fallback"""
        if not self.praw_client:
            return []
        
        # If no specific subreddit provided, use all from config
        if not subreddit:
            target_subreddits = self.config.bot_settings.get("subreddits", [])
        else:
            target_subreddits = [subreddit]
        
        # If no keywords provided, use config keywords
        if not keywords:
            keywords = self.config.bot_settings.get("keywords", [])
        
        posts = []
        
        for sub_name in target_subreddits:
            try:
                subreddit_obj = self.praw_client.subreddit(sub_name)
                
                for submission in subreddit_obj.new(limit=min(limit, 20)):
                    combined = f"{submission.title} {submission.selftext}".lower()
                    
                    # Check for keywords
                    if any(keyword.lower() in combined for keyword in keywords):
                        posts.append({
                            "id": submission.id,
                            "title": submission.title,
                            "body": submission.selftext,
                            "subreddit": sub_name,
                            "score": submission.score,
                            "author": str(submission.author),
                            "url": f"https://reddit.com{submission.permalink}",
                            "created_utc": submission.created_utc,
                            "raw": submission,
                            "method": "api"
                        })
                        
                        if len(posts) >= limit:
                            break
                            
            except Exception as e:
                print(f"Error searching subreddit {sub_name}: {e}")
                continue
            
            if len(posts) >= limit:
                break
        
        return posts
    
    def find_posts_selenium(self, subreddit: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
        """Use Selenium to find posts"""
        try:
            if not self.selenium_bot:
                from selenium_automation.main import RedditAutomation
                self.selenium_bot = RedditAutomation(config=self.config)
                self.selenium_bot.setup()
            
            # Use Selenium bot's search functionality if available
            if hasattr(self.selenium_bot, 'search_posts'):
                return self.selenium_bot.search_posts(
                    subreddit=subreddit,
                    keywords=keywords,
                    limit=limit
                )
            
            # Fallback: Navigate manually
            return self._selenium_manual_search(subreddit, keywords, limit)
            
        except Exception as e:
            print(f"Selenium search error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _selenium_manual_search(self, subreddit: str, keywords: List[str], limit: int) -> List[Dict[str, Any]]:
        """Manual Selenium search as fallback"""
        if not self.selenium_bot or not hasattr(self.selenium_bot, 'driver'):
            return []
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            driver = self.selenium_bot.driver
            
            # Navigate to subreddit (old Reddit)
            if subreddit:
                url = f"https://old.reddit.com/r/{subreddit}/new"
            else:
                # Use first subreddit from config
                subreddits = self.config.bot_settings.get("subreddits", ["test"])
                url = f"https://old.reddit.com/r/{subreddits[0]}/new"
            
            driver.get(url)
            
            # Wait for page load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.thing"))
            )
            
            # Scroll to load more posts
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            # Find posts - old Reddit structure
            posts = []
            post_elements = driver.find_elements(By.CSS_SELECTOR, "div.thing")[:limit * 2]
            
            for element in post_elements:
                try:
                    # Try multiple selectors for title
                    title = ""
                    title_selectors = [
                        "a.title",
                        "a[href*='/comments/']"
                    ]
                    
                    for selector in title_selectors:
                        try:
                            title_elem = element.find_element(By.CSS_SELECTOR, selector)
                            if title_elem.text:
                                title = title_elem.text
                                break
                        except:
                            continue
                    
                    if not title:
                        continue
                    
                    # Check for keywords
                    title_lower = title.lower()
                    keywords_to_check = keywords or self.config.bot_settings.get("keywords", [])
                    
                    if any(keyword.lower() in title_lower for keyword in keywords_to_check):
                        # Get post ID from comments permalink when possible
                        href = ""
                        post_id = ""
                        try:
                            link_elem = element.find_element(By.CSS_SELECTOR, "a.comments")
                            href = link_elem.get_attribute("href") or ""
                        except Exception:
                            try:
                                link_elem = element.find_element(By.CSS_SELECTOR, "a[href*='/comments/']")
                                href = link_elem.get_attribute("href") or ""
                            except Exception:
                                href = ""
                        if "/comments/" in href:
                            post_id = href.split("/comments/")[1].split("/")[0]
                        
                        posts.append({
                            "id": post_id,
                            "title": title,
                            "body": "",  # Would need to click into post to get body
                            "subreddit": subreddit or "",
                            "score": 0,
                            "author": "",
                            "url": href,
                            "raw": element,
                            "method": "selenium-old"
                        })
                        
                        if len(posts) >= limit:
                            break
                            
                except Exception as e:
                    continue
            
            return posts
            
        except Exception as e:
            print(f"Selenium manual search error: {e}")
            return []
    
    def generate_reply(self, post: Dict[str, Any]) -> Tuple[str, bool]:
        """Generate a reply for a post"""
        try:
            default_reply = (
                "I'm a research bot studying microdosing discussions. "
                "I found your post interesting because it mentions microdosing. "
                "Remember to practice harm reduction and consult with healthcare professionals."
            )
            
            return default_reply, True  # Always needs human approval in fallback
            
        except Exception as e:
            print(f"Error generating reply: {e}")
            return "Error generating reply.", True
    
    def reply_to_post(self, post: Dict[str, Any], reply_text: str) -> Dict[str, Any]:
        """Reply to a post using selected method"""
        if self.mode == "api":
            return self.reply_api(post, reply_text)
        else:
            return self.reply_selenium(post, reply_text)
    
    def reply_api(self, post: Dict[str, Any], reply_text: str) -> Dict[str, Any]:
        """Reply using PRAW"""
        try:
            if not self.praw_client:
                return _structured_error("PRAW client not initialized", code="client_uninitialized")
            
            # Check if we should actually post
            if not self.config.bot_settings.get("enable_posting", False):
                return {"success": True, "dry_run": True, "comment_id": "dry_run"}
            
            # Rate/safety gate
            if self.rate_limiter:
                can_post, wait_time = self.rate_limiter.can_perform_action("comment")
                if not can_post:
                    return _structured_error(
                        f"Rate limited: wait {wait_time:.1f}s before commenting",
                        code="rate_limited",
                        extra={"wait_seconds": wait_time},
                    )
            if self.safety_checker:
                allowed, reason = self.safety_checker.can_perform_action("comment", target=post.get("title") or post.get("body", ""))
                if not allowed:
                    return _structured_error(reason, code="safety_blocked")
            
            # Get the submission object
            submission = post.get("raw")
            if not submission or not hasattr(submission, "reply"):
                # Try to fetch by ID
                try:
                    submission = self.praw_client.submission(id=post["id"])
                except:
                    return _structured_error("Could not get submission object", code="missing_submission")
            
            # Post the reply
            comment = submission.reply(reply_text)
            if self.rate_limiter:
                self.rate_limiter.record_action("comment")
            if self.safety_checker:
                self.safety_checker.record_action("comment", target=post.get("title") or post.get("body", ""))
            
            return {
                "success": True, 
                "comment_id": comment.id,
                "permalink": f"https://reddit.com{comment.permalink}"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def reply_selenium(self, post: Dict[str, Any], reply_text: str) -> Dict[str, Any]:
        """Reply using Selenium"""
        try:
            if not self.selenium_bot:
                return _structured_error("Selenium bot not initialized", code="client_uninitialized")
            
            # Check if we should actually post
            if not self.config.bot_settings.get("enable_posting", False):
                return {"success": True, "dry_run": True, "comment_id": "dry_run"}
            
            # Rate/safety gate
            if self.rate_limiter:
                can_post, wait_time = self.rate_limiter.can_perform_action("comment")
                if not can_post:
                    return _structured_error(
                        f"Rate limited: wait {wait_time:.1f}s before commenting",
                        code="rate_limited",
                        extra={"wait_seconds": wait_time},
                    )
            if self.safety_checker:
                allowed, reason = self.safety_checker.can_perform_action("comment", target=post.get("title") or post.get("body", ""))
                if not allowed:
                    return _structured_error(reason, code="safety_blocked")
            
            # Use Selenium bot's reply functionality if available
            if hasattr(self.selenium_bot, 'reply_to_post'):
                return self.selenium_bot.reply_to_post(post, reply_text)
            
            # Fallback: Manual Selenium reply
            return self._selenium_manual_reply(post, reply_text)
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _selenium_manual_reply(self, post: Dict[str, Any], reply_text: str) -> Dict[str, Any]:
        """Manual Selenium reply as fallback"""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            driver = self.selenium_bot.driver
            
            # Navigate to the post
            if 'url' in post and post['url']:
                driver.get(post['url'])
            else:
                # Construct URL from post data
                subreddit = post.get('subreddit', '')
                post_id = post.get('id', '')
                if subreddit and post_id:
                    driver.get(f"https://old.reddit.com/r/{subreddit}/comments/{post_id}/")
                else:
                    return {"success": False, "error": "No valid URL for post"}
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea, [contenteditable='true']"))
            )
            
            # Try to find reply elements
            time.sleep(2)
            
            # Look for reply button/textarea
            reply_selectors = [
                "textarea[name='text']",
                "textarea#comment",
                "textarea[placeholder*='comment']",
                "[contenteditable='true']"
            ]
            
            for selector in reply_selectors:
                try:
                    if "button" in selector and ":contains" in selector:
                        # Handle :contains pseudo-selector
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        for button in buttons:
                            if "Reply" in button.text:
                                button.click()
                                break
                    else:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                        if element.is_displayed() and element.is_enabled():
                            element.click() if "button" in selector else None
                            break
                except:
                    continue
            
            # Wait for reply box
            time.sleep(1)
            
            # Find text area
            text_areas = driver.find_elements(By.CSS_SELECTOR, "textarea, [contenteditable='true']")
            for area in text_areas:
                try:
                    if area.is_displayed() and area.is_enabled():
                        area.clear()
                        area.send_keys(reply_text)
                        break
                except:
                    continue
            
            # Find submit button
            submit_buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
            for button in submit_buttons:
                try:
                    if button.is_displayed() and button.is_enabled() and "Reply" in button.text:
                        button.click()
                        break
                except:
                    continue
            
            # Wait for submission
            time.sleep(3)
            
            return {"success": True, "comment_id": "selenium_reply"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def collect_metrics(self) -> Dict[str, Any]:
        """Collect metrics using bot_step4_metrics if available"""
        try:
            return {
                "mode": self.mode,
                "posts_found": 0,
                "replies_sent": 0,
                "timestamp": time.time()
            }
            
        except Exception as e:
            print(f"Error collecting metrics: {e}")
            return {"error": str(e)}

    def close(self):
        """Cleanup resources"""
        try:
            if self.selenium_bot and hasattr(self.selenium_bot, 'close'):
                self.selenium_bot.close()
        except:
            pass
        
        # PRAW client doesn't need explicit closing
        self.praw_client = None
        self.selenium_bot = None

    # --- Bridging Selenium-scraped posts to PRAW replies ---
    def reply_to_scraped_post_via_api(self, post: Dict[str, Any], reply_text: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Take a Selenium-scraped post dict (needs id or url) and reply using PRAW.
        This is useful if you scrape with Selenium but want the reliability of API posting.
        """
        if not self.praw_client:
            return _structured_error("PRAW client not initialized", code="client_uninitialized")

        if dry_run or not self.config.bot_settings.get("enable_posting", False):
            return {"success": True, "dry_run": True, "comment_id": "dry_run"}

        post_id = post.get("id") or self._extract_post_id_from_url(post.get("url", ""))
        if not post_id:
            return _structured_error("No post ID or URL to derive ID", code="missing_submission")

        try:
            if self.rate_limiter:
                can_post, wait_time = self.rate_limiter.can_perform_action("comment")
                if not can_post:
                    return _structured_error(
                        f"Rate limited: wait {wait_time:.1f}s before commenting",
                        code="rate_limited",
                        extra={"wait_seconds": wait_time},
                    )
            if self.safety_checker:
                allowed, reason = self.safety_checker.can_perform_action("comment", target=post.get("title") or post.get("body", ""))
                if not allowed:
                    return _structured_error(reason, code="safety_blocked")
            submission = self.praw_client.submission(id=post_id)
            comment = submission.reply(reply_text)
            if self.rate_limiter:
                self.rate_limiter.record_action("comment")
            if self.safety_checker:
                self.safety_checker.record_action("comment", target=post.get("title") or post.get("body", ""))
            return {
                "success": True,
                "dry_run": False,
                "comment_id": getattr(comment, "id", ""),
                "permalink": f"https://reddit.com{comment.permalink}" if hasattr(comment, "permalink") else ""
            }
        except Exception as e:
            return _structured_error(str(e), code="exception")

    @staticmethod
    def _extract_post_id_from_url(url: str) -> str:
        """Extract the post ID from a Reddit URL (expects /comments/{id}/...)."""
        if not url or "/comments/" not in url:
            return ""
        try:
            return url.split("/comments/")[1].split("/")[0]
        except Exception:
            return ""
