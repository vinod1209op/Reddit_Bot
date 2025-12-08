"""
Selenium-based Reddit automation - main entry point.

Opens a real browser, guides you through manual Google login, and provides simple
helpers to check messages or scrape recent subreddit posts. Posting is not wired
here; keep usage exploratory and within Reddit’s rules.
"""
import os
import sys
import time
import random
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Fix import path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RedditAutomation:
    """Main Selenium automation class for Reddit"""
    
    def __init__(self, config=None):
        self.config = config
        self.driver = None
        self.wait = None
        
        # Check which components are available
        self.components_available = self.check_components()
    
    def check_components(self):
        """Check which utility components are available"""
        available = {
            "login_manager": False,
            "browser_manager": False,
            "message_processor": False,
            "rate_limiter": False
        }
        
        # Check for login_manager.py in same directory
        login_manager_path = Path(__file__).parent / "login_manager.py"
        if login_manager_path.exists():
            available["login_manager"] = True
            logger.info("login_manager.py found")
        
        # Check for utils directory
        utils_dir = Path(__file__).parent / "utils"
        if utils_dir.exists():
            # Check each util module
            util_files = ["browser_manager.py", "message_processor.py", "rate_limiter.py"]
            for util_file in util_files:
                if (utils_dir / util_file).exists():
                    available[util_file.replace(".py", "")] = True
                    logger.info(f"{util_file} found")
        
        # Check if any components are available
        return any(available.values())
    
    def setup(self):
        """Setup Chrome driver using undetected-chromedriver"""
        logger.info("Setting up browser...")
        
        # Try undetected chromedriver first
        try:
            import undetected_chromedriver as uc
            return self._setup_undetected_chrome(uc)
        except ImportError:
            logger.warning("undetected_chromedriver not found, trying regular selenium")
            return self._setup_regular_selenium()
    
    def _setup_undetected_chrome(self, uc):
        """Setup using undetected-chromedriver"""
        try:
            options = uc.ChromeOptions()
            
            # Get settings from config
            headless = False
            if self.config and hasattr(self.config, 'selenium_settings'):
                headless = self.config.selenium_settings.get("headless", False)
            
            # Add arguments
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            
            # Fix SSL certificate errors
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--ignore-ssl-errors")
            options.add_argument("--allow-running-insecure-content")
            
            # Exclude automation detection
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Add preferences to ignore SSL errors
            options.add_experimental_option('prefs', {
                'profile.managed_default_content_settings.images': 1,
                'profile.default_content_setting_values.notifications': 2,
                'profile.default_content_setting_values.insecure_ssl': 1,
            })
            
            # Headless mode if configured
            if headless:
                options.add_argument("--headless=new")
                logger.info("Running in headless mode")
            else:
                options.add_argument("--start-maximized")
            
            # Initialize driver with SSL ignore
            logger.info("Initializing undetected-chromedriver...")
            self.driver = uc.Chrome(
                options=options,
                suppress_welcome=True,
                use_subprocess=False,
            )
            
            # Set wait
            from selenium.webdriver.support.ui import WebDriverWait
            self.wait = WebDriverWait(self.driver, 15)
            
            logger.info("Browser setup complete with undetected-chromedriver")
            return self.driver
            
        except Exception as e:
            logger.error(f"Undetected chromedriver setup failed: {e}")
            return self._setup_regular_selenium()
    
    def _setup_regular_selenium(self):
        """Setup using regular selenium"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
            
            options = Options()
            
            # Get settings from config
            headless = False
            if self.config and hasattr(self.config, 'selenium_settings'):
                headless = self.config.selenium_settings.get("headless", False)
            
            # Add arguments
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            
            # Fix SSL certificate errors
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--ignore-ssl-errors")
            options.add_argument("--allow-running-insecure-content")
            
            # Headless mode if configured
            if headless:
                options.add_argument("--headless=new")
            else:
                options.add_argument("--start-maximized")
            
            # Try webdriver-manager
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                logger.info("Using webdriver-manager")
            except ImportError:
                # Fallback to system ChromeDriver
                self.driver = webdriver.Chrome(options=options)
                logger.info("Using system ChromeDriver")
            
            self.wait = WebDriverWait(self.driver, 15)
            logger.info("Regular Selenium setup complete")
            return self.driver
            
        except Exception as e:
            logger.error(f"Regular selenium setup failed: {e}")
            return None
    
    def get_login_manager(self):
        """Get login manager instance"""
        try:
            # Try to import login_manager
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "login_manager", 
                Path(__file__).parent / "login_manager.py"
            )
            if spec and spec.loader:
                login_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(login_module)
                return login_module.LoginManager(self.driver)
        except Exception as e:
            logger.error(f"Failed to get login manager: {e}")
            return None
    
    def login(self) -> bool:
        """Login to Reddit"""
        if not self.driver:
            logger.error("Driver not initialized")
            return False
        
        try:
            # Try cookie login first
            if self.components_available:
                try:
                    login_manager = self.get_login_manager()
                    if login_manager and login_manager.login_with_cookies():
                        logger.info("Logged in with cookies")
                        return True
                    else:
                        logger.info("No valid cookies, proceeding with manual login")
                except Exception as e:
                    logger.warning(f"Cookie login failed: {e}")
            
            # SIMPLEST APPROACH: Manual Google login
            logger.info("Using simple manual login approach...")
            return self._simple_manual_login()
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def _simple_manual_login(self):
        """Simplest approach - manual Google login"""
        try:
            logger.info("\n" + "="*60)
            logger.info("MANUAL GOOGLE LOGIN REQUIRED")
            logger.info("="*60)
            logger.info("The browser will open to Reddit login page.")
            logger.info("Please manually:")
            logger.info("1. Click 'Continue with Google'")
            logger.info("2. Log in with your Google account")
            logger.info("3. Return here and press Enter")
            logger.info("="*60 + "\n")
            
            # Open Reddit login
            self.driver.get("https://www.reddit.com/login")
            time.sleep(3)
            
            # Maximize window for better visibility
            self.driver.maximize_window()
            
            # Take screenshot
            self.driver.save_screenshot("manual_login_start.png")
            logger.info("Screenshot saved: manual_login_start.png")
            
            # Wait for manual login
            input("\n⚠️  PRESS ENTER AFTER MANUALLY LOGGING IN WITH GOOGLE ⚠️\n")
            
            # Verify login
            time.sleep(3)
            return self._verify_login()
            
        except Exception as e:
            logger.error(f"Manual login error: {e}")
            return False
    
    def _verify_login(self):
        """Verify login by checking for user elements"""
        try:
            from selenium.webdriver.common.by import By
            
            # Give it a moment
            time.sleep(2)
            
            # Check current URL
            current_url = self.driver.current_url.lower()
            logger.info(f"Current URL: {current_url}")
            
            # If we're still on login page, login failed
            if "login" in current_url:
                logger.error("Still on login page")
                return False
            
            # Check for user menu
            user_menu_selectors = [
                "//button[@aria-label='User menu']",
                "//img[contains(@src, 'avatar')]",
                "//span[contains(text(), '/u/')]",
                "//a[contains(text(), 'Create Post')]",
            ]
            
            for selector in user_menu_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        logger.info(f"✓ Login successful! Found: {selector}")
                        return True
                except:
                    continue
            
            # If we're on Reddit and not on login page, assume success
            if "reddit.com" in current_url and "login" not in current_url:
                logger.info("✓ Login appears successful (on Reddit, not login page)")
                return True
            
            logger.error("✗ Login verification failed")
            return False
            
        except Exception as e:
            logger.error(f"Login verification error: {e}")
            return False
    
    def check_messages(self) -> List[Dict[str, Any]]:
        """Check Reddit messages - SIMPLIFIED VERSION"""
        logger.info("Checking messages...")
        
        if not self.driver:
            logger.error("Driver not initialized")
            return []
        
        try:
            # Just navigate to messages page
            self.driver.get("https://www.reddit.com/message/unread")
            time.sleep(3)
            logger.info("At messages page")
            return []  # Return empty list for now
        
        except Exception as e:
            logger.error(f"Error checking messages: {e}")
            return []
    
    def search_posts(self, subreddit: Optional[str] = None, 
                    keywords: Optional[List[str]] = None,
                    limit: int = 20,
                    include_body: bool = False,
                    include_comments: bool = False,
                    comments_limit: int = 3) -> List[Dict[str, Any]]:
        """
        Search for posts in subreddits.
        
        include_body / include_comments trigger a follow-up visit to each post URL
        (best-effort; keeps volume low). comments_limit caps how many top-level
        comments to collect per post.
        """
        if not self.driver:
            logger.error("Driver not initialized")
            return []
        
        # Use config if available (default to first configured subreddit)
        if not subreddit and self.config:
            if hasattr(self.config.bot_settings, "subreddits"):
                subreddits = self.config.bot_settings.subreddits
            elif hasattr(self.config, "bot_settings") and isinstance(self.config.bot_settings, dict):
                subreddits = self.config.bot_settings.get("subreddits", ["test"])
            else:
                subreddits = ["test"]
            subreddit = subreddits[0] if subreddits else "test"
        
        logger.info(f"Searching r/{subreddit}...")
        
        try:
            from selenium.webdriver.common.by import By
            
            # Navigate to subreddit (new Reddit UI)
            self.driver.get(f"https://www.reddit.com/r/{subreddit}/new")
            time.sleep(3)
            self._dismiss_popups()
            
            # Wait for posts to render, then scroll to load more
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "article, shreddit-post, div[data-testid='post-container']")
                    )
                )
            except Exception as e:
                logger.debug(f"No initial post elements yet: {e}")

            for _ in range(4):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            posts = []
            post_elements = self._find_post_elements(limit)
            logger.info(f"Selector scrape found {len(post_elements)} elements")
            
            # If nothing found, try old.reddit as a fallback (simpler DOM)
            if not post_elements:
                logger.info("No posts found on new Reddit; trying old.reddit fallback...")
                self.driver.get(f"https://old.reddit.com/r/{subreddit}/new")
                time.sleep(3)
                self._dismiss_popups(old_reddit=True)
                post_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")[:limit]
                logger.info(f"Old Reddit selector scrape found {len(post_elements)} elements")
            
            if not post_elements:
                logger.info("No posts found via elements; trying JS scrape of shreddit-post components...")
                posts = self._scrape_via_js(limit=limit, subreddit=subreddit)
                logger.info(f"JS scrape returned {len(posts)} posts")
                if posts:
                    posts = self._dedupe_posts(posts)
                    return posts
            
            for element in post_elements:
                try:
                    href = ""
                    title = ""
                    
                    title_selectors = [
                        "h3",
                        "[data-click-id='body'] h3",
                        "a[data-click-id='body']",
                        "faceplate-screenreader-only",
                        "span[class*='title']",
                    ]
                    for selector in title_selectors:
                        try:
                            t_elem = element.find_element(By.CSS_SELECTOR, selector)
                            if t_elem.text:
                                title = t_elem.text
                                break
                        except:
                            continue
                    
                    if not title:
                        continue
                    
                    post_id = ""
                    link_selectors = [
                        "a[data-click-id='comments']",
                        "a[href*='/comments/']",
                    ]
                    for selector in link_selectors:
                        try:
                            link = element.find_element(By.CSS_SELECTOR, selector)
                            href = link.get_attribute("href")
                            if "/comments/" in href:
                                post_id = href.split("/comments/")[1].split("/")[0]
                                break
                        except:
                            continue
                    
                    posts.append({
                        "id": post_id,
                        "title": title,
                        "body": "",
                        "subreddit": subreddit,
                        "score": 0,
                        "author": "",
                        "url": href,
                        "raw": element,
                        "method": "selenium"
                    })
                    
                except Exception as e:
                    logger.debug(f"Error extracting post: {e}")
                    continue
            
            logger.info(f"Found {len(posts)} posts")
            
            if not posts:
                # Last resort: JS scrape even if selector pass produced elements but no parsed posts
                extra = self._scrape_via_js(limit=limit, subreddit=subreddit)
                logger.info(f"Fallback JS scrape added {len(extra)} posts")
                posts.extend(extra)

            posts = self._dedupe_posts(posts)

            if (include_body or include_comments) and posts:
                logger.info("Enriching posts with body/comments (best-effort, low volume)...")
                limited_posts = posts[:limit]
                for post in limited_posts:
                    if not post.get("url"):
                        continue
                    self._enrich_post_details(
                        post,
                        include_body=include_body,
                        include_comments=include_comments,
                        comments_limit=comments_limit
                    )
            
            return posts
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def _find_post_elements(self, limit: int):
        """Try multiple selectors for post cards across Reddit UI variants."""
        try:
            from selenium.webdriver.common.by import By
        except ImportError:
            return []
        
        selectors = [
            "article",  # new Reddit
            "div[data-testid='post-container']",
            "shreddit-post",
            "div.Post",  # legacy class
        ]
        elements = []
        for selector in selectors:
            try:
                found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    elements = found
                    break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        return elements[:limit] if elements else []

    def _dismiss_popups(self, old_reddit: bool = False) -> None:
        """Attempt to close cookie/consent popups that block interaction."""
        try:
            from selenium.webdriver.common.by import By
        except ImportError:
            return
        
        try:
            # Generic button scan for consent/close
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            keywords = ["accept", "agree", "continue", "got it"]
            for btn in buttons:
                try:
                    text = btn.text.strip().lower()
                    if any(k in text for k in keywords):
                        btn.click()
                        time.sleep(0.5)
                        break
                except:
                    continue
            
            # Specific selectors for Reddit consent overlays
            selectors = [
                "[data-testid='accept-button']",
                "button[aria-label='close']",
                "button[aria-label*='consent']",
            ]
            for selector in selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        time.sleep(0.5)
                except:
                    continue
            
            if old_reddit:
                try:
                    pref = self.driver.find_elements(By.CSS_SELECTOR, "form > button")
                    for el in pref:
                        if "accept" in el.text.lower():
                            el.click()
                            time.sleep(0.5)
                            break
                except:
                    pass
        except Exception as e:
            logger.debug(f"Popup dismissal error: {e}")

    def _scrape_via_js(self, limit: int = 20, subreddit: str = "") -> List[Dict[str, Any]]:
        """Best-effort scrape using JS to traverse shreddit-post and article elements."""
        try:
            posts = self.driver.execute_script(
                """
