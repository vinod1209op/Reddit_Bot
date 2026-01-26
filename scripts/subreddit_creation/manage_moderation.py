#!/usr/bin/env python3
"""
MCRDSE Subreddit Moderation Manager
"""

import json
import time
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/moderation_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SeleniumModerationManager:
    """Selenium-based moderation manager for MCRDSE subreddits"""
    
    def __init__(self, account_name="account1", headless=True):
        """
        Initialize moderation manager with Selenium
        
        Args:
            account_name: Which Reddit account to use (from config/accounts.json)
            headless: Run browser in background
        """
        self.account_name = account_name
        self.headless = headless
        self.driver = None
        self.config = self.load_config()
        self.moderation_stats = {}
        
        # Load account-specific settings
        self.account_config = self.load_account_config()
        
    def load_config(self) -> Dict:
        """Load moderation configuration"""
        config_path = Path("config/moderation_config.json")
        
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Config file corrupted, using defaults")
        
        # Default configuration
        default_config = {
            "moderation": {
                "auto_approve_trusted_users": True,
                "remove_spam_keywords": ["buy", "sell", "vendor", "price", "dm me"],
                "remove_self_harm_keywords": ["suicide", "kill myself", "end my life"],
                "require_flair": True,
                "min_post_length": 50,
                "max_posts_per_hour": 3,
                "max_comments_per_hour": 10
            },
            "flairs": {
                "post_flairs": [
                    {"name": "Research Discussion", "color": "#0DD3BB"},
                    {"name": "Personal Experience", "color": "#FFB000"},
                    {"name": "Scientific Study", "color": "#46D160"},
                    {"name": "Question", "color": "#FFD635"},
                    {"name": "Resource Share", "color": "#0079D3"},
                    {"name": "Community News", "color": "#FF4500"},
                    {"name": "Meta Discussion", "color": "#7E53C1"}
                ],
                "user_flairs": [
                    {"name": "Researcher", "color": "#0DD3BB"},
                    {"name": "Therapist", "color": "#FFB000"},
                    {"name": "Educator", "color": "#46D160"},
                    {"name": "Student", "color": "#FFD635"},
                    {"name": "Advocate", "color": "#0079D3"},
                    {"name": "MCRDSE Team", "color": "#FF4500"}
                ]
            },
            "automod_templates": {
                "basic": """---
# Basic AutoModerator rules for MCRDSE communities
type: submission
author:
    account_age: "< 24 hours"
    combined_karma: "< 10"
action: filter
action_reason: "New account/low karma"

type: submission
title+body (includes): ["buy", "sell", "vendor", "price", "dm me"]
action: filter
action_reason: "Potential sourcing"

type: submission
title+body (includes): ["suicide", "kill myself", "end my life"]
action: report
action_reason: "Self-harm concerns"

type: comment
author:
    account_age: "< 7 days"
    comment_karma: "< 5"
action: filter
action_reason: "New user comment"
---
""",
                "advanced": """---
# Advanced AutoModerator rules for MCRDSE communities
# Spam protection
type: any
author:
    account_age: "< 24 hours"
    combined_karma: "< 10"
action: filter
action_reason: "New account/low karma"

# Sourcing prevention
type: any
title+body (includes): ["buy", "sell", "vendor", "dealer", "price", "\\$", "ship"]
action: filter
action_reason: "Potential sourcing"

# Medical advice prevention
type: any
title+body (includes): ["prescribe", "diagnose", "treatment", "cure", "you should take"]
action: filter
action_reason: "Potential medical advice"

# Self-harm detection
type: any
title+body (includes): ["suicide", "kill myself", "want to die", "end my life"]
action: report
action_reason: "Self-harm concerns"
modmail: "Self-harm content detected: {{permalink}}"

# Welcome new users
type: comment
author:
    comment_karma: "< 10"
    account_age: "< 7 days"
message: |
    Welcome to our community! Please review our guidelines.

# Quality control
type: submission
body (regex): '^\\s*[\\s\\S]{0,49}\\s*$'
action: filter
action_reason: "Post too short"
message: |
    Your post appears to be very short. Please add more content.
---
"""
            },
            "subreddit_rules": [
                "All posts must be research-focused or evidence-based",
                "No sourcing or discussion of acquiring substances",
                "No medical advice - share experiences, not prescriptions",
                "Be respectful to all community members",
                "Practice harm reduction in all discussions",
                "Cite sources when making factual claims",
                "Use appropriate post flair for your content",
                "No spam, self-promotion, or low-effort content"
            ],
            "scheduled_tasks": {
                "check_queue_interval_minutes": 60,
                "daily_report_time": "22:00",
                "weekly_cleanup_day": "Sunday"
            }
        }
        
        # Save default config
        config_path.parent.mkdir(exist_ok=True, parents=True)
        config_path.write_text(json.dumps(default_config, indent=2))
        logger.info(f"Created default config at {config_path}")
        
        return default_config
    
    def load_account_config(self) -> Dict:
        """Load account-specific configuration"""
        accounts_path = Path("config/accounts.json")
        if accounts_path.exists():
            try:
                accounts = json.loads(accounts_path.read_text())
                for account in accounts:
                    if account.get("name") == self.account_name:
                        return account
            except:
                pass
        
        # Return default if not found
        return {
            "name": self.account_name,
            "cookies_path": f"data/cookies_{self.account_name}.pkl"
        }
    
    def setup_browser(self):
        """Setup Selenium browser with anti-detection measures"""
        try:
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            # Setup Chrome options
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless=new")
            
            # Anti-detection settings
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Random user agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
            ]
            chrome_options.add_argument(f'user-agent={random.choice(user_agents)}')
            
            # Disable automation flags
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--no-sandbox')
            
            # Setup driver
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Execute anti-detection script
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("Browser setup complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup browser: {e}")
            return False
    
    def login_with_cookies(self) -> bool:
        """Login to Reddit using saved cookies"""
        try:
            # Load cookies if they exist
            cookies_file = Path(self.account_config.get("cookies_path", f"data/cookies_{self.account_name}.pkl"))
            
            if cookies_file.exists():
                logger.info(f"Loading cookies from {cookies_file}")
                
                # Navigate to Reddit first
                self.driver.get("https://old.reddit.com")
                time.sleep(2)
                
                # In a real implementation, you would load and add cookies
                # For now, we'll use manual login flow
                pass
            
            # Manual login flow
            logger.info("Please log in manually in the browser window")
            
            self.driver.get("https://old.reddit.com/login")
            time.sleep(3)
            
            # Wait for manual login
            if not self.headless:
                input("Press Enter after you have logged in...")
                time.sleep(2)
            else:
                # In headless mode, wait a bit longer
                logger.info("Waiting 30 seconds for manual login in headless mode...")
                time.sleep(30)
            
            # Verify login
            self.driver.get("https://old.reddit.com")
            time.sleep(2)
            
            if "logout" in self.driver.page_source.lower():
                logger.info("Login successful")
                return True
            else:
                logger.error("Login verification failed")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def navigate_to_subreddit(self, subreddit_name: str, section: str = "") -> bool:
        """Navigate to a specific subreddit section"""
        try:
            base_url = f"https://old.reddit.com/r/{subreddit_name}"
            if section:
                base_url += f"/{section}"
            
            self.driver.get(base_url)
            time.sleep(3)
            
            # Check if we have access
            if "you are not allowed to do that" in self.driver.page_source.lower():
                logger.error(f"No moderator access to r/{subreddit_name}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to r/{subreddit_name}: {e}")
            return False
    
    def setup_automoderator(self, subreddit_name: str, template: str = "basic") -> bool:
        """Setup AutoModerator rules via wiki"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "wiki/config/automoderator"):
                logger.error(f"Cannot access AutoModerator config for r/{subreddit_name}")
                return False
            
            # Check if we need to edit
            try:
                edit_button = self.driver.find_element(By.LINK_TEXT, "edit")
                edit_button.click()
                time.sleep(2)
            except NoSuchElementException:
                # Already on edit page or different layout
                pass
            
            # Get automod content from config
            automod_content = self.config["automod_templates"].get(template, self.config["automod_templates"]["basic"])
            
            # Find textarea and insert rules
            textarea = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "content"))
            )
            
            # Clear and insert
            textarea.clear()
            textarea.send_keys(automod_content)
            time.sleep(2)
            
            # Save
            save_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            save_button.click()
            time.sleep(3)
            
            logger.info(f"AutoModerator configured for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up AutoModerator for r/{subreddit_name}: {e}")
            return False
    
    def setup_post_flairs(self, subreddit_name: str) -> bool:
        """Setup post flairs for the subreddit"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/flair"):
                logger.error(f"Cannot access flair settings for r/{subreddit_name}")
                return False
            
            # Switch to link flair (post flair) section
            try:
                link_flair_tab = self.driver.find_element(By.CSS_SELECTOR, "a[href$='link_flair']")
                link_flair_tab.click()
                time.sleep(2)
            except NoSuchElementException:
                # Might already be on the right page
                pass
            
            # Get flairs from config
            flairs = self.config["flairs"]["post_flairs"]
            
            for flair in flairs:
                try:
                    # Click "Add flair" button
                    add_button = self.driver.find_element(By.CSS_SELECTOR, "button.add-flair-row")
                    add_button.click()
                    time.sleep(1)
                    
                    # Find the new row
                    rows = self.driver.find_elements(By.CSS_SELECTOR, ".flairrow")
                    new_row = rows[-1] if rows else None
                    
                    if new_row:
                        # Fill flair text
                        text_input = new_row.find_element(By.CSS_SELECTOR, "input.flair-text-input")
                        text_input.clear()
                        text_input.send_keys(flair["name"])
                        time.sleep(0.5)
                        
                        # Set color
                        color_input = new_row.find_element(By.CSS_SELECTOR, "input.flair-color-input")
                        color_input.clear()
                        color_input.send_keys(flair["color"])
                        time.sleep(0.5)
                        
                        # Save (there's usually an implicit save on blur)
                        text_input.send_keys(Keys.TAB)
                        time.sleep(1)
                
                except Exception as e:
                    logger.warning(f"Error creating flair '{flair['name']}': {e}")
                    continue
            
            # Click save button at bottom
            try:
                save_button = self.driver.find_element(By.CSS_SELECTOR, "button.save-button")
                save_button.click()
                time.sleep(2)
            except:
                pass
            
            logger.info(f"Created {len(flairs)} post flairs for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up post flairs for r/{subreddit_name}: {e}")
            return False
    
    def setup_user_flairs(self, subreddit_name: str) -> bool:
        """Setup user flairs for the subreddit"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/flair"):
                logger.error(f"Cannot access flair settings for r/{subreddit_name}")
                return False
            
            # Switch to user flair section
            try:
                user_flair_tab = self.driver.find_element(By.CSS_SELECTOR, "a[href$='user_flair']")
                user_flair_tab.click()
                time.sleep(2)
            except NoSuchElementException:
                # Might already be on the right page
                pass
            
            # Get flairs from config
            flairs = self.config["flairs"]["user_flairs"]
            
            for flair in flairs:
                try:
                    # Click "Add flair" button
                    add_button = self.driver.find_element(By.CSS_SELECTOR, "button.add-flair-row")
                    add_button.click()
                    time.sleep(1)
                    
                    # Find the new row
                    rows = self.driver.find_elements(By.CSS_SELECTOR, ".flairrow")
                    new_row = rows[-1] if rows else None
                    
                    if new_row:
                        # Fill flair text
                        text_input = new_row.find_element(By.CSS_SELECTOR, "input.flair-text-input")
                        text_input.clear()
                        text_input.send_keys(flair["name"])
                        time.sleep(0.5)
                        
                        # Set color
                        color_input = new_row.find_element(By.CSS_SELECTOR, "input.flair-color-input")
                        color_input.clear()
                        color_input.send_keys(flair["color"])
                        time.sleep(0.5)
                        
                        # Save (there's usually an implicit save on blur)
                        text_input.send_keys(Keys.TAB)
                        time.sleep(1)
                
                except Exception as e:
                    logger.warning(f"Error creating user flair '{flair['name']}': {e}")
                    continue
            
            # Click save button at bottom
            try:
                save_button = self.driver.find_element(By.CSS_SELECTOR, "button.save-button")
                save_button.click()
                time.sleep(2)
            except:
                pass
            
            logger.info(f"Created {len(flairs)} user flairs for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up user flairs for r/{subreddit_name}: {e}")
            return False
    
    def setup_subreddit_rules(self, subreddit_name: str) -> bool:
        """Setup subreddit rules"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/rules"):
                logger.error(f"Cannot access rules settings for r/{subreddit_name}")
                return False
            
            rules = self.config["subreddit_rules"]
            
            for i, rule_text in enumerate(rules, 1):
                try:
                    # Click "Add rule" button
                    add_button = self.driver.find_element(By.CSS_SELECTOR, "button.add-rule")
                    add_button.click()
                    time.sleep(1)
                    
                    # Find the new rule row (last one)
                    rule_rows = self.driver.find_elements(By.CSS_SELECTOR, ".rule-row")
                    new_row = rule_rows[-1] if rule_rows else None
                    
                    if new_row:
                        # Fill rule text
                        text_input = new_row.find_element(By.CSS_SELECTOR, "input.rule-input")
                        text_input.clear()
                        text_input.send_keys(rule_text)
                        time.sleep(0.5)
                        
                        # Set violation reason (same as rule text for simplicity)
                        reason_input = new_row.find_element(By.CSS_SELECTOR, "input.reason-input")
                        reason_input.clear()
                        reason_input.send_keys(f"Violates rule {i}")
                        time.sleep(0.5)
                
                except Exception as e:
                    logger.warning(f"Error adding rule {i}: {e}")
                    continue
            
            # Click save button
            try:
                save_button = self.driver.find_element(By.CSS_SELECTOR, "button.save-rules")
                save_button.click()
                time.sleep(2)
                logger.info(f"Rules saved for r/{subreddit_name}")
            except:
                logger.warning("Could not find save button, rules may not have been saved")
            
            logger.info(f"Added {len(rules)} rules for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up rules for r/{subreddit_name}: {e}")
            return False
    
    def configure_subreddit_settings(self, subreddit_name: str) -> bool:
        """Configure basic subreddit settings"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/edit"):
                logger.error(f"Cannot access edit settings for r/{subreddit_name}")
                return False
            
            # Fill in basic settings
            try:
                # Title (append "MCRDSE" if not already there)
                title_field = self.driver.find_element(By.ID, "title")
                current_title = title_field.get_attribute("value") or ""
                if "MCRDSE" not in current_title.upper():
                    title_field.clear()
                    title_field.send_keys(f"MCRDSE {subreddit_name.replace('_', ' ')}")
                    time.sleep(0.5)
            except:
                pass
            
            try:
                # Description
                desc_field = self.driver.find_element(By.ID, "public_description")
                desc_field.clear()
                desc_field.send_keys("Evidence-based community for psychedelic microdosing research and discussion")
                time.sleep(0.5)
            except:
                pass
            
            try:
                # Sidebar
                sidebar_field = self.driver.find_element(By.ID, "description")
                current_sidebar = sidebar_field.get_attribute("value") or ""
                if not current_sidebar.strip():
                    sidebar_field.clear()
                    sidebar_field.send_keys(self.generate_sidebar_content(subreddit_name))
                    time.sleep(0.5)
            except:
                pass
            
            # Set content options
            try:
                # Allow images
                images_checkbox = self.driver.find_element(By.NAME, "allow_images")
                if not images_checkbox.is_selected():
                    images_checkbox.click()
                    time.sleep(0.5)
            except:
                pass
            
            try:
                # Allow videos
                videos_checkbox = self.driver.find_element(By.NAME, "allow_videos")
                if not videos_checkbox.is_selected():
                    videos_checkbox.click()
                    time.sleep(0.5)
            except:
                pass
            
            try:
                # Set to public
                public_radio = self.driver.find_element(By.CSS_SELECTOR, "input[value='public']")
                if not public_radio.is_selected():
                    public_radio.click()
                    time.sleep(0.5)
            except:
                pass
            
            # Save settings
            try:
                save_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                save_button.click()
                time.sleep(3)
                logger.info(f"Settings saved for r/{subreddit_name}")
            except:
                logger.warning("Could not find save button")
            
            logger.info(f"Configured basic settings for r/{subreddit_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring settings for r/{subreddit_name}: {e}")
            return False
    
    def generate_sidebar_content(self, subreddit_name: str) -> str:
        """Generate sidebar content for subreddit"""
        return f"""**Welcome to r/{subreddit_name}!**

