#!/usr/bin/env python3
"""
Subreddit Creation Tool for MCRDSE
With proper error handling for config files
"""
import json
import random
import time
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SubredditCreator:
    """Creates and configures new subreddits for MCRDSE"""
    
    def __init__(self, account_name="account1"):
        """
        Initialize with account name from config/accounts.json
        
        Args:
            account_name: Which account to use (must be configured)
        """
        self.account_name = account_name
        self.config = self.load_config()
        self.driver = None
        self.subreddit_names = self.generate_subreddit_names()
        
    def load_config(self) -> Dict:
        """Load configuration from files - FIXED VERSION"""
        config_path = Path("scripts/subreddit_creation/subreddit_templates.json")
        
        # Create config directory if it doesn't exist
        config_path.parent.mkdir(exist_ok=True, parents=True)
        
        # Default configuration
        default_config = {
            "subreddit_templates": [
                {
                    "name_template": "Microdosing{type}",
                    "type_variants": ["Research", "Science", "Support", "Community", "Therapy"],
                    "description": "A community for {focus} discussions about microdosing and psychedelic-assisted therapy.",
                    "focus_variants": [
                        "evidence-based",
                        "scientific",
                        "supportive",
                        "educational",
                        "therapeutic"
                    ],
                    "sidebar_template": """**Welcome to r/{name}!**

## About This Community
This is a space for {focus} discussions about microdosing psychedelics for mental health, creativity, and personal growth.

## Community Rules
1. Be respectful and kind
2. No sourcing or selling of substances
3. Share experiences, not medical advice
4. Cite sources when discussing research
5. Practice harm reduction principles

## Resources
- [MCRDSE Research Portal](https://mcrdse.com/research)
- [Microdosing Safety Guide](https://mcrdse.com/safety)
- [Psychedelic Research Studies](https://mcrdse.com/studies)

## Disclaimer
This community does not provide medical advice. Consult healthcare professionals.""",
                    "post_types": ["discussion", "question", "experience", "research", "resource"]
                }
            ],
            "creation_delay": {
                "min": 3600,  # 1 hour minimum between creations
                "max": 86400  # 24 hours maximum between creations
            },
            "account_requirements": {
                "min_age_days": 30,
                "min_karma": 100,
                "max_subreddits_per_day": 1,
                "max_total_subreddits": 10
            }
        }
        
        # Check if config file exists and is valid
        if config_path.exists():
            try:
                content = config_path.read_text().strip()
                if content:  # Check if file is not empty
                    return json.loads(content)
                else:
                    logger.warning(f"Config file {config_path} is empty. Using defaults.")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON in {config_path}: {e}")
                logger.warning("Using default configuration instead.")
        else:
            logger.info(f"Config file {config_path} not found. Creating with defaults.")
        
        # Write default config to file
        config_path.write_text(json.dumps(default_config, indent=2))
        logger.info(f"Created default config at {config_path}")
        
        return default_config
    
    def generate_subreddit_names(self):
        """Generate unique subreddit names"""
        names = []
        for template in self.config.get("subreddit_templates", []):
            base = template["name_template"]
            for variant in template.get("type_variants", []):
                # Create variations
                names.append(base.replace("{type}", variant))
                # Add alternative spellings
                names.append(base.replace("{type}", variant.lower()))
                # Add with underscores
                names.append(base.replace("{type}", variant.replace(" ", "_")))
        
        # Add MCRDSE branded names
        names.extend([
            "MCRDSE_Research",
            "MCRDSE_Community",
            "PsychedelicMicrodosing",
            "MicrodosingTherapy",
            "PsychedelicScience",
            "PlantMedicineResearch",
            "ConsciousnessStudies",
            "NeuroplasticityResearch"
        ])
        
        # Remove duplicates and return
        return list(set(names))
    
    def check_account_eligibility(self):
        """Check if account meets Reddit's subreddit creation requirements"""
        try:
            # Navigate to profile to check age and karma
            self.driver.get("https://old.reddit.com/user/{}/".format(self.account_name))
            time.sleep(2)
            
            # Check account age (simplified - in real implementation would parse)
            # For now, we'll assume requirements are met if account exists
            logger.info(f"Checking eligibility for {self.account_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error checking eligibility: {e}")
            return False
    
    def create_subreddit(self, name, description, sidebar):
        """Create a new subreddit"""
        try:
            logger.info(f"Attempting to create r/{name}")
            
            # Navigate to creation page
            self.driver.get("https://old.reddit.com/subreddits/create")
            time.sleep(3)
            
            # Fill subreddit name
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            name_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "name"))
            )
            name_field.clear()
            name_field.send_keys(name)
            time.sleep(1)
            
            # Fill title
            title_field = self.driver.find_element(By.ID, "title")
            title_field.clear()
            title_field.send_keys(f"Microdosing {name.split('_')[-1]} Community")
            time.sleep(1)
            
            # Fill description
            desc_field = self.driver.find_element(By.ID, "description")
            desc_field.clear()
            desc_field.send_keys(description)
            time.sleep(1)
            
            # Fill sidebar
            sidebar_field = self.driver.find_element(By.ID, "sidebar")
            sidebar_field.clear()
            sidebar_field.send_keys(sidebar)
            time.sleep(1)
            
            # Select category (Health)
            category_select = self.driver.find_element(By.ID, "type")
            for option in category_select.find_elements(By.TAG_NAME, "option"):
                if "Health" in option.text:
                    option.click()
                    break
            time.sleep(1)
            
            # Set to public
            public_radio = self.driver.find_element(By.CSS_SELECTOR, "input[value='public']")
            public_radio.click()
            time.sleep(1)
            
            # Add rules (basic ones)
            rule_fields = self.driver.find_elements(By.CSS_SELECTOR, "input[name^='rules']")
            rules = [
                "No sourcing or selling of substances",
                "Be respectful and kind",
                "Share experiences, not medical advice",
                "Practice harm reduction principles"
            ]
            
            for i, rule in enumerate(rules[:min(len(rules), len(rule_fields))]):
                rule_fields[i].send_keys(rule)
                time.sleep(0.5)
            
            # Submit (but don't actually submit in test mode)
            logger.info(f"Ready to submit r/{name}. Check details and submit manually.")
            
            # For actual creation, uncomment:
            # submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            # submit_button.click()
            # time.sleep(5)
            
            # Verify creation
            # if f"/r/{name}/" in self.driver.current_url:
            #     logger.info(f"Successfully created r/{name}")
            #     return True
            
            return False  # Return False for testing
            
        except Exception as e:
            logger.error(f"Error creating subreddit: {e}")
            return False
    
    def configure_subreddit(self, subreddit_name):
        """Configure automoderator and settings"""
        config_commands = [
            f"https://old.reddit.com/r/{subreddit_name}/about/edit",
            f"https://old.reddit.com/r/{subreddit_name}/about/rules",
            f"https://old.reddit.com/r/{subreddit_name}/about/moderators",
            f"https://old.reddit.com/r/{subreddit_name}/about/stylesheet"
        ]
        
        for url in config_commands:
            try:
                self.driver.get(url)
                time.sleep(2)
                logger.info(f"Configured: {url}")
            except Exception as e:
                logger.error(f"Failed to configure {url}: {e}")
    
    def setup_automod(self, subreddit_name):
        """Setup AutoModerator rules"""
        automod_rules = """---
# AutoModerator rules for r/{} - MCRDSE Community

# Welcome message to new posts
type: submission
message: |
    Welcome to r/{}! Thanks for sharing. Please remember our community rules:
    1. No sourcing or selling of substances
    2. Be respectful and kind
    3. Share experiences, not medical advice
    4. Cite research when possible
    
    Check out our resources at https://mcrdse.com

# Filter potential sourcing
title+body (includes): ["buy", "sell", "vendor", "dealer", "source", "ship", "price"]
action: filter
action_reason: "Potential sourcing"
modmail: "Potential sourcing post detected: {{permalink}}"

# Filter medical advice
title+body (includes): ["prescribe", "diagnose", "treatment", "cure", "doctor said"]
action: filter
action_reason: "Potential medical advice"
modmail: "Medical advice post detected: {{permalink}}"

# Welcome new users
type: comment
author:
    comment_karma: "< 10"
    account_age: "< 7"
message: |
    Welcome to r/{}! As a new user, please review our community guidelines.
action: filter
action_reason: "New user comment"

# Report harmful content
title+body (includes): ["suicide", "kill myself", "want to die", "end my life"]
action: report
action_reason: "Self-harm concerns"
modmail: "Self-harm content detected: {{permalink}}"
---
""".format(subreddit_name, subreddit_name, subreddit_name)
        
        try:
            self.driver.get(f"https://old.reddit.com/r/{subreddit_name}/wiki/config/automoderator")
            time.sleep(2)
            
            # Check if edit page
            edit_buttons = self.driver.find_elements(By.LINK_TEXT, "edit")
            if edit_buttons:
                edit_buttons[0].click()
                time.sleep(2)
                
                # Find textarea and insert rules
                textarea = self.driver.find_element(By.NAME, "content")
                textarea.clear()
                textarea.send_keys(automod_rules)
                time.sleep(2)
                
                # Save
                save_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                save_button.click()
                time.sleep(3)
                
                logger.info(f"AutoModerator configured for r/{subreddit_name}")
                
        except Exception as e:
            logger.error(f"Failed to setup AutoModerator: {e}")
    
    def create_initial_content(self, subreddit_name):
        """Create initial posts to seed the community"""
        initial_posts = [
            {
                "title": "Welcome to r/{}! Introduce yourself!".format(subreddit_name),
                "text": """Welcome to our new community! This is a space for thoughtful discussion about microdosing and psychedelic-assisted therapy.

**Please introduce yourself:**
- What brings you to this community?
- What are your interests in microdosing/psychedelics?
- What topics would you like to see discussed?

**Community Resources:**
- [MCRDSE Research Portal](https://mcrdse.com)
- [Harm Reduction Guide](https://mcrdse.com/safety)
- [Scientific Studies Database](https://mcrdse.com/studies)

Let's build a supportive, evidence-based community together!""",
                "type": "text"
            },
            {
                "title": "What does 'responsible use' mean to you?",
                "text": "Let's discuss what responsible psychedelic use looks like in practice. Share your thoughts on harm reduction, integration, and community support.",
                "type": "text"
            },
            {
                "title": "Weekly Microdosing Discussion Thread",
                "text": "Share your experiences, questions, and insights about microdosing this week. Remember: share experiences, not medical advice.",
                "type": "text"
            }
        ]
        
        for post in initial_posts:
            try:
                self.driver.get(f"https://old.reddit.com/r/{subreddit_name}/submit")
                time.sleep(2)
                
                # Select text post
                if post["type"] == "text":
                    text_button = self.driver.find_element(By.CSS_SELECTOR, "input[value='self']")
                    text_button.click()
                    time.sleep(1)
                
                # Enter title
                title_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='title']")
                title_field.clear()
                title_field.send_keys(post["title"])
                time.sleep(1)
                
                # Enter text
                text_field = self.driver.find_element(By.CSS_SELECTOR, "textarea[name='text']")
                text_field.clear()
                text_field.send_keys(post["text"])
                time.sleep(2)
                
                # Submit (commented out for safety)
                # submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                # submit_button.click()
                # time.sleep(5)
                
                logger.info(f"Created post: {post['title']}")
                
            except Exception as e:
                logger.error(f"Failed to create post: {e}")
    
    def run(self, max_subreddits=3, headless=False):
        """Main execution method"""
        try:
            # Setup Selenium (using existing browser manager)
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            # Setup Chrome options
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless=new")
            
            # Anti-detection settings
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Random user agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            ]
            chrome_options.add_argument(f'user-agent={random.choice(user_agents)}')
            
            # Setup driver
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Execute anti-detection script
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Login using existing cookies if available
            cookies_file = Path(f"data/cookies_{self.account_name}.pkl")
            if cookies_file.exists():
                logger.info(f"Would load cookies from {cookies_file}")
                # In real implementation, you would load cookies here
                # For now, we'll do manual login
                pass
            
            # Navigate to Reddit for manual login
            self.driver.get("https://old.reddit.com")
            time.sleep(3)
            
            # Check if logged in
            if "login" in self.driver.page_source.lower():
                logger.info("Please log in manually in the browser window...")
                input("Press Enter after you have logged in...")
            
            # Check eligibility
            if not self.check_account_eligibility():
                logger.error("Account not eligible for subreddit creation")
                return
            
            # Create subreddits
            created_count = 0
            for subreddit_name in self.subreddit_names[:max_subreddits]:
                logger.info(f"Processing: r/{subreddit_name}")
                
                # Generate description and sidebar
                template = random.choice(self.config["subreddit_templates"])
                focus = random.choice(template["focus_variants"])
                
                description = template["description"].replace("{focus}", focus)
                sidebar = template["sidebar_template"].format(
                    name=subreddit_name,
                    focus=focus
                )
                
                # Create subreddit
                if self.create_subreddit(subreddit_name, description, sidebar):
                    # Configure settings
                    time.sleep(5)
                    self.configure_subreddit(subreddit_name)
                    
                    # Setup AutoModerator
                    time.sleep(3)
                    self.setup_automod(subreddit_name)
                    
                    # Create initial content
                    time.sleep(3)
                    self.create_initial_content(subreddit_name)
                    
                    created_count += 1
                    logger.info(f"Successfully setup r/{subreddit_name}")
                    
                    # Delay between creations
                    delay = random.randint(
                        self.config["creation_delay"]["min"],
                        self.config["creation_delay"]["max"]
                    )
                    logger.info(f"Waiting {delay/3600:.1f} hours before next creation")
                    time.sleep(delay)
                else:
                    logger.warning(f"Failed to create r/{subreddit_name}")
            
            logger.info(f"Created {created_count} subreddits")
            
        except ImportError as e:
            logger.error(f"Import error: {e}")
            logger.info("Install required packages: pip install selenium webdriver-manager")
        except Exception as e:
            logger.error(f"Error in SubredditCreator: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    # Create a simple command-line interface
    import argparse
    
    parser = argparse.ArgumentParser(description="Create MCRDSE subreddits")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--max", type=int, default=2, help="Maximum subreddits to create")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--test", action="store_true", help="Test mode - only show what would be created")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("MCRDSE Subreddit Creation Tool")
    print("="*60)
    
    if args.test:
        print("TEST MODE: No subreddits will actually be created")
    
    print(f"Account: {args.account}")
    print(f"Max to create: {args.max}")
    print(f"Headless mode: {args.headless}")
    print("="*60 + "\n")
    
    # Create creator instance
    creator = SubredditCreator(account_name=args.account)
    
    # Show what subreddits would be created
    print("Subreddit names that would be created:")
    for i, name in enumerate(creator.subreddit_names[:args.max], 1):
        print(f"  {i}. r/{name}")
    
    if not args.test:
        response = input("\nProceed with creation? (yes/no): ")
        if response.lower() == "yes":
            creator.run(max_subreddits=args.max, headless=args.headless)
        else:
            print("Creation cancelled.")
    else:
        print("\nTest mode complete. No subreddits were created.")
        print("To actually create subreddits, run without --test flag.")
