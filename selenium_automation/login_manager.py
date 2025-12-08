import time
import random
import pickle
import logging
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

class LoginManager:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
    
    def login_with_google(self, google_email, google_password):
        """Login to Reddit using Google OAuth"""
        logger.info("Starting Google OAuth login process...")
        
        try:
            # Go to Reddit login page
            self.driver.get("https://www.reddit.com/login")
            time.sleep(random.uniform(2, 4))
            
            # Click the "Continue with Google" button
            google_button = self._find_google_button()
            if not google_button:
                logger.error("Could not find Google login button")
                return False
            
            google_button.click()
            logger.info("Clicked Google login button")
            time.sleep(random.uniform(2, 4))
            
            # Handle Google OAuth flow
            return self._handle_google_oauth(google_email, google_password)
            
        except Exception as e:
            logger.error(f"Google login failed: {str(e)}")
            return False
    
    def _find_google_button(self):
        """Find the Google login button on Reddit"""
        locators = [
            (By.XPATH, "//button[contains(text(), 'Google')]"),
            (By.XPATH, "//button[contains(text(), 'Continue with Google')]"),
            (By.XPATH, "//button[contains(text(), 'Sign in with Google')]"),
            (By.CSS_SELECTOR, "button[data-provider='google']"),
            (By.CSS_SELECTOR, "button[aria-label*='Google']"),
            (By.XPATH, "//div[contains(text(), 'Google')]/ancestor::button"),
            (By.XPATH, "//span[contains(text(), 'Google')]/ancestor::button"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed() and element.is_enabled():
                    logger.info(f"Found Google button with: {by}={value}")
                    return element
            except:
                continue
        
        logger.error("No Google login button found")
        return None
    
    def _handle_google_oauth(self, email, password):
        """Handle Google OAuth authentication flow"""
        try:
            # Wait for Google login page to load
            time.sleep(3)
            
            # Check if we're on Google login page
            current_url = self.driver.current_url.lower()
            logger.info(f"Current URL: {current_url}")
            
            if "accounts.google.com" not in current_url:
                # Might be on a different OAuth page
                logger.info("Not on Google accounts page, checking for email field")
            
            # Try to find email field
            email_field = self._find_google_email_field()
            if not email_field:
                logger.error("Could not find Google email field")
                return False
            
            # Enter email
            self._human_type(email_field, email)
            time.sleep(random.uniform(1, 2))
            
            # Click next button for email
            next_button = self._find_google_next_button()
            if next_button:
                next_button.click()
                time.sleep(random.uniform(2, 4))
            
            # Try to find password field
            password_field = self._find_google_password_field()
            if not password_field:
                logger.warning("Could not find password field, checking if already logged in")
                # Might be already logged into Google
                return self._check_google_logged_in()
            
            # Enter password
            self._human_type(password_field, password)
            time.sleep(random.uniform(1, 2))
            
            # Click next button for password
            next_button = self._find_google_next_button()
            if next_button:
                next_button.click()
                time.sleep(random.uniform(3, 5))
            
            # Check for 2FA or other security prompts
            if self._check_google_security_prompt():
                logger.warning("Google security prompt detected - may need manual intervention")
                # Wait longer for manual intervention if needed
                time.sleep(10)
            
            # Wait for redirect back to Reddit
            time.sleep(5)
            
            # Verify we're back on Reddit and logged in
            return self.verify_login_success()
            
        except Exception as e:
            logger.error(f"Google OAuth handling failed: {e}")
            return False
    
    def _find_google_email_field(self):
        """Find email field on Google login page"""
        locators = [
            (By.ID, "identifierId"),
            (By.NAME, "identifier"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[autocomplete='username']"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[contains(@aria-label, 'email')]"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed():
                    logger.info(f"Found Google email field with: {by}={value}")
                    return element
            except:
                continue
        
        logger.error("No Google email field found")
        return None
    
    def _find_google_password_field(self):
        """Find password field on Google login page"""
        locators = [
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
            (By.XPATH, "//input[@type='password']"),
            (By.XPATH, "//input[contains(@aria-label, 'password')]"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed():
                    logger.info(f"Found Google password field with: {by}={value}")
                    return element
            except:
                continue
        
        logger.warning("No Google password field found")
        return None
    
    def _find_google_next_button(self):
        """Find next button on Google login page"""
        locators = [
            (By.XPATH, "//button[contains(text(), 'Next')]"),
            (By.XPATH, "//span[contains(text(), 'Next')]/ancestor::button"),
            (By.XPATH, "//div[contains(text(), 'Next')]/ancestor::button"),
            (By.CSS_SELECTOR, "button[type='button']"),
            (By.ID, "identifierNext"),
            (By.ID, "passwordNext"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed() and element.is_enabled():
                    logger.info(f"Found Google next button with: {by}={value}")
                    return element
            except:
                continue
        
        logger.warning("No Google next button found")
        return None
    
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
        
        page_text = self.driver.page_source.lower()
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
                    self.driver.find_element(By.XPATH, selector)
                    logger.info("On Google account selection screen")
                    # Click the first account (usually the desired one)
                    account_buttons = self.driver.find_elements(
                        By.XPATH, "//div[@role='button' and contains(@aria-label, '@')]"
                    )
                    if account_buttons:
                        account_buttons[0].click()
                        time.sleep(3)
                        return True
                except:
                    continue
            
            # Check if already redirected
            if "reddit.com" in self.driver.current_url:
                return True
                
        except Exception as e:
            logger.error(f"Error checking Google login status: {e}")
        
        return False
    
    def _human_type(self, element, text):
        """Type text with human-like delays"""
        try:
            element.click()
            time.sleep(random.uniform(0.2, 0.5))
            
            element.clear()
            time.sleep(random.uniform(0.1, 0.3))
            
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            time.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            logger.warning(f"Human typing failed, using simple typing: {e}")
            try:
                element.clear()
                element.send_keys(text)
            except:
                pass
    
    def verify_login_success(self):
        """Check if login was successful with multiple methods"""
        try:
            # Give it a moment to redirect
            time.sleep(3)
            
            # Check current URL
            current_url = self.driver.current_url.lower()
            if "login" in current_url or "auth" in current_url or "accounts.google.com" in current_url:
                logger.warning(f"Still on login/auth page: {current_url}")
                return False
            
            # Try multiple indicators
            indicators = [
                # User menu button
                ("//button[@aria-label='User menu']", "User menu button"),
                # Create post button/link
                ("//a[contains(text(), 'Create Post')]", "Create Post link"),
                ("//button[contains(text(), 'Create Post')]", "Create Post button"),
                # User avatar
                ("//img[contains(@src, 'avatar')]", "User avatar"),
                ("//*[contains(@class, 'user-avatar')]", "User avatar class"),
                # Username display
                ("//span[contains(text(), '/u/')]", "Username span"),
                # Home page indicators
                ("//h1[contains(text(), 'Home')]", "Home header"),
                ("//a[contains(@href, '/user/')]", "User profile link"),
            ]
            
            for xpath, description in indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        logger.info(f"Login success indicator found: {description}")
                        return True
                except:
                    continue
            
            # Check page title or content
            page_source = self.driver.page_source.lower()
            if "logout" in page_source or "my profile" in page_source:
                logger.info("Found logout or profile in page source")
                return True
            
            # If we're not on login page and not getting errors, assume success
            if "reddit.com" in current_url and "login" not in current_url:
                logger.info("Assuming login successful (on Reddit, not login page)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Login verification error: {e}")
            return False
    
    def save_login_cookies(self, cookie_file="cookies.pkl"):
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
    
    def load_cookies(self, cookie_file="cookies.pkl"):
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
    
    def login_with_cookies(self, cookie_file="cookies.pkl"):
        """Try to login using saved cookies"""
        try:
            logger.info("Attempting cookie login...")
            
            # First go to reddit.com to set cookies
            self.driver.get("https://www.reddit.com")
            time.sleep(2)
            
            cookies = self.load_cookies(cookie_file)
            
            if not cookies:
                logger.warning("No cookies to load")
                return False
            
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
            time.sleep(3)
            
            if self.verify_login_success():
                logger.info("✓ Logged in with cookies")
                return True
            else:
                logger.warning("Cookie login verification failed")
                return False
                
        except Exception as e:
            logger.warning(f"Cookie login failed: {e}")
            return False
    
    def logout(self):
        """Clean logout function"""
        try:
            self.driver.get("https://www.reddit.com/logout")
            time.sleep(2)
            logger.info("Logged out successfully")
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False

    # Keep the original login_with_credentials for direct Reddit login (optional)
    def login_with_credentials(self, username, password):
        """Direct Reddit login (if not using Google)"""
        logger.info("Starting direct Reddit login...")
        
        try:
            self.driver.get("https://www.reddit.com/login")
            time.sleep(random.uniform(2, 4))
            
            # Check if Google button is present
            google_button = self._find_google_button()
            if google_button and google_button.is_displayed():
                logger.warning("Google button detected but using direct login")
            
            # Find username field
            username_field = self._find_reddit_username_field()
            if not username_field:
                logger.error("Could not find Reddit username field")
                return False
            
            self._human_type(username_field, username)
            time.sleep(random.uniform(0.5, 1.5))
            
            # Find password field
            password_field = self._find_reddit_password_field()
            if not password_field:
                logger.error("Could not find Reddit password field")
                return False
            
            self._human_type(password_field, password)
            time.sleep(random.uniform(0.8, 1.2))
            
            # Find login button
            login_button = self._find_reddit_login_button()
            if not login_button:
                logger.error("Could not find Reddit login button")
                return False
            
            login_button.click()
            time.sleep(random.uniform(3, 5))
            
            if self.verify_login_success():
                logger.info("✓ Direct Reddit login successful!")
                self.save_login_cookies()
                return True
            else:
                logger.warning("Direct login verification failed")
                return False
                
        except Exception as e:
            logger.error(f"Direct login failed: {str(e)}")
            return False
    
    def _find_reddit_username_field(self):
        """Find Reddit username field"""
        locators = [
            (By.ID, "loginUsername"),
            (By.NAME, "username"),
            (By.CSS_SELECTOR, "input[name='username']"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed():
                    return element
            except:
                continue
        return None
    
    def _find_reddit_password_field(self):
        """Find Reddit password field"""
        locators = [
            (By.ID, "loginPassword"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[name='password']"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed():
                    return element
            except:
                continue
        return None
    
    def _find_reddit_login_button(self):
        """Find Reddit login button"""
        locators = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Log In')]"),
        ]
        
        for by, value in locators:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed():
                    return element
            except:
                continue
        return None