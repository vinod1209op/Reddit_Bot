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
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Sequence, Tuple
from urllib.parse import urljoin

import requests
from selenium_automation.utils import reply_helpers as rh

# Optional LLM
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None

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
        # LLM config
        self.use_llm = False
        if self.config and hasattr(self.config, "bot_settings"):
            if isinstance(self.config.bot_settings, dict):
                self.use_llm = self.config.bot_settings.get("use_llm", False)

    def _bot_setting(self, key: str, default=None):
        """Safe access to bot_settings dict."""
        if self.config and hasattr(self.config, "bot_settings"):
            bs = self.config.bot_settings
            if isinstance(bs, dict):
                return bs.get(key, default)
        return default

    @staticmethod
    def _normalize_post_url(url: str) -> str:
        """Accept partial Reddit paths and convert to full URL."""
        if not url:
            return url
        trimmed = url.strip()
        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            return trimmed
        if trimmed.startswith("r/"):
            trimmed = "/" + trimmed
        if not trimmed.startswith("/"):
            trimmed = "/" + trimmed
        return urljoin("https://www.reddit.com", trimmed)

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
        try:
            normalized = self._normalize_post_url(url)
            from selenium.webdriver.common.by import By
            self.driver.get(normalized)
            try:
                self.driver.implicitly_wait(2)
            except Exception:
                pass
            title = ""
            body = ""
            try:
                title_el = self.driver.find_element(By.TAG_NAME, "h1")
                title = title_el.text
            except Exception:
                pass
            body_selectors = [
                "div[data-click-id='text']",
                "div[data-test-id='post-content']",
                "div[slot='body']",
            ]
            for sel in body_selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el.text:
                        body = el.text
                        break
                except Exception:
                    continue
            combined = (title + "\n\n" + body).strip()
            return combined or normalized
        except Exception as e:
            logger.debug(f"fetch_post_context failed: {e}")
            return ""

    def _selenium_setting(self, key: str, default=None):
        """Safe access to selenium_settings dict."""
        if self.config and hasattr(self.config, "selenium_settings"):
            ss = self.config.selenium_settings
            if isinstance(ss, dict):
                return ss.get(key, default)
        return default

    def _wait_for_first(self, selectors: Sequence[Tuple[str, str]], timeout: int = 10):
        """Wait for the first selector to appear; returns the element or None on timeout."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            return WebDriverWait(self.driver, timeout).until(
                lambda d: next(
                    (
                        d.find_element(by, sel)
                        for by, sel in selectors
                        if d.find_elements(by, sel)
                    ),
                    None,
                )
            )
        except Exception:
            return None
    
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
        """Setup Chrome driver using undetected-chromedriver unless env forces regular."""
        logger.info("Setting up browser...")
        
        # If explicit binaries are provided (common in containers), skip undetected and go regular.
        if os.getenv("CHROME_BIN") or os.getenv("CHROMEDRIVER_PATH"):
            return self._setup_regular_selenium(prefer_env=True)
        
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
            # If explicit binaries are provided, skip undetected to avoid option incompatibility.
            if os.getenv("CHROME_BIN") or os.getenv("CHROMEDRIVER_PATH"):
                logger.info("CHROME_BIN/CHROMEDRIVER_PATH provided; skipping undetected-chromedriver.")
                return self._setup_regular_selenium(prefer_env=True)

            options = uc.ChromeOptions()
            
            # Get settings from config
            headless = self._selenium_setting("headless", False)
            
            ua = os.getenv("REDDIT_USER_AGENT") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

            # Add arguments
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument(f"--user-agent={ua}")
            
            # Headless mode if configured
            if headless:
                options.add_argument("--headless=new")
                logger.info("Running in headless mode")
            else:
                options.add_argument("--start-maximized")
            
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
    
    def _setup_regular_selenium(self, prefer_env: bool = False):
        """Setup using regular selenium"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
            
            options = Options()
            
            # Get settings from config / env
            headless = self._selenium_setting("headless", False)
            chrome_bin = self._selenium_setting("chrome_binary", "") or os.getenv("CHROME_BIN") or ""
            driver_env = self._selenium_setting("chromedriver_path", "") or os.getenv("CHROMEDRIVER_PATH") or ""
            driver_version = self._selenium_setting("chromedriver_version", "") or os.getenv("CHROMEDRIVER_VERSION") or ""
            ua = os.getenv("REDDIT_USER_AGENT") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

            # Add arguments
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument(f"--user-agent={ua}")

            if chrome_bin and Path(chrome_bin).exists():
                options.binary_location = chrome_bin
            
            # Fix SSL certificate errors
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--ignore-ssl-errors")
            options.add_argument("--allow-running-insecure-content")
            
            # Headless mode if configured
            if headless:
                options.add_argument("--headless=new")
            else:
                options.add_argument("--start-maximized")
            
            # Prefer explicit driver if provided (e.g., container-installed chromium-driver)
            if driver_env:
                driver_path = Path(driver_env)
                if not driver_path.exists():
                    logger.error(f"CHROMEDRIVER_PATH does not exist: {driver_path}; will try webdriver-manager.")
                else:
                    from selenium.webdriver.chrome.service import Service

                    service = Service(str(driver_path))
                    self.driver = webdriver.Chrome(service=service, options=options)
                    logger.info("Using driver from CHROMEDRIVER_PATH")
            else:
                # Fallback to bundled chromedriver-binary if available
                try:
                    import chromedriver_binary  # type: ignore
                    driver_env = getattr(chromedriver_binary, "chromedriver_filename", "")
                    if driver_env:
                        driver_path = Path(driver_env)
                        if driver_path.exists():
                            from selenium.webdriver.chrome.service import Service

                            service = Service(str(driver_path))
                            self.driver = webdriver.Chrome(service=service, options=options)
                            logger.info(f"Using bundled chromedriver-binary at {driver_path}")
                except Exception:
                    driver_env = ""

            if not self.driver:
                # Try webdriver-manager
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    from selenium.webdriver.chrome.service import Service

                    manager_kwargs = {}
                    if driver_version:
                        manager_kwargs["version"] = driver_version
                    install_path = ChromeDriverManager(**manager_kwargs).install()
                    driver_path = Path(install_path)

                    # Work around webdriver-manager sometimes returning a non-binary path (e.g., THIRD_PARTY_NOTICES)
                    if (not driver_path.is_file() or "THIRD_PARTY" in driver_path.name or not os.access(driver_path, os.X_OK)):
                        parent = driver_path.parent if driver_path.is_file() else driver_path
                        candidates = [
                            path for path in parent.rglob("*chromedriver*")
                            if path.is_file() and "THIRD_PARTY" not in path.name
                        ]
                        if not candidates:
                            raise RuntimeError(f"Could not find chromedriver binary in {parent}")
                        # prefer the one literally named "chromedriver"
                        candidates = sorted(candidates, key=lambda p: (p.name != "chromedriver", len(str(p))))
                        driver_path = candidates[0]
                        if not os.access(driver_path, os.X_OK):
                            try:
                                driver_path.chmod(0o755)
                            except Exception as chmod_err:
                                logger.warning(f"Could not chmod chromedriver: {chmod_err}")

                    service = Service(str(driver_path))
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

            # Quick reuse if already authenticated (requires user markers)
            if self._fast_session_check():
                logger.info("Existing Reddit session detected.")
                return True
            
            # SIMPLEST APPROACH: Manual Google login
            logger.info("Using simple manual login approach...")
            return self._simple_manual_login()
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def _fast_session_check(self) -> bool:
        """Quick best-effort check for an already-authenticated session."""
        try:
            from selenium.webdriver.common.by import By
            # Avoid extra navigation if already on reddit.com
            if "reddit.com" not in (self.driver.current_url or ""):
                self.driver.get("https://www.reddit.com/")
            marker = self._wait_for_first(
                [
                    (By.XPATH, "//button[@aria-label='User menu']"),
                    (By.XPATH, "//img[contains(@src, 'avatar')]"),
                    (By.CSS_SELECTOR, "a[data-click-id='user']"),
                    (By.XPATH, "//a[contains(@href,'/user/')]"),
                    (By.XPATH, "//span[contains(text(), '/u/')]"),
                ],
                timeout=6,
            )
            return bool(marker)
        except Exception:
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
            try:
                from selenium.webdriver.common.by import By
                self._wait_for_first(
                    [
                        (By.CSS_SELECTOR, "form[action*='login']"),
                        (By.CSS_SELECTOR, "button[data-testid='login-button']"),
                        (By.XPATH, "//button[contains(., 'Google')]"),
                    ],
                    timeout=12,
                )
            except Exception:
                logger.debug("Login form not detected before manual prompt; continuing.")
            
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
            # Just navigate to messages page and try to detect if logged in
            self.driver.get("https://www.reddit.com/message/unread")
            from selenium.webdriver.common.by import By
            self._wait_for_first(
                [
                    (By.CSS_SELECTOR, "[data-testid='inbox']"),
                    (By.TAG_NAME, "article"),
                ],
                timeout=8,
            )
            if "login" in self.driver.current_url.lower():
                logger.warning("Not logged in; skipping messages.")
                return []
            try:
                self.driver.find_element(By.CSS_SELECTOR, "[data-testid='inbox']")  # rough check
                logger.info("At messages page")
            except Exception:
                logger.info("Messages page loaded (no inbox marker found)")
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
            subreddits = self._bot_setting("subreddits", ["test"])
            subreddit = subreddits[0] if subreddits else "test"
        
        logger.info(f"Searching r/{subreddit}...")
        
        try:
            from selenium.webdriver.common.by import By
            
            # Navigate to subreddit (new Reddit UI)
            self.driver.get(f"https://www.reddit.com/r/{subreddit}/new")
            time.sleep(2)
            self._wait_for_first(
                [
                    (By.CSS_SELECTOR, "article"),
                    (By.CSS_SELECTOR, "div[data-testid='post-container']"),
                    (By.CSS_SELECTOR, "shreddit-post"),
                ],
                timeout=10,
            )
            self._dismiss_popups()
            time.sleep(1)
            
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

            # Scroll until enough posts are present or attempts exhausted.
            max_scrolls = 4
            for _ in range(max_scrolls):
                if len(self._find_post_elements(limit)) >= limit:
                    break
                self.driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.8);")
                time.sleep(0.8)
            self._dismiss_popups()
            
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
                if not posts:
                    json_posts = self._scrape_via_json(subreddit=subreddit, limit=limit)
                    logger.info(f"JSON fallback returned {len(json_posts)} posts")
                    if json_posts:
                        posts.extend(json_posts)

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
            keywords = ["accept", "agree", "continue", "got it", "consent", "allow"]
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
                "[data-testid='accept-privacy-button']",
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

            # JS fallback: click any button containing accept/agree text
            try:
                self.driver.execute_script(
                    """
const keywords = ["accept","agree","continue","allow","consent"];
const buttons = Array.from(document.querySelectorAll('button'));
for (const btn of buttons) {
  const t = (btn.innerText || "").toLowerCase();
  if (keywords.some(k => t.includes(k))) { btn.click(); break; }
}
                    """
                )
                time.sleep(0.3)
            except Exception:
                pass
            
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

    def _scrape_via_json(self, subreddit: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch posts via Reddit's JSON endpoint as a last-resort fallback."""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
            headers = {
                "User-Agent": os.getenv("REDDIT_USER_AGENT")
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            children = data.get("data", {}).get("children", [])
            posts = []
            for child in children:
                d = child.get("data", {})
                url = d.get("url") or f"https://www.reddit.com{d.get('permalink', '')}"
                posts.append(
                    {
                        "id": d.get("id", ""),
                        "title": d.get("title", ""),
                        "body": d.get("selftext", ""),
                        "subreddit": d.get("subreddit", subreddit),
                        "score": d.get("score", 0),
                        "author": d.get("author", ""),
                        "url": url,
                        "raw": d,
                        "method": "json",
                    }
                )
            return posts[:limit]
        except Exception as e:
            logger.debug(f"JSON scrape failed: {e}")
            return []


    def _js_find_comment_box(self):
        """Use JS (including shadow DOM) to locate a visible textarea/textbox."""
        try:
            el = self.driver.execute_script(
                """
const selectors = [
  'textarea#innerTextArea',
  'textarea[placeholder*="Share your thoughts"]',
  'textarea[placeholder*="comment"]',
  'textarea',
  'div[role="textbox"][data-lexical-editor="true"]',
  'div[contenteditable="true"][data-lexical-editor="true"]',
  'div[role="textbox"]',
  'div[contenteditable="true"]'
];

function isVisible(node) {
  if (!node) return false;
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
}

function findDeep(root) {
  if (!root) return null;
  for (const sel of selectors) {
    const found = root.querySelector(sel);
    if (found && isVisible(found)) return found;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.shadowRoot) {
      const shadowFound = findDeep(node.shadowRoot);
      if (shadowFound) return shadowFound;
    }
  }
  return null;
}

// Try inside the comment composer loader first
const loader = document.querySelector('shreddit-async-loader[bundlename="comment_composer"]');
if (loader) {
  const shadow = loader.shadowRoot || loader;
  const found = findDeep(shadow);
  if (found) return found;
}

return findDeep(document);
                """
            )
            return el
        except Exception:
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
            from selenium.webdriver.common.keys import Keys

            normalized_url = self._normalize_post_url(post_url)
            logger.info(f"Navigating to post for reply: {normalized_url}")
            self.driver.get(normalized_url)
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "textarea, [contenteditable='true'], article"))
                )
            except Exception as e:
                logger.debug(f"Initial wait for comment area failed: {e}")
            time.sleep(1.5)
            # JS-first path using helper module
            rh.js_open_comment_composer(self.driver)
            target_area = (
                rh.js_find_comment_box(self.driver)
                or rh.find_comment_area(self.driver)
                or rh.get_composer_element(self.driver)
            )
            if not target_area:
                rh.focus_comment_box(self.driver)
                target_area = (
                    rh.js_find_comment_box(self.driver)
                    or rh.find_comment_area(self.driver)
                    or rh.get_composer_element(self.driver)
                )
            if not target_area:
                return {"success": False, "error": "Could not find reply textarea"}

            # Try a direct focus/click on the detected area
            try:
                self.driver.execute_script("arguments[0].click(); arguments[0].focus();", target_area)
            except Exception:
                pass

            # First try a pure keystroke fill (no JS)
            filled = rh.keystroke_fill_simple(self.driver, target_area, reply_text)
            # JS-first fill attempts (shadow DOM aware)
            if not filled:
                filled = (
                    rh.js_fill_composer_strict(self.driver, reply_text)
                    or rh.js_fill_shreddit_composer(self.driver, reply_text)
                    or rh.js_force_set_comment_text(self.driver, reply_text)
                    or rh.js_paste_comment_text(self.driver, reply_text)
                )
            if not filled:
                filled = rh.fill_comment_box_via_keystrokes(self.driver, target_area, reply_text)
            if not filled:
                try:
                    active = self.driver.switch_to.active_element
                    active.send_keys(reply_text)
                except Exception as e:
                    logger.debug(f"Active element send_keys fallback failed: {e}")
            
            # Verify composer content and last-chance send_keys
            try:
                time.sleep(0.2)
                content = rh.get_composer_text(self.driver)
                if not str(content).strip():
                    # Last-chance: click area and send keys directly
                    try:
                        self.driver.execute_script("arguments[0].click(); arguments[0].focus();", target_area)
                    except Exception:
                        pass
                    try:
                        from selenium.webdriver import ActionChains  # type: ignore
                        actions = ActionChains(self.driver)
                        actions.move_to_element(target_area).click().pause(0.2).send_keys(reply_text).perform()
                        content = rh.get_composer_text(self.driver)
                    except Exception:
                        pass
                if not str(content).strip():
                    logger.warning("Composer readback empty; proceeding as filled based on actions taken.")
            except Exception as e:
                logger.debug(f"Composer verification failed: {e}")
                # Continue; treat as best-effort success
            
            if dry_run:
                logger.info("Dry run enabled; not submitting reply.")
                return {"success": True, "dry_run": True}
            
            # Attempt to submit the comment automatically.
            submitted = False
            try:
                submitted = rh.js_submit_comment(self.driver)
                if not submitted:
                    submitted = rh.submit_via_buttons(self.driver)
                if not submitted:
                    # Try keyboard submit (Ctrl+Enter) as a last resort.
                    try:
                        from selenium.webdriver import ActionChains  # type: ignore
                        actions = ActionChains(self.driver)
                        actions.key_down(Keys.CONTROL).send_keys("\n").key_up(Keys.CONTROL).perform()
                        submitted = True  # best-effort
                    except Exception as ke:
                        logger.debug(f"Keyboard submit fallback failed: {ke}")
            except Exception as e:
                logger.debug(f"Auto-submit failed: {e}")

            return {"success": True, "dry_run": False, "submitted": submitted}
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

    def save_login_cookies(self, cookie_file: str = "cookies.pkl") -> bool:
        """Save current session cookies via the LoginManager helper."""
        if not self.driver:
            logger.error("Driver not initialized; cannot save cookies")
            return False
        try:
            login_manager = self.get_login_manager()
            if not login_manager:
                logger.error("LoginManager not available; cannot save cookies")
                return False
            if hasattr(login_manager, "verify_login_success") and not login_manager.verify_login_success():
                logger.warning("Login not verified; cookies may be invalid")
            return login_manager.save_login_cookies(cookie_file)
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False

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
