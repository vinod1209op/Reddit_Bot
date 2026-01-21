"""
Selenium-based Reddit automation - main entry point.

Now uses BrowserManager for all browser interactions and LoginManager for authentication.
"""
import os
import sys
import time
import random
import logging
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse, urlunparse


# Selenium selectors/wait helpers
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# Import our refactored managers
from selenium_automation.utils.browser_manager import BrowserManager
from selenium_automation.login_manager import LoginManager

# Optional LLM
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None

project_root = Path(__file__).resolve().parents[2]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Rotate file logs to avoid unbounded growth; fallback to stdout if path unavailable.
if not logger.handlers:
    try:
        logs_dir = project_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_path = logs_dir / "selenium_automation.log"
        handler = RotatingFileHandler(file_path, maxBytes=5 * 1024 * 1024, backupCount=2)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
    except Exception as e:
        logger.warning(f"Could not initialize rotating file handler: {e}")

class RedditAutomation:
    """Main Selenium automation class for Reddit - Now using BrowserManager and LoginManager"""
    
    def __init__(self, config=None):
        self.config = config
        self.driver = None
        self.browser_manager = None
        self.login_manager = None
        self.wait = None
        
        # Check which components are available
        self.components_available = self.check_components()
        
        # LLM config
        self.use_llm = False
        if self.config and hasattr(self.config, "bot_settings"):
            if isinstance(self.config.bot_settings, dict):
                self.use_llm = self.config.bot_settings.get("use_llm", False)
        
        # Initialize managers
        self._initialize_managers()
    
    def _initialize_managers(self):
        """Initialize BrowserManager and LoginManager"""
        try:
            # Get settings from config
            headless = False
            stealth_mode = True
            randomize_fingerprint = True
            use_undetected = True
            if self.config and hasattr(self.config, "selenium_settings"):
                ss = self.config.selenium_settings
                if isinstance(ss, dict):
                    headless = ss.get("headless", False)
                    stealth_mode = ss.get("stealth_mode", True)
                    randomize_fingerprint = ss.get("randomize_fingerprint", True)
                    use_undetected = ss.get("use_undetected", True)
            
            # Create BrowserManager
            self.browser_manager = BrowserManager(
                headless=headless,
                stealth_mode=stealth_mode,
                randomize_fingerprint=randomize_fingerprint,
                use_undetected=use_undetected,
            )
            
            # Create LoginManager (share BrowserManager; driver set after setup)
            self.login_manager = LoginManager(browser_manager=self.browser_manager)
            
            logger.info("✓ Managers initialized: BrowserManager, LoginManager")
        except Exception as e:
            logger.error(f"Failed to initialize managers: {e}")

    def _sync_login_manager(self) -> None:
        """Ensure LoginManager shares the current BrowserManager/driver."""
        if not self.login_manager:
            return
        if self.browser_manager:
            self.login_manager.browser_manager = self.browser_manager
        if self.driver:
            self.login_manager.driver = self.driver
    
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
        
        # Check for utils directory
        utils_dir = Path(__file__).parent / "utils"
        if utils_dir.exists():
            util_files = ["browser_manager.py", "message_processor.py", "rate_limiter.py"]
            for util_file in util_files:
                if (utils_dir / util_file).exists():
                    available[util_file.replace(".py", "")] = True
        
        return available
    
    def setup(self):
        """Setup browser using BrowserManager"""
        logger.info("Setting up browser with BrowserManager...")
        
        try:
            # Get settings from config
            headless = False
            use_undetected = True
            
            if self.config and hasattr(self.config, "selenium_settings"):
                ss = self.config.selenium_settings
                if isinstance(ss, dict):
                    headless = ss.get("headless", False)
                    use_undetected = ss.get("use_undetected", True)
            
            # Create driver using BrowserManager
            self.driver = self.browser_manager.create_driver(use_undetected=use_undetected)
            
            if not self.driver:
                logger.error("Failed to create driver")
                return None
            
            # Set wait using Selenium WebDriverWait
            self.wait = WebDriverWait(self.driver, 15)
            
            # Randomize fingerprint to avoid detection
            self.browser_manager.randomize_fingerprint(self.driver)

            # Keep LoginManager in sync with the current driver
            self._sync_login_manager()
            
            logger.info("✓ Browser setup complete with BrowserManager")
            return self.driver
            
        except Exception as e:
            logger.error(f"Browser setup failed: {e}")
            return None
    
    def ensure_driver(self) -> bool:
        """Ensure driver/session is alive; recreate if needed."""
        try:
            if self.driver and getattr(self.driver, "session_id", None):
                return True
        except Exception:
            pass
        
        try:
            self.close()
        except Exception:
            pass
        
        self._log_event("driver_restart")
        
        if self.setup():
            self._sync_login_manager()
            try:
                # Try cookie login first
                if self.login_manager:
                    cookie_file = None
                    if self.config and hasattr(self.config, "selenium_settings"):
                        ss = self.config.selenium_settings
                        if isinstance(ss, dict):
                            cookie_file = ss.get("cookie_file")
                    
                    cookie_file = cookie_file or "cookies.pkl"
                    if self.login_manager.login_with_cookies(cookie_file=cookie_file, headless=False):
                        logger.info("Restored session with cookies")
                        return True
            except Exception:
                pass
            return self.driver is not None
        return False
    
    def _bot_setting(self, key: str, default=None):
        """Safe access to bot_settings dict."""
        if self.config and hasattr(self.config, "bot_settings"):
            bs = self.config.bot_settings
            if isinstance(bs, dict):
                return bs.get(key, default)
        return default
    
    def _automation_setting(self, key: str, default=None):
        """Safe access to automation_settings dict."""
        if self.config and hasattr(self.config, "automation_settings"):
            settings = self.config.automation_settings
            if isinstance(settings, dict):
                return settings.get(key, default)
        return default
    
    def _selenium_setting(self, key: str, default=None):
        """Safe access to selenium_settings dict."""
        if self.config and hasattr(self.config, "selenium_settings"):
            ss = self.config.selenium_settings
            if isinstance(ss, dict):
                return ss.get(key, default)
        return default
    
    def _delay(self, min_s: float, max_s: float, label: str = "") -> None:
        """Use BrowserManager's human delay method"""
        if not self._automation_setting("human_delays", True):
            return
        
        try:
            factor = float(self._automation_setting("randomization_factor", 0.0) or 0.0)
        except (TypeError, ValueError):
            factor = 0.0
        
        min_s = max(0.0, min_s)
        max_s = max(min_s, max_s)
        
        if factor > 0:
            min_s = max(0.0, min_s * (1 - factor))
            max_s = max(min_s, max_s * (1 + factor))
        
        if self.browser_manager and self.driver:
            delay = self.browser_manager.add_human_delay(min_s, max_s)
            if label and delay > 0:
                logger.debug(f"Human delay {delay:.2f}s ({label})")
        else:
            # Fallback
            delay = random.uniform(min_s, max_s) if max_s > 0 else 0.0
            if delay > 0:
                time.sleep(delay)
    
    def _log_event(self, action: str, **fields) -> None:
        """Emit a minimal JSON event to stdout when LOG_JSON is enabled."""
        if os.getenv("LOG_JSON", "0").lower() not in ("1", "true", "yes"):
            return
        payload = {"action": action, "ts": time.time()}
        payload.update(fields)
        try:
            logger.info(json.dumps(payload))
        except Exception:
            pass
    
    @staticmethod
    def _normalize_post_url(url: str) -> str:
        """Accept partial Reddit paths and convert to full URL."""
        if not url:
            return url
        trimmed = url.strip()
        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            return RedditAutomation._normalize_reddit_url(trimmed)
        if trimmed.startswith("r/"):
            trimmed = "/" + trimmed
        if not trimmed.startswith("/"):
            trimmed = "/" + trimmed
        normalized = urljoin("https://old.reddit.com", trimmed)
        return RedditAutomation._normalize_reddit_url(normalized)
    
    @staticmethod
    def _normalize_reddit_url(url: str) -> str:
        """Normalize Reddit URLs to https://old.reddit.com/... when possible."""
        if not url:
            return url
        trimmed = url.strip()
        if not trimmed:
            return trimmed
        if "://" not in trimmed:
            return trimmed
        try:
            parsed = urlparse(trimmed)
        except Exception:
            return trimmed
        if "reddit.com" not in parsed.netloc:
            return trimmed
        normalized = parsed._replace(scheme="https", netloc="old.reddit.com")
        return urlunparse(normalized)
    
    def generate_llm_reply(self, context: str) -> Optional[str]:
        """Generate a reply via OpenAI if enabled and configured."""
        if not self.use_llm or OpenAI is None:
            return None
        
        import os

        # Use OpenRouter key
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return None

        # If using OpenRouter key, default the base URL accordingly
        base_url_env = os.getenv("OPENROUTER_BASE_URL", "").strip()
        base_url = base_url_env or "https://openrouter.ai/api/v1"

        safety_prompt = (
            "You are an educational assistant focused on harm reduction and neutral information.\n"
            "Rules:\n"
            "- Do not give medical or dosing advice.\n"
            "- Do not encourage illegal activity or acquisition of substances.\n"
            "- Do not promote products, brands, or websites.\n"
            "- Do not provide microdosing protocols, schedules, or dose guidance; emphasize legal/health risks and uncertainty.\n"
            "- Keep replies short (2-5 sentences), neutral, and focus on general risks/considerations.\n"
            "- Suggest speaking with qualified professionals for personal guidance.\n"
            "- Respect community rules and be considerate in tone."
        )
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        if api_key.startswith("sk-or-"):
            client_kwargs["default_headers"] = {
                "HTTP-Referer": os.getenv("OPENAI_HTTP_REFERER", "http://localhost"),
                "X-Title": os.getenv("OPENAI_X_TITLE", "Reddit_Bot"),
            }
        try:
            client = OpenAI(**client_kwargs)
        except TypeError as e:
            # Fallback for older httpx missing 'proxies' argument: build our own client.
            logger.warning(f"LLM client init failed (possible httpx version mismatch): {e}")
            try:
                import httpx

                manual_client = httpx.Client()
                client = OpenAI(http_client=manual_client, **{k: v for k, v in client_kwargs.items() if k != "default_headers"})
                if "default_headers" in client_kwargs and hasattr(client, "_default_headers"):
                    client._default_headers.update(client_kwargs["default_headers"])
            except Exception as e2:
                logger.warning(f"LLM client fallback init failed: {e2}")
                return None
        except Exception as e:
            logger.warning(f"LLM client init failed: {e}")
            return None
        try:
            resp = client.completions.create(
                model="gpt-3.5-turbo-instruct",
                prompt=f"{safety_prompt}\n\nContext: {context}\nWrite one short reply that follows the rules.",
                max_tokens=180,
                temperature=0.4,
            )
            text = resp.choices[0].text.strip()
            # Some models wrap the reply in quotes; unwrap a matching single/double pair.
            if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
                text = text[1:-1].strip()
            return text
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}")
            return None
    
    def fetch_post_context(self, url: str) -> str:
        """Fetch a post's title and body text for LLM context (best-effort)."""
        if not self.ensure_driver():
            return ""
        
        try:
            normalized = self._normalize_post_url(url)
            
            if self.browser_manager:
                # Use BrowserManager's wait method
                from selenium.webdriver.common.by import By
                self.driver.get(normalized)
                self._delay(0.4, 1.0, "post_context_load")
                
                # Wait for page to load
                self.browser_manager.wait_for_element(
                    self.driver, By.TAG_NAME, "h1", timeout=5
                )
                
                title = ""
                body = ""
                
                # Try to get title
                try:
                    title_el = self.browser_manager.wait_for_element(
                        self.driver, By.TAG_NAME, "h1", timeout=3
                    )
                    if title_el:
                        title = title_el.text
                except:
                    pass
                if not title:
                    try:
                        title_el = self.browser_manager.wait_for_element(
                            self.driver, By.CSS_SELECTOR, "a.title", timeout=2
                        )
                        if title_el:
                            title = title_el.text
                    except Exception:
                        pass
                
                # Try to get body
                body_selectors = [
                    "div.usertext-body",
                    "div.expando div.md",
                    "div.md",
                ]
                
                for selector in body_selectors:
                    try:
                        el = self.browser_manager.wait_for_element(
                            self.driver, By.CSS_SELECTOR, selector, timeout=2
                        )
                        if el and el.text:
                            body = el.text
                            break
                    except:
                        continue
                
                combined = (title + "\n\n" + body).strip()
                return combined or normalized
                
        except Exception as e:
            logger.debug(f"fetch_post_context failed: {e}")
        
        return ""
    
    def _wait_for_first(self, selectors: Sequence[Tuple[str, str]], timeout: int = 10):
        """Wait for the first selector to appear; returns the element or None on timeout."""
        if not self.driver or not self.browser_manager:
            return None
        
        try:
            # Try each selector with BrowserManager's wait method
            for by, value in selectors:
                try:
                    element = self.browser_manager.wait_for_element(
                        self.driver, by, value, timeout=2
                    )
                    if element:
                        return element
                except:
                    continue
            
            # Fallback: try to find any of them
            for by, value in selectors:
                try:
                    elements = self.driver.find_elements(by, value)
                    for element in elements:
                        if element.is_displayed():
                            return element
                except:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def login(self, use_cookies_only: bool = False) -> bool:
        """Login to Reddit using LoginManager"""
        logger.info("Starting login process...")
        
        try:
            # Ensure we have a driver
            if not self.driver:
                if not self.setup():
                    logger.error("Failed to setup browser")
                    return False
            self._sync_login_manager()
            
            # Get login credentials from config or env
            google_email = None
            google_password = None
            cookie_file = None
            
            if self.config and hasattr(self.config, "selenium_settings"):
                ss = self.config.selenium_settings
                if isinstance(ss, dict):
                    google_email = ss.get("google_email")
                    google_password = ss.get("google_password")
                    cookie_file = ss.get("cookie_file")
            
            # Fallback to environment variables
            if not google_email:
                google_email = os.getenv("GOOGLE_EMAIL")
            if not google_password:
                google_password = os.getenv("GOOGLE_PASSWORD")
            
            cookie_file = cookie_file or "cookies.pkl"
            
            # Try cookie login first
            if self.login_manager.login_with_cookies(cookie_file=cookie_file, headless=False):
                logger.info("✓ Logged in with cookies")
                self.driver = self.login_manager.get_driver()
                return True
            
            # If cookie login failed and not use_cookies_only, try Google login
            if not use_cookies_only and google_email and google_password:
                logger.info("Attempting Google login...")
                if self.login_manager.login_with_google(
                    google_email=google_email,
                    google_password=google_password,
                    headless=False
                ):
                    logger.info("✓ Google login successful")
                    self.driver = self.login_manager.get_driver()
                    
                    # Save cookies for next time
                    self.login_manager.save_login_cookies(cookie_file)
                    return True
                else:
                    logger.error("Google login failed")
                    return False
            
            # Last resort: direct Reddit login
            reddit_username = os.getenv("REDDIT_USERNAME")
            reddit_password = os.getenv("REDDIT_PASSWORD")
            
            if reddit_username and reddit_password:
                logger.info("Attempting direct Reddit login...")
                if self.login_manager.login_with_credentials(
                    username=reddit_username,
                    password=reddit_password,
                    headless=False
                ):
                    logger.info("✓ Direct Reddit login successful")
                    self.driver = self.login_manager.get_driver()
                    
                    # Save cookies
                    self.login_manager.save_login_cookies(cookie_file)
                    return True
            
            logger.error("All login methods failed")
            return False
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def check_messages(self) -> List[Dict[str, Any]]:
        """Check Reddit messages"""
        logger.info("Checking messages...")
        
        if not self.ensure_driver():
            logger.error("Driver not initialized")
            return []
        
        try:
            # Navigate to messages page
            self.driver.get("https://old.reddit.com/message/unread")
            self._delay(0.4, 0.9, "messages_load")
            
            # Check if logged in
            if "login" in self.driver.current_url.lower():
                logger.warning("Not logged in; skipping messages.")
                return []
            
            # Simple check for messages (old Reddit inbox page)
            logger.info("At messages page (old Reddit)")
            return []  # Return empty list for now
        
        except Exception as e:
            logger.error(f"Error checking messages: {e}")
            return []
    
    def search_posts(self, subreddit: Optional[str] = None, 
                    keywords: Optional[List[str]] = None,
                    limit: int = 20,
                    include_body: bool = False,
                    include_comments: bool = False,
                    comments_limit: int = 3,
                    sort: str = "new",
                    time_range: Optional[str] = None,
                    page_offset: int = 0) -> List[Dict[str, Any]]:
        """
        Search for posts in subreddits.
        """
        if not self.ensure_driver():
            logger.error("Driver not initialized")
            return []
        
        # Use config if available
        if not subreddit and self.config:
            subreddits = self._bot_setting("subreddits", ["test"])
            subreddit = subreddits[0] if subreddits else "test"
        
        logger.info(f"Searching r/{subreddit}...")
        
        try:
            # Always use old Reddit for scraping to avoid modern UI volatility.
            target_url = self._build_old_reddit_url(subreddit, sort, time_range)
            logger.info(f"Loading {target_url}")
            self.driver.get(target_url)
            self._delay(0.6, 1.1, "old_subreddit_load")

            # Dismiss any old Reddit popups (rare but possible).
            self._dismiss_popups(old_reddit=True)
            self._delay(0.3, 0.6, "old_post_list_settle")

            if page_offset and page_offset > 0:
                logger.info(
                    f"Applying pagination offset {page_offset} for r/{subreddit} (sort={sort}, time={time_range or 'none'})"
                )
                for _ in range(page_offset):
                    next_url = self._get_old_reddit_next_url()
                    if not next_url:
                        break
                    logger.info(f"Loading next page: {next_url}")
                    self.driver.get(next_url)
                    self._delay(0.5, 0.9, "old_subreddit_next_page")
                    self._dismiss_popups(old_reddit=True)

            posts = self._scrape_old_reddit_posts(subreddit, limit)
            if not posts:
                logger.warning("No posts found via old Reddit selectors.")

            # Enrich posts if needed
            if (include_body or include_comments) and posts:
                logger.info("Enriching posts with body/comments...")
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
            
            self._log_event("search_posts", subreddit=subreddit, limit=limit, found=len(posts))
            return posts
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def _scrape_old_reddit_posts(self, subreddit: str, limit: int) -> List[Dict[str, Any]]:
        """Scrape posts from old.reddit.com."""
        if not self.driver:
            return []

        posts: List[Dict[str, Any]] = []
        selector = "div.thing"
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                if len(posts) >= limit:
                    break
                try:
                    post = self._extract_old_reddit_post(element, subreddit)
                    if post:
                        posts.append(post)
                except Exception as exc:
                    logger.debug(f"Old Reddit extraction error: {exc}")
        except Exception as exc:
            logger.debug(f"Old Reddit page scraping failed: {exc}")

        return self._dedupe_posts(posts)[:limit]
    def _extract_old_reddit_post(self, element, subreddit: str) -> Optional[Dict[str, Any]]:
        """Extract data from a post element (old Reddit)"""
        try:
            title = ""
            url = ""
            post_id = ""
            
            # Get title from old Reddit
            try:
                title_elem = element.find_element(
                    By.CLASS_NAME, "title"
                )
                title_link = title_elem.find_element(
                    By.TAG_NAME, "a"
                )
                title = (title_link.text or "").strip()
                url = title_link.get_attribute("href") or ""
            except:
                pass
            
            if not title:
                return None
            
            # Prefer the comments permalink for ID + URL (external links won't have /comments/).
            comments_url = ""
            for selector in ("a.comments", "a[href*='/comments/']"):
                try:
                    comments_link = element.find_element(By.CSS_SELECTOR, selector)
                    href = comments_link.get_attribute("href") or ""
                    if "/comments/" in href:
                        comments_url = href
                        break
                except Exception:
                    continue

            if comments_url:
                url = comments_url

            # Extract post ID from permalink
            if "/comments/" in url:
                post_id = url.split("/comments/")[1].split("/")[0]
            
            if url:
                url = self._normalize_post_url(url)
            
            return {
                "id": post_id,
                "title": title,
                "body": "",
                "subreddit": subreddit,
                "score": 0,
                "author": "",
                "url": url,
                "method": "selenium-old"
            }
            
        except Exception as e:
            logger.debug(f"Error extracting old reddit post: {e}")
            return None
    
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
    
    def _dismiss_popups(self, old_reddit: bool = False) -> None:
        """Attempt to close cookie/consent popups."""
        try:
            # Try to find and click accept buttons
            buttons = self.driver.find_elements(
                By.TAG_NAME, "button"
            )
            keywords = ["accept", "agree", "continue", "got it", "consent", "allow"]
            
            for btn in buttons:
                try:
                    text = btn.text.strip().lower()
                    if any(k in text for k in keywords):
                        if self.browser_manager:
                            self.browser_manager.safe_click(self.driver, btn)
                        else:
                            btn.click()
                        self._delay(0.5, 1)
                        break
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Popup dismissal error: {e}")

    def _build_old_reddit_url(self, subreddit: str, sort: str, time_range: Optional[str]) -> str:
        sort = (sort or "new").strip().lower()
        if sort not in ("new", "top", "hot", "rising"):
            sort = "new"
        base = f"https://old.reddit.com/r/{subreddit}/{sort}"
        if sort == "top" and time_range:
            return f"{base}?t={time_range}"
        return base

    def _get_old_reddit_next_url(self) -> Optional[str]:
        if not self.driver:
            return None
        selectors = ("span.next-button a", "a[rel='next']")
        for selector in selectors:
            try:
                link = self.driver.find_element(By.CSS_SELECTOR, selector)
                href = link.get_attribute("href") or ""
                if href:
                    return href
            except Exception:
                continue
        return None
    
    def _enrich_post_details(self, post: Dict[str, Any], include_body: bool, include_comments: bool, comments_limit: int = 3) -> None:
        """Navigate to a post URL and collect body text and comments."""
        if not self.driver or not post.get("url"):
            return
        
        try:
            self.driver.get(post["url"])
            self._delay(0.8, 1.4, "post_detail_load")
            
            if include_body:
                body_text = ""
                body_selectors = [
                    "div.usertext-body",
                    "div.expando div.md",
                    "div.md",
                ]
                
                for selector in body_selectors:
                    try:
                        if self.browser_manager:
                            body_elem = self.browser_manager.wait_for_element(
                                self.driver,
                                By.CSS_SELECTOR,
                                selector,
                                timeout=3
                            )
                            if body_elem and body_elem.text:
                                body_text = body_elem.text
                                break
                    except:
                        continue
                
                post["body"] = body_text
            
            if include_comments and comments_limit > 0:
                comments = []
                try:
                    comment_divs = self.driver.find_elements(
                        By.CSS_SELECTOR, "div.comment div.md"
                    )
                    for div in comment_divs[:comments_limit]:
                        try:
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
        Post a reply on a thread.
        Defaults to dry_run=True for safety.
        """
        if not self.ensure_driver():
            return {"success": False, "error": "Driver not initialized"}
        
        try:
            # We need to import reply_helpers for this functionality
            try:
                from selenium_automation.utils import reply_helpers as rh
            except ImportError:
                return {"success": False, "error": "reply_helpers module not found"}
            
            normalized_url = self._normalize_post_url(post_url)
            logger.info(f"Navigating to post for reply: {normalized_url}")
            
            self.driver.get(normalized_url)
            self._delay(0.7, 1.4, "reply_page_load")

            # Try to open comment composer
            rh.js_open_comment_composer(self.driver)
            self._delay(0.3, 0.7, "composer_open")
            if hasattr(rh, "focus_comment_box"):
                rh.focus_comment_box(self.driver)
                self._delay(0.2, 0.4, "composer_focus")

            filled = False
            if hasattr(rh, "fill_modern_reddit_comment"):
                filled = rh.fill_modern_reddit_comment(self.driver, reply_text)

            def _normalize_text(text: str) -> str:
                return " ".join((text or "").split())

            def _read_composer_text() -> str:
                content = ""
                if hasattr(rh, "js_read_comment_text"):
                    content = rh.js_read_comment_text(self.driver) or ""
                if hasattr(rh, "get_composer_text"):
                    content = content or rh.get_composer_text(self.driver) or ""
                if not content.strip():
                    try:
                        element = rh.js_find_comment_box(self.driver) or rh.find_comment_area(self.driver)
                        if element:
                            content = self.driver.execute_script(
                                """
