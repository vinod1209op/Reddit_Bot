"""
Simple manual login helper for Reddit with Google OAuth
"""
import time
import random
import logging
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

class SimpleLogin:
    """Simple login helper that waits for manual Google login"""
    
    def __init__(self, driver):
        self.driver = driver
    
    def manual_google_login(self):
        """Simplest approach: Open Reddit login and wait for manual Google login"""
        logger.info("Starting manual Google login process...")
        
        try:
            # Go to Reddit login page
            self.driver.get("https://www.reddit.com/login")
            
            logger.info("\n" + "="*60)
            logger.info("MANUAL LOGIN INSTRUCTIONS:")
            logger.info("1. In the browser window that opened:")
            logger.info("2. Click 'Continue with Google'")
            logger.info("3. Complete the Google login process")
            logger.info("4. Return here and press Enter")
            logger.info("="*60 + "\n")
            
            # Wait for user to manually complete login
            input("Press Enter AFTER completing Google login in the browser...")
            
            # Wait a bit more
            time.sleep(3)
            
            # Verify login
            return self.verify_login()
            
        except Exception as e:
            logger.error(f"Manual login error: {e}")
            return False
    
    def verify_login(self):
        """Verify if login was successful"""
        try:
            # Check current URL
            current_url = self.driver.current_url.lower()
            logger.info(f"Current URL: {current_url}")
            
            # If still on login page, failed
            if "login" in current_url:
                logger.error("Still on login page - login may have failed")
                return False
            
            # Look for logged-in indicators
            indicators = [
                "//button[@aria-label='User menu']",
                "//img[contains(@src, 'avatar')]",
                "//span[contains(text(), '/u/')]",
                "//a[contains(text(), 'Create Post')]",
            ]
            
            for xpath in indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        logger.info(f"✓ Login successful! Found: {xpath}")
                        return True
                except:
                    continue
            
            # If on Reddit homepage, assume success
            if "reddit.com" in current_url and "login" not in current_url:
                logger.info("✓ Login appears successful (on Reddit, not login page)")
                return True
            
            logger.error("✗ Login verification failed")
            return False
            
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return False