const max = arguments[0] || 20;
const sub = arguments[1] || '';
const results = [];
const collect = (nodes) => {
  for (const el of nodes) {
    let title = '';
    let url = '';
    let postId = '';
    // Try shadow root first (shreddit-post)
    const roots = [];
    if (el.shadowRoot) roots.push(el.shadowRoot);
    roots.push(el);
    for (const root of roots) {
      if (!title) {
        const t = root.querySelector('h3, faceplate-screenreader-only, [slot=\"title\"]');
        if (t && t.textContent) title = t.textContent.trim();
      }
      if (!url) {
        const a = root.querySelector('a[data-click-id=\"comments\"]');
        if (a && a.href) url = a.href;
      }
    }
    if (!url && el.getAttribute) {
      const maybe = el.getAttribute('permalink');
      if (maybe) url = maybe;
    }
    if (url && url.includes('/comments/')) {
      postId = url.split('/comments/')[1].split('/')[0];
    }
    if (title || url) {
      results.push({
        id: postId,
        title,
        url,
        body: '',
        subreddit: sub || '',
        score: 0,
        author: '',
        method: 'selenium-js'
      });
    }
    if (results.length >= max) break;
  }
};
collect(Array.from(document.querySelectorAll('shreddit-post')));
if (results.length < max) {
  collect(Array.from(document.querySelectorAll('article')).slice(0, max - results.length));
}
return results.slice(0, max);
                """,
                limit,
                subreddit,
            )
            return posts or []
        except Exception as e:
            logger.debug(f"JS scrape failed: {e}")
            return []

    def _dedupe_posts(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate posts based on ID or (title + URL)."""
        seen = set()
        unique = []
        for post in posts:
            key = post.get("id") or f"{post.get('title','')}|{post.get('url','')}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(post)
        return unique

    def _focus_comment_box(self) -> None:
        """Try to bring the comment composer into focus."""
        try:
            from selenium.webdriver.common.by import By
        except ImportError:
            return
        
        # Scroll near the comment area
        try:
            self.driver.execute_script("window.scrollBy(0, window.innerHeight * 0.4);")
            time.sleep(0.5)
        except Exception:
            pass
        
        # Common triggers to open the comment box
        triggers = [
            "button[aria-label*='comment']",
            "button[aria-label*='reply']",
            "div[data-testid='comment-field']",
            "div[data-test-id='comment-field']",
            "div[placeholder*='thoughts']",
        ]
        for selector in triggers:
            try:
                elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        time.sleep(0.5)
                        return
            except Exception:
                continue

    def _find_comment_area(self):
        """Locate a writable comment area."""
        try:
            from selenium.webdriver.common.by import By
        except ImportError:
            return None
        
        selectors = [
            "div[contenteditable='true']",
            "div[role='textbox']",
            "textarea",
            "div[data-testid='comment-field'] div[contenteditable='true']",
            "div[data-test-id='comment-field'] div[contenteditable='true']",
        ]
        for selector in selectors:
            try:
                candidates = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in candidates:
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                continue
        return None

    def _enrich_post_details(self, post: Dict[str, Any], include_body: bool, include_comments: bool, comments_limit: int = 3) -> None:
        """Navigate to a post URL and collect body text and a few top comments."""
        if not self.driver:
            return
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.keys import Keys
            
            comments_limit = max(0, comments_limit)
            self.driver.get(post["url"])
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "article"))
            )
            time.sleep(1.5)
            
            if include_body:
                body_text = ""
                body_selectors = [
                    "div[data-test-id='post-content']",
                    "div[data-click-id='text']",
                ]
                for selector in body_selectors:
                    try:
                        body_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if body_elem.text:
                            body_text = body_elem.text
                            break
                    except:
                        continue
                post["body"] = body_text
            
            if include_comments and comments_limit > 0:
                comments = []
                try:
                    comment_divs = self.driver.find_elements(By.CSS_SELECTOR, "div[data-test-id='comment']")
                    for div in comment_divs[:comments_limit]:
                        try:
                            # Grab visible text from the comment container
                            text = div.text.strip()
                            if text:
                                comments.append(text)
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"Could not extract comments: {e}")
                post["comments"] = comments
        except Exception as e:
            logger.debug(f"Enrichment failed for {post.get('url', '')}: {e}")

    def reply_to_post(self, post_url: str, reply_text: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Post a reply on a thread using the current Selenium session.
        
        Defaults to dry_run=True so you can validate selectors and text safely.
        Set dry_run=False only after manual review and with subreddit approval.
        """
        if not self.driver:
            return {"success": False, "error": "Driver not initialized"}
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            logger.info(f"Navigating to post for reply: {post_url}")
            self.driver.get(post_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea, [contenteditable='true']"))
            )
            time.sleep(1.5)
            
            # Bring reply box into view and try to focus it
            self._focus_comment_box()
            
            # Type reply
            target_area = self._find_comment_area()
            if not target_area:
                return {"success": False, "error": "Could not find reply textarea"}
            
            target_area.clear()
            target_area.send_keys(reply_text)
            
            if dry_run:
                logger.info("Dry run enabled; not submitting reply.")
                return {"success": True, "dry_run": True}
            
            clicked = False
            submit_selectors = [
                "button[data-testid='comment-submit-button']",
                "button[type='submit']",
                "button[aria-label*='comment']",
            ]
            for selector in submit_selectors:
                try:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            clicked = True
                            break
                    if clicked:
                        break
                except Exception:
                    continue
            
            if not clicked:
                # Fallback: try keyboard shortcut (Ctrl/Cmd + Enter)
                try:
                    target_area.send_keys(Keys.CONTROL, Keys.ENTER)
                    clicked = True
                except Exception:
                    try:
                        target_area.send_keys(Keys.COMMAND, Keys.ENTER)
                        clicked = True
                    except Exception:
                        pass
            
            time.sleep(2.5)
            
            # Quick verification: check if reply text appears in page source
            snippet = reply_text[:80]
            if snippet and snippet in self.driver.page_source:
                return {"success": True, "dry_run": False, "verified": True}
            else:
                return {"success": clicked, "dry_run": False, "verified": False, "error": "Reply not detected after submit"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def close(self):
        """Close the browser"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed")
            except:
                pass

