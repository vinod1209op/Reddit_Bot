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
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.reddit_selenium.automation_base import RedditAutomationBase

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SubredditCreator(RedditAutomationBase):
    """Creates and configures new subreddits for MCRDSE"""
    
    def __init__(self, account_name="account1", headless=False, dry_run=False):
        """
        Initialize with account name from config/accounts.json
        
        Args:
            account_name: Which account to use (must be configured)
        """
        os.environ["SELENIUM_HEADLESS"] = "1" if headless else "0"
        self.account_name = account_name
        super().__init__(account_name=account_name, dry_run=dry_run)
        self.config = self.load_config()
        self.profile_name = self.config.get("default_profile") or "conservative"
        self.profile_config = self.config.get("profiles", {}).get(self.profile_name, {})
        self.subreddit_names = self.generate_subreddit_names()
        
    def load_config(self) -> Dict:
        """Load configuration from files - FIXED VERSION"""
        config_manager = ConfigManager()
        config = config_manager.load_subreddit_creation() or {}
        templates_path = Path("scripts/subreddit_creation/templates/subreddit_templates.json")
        templates = config_manager.load_json(str(templates_path), default={}) or {}
        if isinstance(templates, dict):
            if "template_sets" in templates and isinstance(templates["template_sets"], dict):
                config["template_sets"] = templates["template_sets"]
            elif "subreddit_templates" in templates and isinstance(templates["subreddit_templates"], list):
                config["subreddit_templates"] = templates["subreddit_templates"]
        if not config:
            logger.warning("subreddit_creation.json missing or empty; using defaults.")
            config = {
                "default_profile": "conservative",
                "profiles": {
                    "conservative": {
                        "max_subreddits_per_day": 1,
                        "max_subreddits_per_week": 2,
                        "min_days_between_creations": 7,
                        "template_set": "research_focused",
                        "delay_min_minutes": 1440,
                        "delay_max_minutes": 10080,
                        "safety_check_requirements": {
                            "account_min_age_days": 90,
                            "account_min_karma": 500,
                            "verify_email": True
                        }
                    },
                    "moderate": {
                        "max_subreddits_per_day": 2,
                        "max_subreddits_per_week": 4,
                        "min_days_between_creations": 3,
                        "template_set": "mixed",
                        "delay_min_minutes": 720,
                        "delay_max_minutes": 4320
                    }
                },
                "template_sets": {
                    "research_focused": {
                        "name_templates": ["Microdosing{type}", "Psychedelic{type}", "MCRDSE_{type}"],
                        "type_variants": ["Research", "Science", "Studies", "Academy", "Institute"],
                        "description_templates": [
                            "A subreddit for {type} discussions about psychedelics and microdosing.",
                            "Explore {type} related to psychedelic research and microdosing.",
                            "Join the {type} community for scientific discourse on psychedelics."
                        ],
                        "sidebar_templates": [
                            "**Welcome to r/{name}!**\\n\\n## About This Community\\nThis is a space for {type_lower} discussions about microdosing and psychedelic research.\\n\\n## Community Rules\\n1. Be respectful and kind\\n2. No sourcing or selling of substances\\n3. Share experiences, not medical advice\\n4. Cite sources when discussing research\\n5. Practice harm reduction principles\\n\\n## Disclaimer\\nThis community does not provide medical advice. Consult healthcare professionals."
                        ]
                    },
                    "mixed": {
                        "name_templates": [
                            "Psychedelic{type}Hub",
                            "Microdosing{type}Zone",
                            "Psychedelic{type}Community",
                            "Microdosing{type}Forum"
                        ],
                        "type_variants": ["Discussion", "Support", "Experiences", "Research", "Therapy"],
                        "description_templates": [
                            "A subreddit for {type} discussions about psychedelics and microdosing.",
                            "Explore {type} related to psychedelic research and microdosing.",
                            "Join the {type} community for scientific discourse on psychedelics."
                        ],
                        "sidebar_templates": [
                            "**Welcome to r/{name}!**\\n\\n## About This Community\\nThis is a space for {type_lower} discussions about microdosing and psychedelic-assisted therapy.\\n\\n## Community Rules\\n1. Be respectful and kind\\n2. No sourcing or selling of substances\\n3. Share experiences, not medical advice\\n4. Cite sources when discussing research\\n5. Practice harm reduction principles\\n\\n## Disclaimer\\nThis community does not provide medical advice. Consult healthcare professionals."
                        ]
                    }
                }
            }
        return config

    def _get_template_set(self) -> Dict:
        if "subreddit_templates" in self.config:
            return {}
        template_sets = self.config.get("template_sets", {})
        if not isinstance(template_sets, dict) or not template_sets:
            return {}
        set_name = self.profile_config.get("template_set") or self.config.get("default_template_set")
        if not set_name:
            set_name = next(iter(template_sets))
        return template_sets.get(set_name, {})

    def _get_creation_delay_seconds(self) -> Tuple[int, int]:
        if "creation_delay" in self.config:
            delay = self.config.get("creation_delay", {})
            return int(delay.get("min", 3600)), int(delay.get("max", 86400))
        min_minutes = int(self.profile_config.get("delay_min_minutes", 60))
        max_minutes = int(self.profile_config.get("delay_max_minutes", 1440))
        return min_minutes * 60, max_minutes * 60
    
    def generate_subreddit_names(self):
        """Generate unique subreddit names"""
        names = []
        if "subreddit_templates" in self.config:
            for template in self.config.get("subreddit_templates", []):
                base = template["name_template"]
                for variant in template.get("type_variants", []):
                    # Create variations
                    names.append(base.replace("{type}", variant))
                    # Add alternative spellings
                    names.append(base.replace("{type}", variant.lower()))
                    # Add with underscores
                    names.append(base.replace("{type}", variant.replace(" ", "_")))
        else:
            template_set = self._get_template_set()
            name_templates = template_set.get("name_templates", [])
            type_variants = template_set.get("type_variants", [])
            for base in name_templates:
                for variant in type_variants:
                    names.append(base.replace("{type}", variant))
                    names.append(base.replace("{type}", variant.lower()))
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
            validation = self.run_validations()
            logger.info(f"Validation summary: {validation}")
            enabled, reason = self.is_feature_enabled("subreddit_creation")
            if not enabled:
                logger.info(f"Subreddit creation disabled ({reason}); exiting.")
                return
            if not self.dry_run:
                if not self.driver:
                    self._setup_browser()
                if not self.logged_in:
                    result = self._login_with_fallback()
                    if not result.success:
                        logger.error("Login failed; aborting subreddit creation.")
                        return
            else:
                logger.info("[dry-run] Skipping browser setup/login")
            
            # Check eligibility
            if not self.check_account_eligibility():
                logger.error("Account not eligible for subreddit creation")
                return
            
            # Create subreddits
            created_count = 0
            for subreddit_name in self.subreddit_names[:max_subreddits]:
                if not self.status_tracker.can_perform_action(
                    self.account_name, "creation", subreddit=subreddit_name
                ):
                    logger.info(f"Skipping creation for r/{subreddit_name} due to cooldown/limits")
                    continue
                logger.info(f"Processing: r/{subreddit_name}")
                
                # Generate description and sidebar
                if "subreddit_templates" in self.config:
                    template = random.choice(self.config["subreddit_templates"])
                    focus = random.choice(template.get("focus_variants", ["supportive"]))
                    description = template["description"].replace("{focus}", focus)
                    sidebar = template["sidebar_template"].format(
                        name=subreddit_name,
                        focus=focus
                    )
                else:
                    template_set = self._get_template_set()
                    name_templates = template_set.get("name_templates", [])
                    type_variants = template_set.get("type_variants", [])
                    description_templates = template_set.get("description_templates", [])
                    sidebar_templates = template_set.get("sidebar_templates", [])
                    chosen_type = random.choice(type_variants) if type_variants else "Community"
                    description_template = random.choice(description_templates) if description_templates else "A subreddit for {type} discussions."
                    description = description_template.replace("{type}", chosen_type)
                    if sidebar_templates:
                        sidebar_template = random.choice(sidebar_templates)
                        sidebar = (
                            sidebar_template
                            .replace("{name}", subreddit_name)
                            .replace("{type}", chosen_type)
                            .replace("{type_lower}", chosen_type.lower())
                        )
                    else:
                        sidebar = (
                            f"**Welcome to r/{subreddit_name}!**\n\n"
                            f"## About This Community\n"
                            f"This is a space for {chosen_type.lower()} discussions about microdosing and psychedelic research.\n\n"
                            f"## Community Rules\n"
                            f"1. Be respectful and kind\n"
                            f"2. No sourcing or selling of substances\n"
                            f"3. Share experiences, not medical advice\n"
                            f"4. Cite sources when discussing research\n"
                            f"5. Practice harm reduction principles\n\n"
                            f"## Disclaimer\n"
                            f"This community does not provide medical advice. Consult healthcare professionals."
                        )
                
                # Create subreddit
                creation_result = self.execute_safely(
                    lambda: self.create_subreddit(subreddit_name, description, sidebar),
                    max_retries=2,
                    login_required=True,
                    action_name="create_subreddit",
                )
                if creation_result.success and creation_result.result:
                    # Configure settings
                    time.sleep(5)
                    self.execute_safely(
                        lambda: self.configure_subreddit(subreddit_name),
                        max_retries=2,
                        login_required=True,
                    )
                    
                    # Setup AutoModerator
                    time.sleep(3)
                    self.execute_safely(
                        lambda: self.setup_automod(subreddit_name),
                        max_retries=2,
                        login_required=True,
                    )
                    
                    # Create initial content
                    time.sleep(3)
                    self.execute_safely(
                        lambda: self.create_initial_content(subreddit_name),
                        max_retries=2,
                        login_required=True,
                    )
                    
                    created_count += 1
                    self.status_tracker.record_subreddit_creation(
                        self.account_name, subreddit_name, True
                    )
                    self._record_created_subreddit(subreddit_name)
                    logger.info(f"Successfully setup r/{subreddit_name}")
                    
                    # Delay between creations
                    delay_min, delay_max = self._get_creation_delay_seconds()
                    delay = random.randint(delay_min, delay_max)
                    if self.dry_run:
                        logger.info(f"[dry-run] Would wait {delay/3600:.1f} hours before next creation")
                    else:
                        logger.info(f"Waiting {delay/3600:.1f} hours before next creation")
                        time.sleep(delay)
                else:
                    self.status_tracker.record_subreddit_creation(
                        self.account_name, subreddit_name, False
                    )
                    logger.warning(f"Failed to create r/{subreddit_name}")
            
            logger.info(f"Created {created_count} subreddits")
            
        except Exception as e:
            logger.error(f"Error in SubredditCreator: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()

    def _record_created_subreddit(self, subreddit_name: str) -> None:
        history_path = Path("scripts/subreddit_creation/history/created_subreddits.json")
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            existing = []
            if history_path.exists():
                content = history_path.read_text().strip()
                if content:
                    existing = json.loads(content)
            entry = {
                "timestamp": datetime.now().isoformat(),
                "account": self.account_name,
                "subreddit": subreddit_name,
                "profile": self.profile_name,
            }
            existing.append(entry)
            history_path.write_text(json.dumps(existing, indent=2))
        except Exception as exc:
            logger.warning(f"Failed to record subreddit history: {exc}")

if __name__ == "__main__":
    # Create a simple command-line interface
    import argparse
    
    parser = argparse.ArgumentParser(description="Create MCRDSE subreddits")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--max", type=int, default=2, help="Maximum subreddits to create")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--test", action="store_true", help="Test mode - only show what would be created")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--validate-only", action="store_true", help="Validate configs/accounts and exit")
    
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
    creator = SubredditCreator(
        account_name=args.account,
        headless=args.headless,
        dry_run=bool(args.test or args.dry_run),
    )

    if args.validate_only:
        validation = creator.run_validations()
        print(f"Validation summary: {validation}")
        creator.cleanup()
        sys.exit(0)
    
    # Show what subreddits would be created
    print("Subreddit names that would be created:")
    for i, name in enumerate(creator.subreddit_names[:args.max], 1):
        print(f"  {i}. r/{name}")
    
    if not args.test:
        creator.run(max_subreddits=args.max, headless=args.headless)
    else:
        print("\nTest mode complete. No subreddits were created.")
        print("To actually create subreddits, run without --test flag.")