const el = arguments[0];
if (!el) return '';
if (el.value !== undefined) return el.value;
return el.innerText || el.textContent || '';
                                """,
                                element,
                            ) or ""
                    except Exception:
                        content = ""
                return content

            if not filled:
                existing = _read_composer_text()
                if _normalize_text(reply_text) and _normalize_text(reply_text) in _normalize_text(existing):
                    filled = True

            # Find comment box
            target_area = (
                rh.js_find_comment_box(self.driver)
                or rh.find_comment_area(self.driver)
                or rh.get_composer_element(self.driver)
            )

            if not target_area and not filled:
                return {"success": False, "error": "Could not find reply textarea"}

            # Try different methods to fill the comment
            if not filled and hasattr(rh, 'keystroke_fill_simple') and target_area:
                filled = rh.keystroke_fill_simple(self.driver, target_area, reply_text)

            if not filled and hasattr(rh, 'fill_comment_box_via_keystrokes') and target_area:
                filled = rh.fill_comment_box_via_keystrokes(self.driver, target_area, reply_text)

            if filled:
                content = _read_composer_text()
                if not content or not content.strip():
                    filled = False

            if not filled:
                # Last resort: direct typing
                try:
                    target_area.clear()
                    if self.browser_manager:
                        self.browser_manager.human_like_typing(target_area, reply_text)
                    else:
                        target_area.send_keys(reply_text)
                    filled = True
                except:
                    filled = False

            if not filled:
                return {"success": False, "error": "Could not fill reply text"}
            
            self._delay(0.2, 0.5, "composer_settle")
            
            if dry_run:
                logger.info("Dry run enabled; not submitting reply.")
                return {"success": True, "dry_run": True}
            
            # Try to submit
            submitted = False
            if hasattr(rh, 'js_submit_comment'):
                submitted = rh.js_submit_comment(self.driver)
            
            if not submitted and hasattr(rh, 'submit_via_buttons'):
                submitted = rh.submit_via_buttons(self.driver)
            
            self._log_event("reply_submit", dry_run=False, submitted=submitted)
            return {"success": True, "dry_run": False, "submitted": submitted}
            
        except Exception as e:
            self._log_event("reply_error", error=str(e))
            return {"success": False, "error": str(e)}
    
    def close(self):
        """Close the browser"""
        if self.login_manager:
            try:
                self.login_manager.close_browser()
                logger.info("Browser closed via LoginManager")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
        elif self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed")
            except:
                pass
    
    def save_login_cookies(self, cookie_file: str = "cookies.pkl") -> bool:
        """Save current session cookies via LoginManager."""
        if not self.login_manager:
            logger.error("LoginManager not initialized")
            return False
        
        try:
            return self.login_manager.save_login_cookies(cookie_file)
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False

def test_selenium():
    """Test Selenium functionality with new managers"""
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
                
                # Save cookies
                if bot.save_login_cookies():
                    logger.info("✓ Cookies saved")
                
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