def test_selenium():
    """Test Selenium functionality"""
    bot = None
    try:
        # Try to load config
        config = None
        try:
            from shared.config_manager import ConfigManager
            config = ConfigManager().load_env()
            logger.info("Config loaded")
        except ImportError as e:
            logger.warning(f"Could not load config: {e}")
        
        # Create and test bot
        bot = RedditAutomation(config=config)
        
        if bot.setup():
            if bot.login():
                logger.info("✓ Login successful!")
                
                # Test functions
                messages = bot.check_messages()
                logger.info(f"Checked messages, found {len(messages)} messages")
                
                posts = bot.search_posts(limit=5)
                logger.info(f"Found {len(posts)} posts")
                
                # Display posts
                if posts:
                    print("\n" + "="*50)
                    print("RECENT POSTS FOUND:")
                    print("="*50)
                    for i, post in enumerate(posts, 1):
                        title = post.get('title', 'No title')
                        if len(title) > 60:
                            title = title[:57] + "..."
                        print(f"{i}. {title}")
                    print("="*50)
                
                # Keep browser open
                input("\nPress Enter to close browser...")
            else:
                logger.error("✗ Login failed!")
        else:
            logger.error("✗ Browser setup failed!")
            
    except Exception as e:
        logger.error(f"Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if bot:
            bot.close()

if __name__ == "__main__":
    test_selenium()