## About This Community
This is a research-focused community for evidence-based discussions about psychedelic microdosing, mental health, and consciousness studies.

## Community Guidelines
1. Be respectful and kind to all members
2. No sourcing or discussion of acquiring substances
3. Share experiences, not medical advice
4. Practice harm reduction principles
5. Cite sources when discussing research

## Resources
- [MCRDSE Research Portal](https://mcrdse.com/research)
- [Safety Guidelines](https://mcrdse.com/safety)
- [Academic Studies](https://mcrdse.com/studies)

## Disclaimer
This community is for educational purposes only. Not medical advice.

---
*Part of the MCRDSE network - Advancing psychedelic research and education.*"""
    
    def check_moderation_queue(self, subreddit_name: str) -> Dict:
        """Check and process moderation queue"""
        try:
            if not self.navigate_to_subreddit(subreddit_name, "about/modqueue"):
                logger.error(f"Cannot access mod queue for r/{subreddit_name}")
                return {}
            
            stats = {
                "subreddit": subreddit_name,
                "timestamp": datetime.now().isoformat(),
                "total_items": 0,
                "approved": 0,
                "removed": 0,
                "ignored": 0,
                "processed_items": []
            }
            
            # Find all queue items
            queue_items = self.driver.find_elements(By.CSS_SELECTOR, ".thing")
            
            for item in queue_items:
                try:
                    item_stats = self.process_queue_item(item)
                    stats["total_items"] += 1
                    
                    if item_stats["action"] == "approved":
                        stats["approved"] += 1
                    elif item_stats["action"] == "removed":
                        stats["removed"] += 1
                    else:
                        stats["ignored"] += 1
                    
                    stats["processed_items"].append(item_stats)
                    
                    # Small delay between items
                    time.sleep(1)
                    
                except Exception as e:
                    logger.warning(f"Error processing queue item: {e}")
                    continue
            
            logger.info(f"Processed {stats['total_items']} items in r/{subreddit_name} queue")
            return stats
            
        except Exception as e:
            logger.error(f"Error checking moderation queue for r/{subreddit_name}: {e}")
            return {}
    
    def process_queue_item(self, item_element) -> Dict:
        """Process a single queue item"""
        item_info = {
            "type": "unknown",
            "title": "",
            "author": "",
            "reason": "",
            "action": "ignored",
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Get item type (post or comment)
            if "comment" in item_element.get_attribute("class"):
                item_info["type"] = "comment"
            else:
                item_info["type"] = "post"
            
            # Get title/author
            try:
                title_elem = item_element.find_element(By.CSS_SELECTOR, "a.title")
                item_info["title"] = title_elem.text[:100]
            except:
                pass
            
            try:
                author_elem = item_element.find_element(By.CSS_SELECTOR, ".author")
                item_info["author"] = author_elem.text
            except:
                pass
            
            # Get report reason
            try:
                reason_elem = item_element.find_element(By.CSS_SELECTOR, ".report-reason")
                item_info["reason"] = reason_elem.text
            except:
                pass
            
            # Analyze content
            should_remove = self.should_remove_item(item_element, item_info)
            
            # Take action
            if should_remove:
                self.remove_item(item_element)
                item_info["action"] = "removed"
            else:
                self.approve_item(item_element)
                item_info["action"] = "approved"
            
        except Exception as e:
            logger.warning(f"Error in process_queue_item: {e}")
        
        return item_info
    
    def should_remove_item(self, item_element, item_info: Dict) -> bool:
        """Determine if an item should be removed"""
        content = ""
        
        try:
            # Get content text
            if item_info["type"] == "post":
                # Try to get post content
                try:
                    content_elem = item_element.find_element(By.CSS_SELECTOR, ".md")
                    content = content_elem.text.lower()
                except:
                    content = item_info.get("title", "").lower()
            else:
                # For comments
                try:
                    content_elem = item_element.find_element(By.CSS_SELECTOR, ".md")
                    content = content_elem.text.lower()
                except:
                    pass
        except:
            pass
        
        # Check against removal criteria
        removal_keywords = self.config["moderation"]["remove_spam_keywords"] + \
                          self.config["moderation"]["remove_self_harm_keywords"]
        
        for keyword in removal_keywords:
            if keyword.lower() in content:
                return True
        
        # Check for new account/low karma (simplified)
        try:
            # This would require parsing user info, which is complex
            # For now, we'll trust AutoModerator's filtering
            pass
        except:
            pass
        
        return False
    
    def approve_item(self, item_element):
        """Approve a queue item"""
        try:
            # Find approve button
            approve_button = item_element.find_element(By.CSS_SELECTOR, "button.approve")
            approve_button.click()
            time.sleep(0.5)
        except:
            logger.warning("Could not find approve button")
    
    def remove_item(self, item_element):
        """Remove a queue item"""
        try:
            # Find remove button
            remove_button = item_element.find_element(By.CSS_SELECTOR, "button.remove")
            remove_button.click()
            time.sleep(0.5)
            
            # Sometimes there's a removal reason dropdown
            try:
                removal_reason = Select(item_element.find_element(By.CSS_SELECTOR, "select.remove-reason"))
                removal_reason.select_by_index(1)  # Select first reason
                time.sleep(0.5)
            except:
                pass
            
            # Confirm removal
            try:
                confirm_button = item_element.find_element(By.CSS_SELECTOR, "button.confirm-remove")
                confirm_button.click()
                time.sleep(0.5)
            except:
                pass
            
        except:
            logger.warning("Could not find remove button")
    
    def setup_complete_moderation(self, subreddit_name: str) -> bool:
        """Complete moderation setup for a subreddit"""
        logger.info(f"Starting complete moderation setup for r/{subreddit_name}")
        
        steps = [
            ("Configure settings", self.configure_subreddit_settings),
            ("Setup AutoModerator", self.setup_automoderator),
            ("Setup post flairs", self.setup_post_flairs),
            ("Setup user flairs", self.setup_user_flairs),
            ("Setup rules", self.setup_subreddit_rules)
        ]
        
        success_count = 0
        for step_name, step_function in steps:
            try:
                logger.info(f"  Starting: {step_name}")
                if step_function(subreddit_name):
                    success_count += 1
                    logger.info(f"  ✓ {step_name} completed")
                else:
                    logger.warning(f"  ✗ {step_name} failed")
                
                # Delay between steps
                time.sleep(3)
                
            except Exception as e:
                logger.error(f"Error in {step_name}: {e}")
        
        logger.info(f"Completed {success_count}/{len(steps)} setup steps for r/{subreddit_name}")
        return success_count >= 3  # Require at least 3 successful steps
    
    def run_daily_moderation(self, subreddit_names: List[str] = None):
        """Run daily moderation tasks for specified subreddits"""
        if subreddit_names is None:
            # Get subreddits from tracking file
            subreddit_names = self.get_managed_subreddits()
        
        logger.info(f"Starting daily moderation for {len(subreddit_names)} subreddits")
        
        results = {}
        for subreddit in subreddit_names:
            logger.info(f"Processing r/{subreddit}")
            
            queue_stats = self.check_moderation_queue(subreddit)
            results[subreddit] = queue_stats
            
            # Delay between subreddits
            time.sleep(5)
        
        # Save results
        daily_file = Path(f"data/moderation_daily_{datetime.now().strftime('%Y%m%d')}.json")
        daily_file.parent.mkdir(exist_ok=True, parents=True)
        daily_file.write_text(json.dumps(results, indent=2))
        
        logger.info(f"Daily moderation complete. Results saved to {daily_file}")
        return results
    
    def get_managed_subreddits(self) -> List[str]:
        """Get list of subreddits we manage"""
        tracking_file = Path("data/created_subreddits.json")
        if tracking_file.exists():
            try:
                data = json.loads(tracking_file.read_text())
                return [sub["name"] for sub in data.get("subreddits", [])]
            except:
                pass
        
        # Fallback: prompt user
        if not self.headless:
            subreddits_input = input("Enter subreddit names (comma-separated): ")
            return [s.strip() for s in subreddits_input.split(",") if s.strip()]
        
        return []
    
    def setup_all_moderation(self):
        """Setup moderation for all managed subreddits"""
        subreddits = self.get_managed_subreddits()
        
        if not subreddits:
            logger.error("No subreddits found to manage")
            return
        
        logger.info(f"Setting up moderation for {len(subreddits)} subreddits")
        
        results = {}
        for subreddit in subreddits:
            success = self.setup_complete_moderation(subreddit)
            results[subreddit] = {"success": success}
            time.sleep(5)  # Delay between subreddits
        
        # Save setup results
        setup_file = Path(f"data/moderation_setup_{datetime.now().strftime('%Y%m%d')}.json")
        setup_file.parent.mkdir(exist_ok=True, parents=True)
        setup_file.write_text(json.dumps(results, indent=2))
        
        logger.info(f"Setup complete. Results saved to {setup_file}")
        return results

def main():
    """Command-line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCRDSE Selenium Moderation Manager")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--subreddit", help="Subreddit to manage")
    parser.add_argument("--all", action="store_true", help="Manage all MCRDSE subreddits")
    parser.add_argument("--setup", action="store_true", help="Setup moderation")
    parser.add_argument("--daily", action="store_true", help="Run daily moderation tasks")
    parser.add_argument("--queue", action="store_true", help="Check moderation queue")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("MCRDSE Selenium Moderation Manager")
    print("="*60)
    
    # Initialize manager
    manager = SeleniumModerationManager(
        account_name=args.account,
        headless=args.headless
    )
    
    # Setup browser and login
    print("Setting up browser...")
    if not manager.setup_browser():
        print("❌ Failed to setup browser")
        return
    
    print("Logging in to Reddit...")
    if not manager.login_with_cookies():
        print("❌ Login failed")
        manager.driver.quit()
        return
    
    print("✅ Ready")
    
    # Determine action
    if args.setup:
        if args.subreddit:
            print(f"\nSetting up moderation for r/{args.subreddit}...")
            success = manager.setup_complete_moderation(args.subreddit)
            print(f"✅ Setup {'complete' if success else 'partially complete'}")
        elif args.all:
            print("\nSetting up moderation for all subreddits...")
            manager.setup_all_moderation()
        else:
            print("Please specify --subreddit or --all")
    
    elif args.daily:
        print("\nRunning daily moderation tasks...")
        if args.subreddit:
            manager.run_daily_moderation([args.subreddit])
        elif args.all:
            manager.run_daily_moderation()
        else:
            print("Please specify --subreddit or --all")
    
    elif args.queue:
        print("\nChecking moderation queue...")
        if args.subreddit:
            stats = manager.check_moderation_queue(args.subreddit)
            if stats:
                print(f"\nQueue stats for r/{args.subreddit}:")
                print(f"  Total items: {stats.get('total_items', 0)}")
                print(f"  Approved: {stats.get('approved', 0)}")
                print(f"  Removed: {stats.get('removed', 0)}")
                print(f"  Ignored: {stats.get('ignored', 0)}")
        else:
            print("Please specify --subreddit")
    
    elif args.interactive or not any([args.setup, args.daily, args.queue]):
        # Interactive mode
        print("\nInteractive Mode")
        print("1. Setup moderation for a subreddit")
        print("2. Run daily moderation tasks")
        print("3. Check moderation queue")
        print("4. Setup all subreddits")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ")
        
        if choice == "1":
            subreddit = input("Enter subreddit name: ").strip()
            if subreddit:
                success = manager.setup_complete_moderation(subreddit)
                print(f"Setup {'complete' if success else 'partially complete'}")
        
        elif choice == "2":
            subreddit = input("Enter subreddit name (or press Enter for all): ").strip()
            if subreddit:
                manager.run_daily_moderation([subreddit])
            else:
                manager.run_daily_moderation()
        
        elif choice == "3":
            subreddit = input("Enter subreddit name: ").strip()
            if subreddit:
                stats = manager.check_moderation_queue(subreddit)
                if stats:
                    print(f"\nQueue stats:")
                    print(f"  Total: {stats.get('total_items', 0)}")
                    print(f"  Approved: {stats.get('approved', 0)}")
                    print(f"  Removed: {stats.get('removed', 0)}")
        
        elif choice == "4":
            confirm = input("Setup moderation for ALL MCRDSE subreddits? (yes/no): ")
            if confirm.lower() == "yes":
                manager.setup_all_moderation()
    
    # Cleanup
    if manager.driver:
        manager.driver.quit()
        print("\nBrowser closed")
    
    print("\n" + "="*60)
    print("Moderation management complete!")
    print("="*60)

if __name__ == "__main__":
    main()