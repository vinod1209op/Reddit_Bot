"""
Purpose: Login manager for Reddit (cookies/Google/credentials).
Constraints: Uses real browser; avoid automation outside approved flows.
"""

# Imports
import time
import random
import pickle
import logging
import os
from pathlib import Path

# Selenium selectors
from selenium.webdriver.common.by import By

# Setup logging
# Constants
logger = logging.getLogger(__name__)

# Import BrowserManager - all Selenium interactions go through this
from microdose_study_bot.reddit_selenium.utils.browser_manager import BrowserManager


# Public API
class LoginManager:
    def __init__(self, browser_manager=None, driver=None, headless=False):
        """Initialize LoginManager with optional shared BrowserManager/driver."""
        self.browser_manager = browser_manager or BrowserManager(headless=headless)
        self.driver = driver
        self.wait_time = 20  # Default wait time for operations

    def _log_security_challenge(self, context: str) -> None:
        """Log CAPTCHA/security challenge indicators if present."""
        if not self.driver:
            return
        try:
            current_url = self.driver.current_url
        except Exception:
            current_url = "unknown"

        keywords = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "verify you are human",
            "are you a human",
            "security challenge",
            "robot check",
        ]
        selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "div[data-sitekey]",
            "input[name='captcha']",
            "div[class*='captcha']",
            "div[id*='captcha']",
        ]

        page_source = self.browser_manager.get_page_source_safely(self.driver).lower()
        keyword_hit = any(key in page_source for key in keywords)

        selector_hit = False
        try:
            for selector in selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    selector_hit = True
                    break
        except Exception:
            selector_hit = False

        if keyword_hit or selector_hit:
            logger.warning(
                f"CAPTCHA_OR_CHALLENGE_DETECTED ({context}) url={current_url}"
            )
    
    def check_account_status(self) -> str:
        """
        Check if the current page indicates a ban, restriction, or other account issue.
        Returns:
            'active': No issues detected
            'suspended': Account has been suspended
            'rate_limited': Rate limit or temporary restriction
            'blocked': IP or account blocked
            'captcha': CAPTCHA challenge present
            'unknown': Could not determine status
        """
        if not self.driver:
            return "unknown"
        
        try:
            # Get page content safely
            page_source = self.browser_manager.get_page_source_safely(self.driver).lower()
            current_url = (self.driver.current_url or "").lower()
            
            # Define ban indicators with their priority (captcha tracked separately)
            ban_indicators = {
                "suspended": [
                    "this account has been suspended",
                    "account suspension",
                    "suspended from reddit",
                    "violated reddit's content policy"
                ],
                "rate_limited": [
                    "you are doing that too much",
                    "try again in",
                    "rate limit exceeded",
                    "too many requests",
                    "please try again later"
                ],
                "blocked": [
                    "access denied",
                    "you are blocked",
                    "restricted access",
                    "this content is not available"
                ],
            }
            captcha_indicators = [
                "recaptcha",
                "captcha",
                "verify you are human",
                "are you a robot",
            ]
            
            # Check for each type of issue
            for status_type, phrases in ban_indicators.items():
                if any(phrase in page_source for phrase in phrases):
                    logger.warning(f"ACCOUNT_STATUS_{status_type.upper()} detected")
                    return status_type

            captcha_detected = any(phrase in page_source for phrase in captcha_indicators)
            if captcha_detected:
                logger.warning("ACCOUNT_STATUS_CAPTCHA detected")
            
            # Special check for login page when we expected to be logged in
            if "login" in current_url or "auth" in current_url:
                # Check if this is a forced login (security challenge)
                if any(keyword in page_source for keyword in ["security check", "verify login"]):
                    logger.warning("ACCOUNT_STATUS_SECURITY_CHECK - Login verification required")
                    return "security_check"
            
            # Check for successful login indicators
            login_indicators = [
                "user menu",
                "create post",
                "/u/",
                "logout",
                "my profile"
            ]
            
            if any(indicator in page_source for indicator in login_indicators):
                if captcha_detected:
                    logger.warning("CAPTCHA detected while logged in; continuing as active")
                return "active"
            
            # If we're on reddit.com but none of the above, it's probably active
            if "reddit.com" in current_url and "login" not in current_url:
                if captcha_detected:
                    logger.warning("CAPTCHA detected on Reddit page; continuing as active")
                return "active"

            if captcha_detected:
                return "captcha"
            
            return "unknown"
            
        except Exception as e:
            logger.error(f"Error checking account status: {e}")
            return "unknown"
    
    def create_driver(self, headless=False):
        """Create a new browser driver using BrowserManager"""
        if not self.browser_manager or self.browser_manager.headless != headless:
            self.browser_manager = BrowserManager(headless=headless)
        self.driver = self.browser_manager.create_driver(use_undetected=self.browser_manager.use_undetected_default)
        
        # Randomize fingerprint to avoid detection
        self.browser_manager.randomize_fingerprint(self.driver)
        
        return self.driver
    
    def _wait_for_clickable(self, locators, timeout=None):
        """Wait for any locator to be clickable; returns element or None."""
        timeout = timeout or self.wait_time
        
        for by, value in locators:
            try:
                element = self.browser_manager.wait_for_clickable(
                    self.driver, by, value, timeout=2  # Try each locator for 2 seconds
                )
                if element:
                    return element
            except:
                continue
        
        # Fallback: manually try to find any clickable element
        try:
            for by, value in locators:
                elements = self.driver.find_elements(by, value)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        return element
        except:
            pass
        
        return None
    
    def _google_button_locators(self):
        return [
            (By.XPATH, "//button[contains(text(), 'Google')]"),
            (By.XPATH, "//button[contains(text(), 'Continue with Google')]"),
            (By.XPATH, "//button[contains(text(), 'Sign in with Google')]"),
            (By.CSS_SELECTOR, "button[data-provider='google']"),
            (By.CSS_SELECTOR, "button[aria-label*='Google']"),
            (By.CSS_SELECTOR, "button[data-testid*='google']"),
            (By.CSS_SELECTOR, "button[aria-label*='Continue with Google']"),
            (By.CSS_SELECTOR, "a[href*='accounts.google.com']"),
            (By.XPATH, "//div[contains(text(), 'Google')]/ancestor::button"),
            (By.XPATH, "//span[contains(text(), 'Google')]/ancestor::button"),
        ]

    def _find_google_button_js(self):
        """Attempt to find a Google login button via DOM + shadow DOM search."""
        if not self.driver:
            return None
        script = """
const queue = [document];
const seen = new Set();
const matchText = (el) => {
  const text = (el && el.textContent || '').toLowerCase();
  return text.includes('google') && (el.tagName === 'BUTTON' || el.tagName === 'A');
};

while (queue.length) {
  const root = queue.shift();
  if (!root || seen.has(root)) continue;
  seen.add(root);

  const nodes = root.querySelectorAll ? root.querySelectorAll('button,a') : [];
  for (const node of nodes) {
    if (matchText(node)) return node;
  }

  const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
  for (const el of all) {
    if (el.shadowRoot) queue.push(el.shadowRoot);
  }
}
return null;
"""
        try:
            return self.driver.execute_script(script)
        except Exception:
            return None
    
    def _google_email_locators(self):
        return [
            (By.ID, "identifierId"),
            (By.NAME, "identifier"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[autocomplete='username']"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[contains(@aria-label, 'email')]"),
        ]
    
    def _google_password_locators(self):
        return [
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
            (By.XPATH, "//input[@type='password']"),
            (By.XPATH, "//input[contains(@aria-label, 'password')]"),
        ]
    
    def _google_next_locators(self):
        return [
            (By.XPATH, "//button[contains(text(), 'Next')]"),
            (By.XPATH, "//span[contains(text(), 'Next')]/ancestor::button"),
            (By.XPATH, "//div[contains(text(), 'Next')]/ancestor::button"),
            (By.CSS_SELECTOR, "button[type='button']"),
            (By.ID, "identifierNext"),
            (By.ID, "passwordNext"),
        ]
    
    def login_with_google(self, google_email, google_password, headless=False):
        """Login to Reddit using Google OAuth with BrowserManager"""
        logger.info("Starting Google OAuth login process...")
        
        try:
            # Create driver if not already created
            if not self.driver:
                self.create_driver(headless=headless)
            
            # Go to Reddit login page
            self.driver.get("https://www.reddit.com/login")
            self.browser_manager.add_human_delay(2, 4)
            
            # Find and click Google button
            google_button = self._wait_for_clickable(self._google_button_locators(), timeout=12)
            if not google_button:
                google_button = self._find_google_button_js()
            if not google_button:
                # Check account status before giving up
                status = self.check_account_status()
                if status == "active":
                    logger.info("Already logged in; skipping Google login.")
                    return True, status
                logger.error("Could not find Google login button")
                return False, status
            
            self.browser_manager.safe_click(self.driver, google_button)
            logger.info("Clicked Google login button")
            
            # Handle Google OAuth flow
            success = self._handle_google_oauth(google_email, google_password)
            status = self.check_account_status()
            return success, status
            
        except Exception as e:
            logger.error(f"Google login failed: {str(e)}")
            status = self.check_account_status()
            return False, status
    
    def _handle_google_oauth(self, email, password):
        """Handle Google OAuth authentication flow using BrowserManager"""
        try:
            # Check if we're on Google login page
            current_url = self.driver.current_url.lower()
            logger.info(f"Current URL: {current_url}")
            
            if "accounts.google.com" not in current_url:
                logger.info("Not on Google accounts page, checking for email field")
            
            # Try to find email field
            email_field = self._wait_for_clickable(self._google_email_locators(), timeout=12)
            if not email_field:
                logger.error("Could not find Google email field")
                return False
            
            # Enter email with human-like typing
            self.browser_manager.human_like_typing(email_field, email)
            
            # Click next button for email
            next_button = self._wait_for_clickable(self._google_next_locators(), timeout=8)
            if next_button:
                self.browser_manager.safe_click(self.driver, next_button)
                self.browser_manager.add_human_delay(1, 2)
            
            # Try to find password field
            password_field = self._wait_for_clickable(self._google_password_locators(), timeout=12)
            if not password_field:
                logger.warning("Could not find password field, checking if already logged in")
                # Might be already logged into Google
                return self._check_google_logged_in()
            
            # Enter password with human-like typing
            self.browser_manager.human_like_typing(password_field, password)
            
            # Click next button for password
            next_button = self._wait_for_clickable(self._google_next_locators(), timeout=8)
            if next_button:
                self.browser_manager.safe_click(self.driver, next_button)
                self.browser_manager.add_human_delay(2, 4)
            
            # Check for 2FA or other security prompts
            if self._check_google_security_prompt():
                logger.warning("Google security prompt detected - may need manual intervention")
                # Wait longer for manual intervention if needed
                time.sleep(10)
            
            # Wait for redirect back to Reddit
            self.browser_manager.add_human_delay(3, 6)
            
            # Verify we're back on Reddit and logged in
            return self.verify_login_success()
            
        except Exception as e:
            logger.error(f"Google OAuth handling failed: {e}")
            return False
    
    def _check_google_security_prompt(self):
        """Check for Google security prompts (2FA, suspicious login, etc.)"""
        security_indicators = [
            "This device isn't recognized",
            "Verify it's you",
            "suspicious activity",
            "2-Step Verification",
            "Enter the code",
            "Get a verification code",
        ]
        
        page_text = self.browser_manager.get_page_source_safely(self.driver).lower()
        for indicator in security_indicators:
            if indicator.lower() in page_text:
                logger.warning(f"Google security prompt detected: {indicator}")
                return True
        
        return False
    
    def _check_google_logged_in(self):
        """Check if already logged into Google"""
        try:
            # Check for "Choose an account" screen
            choose_account_selectors = [
                "//div[contains(text(), 'Choose an account')]",
                "//div[contains(text(), 'Select an account')]",
                "//h1[contains(text(), 'Sign in')]",
            ]
            
            for selector in choose_account_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        logger.info("On Google account selection screen")
                        # Click the first account (usually the desired one)
                        account_buttons = self.driver.find_elements(
                            By.XPATH, 
                            "//div[@role='button' and contains(@aria-label, '@')]"
                        )
                        if account_buttons:
                            self.browser_manager.safe_click(self.driver, account_buttons[0])
                            self.browser_manager.add_human_delay(2, 3)
                            return True
                except:
                    continue
            
            # Check if already redirected
            if "reddit.com" in self.driver.current_url:
                return True
                
        except Exception as e:
            logger.error(f"Error checking Google login status: {e}")
        
        return False
    
    def verify_login_success(self):
        """Check if login was successful with multiple methods"""
        try:
            # Fast path for environments with tight timeouts (e.g., Render)
            if os.getenv("FAST_LOGIN_CHECK", "0").lower() in ("1", "true", "yes"):
                current_url = (self.driver.current_url or "").lower()
                if "reddit.com" in current_url and "login" not in current_url and "auth" not in current_url:
                    return True
                return False

            # Give it a moment to redirect
            self.browser_manager.add_human_delay(2, 4)
            
            # Check current URL
            current_url = self.driver.current_url.lower()
            if "login" in current_url or "auth" in current_url or "accounts.google.com" in current_url:
                self._log_security_challenge("verify_login_success")
                logger.warning(f"Still on login/auth page: {current_url}")
                return False
            
            # Check account status first
            status = self.check_account_status()
            if status != "active" and status != "unknown":
                logger.warning(f"Account status check failed: {status}")
                return False
            
            # Try multiple indicators using BrowserManager's wait methods
            indicators = [
                # User menu button
                (By.XPATH, "//button[@aria-label='User menu']", "User menu button"),
                # Create post button/link
                (By.XPATH, "//a[contains(text(), 'Create Post')]", "Create Post link"),
                (By.XPATH, "//button[contains(text(), 'Create Post')]", "Create Post button"),
                # User avatar
                (By.XPATH, "//img[contains(@src, 'avatar')]", "User avatar"),
                (By.XPATH, "//*[contains(@class, 'user-avatar')]", "User avatar class"),
                # Username display
                (By.XPATH, "//span[contains(text(), '/u/')]", "Username span"),
                # Home page indicators
                (By.XPATH, "//h1[contains(text(), 'Home')]", "Home header"),
                (By.XPATH, "//a[contains(@href, '/user/')]", "User profile link"),
            ]
            
            for by, xpath, description in indicators:
                try:
                    element = self.browser_manager.wait_for_element(
                        self.driver, by, xpath, timeout=3
                    )
                    if element:
                        logger.info(f"Login success indicator found: {description}")
                        return True
                except:
                    continue
            
            # Check page title or content
            page_source = self.browser_manager.get_page_source_safely(self.driver).lower()
            if "logout" in page_source or "my profile" in page_source:
                logger.info("Found logout or profile in page source")
                return True
            
            # If we're not on login page and not getting errors, assume success
            if "reddit.com" in current_url and "login" not in current_url:
                logger.info("Assuming login successful (on Reddit, not login page)")
                return True
            
            self._log_security_challenge("verify_login_success")
            return False
            
        except Exception as e:
            logger.error(f"Login verification error: {e}")
            return False
    
    def save_login_cookies(self, cookie_file="data/cookies_account1.pkl"):
        """Save cookies to file"""
        try:
            # Create directory if it doesn't exist
            cookie_path = Path(cookie_file)
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            
            cookies = self.driver.get_cookies()
            with open(cookie_file, 'wb') as f:
                pickle.dump(cookies, f)
            logger.info(f"✓ Saved {len(cookies)} cookies to {cookie_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False
    
    def load_cookies(self, cookie_file="data/cookies_account1.pkl"):
        """Load cookies from file"""
        try:
            cookie_path = Path(cookie_file)
            if not cookie_path.exists():
                logger.warning(f"Cookie file does not exist: {cookie_file}")
                return []
            
            with open(cookie_file, 'rb') as f:
                cookies = pickle.load(f)
            logger.info(f"Loaded {len(cookies)} cookies from {cookie_file}")
            return cookies
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return []
    
    def login_with_cookies(self, cookie_file="data/cookies_account1.pkl", headless=False):
        """Try to login using saved cookies"""
        try:
            logger.info("Attempting cookie login...")
            
            # Create driver if not already created
            if not self.driver:
                self.create_driver(headless=headless)
            
            # First go to reddit.com to set cookies
            self.driver.get("https://www.reddit.com")
            self.browser_manager.add_human_delay(1, 2)
            
            cookies = self.load_cookies(cookie_file)
            
            if not cookies:
                logger.warning("No cookies to load")
                return False, "no_cookies"
            
            # Clear existing cookies and add saved ones
            self.driver.delete_all_cookies()
            for cookie in cookies:
                try:
                    # Ensure cookie has required fields
                    if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                        cookie['sameSite'] = 'Lax'
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Could not add cookie: {e}")
            
            # Refresh to apply cookies
            self.driver.refresh()
            self.browser_manager.add_human_delay(2, 4)
            
            if self.verify_login_success():
                logger.info("✓ Logged in with cookies")
                return True, "active"
            else:
                self._log_security_challenge("cookie_login")
                # Check what specific issue we have
                status = self.check_account_status()
                logger.warning(f"Cookie login verification failed. Status: {status}")
                return False, status
                
        except Exception as e:
            logger.warning(f"Cookie login failed: {e}")
            status = self.check_account_status()
            return False, status
    
    def logout(self):
        """Clean logout function"""
        try:
            self.driver.get("https://www.reddit.com/logout")
            self.browser_manager.add_human_delay(1, 2)
            logger.info("Logged out successfully")
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False
    
    def login_with_credentials(self, username, password, headless=False):
        """Direct Reddit login (if not using Google)"""
        logger.info("Starting direct Reddit login...")
        
        try:
            # Create driver if not already created
            if not self.driver:
                self.create_driver(headless=headless)
            
            self.driver.get("https://www.reddit.com/login")
            self.browser_manager.add_human_delay(2, 4)
            
            # Find username field using BrowserManager
            username_field = self.browser_manager.wait_for_element(
                self.driver, 
                By.ID, 
                "loginUsername",
                timeout=10
            )
            if not username_field:
                logger.error("Could not find Reddit username field")
                return False, "element_not_found"
            
            # Human-like typing for username
            self.browser_manager.human_like_typing(username_field, username)
            self.browser_manager.add_human_delay(0.5, 1.5)
            
            # Find password field
            password_field = self.browser_manager.wait_for_element(
                self.driver,
                By.ID,
                "loginPassword",
                timeout=10
            )
            if not password_field:
                logger.error("Could not find Reddit password field")
                return False, "element_not_found"
            
            # Human-like typing for password
            self.browser_manager.human_like_typing(password_field, password)
            self.browser_manager.add_human_delay(0.8, 1.2)
            
            # Find login button
            login_button = self.browser_manager.wait_for_element(
                self.driver,
                By.XPATH,
                "//button[@type='submit']",
                timeout=10
            )
            if not login_button:
                logger.error("Could not find Reddit login button")
                return False, "element_not_found"
            
            # Safe click on login button
            self.browser_manager.safe_click(self.driver, login_button)
            self.browser_manager.add_human_delay(3, 5)
            
            # Verify login
            if self.verify_login_success():
                logger.info("✓ Direct Reddit login successful!")
                self.save_login_cookies()
                return True, "active"
            else:
                logger.warning("Direct login verification failed")
                status = self.check_account_status()
                return False, status
                
        except Exception as e:
            logger.error(f"Direct login failed: {str(e)}")
            status = self.check_account_status()
            return False, status
    
    def close_browser(self):
        """Close browser using BrowserManager"""
        if self.driver:
            self.browser_manager.close_driver(self.driver)
            self.driver = None
            logger.info("Browser closed")
    
    def get_driver(self):
        """Get the current driver instance"""
        return self.driver
    
    def is_logged_in(self):
        """Check if currently logged in"""
        if not self.driver:
            return False
        return self.verify_login_success()


# Legacy function for backward compatibility
def login_to_reddit(driver, username, password):
    """
    Legacy function - use LoginManager class instead
    Log in to Reddit with human-like behavior
    """
    logger = logging.getLogger(__name__)
    logger.warning("Using deprecated login_to_reddit function. Use LoginManager class instead.")
    
    # Create a BrowserManager instance
    from microdose_study_bot.reddit_selenium.utils.browser_manager import BrowserManager
    bm = BrowserManager(headless=False)
    
    try:
        # Go to login page
        driver.get("https://www.reddit.com/login")
        bm.add_human_delay(2, 4)
        
        # Wait for username field
        username_field = bm.wait_for_element(
            driver,
            By.ID,
            "loginUsername",
            timeout=10
        )
        
        if not username_field:
            logger.error("Could not find username field")
            return False
        
        # Human-like typing for username
        bm.human_like_typing(username_field, username)
        bm.add_human_delay(0.5, 1)
        
        # Find password field
        password_field = bm.wait_for_element(
            driver,
            By.ID,
            "loginPassword",
            timeout=5
        )
        
        if not password_field:
            logger.error("Could not find password field")
            return False
        
        # Human-like typing for password
        bm.human_like_typing(password_field, password)
        bm.add_human_delay(0.5, 1)
        
        # Find and click login button
        login_button = bm.wait_for_element(
            driver,
            By.XPATH,
            "//button[@type='submit']",
            timeout=5
        )
        
        if login_button:
            bm.safe_click(driver, login_button)
            bm.add_human_delay(3, 6)
            
            # Verify login success
            login_manager = LoginManager()
            login_manager.driver = driver
            login_manager.browser_manager = bm
            if login_manager.verify_login_success():
                logger.info("Login successful!")
                return True
        
        return False
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False
