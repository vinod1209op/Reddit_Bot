"""
Browser management for Selenium automation
"""
import os
import sys
import random
import time
import logging
from pathlib import Path

try:
    from tor_proxy import tor_proxy
    TOR_AVAILABLE = True
except ImportError:
    TOR_AVAILABLE = False
    logger.warning("TorProxy not available")

# Fix import path - add parent directory to sys.path
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # Go up two levels to Reddit_Bot
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Setup logging
logger = logging.getLogger(__name__)

def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

# Try to import Selenium components
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available")


class BrowserManager:
    def __init__(self, headless=False, stealth_mode=None, randomize_fingerprint=None, use_undetected=None):
        self.headless = headless
        self.stealth_mode = _env_flag("SELENIUM_STEALTH", True) if stealth_mode is None else bool(stealth_mode)
        self.randomize_fingerprint_enabled = (
            _env_flag("SELENIUM_RANDOMIZE_FINGERPRINT", True)
            if randomize_fingerprint is None
            else bool(randomize_fingerprint)
        )
        self.use_undetected_default = (
            _env_flag("SELENIUM_USE_UNDETECTED", True)
            if use_undetected is None
            else bool(use_undetected)
        )
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]
        self.wait_time = 10  # Default wait time
        self.use_tor = _env_flag("USE_TOR_PROXY", False)

    def _get_chrome_paths(self):
        """Return (chromedriver_path, chrome_bin) if set and present."""
        chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "").strip()
        chrome_bin = os.getenv("CHROME_BIN", "").strip()

        if chromedriver_path and not os.path.exists(chromedriver_path):
            logger.warning("CHROMEDRIVER_PATH not found: %s", chromedriver_path)
            chromedriver_path = ""

        if chrome_bin and not os.path.exists(chrome_bin):
            logger.warning("CHROME_BIN not found: %s", chrome_bin)
            chrome_bin = ""

        return chromedriver_path, chrome_bin
    
    def create_driver(self, use_undetected=None):
        """Create Chrome driver with optional undetected mode."""
        try:
            if use_undetected is None:
                use_undetected = self.use_undetected_default

            chromedriver_path, _ = self._get_chrome_paths()
            ci_mode = os.getenv("CI", "").lower() == "true"
            if ci_mode:
                use_undetected = True
                logger.info("CI detected: forcing undetected-chromedriver")

            if self.use_tor and TOR_AVAILABLE and ci_mode:
                logger.info("Starting Tor proxy for CI...")
                tor_proxy.start()

            if use_undetected:
                import undetected_chromedriver as uc
                driver = (
                    self._create_undetected_driver_ci(uc)
                    if ci_mode
                    else self._create_undetected_driver(uc)
                )
            else:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                driver = self._create_regular_driver(webdriver, Options)

            return driver
        except ImportError as e:
            logger.error(f"Failed to import required modules: {e}")
            raise
    
    def _create_undetected_driver(self, uc):
        """Create undetected Chrome driver"""
        options = uc.ChromeOptions()

        chromedriver_path, chrome_bin = self._get_chrome_paths()
        if chrome_bin:
            options.binary_location = chrome_bin
        self._apply_tor_proxy_to_options(options)
        
        # Add arguments to mimic human behavior (when stealth is enabled)
        if self.stealth_mode:
            options.add_argument(f"user-agent={random.choice(self.user_agents)}")
            options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        
        # Fix SSL certificate errors
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--allow-insecure-localhost")
        
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
        
        driver_kwargs = {
            "options": options,
            "suppress_welcome": True,
            "use_subprocess": False,
        }
        if chromedriver_path:
            driver_kwargs["driver_executable_path"] = chromedriver_path
        if chrome_bin:
            driver_kwargs["browser_executable_path"] = chrome_bin

        driver = uc.Chrome(**driver_kwargs)
        
        # Execute CDP commands to avoid detection (stealth only)
        if self.stealth_mode:
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

    def _apply_tor_proxy_to_options(self, options):
        """Add Tor proxy settings to Chrome options if enabled."""
        if self.use_tor and TOR_AVAILABLE and hasattr(tor_proxy, "proxy_url"):
            options.add_argument(f"--proxy-server={tor_proxy.proxy_url}")
            logger.info(f"Applying Tor proxy to browser options: {tor_proxy.proxy_url}")

    def _create_undetected_driver_ci(self, uc):
        """Create undetected Chrome driver optimized for CI."""
        options = uc.ChromeOptions()

        chromedriver_path, chrome_bin = self._get_chrome_paths()
        if chrome_bin:
            options.binary_location = chrome_bin

        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-blink-features")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-US,en;q=0.9")
        options.add_argument("--accept-lang=en-US,en;q=0.9")

        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        options.add_argument(f"user-agent={user_agent}")

        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_setting_values.popups": 2,
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.cookies": 1,
            "enable_do_not_track": True,
        }
        options.add_experimental_option("prefs", prefs)

        driver_kwargs = {
            "options": options,
            "use_subprocess": False,
            "version_main": 120,
        }
        if chromedriver_path:
            driver_kwargs["driver_executable_path"] = chromedriver_path

        driver = uc.Chrome(**driver_kwargs)

        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            const defineProp = (target, name, descriptor) => {
                try {
                    Object.defineProperty(target, name, descriptor);
                } catch (err) {
                    if (err && err.message && err.message.includes('Cannot redefine property')) {
                        return;
                    }
                    throw err;
                }
            };

            defineProp(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            defineProp(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
                configurable: true
            });
            defineProp(navigator, 'languages', {
                get: () => ['en-US', 'en'],
                configurable: true
            });

            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {};
            window.chrome.loadTimes = function(){};
            window.chrome.csi = function(){};
            window.chrome.app = window.chrome.app || {};

            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            """
        })

        driver.execute_cdp_cmd("Network.setUserAgentOverride", {
            "userAgent": user_agent,
            "platform": "Win32"
        })

        driver.execute_script("""
            if (!Object.getOwnPropertyDescriptor(navigator, 'webdriver')?.configurable) {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
            }
        """)

        logger.info("Created anti-block Chrome driver for CI")
        return driver
    
    def _create_regular_driver(self, webdriver, Options):
        """Create regular Selenium Chrome driver"""
        options = Options()

        chromedriver_path, chrome_bin = self._get_chrome_paths()
        if chrome_bin:
            options.binary_location = chrome_bin
        self._apply_tor_proxy_to_options(options)
        
        # Add arguments (stealth only)
        if self.stealth_mode:
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
        
        if chromedriver_path:
            try:
                from selenium.webdriver.chrome.service import Service

                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=options)
                logger.info("Regular Chrome browser created with CHROMEDRIVER_PATH")
                return driver
            except Exception as chrome_error:
                logger.error(f"CHROMEDRIVER_PATH failed: {chrome_error}")

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
        return delay
    
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
    
    def wait_for_element(self, driver, by, value, timeout=None):
        """Wait for element to be present"""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available for wait_for_element")
            return None
        
        timeout = timeout or self.wait_time
        try:
            wait = WebDriverWait(driver, timeout)
            element = wait.until(EC.presence_of_element_located((by, value)))
            return element
        except Exception as e:
            warn = _env_flag("SELENIUM_WAIT_WARN", False)
            level = logging.WARNING if warn else logging.DEBUG
            logger.log(level, f"Element not found: {by}={value} - {e}")
            return None
    
    def wait_for_clickable(self, driver, by, value, timeout=None):
        """Wait for element to be clickable"""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available for wait_for_clickable")
            return None
        
        timeout = timeout or self.wait_time
        try:
            wait = WebDriverWait(driver, timeout)
            element = wait.until(EC.element_to_be_clickable((by, value)))
            return element
        except Exception as e:
            warn = _env_flag("SELENIUM_WAIT_WARN", False)
            level = logging.WARNING if warn else logging.DEBUG
            logger.log(level, f"Element not clickable: {by}={value} - {e}")
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
            directory = os.path.dirname(filename)
            if directory:
                os.makedirs(directory, exist_ok=True)
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
    
    def randomize_fingerprint(self, driver):
        """Randomize browser fingerprint to avoid detection"""
        if not self.stealth_mode or not self.randomize_fingerprint_enabled:
            return False
        # Random viewport
        viewports = [
            (1920, 1080), (1366, 768), (1536, 864),
            (1440, 900), (1280, 720), (1600, 900)
        ]
        width, height = random.choice(viewports)
        driver.set_window_size(width, height)
        
        # Random user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"
        ]
        
        # Use CDP to override user agent
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": random.choice(user_agents)
            })
        except:
            pass
        
        # Remove automation flags
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Random timezone (via JavaScript)
        timezones = ['America/Los_Angeles', 'America/New_York', 'Europe/London', 'Australia/Sydney']
        driver.execute_script(f"""
            Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {{
                get() {{
                    const result = Reflect.apply(Intl.DateTimeFormat.prototype.resolvedOptions, this, arguments);
                    result.timeZone = '{random.choice(timezones)}';
                    return result;
                }}
            }});
        """)
        
        return True

    @staticmethod
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
            except Exception:
                logger.warning("Login might have failed, checking URL...")
                if "login" not in driver.current_url:
                    logger.info("Login successful (redirected)")
                    return True
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def human_like_pause(self, min_seconds=1, max_seconds=5):
        """Human-like pause with exponential distribution"""
        pause = random.expovariate(1.0/3)  # Mean 3 seconds
        pause = max(min_seconds, min(pause, max_seconds))
        time.sleep(pause)
        return pause
    
    def close_driver(self, driver):
        """Safely close the driver with cleanup"""
        if self.use_tor and TOR_AVAILABLE:
            tor_proxy.stop()
        if driver:
            try:
                driver.quit()
            except:
                pass


# Legacy function kept for backward compatibility (keep outside class)
def login_to_reddit(driver, username, password):
    return BrowserManager.login_to_reddit(driver, username, password)
