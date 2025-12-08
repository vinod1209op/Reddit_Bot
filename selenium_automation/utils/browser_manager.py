"""
Browser management for Selenium automation
"""
import os
import sys
import random
import time
import logging
from pathlib import Path

# Fix import path - add parent directory to sys.path
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # Go up two levels to Reddit_Bot
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Setup logging
logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self, headless=False):
        self.headless = headless
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]
    
    def create_driver(self, use_undetected=True):
        """Create Chrome driver"""
        try:
            if use_undetected:
                import undetected_chromedriver as uc
                return self._create_undetected_driver(uc)
            else:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                return self._create_regular_driver(webdriver, Options)
        except ImportError as e:
            logger.error(f"Failed to import required modules: {e}")
            raise
    
    def _create_undetected_driver(self, uc):
        """Create undetected Chrome driver"""
        options = uc.ChromeOptions()
        
        # Add arguments to mimic human behavior
        options.add_argument(f"user-agent={random.choice(self.user_agents)}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        
        # Fix SSL certificate errors
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--allow-insecure-localhost")
        
        # Exclude automation detection
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Add stealth settings
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        if self.headless:
            options.add_argument("--headless=new")
            logger.info("Creating headless browser")
        else:
            options.add_argument("--start-maximized")
        
        driver = uc.Chrome(
            options=options,
            suppress_welcome=True,
            use_subprocess=False,
        )
        
        # Execute CDP commands to avoid detection
        try:
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": random.choice(self.user_agents)
            })
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            })
        except:
            pass
        
        logger.info("Undetected Chrome browser created successfully")
        return driver
    
    def _create_regular_driver(self, webdriver, Options):
        """Create regular Selenium Chrome driver"""
        options = Options()
        
        # Add arguments
        options.add_argument(f"user-agent={random.choice(self.user_agents)}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        
        # Fix SSL certificate errors
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--allow-insecure-localhost")
        
        if self.headless:
            options.add_argument("--headless=new")
            logger.info("Creating headless browser")
        else:
            options.add_argument("--start-maximized")
        
        # Try to use webdriver-manager for automatic driver management
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            logger.info("Regular Chrome browser created with webdriver-manager")
        except ImportError:
            # Fallback to system ChromeDriver
            try:
                driver = webdriver.Chrome(options=options)
                logger.info("Using system ChromeDriver")
            except Exception as chrome_error:
                logger.error(f"System ChromeDriver failed: {chrome_error}")
                raise
        
        return driver
    
    def add_human_delay(self, min_seconds=1, max_seconds=3):
        """Add random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"Adding human delay: {delay:.2f}s")
        time.sleep(delay)
    
    def human_like_typing(self, element, text):
        """Type text with human-like delays"""
        try:
            element.click()
            time.sleep(random.uniform(0.2, 0.5))
            
            logger.debug(f"Typing text: {text[:20]}...")
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            time.sleep(random.uniform(0.1, 0.3))
            return True
        except Exception as e:
            logger.error(f"Human typing failed: {e}")
            # Fallback: just send keys
            try:
                element.clear()
                element.send_keys(text)
                return True
            except:
                return False

# Import Selenium components here to avoid circular imports
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available")

if SELENIUM_AVAILABLE:
    def wait_for_element(self, driver, by, value, timeout=10):
        """Wait for element to be present"""
        try:
            wait = WebDriverWait(driver, timeout)
            element = wait.until(EC.presence_of_element_located((by, value)))
            return element
        except Exception as e:
            logger.warning(f"Element not found: {by}={value} - {e}")
            return None
    
    def wait_for_clickable(self, driver, by, value, timeout=10):
        """Wait for element to be clickable"""
        try:
            wait = WebDriverWait(driver, timeout)
            element = wait.until(EC.element_to_be_clickable((by, value)))
            return element
        except Exception as e:
            logger.warning(f"Element not clickable: {by}={value} - {e}")
            return None
else:
    def wait_for_element(self, driver, by, value, timeout=10):
        """Dummy function when selenium not available"""
        logger.error("Selenium not available for wait_for_element")
        return None
    
    def wait_for_clickable(self, driver, by, value, timeout=10):
        """Dummy function when selenium not available"""
        logger.error("Selenium not available for wait_for_clickable")
        return None

def scroll_to_element(self, driver, element):
    """Scroll to element smoothly"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(random.uniform(0.5, 1))
        return True
    except Exception as e:
        logger.debug(f"Could not scroll to element: {e}")
        return False

def scroll_down(self, driver, pixels=500):
    """Scroll down by pixels"""
    try:
        driver.execute_script(f"window.scrollBy(0, {pixels});")
        time.sleep(random.uniform(0.5, 1))
        return True
    except Exception as e:
        logger.debug(f"Could not scroll: {e}")
        return False

def take_screenshot(self, driver, filename="screenshot.png"):
    """Take screenshot of current page"""
    try:
        # Create screenshots directory if it doesn't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        driver.save_screenshot(filename)
        logger.info(f"Screenshot saved: {filename}")
        return True
    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")
        return False

def get_page_source_safely(self, driver):
    """Get page source with error handling"""
    try:
        return driver.page_source
    except Exception as e:
        logger.error(f"Failed to get page source: {e}")
        return ""

def safe_click(self, driver, element):
    """Safely click element with retry"""
    try:
        # Scroll to element first
        self.scroll_to_element(driver, element)
        
        # Wait for clickable
        time.sleep(random.uniform(0.5, 1))
        
        # Try to click
        element.click()
        return True
    except Exception as e:
        logger.warning(f"Click failed, trying JavaScript: {e}")
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as js_e:
            logger.error(f"JavaScript click also failed: {js_e}")
            return False

def fill_form_field(self, driver, field_id, value):
    """Fill form field with human-like behavior"""
    element = self.wait_for_element(driver, By.ID, field_id)
    if element:
        return self.human_like_typing(element, value)
    return False

# Legacy function kept for backward compatibility
def login_to_reddit(driver, username, password):
    """
    Log in to Reddit with human-like behavior
    
    Note: Prefer using LoginManager class for better functionality
    """
    if not SELENIUM_AVAILABLE:
        logger.error("Selenium not available for login_to_reddit")
        return False
    
    logger.info("Logging in to Reddit...")
    
    # Go to login page
    driver.get("https://www.reddit.com/login")
    time.sleep(random.uniform(2, 4))
    
    try:
        # Wait for username field
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "loginUsername"))
        )
        
        # Human-like typing for username
        for char in username:
            username_field.send_keys(char)
            time.sleep(random.uniform(0.08, 0.15))
        
        time.sleep(random.uniform(0.5, 1))
        
        # Fill password
        password_field = driver.find_element(By.ID, "loginPassword")
        for char in password:
            password_field.send_keys(char)
            time.sleep(random.uniform(0.05, 0.12))
        
        time.sleep(random.uniform(0.5, 1.5))
        
        # Click login button
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        # Wait for login to complete
        time.sleep(random.uniform(3, 6))
        
        # Verify login success
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[@aria-label='User menu']"))
            )
            logger.info("Login successful!")
            return True
        except:
            logger.warning("Login might have failed, checking URL...")
            if "login" not in driver.current_url:
                logger.info("Login successful (redirected)")
                return True
            return False
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False

# Add methods to BrowserManager class
BrowserManager.wait_for_element = wait_for_element
BrowserManager.wait_for_clickable = wait_for_clickable
BrowserManager.scroll_to_element = scroll_to_element
BrowserManager.scroll_down = scroll_down
BrowserManager.take_screenshot = take_screenshot
BrowserManager.get_page_source_safely = get_page_source_safely
BrowserManager.safe_click = safe_click
BrowserManager.fill_form_field = fill_form_field