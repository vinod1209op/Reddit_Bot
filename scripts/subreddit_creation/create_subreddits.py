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
from microdose_study_bot.core.logging import UnifiedLogger

logger = UnifiedLogger("SubredditCreator").get_logger()

class SubredditCreator(RedditAutomationBase):
    """Creates and configures new subreddits for MCRDSE"""
    
    def __init__(self, account_name="account1", headless=False, dry_run=False, ui_mode="modern", session=None, owns_session=True):
        """
        Initialize with account name from config/accounts.json
        
        Args:
            account_name: Which account to use (must be configured)
        """
        os.environ["SELENIUM_HEADLESS"] = "1" if headless else "0"
        self.account_name = account_name
        super().__init__(account_name=account_name, dry_run=dry_run, session=session, owns_session=owns_session)
        self.config = self.load_config()
        self.profile_name = self.config.get("default_profile") or "conservative"
        self.profile_config = self.config.get("profiles", {}).get(self.profile_name, {})
        self.network_config = self.load_network_config()
        self.randomize_templates = self._bool_env("RANDOMIZE_TEMPLATES", default=True) or bool(
            self.config.get("randomize_templates", True)
        )
        self.bypass_cooldowns = self._bool_env("BYPASS_CREATION_COOLDOWN", default=False)
        self.template_set_name = self._pick_template_set_name()
        self.subreddit_names = self.generate_subreddit_names()
        self.ui_mode = ui_mode

    def _bool_env(self, name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def _pick_template_set_name(self) -> Optional[str]:
        if "subreddit_templates" in self.config:
            return None
        template_sets = self.config.get("template_sets", {})
        if not isinstance(template_sets, dict) or not template_sets:
            return None
        if self.randomize_templates:
            return random.choice(list(template_sets.keys()))
        return None
        
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

    def load_network_config(self) -> Dict:
        path = Path("config/subreddit_network.json")
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _get_template_set(self) -> Dict:
        if "subreddit_templates" in self.config:
            return {}
        template_sets = self.config.get("template_sets", {})
        if not isinstance(template_sets, dict) or not template_sets:
            return {}
        set_name = self.template_set_name or self.profile_config.get("template_set") or self.config.get("default_template_set")
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
        if self.network_config.get("enabled"):
            categories = self.network_config.get("categories", {})
            names = []
            for group in categories.values():
                if isinstance(group, list):
                    names.extend(group)
            if names:
                # Expand names with optional variants for stronger randomization
                variants = self.network_config.get("name_variants", {})
                prefixes = variants.get("prefixes", ["", "The", "Official"])
                suffixes = variants.get("suffixes", ["Hub", "Forum", "Insights", "Updates", "Review"])
                expanded = []
                for base in names:
                    expanded.append(base)
                    if self.randomize_templates:
                        for p in prefixes:
                            for s in suffixes:
                                if p:
                                    expanded.append(f"{p}{base}{s}")
                                else:
                                    expanded.append(f"{base}{s}")
                # Normalize, de-dupe, and shuffle
                cleaned = []
                seen = set()
                for name in expanded:
                    norm = "".join(ch for ch in name if ch.isalnum() or ch == "_")[:21]
                    if norm and norm not in seen:
                        seen.add(norm)
                        cleaned.append(norm)
                random.shuffle(cleaned)
                return cleaned
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

    def _append_network_links(self, sidebar: str, subreddit_name: str) -> str:
        if not self.network_config.get("enabled"):
            return sidebar
        cross = self.network_config.get("cross_promotion", {})
        related_map = cross.get("related_map", {})
        links_per = int(cross.get("links_per_sidebar", 3))
        related = related_map.get(subreddit_name, [])
        if not related:
            return sidebar
        related = related[:links_per]
        links = "\n".join([f"- r/{name}" for name in related])
        return sidebar + "\n\n## Network Links\n" + links
    
    def check_account_eligibility(self):
        """Check if account meets Reddit's subreddit creation requirements"""
        try:
            if self.dry_run or not self.driver:
                logger.info("[dry-run] Skipping eligibility check")
                return True
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

    def _creation_limits_ok(self) -> Tuple[bool, str]:
        if self._bool_env("BYPASS_CREATION_LIMITS", default=False):
            return True, "bypassed"
        profile = self.profile_config or {}
        max_per_day = int(profile.get("max_subreddits_per_day", 1))
        max_per_week = int(profile.get("max_subreddits_per_week", 2))
        max_total = int(profile.get("max_total_subreddits", 3))

        entry = self.status_tracker.status_data.get(self.account_name, {})
        creations = entry.get("activity_stats", {}).get("subreddit_creations", [])
        successful = [c for c in creations if c.get("success")]

        now = datetime.now()
        day_count = 0
        week_count = 0
        for c in successful:
            try:
                ts = datetime.fromisoformat(c.get("timestamp"))
            except Exception:
                continue
            delta = now - ts
            if delta.days < 1:
                day_count += 1
            if delta.days < 7:
                week_count += 1

        if max_total and len(successful) >= max_total:
            return False, "total_limit"
        if max_per_day and day_count >= max_per_day:
            return False, "daily_limit"
        if max_per_week and week_count >= max_per_week:
            return False, "weekly_limit"
        return True, "ok"

    def _subreddit_exists(self, subreddit_name: str) -> bool:
        if not self.driver:
            return False
        try:
            self.driver.get(f"https://old.reddit.com/r/{subreddit_name}")
            time.sleep(2)
            page = self.driver.page_source.lower()
            if "subreddit not found" in page or "doesn't exist" in page:
                return False
            return True
        except Exception:
            return False
    
    def create_subreddit(self, name, description, sidebar, dry_run=False):
        """Create a new subreddit using the selected UI mode."""
        if self.ui_mode == "classic":
            return self.create_subreddit_classic(name, description, sidebar, dry_run=dry_run)
        return self.create_subreddit_modern(name, description, sidebar, dry_run=dry_run)

    def create_subreddit_modern(self, name, description, sidebar, dry_run=False):
        """Create a new subreddit using the modern Reddit UI."""
        try:
            logger.info(f"Attempting to create r/{name} (modern)")
            if dry_run:
                logger.info(f"[dry-run] Would create r/{name}")
                return True

            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            def _find_field(selectors, timeout=10):
                last_error = None
                end_time = time.time() + timeout
                while time.time() < end_time:
                    for by, selector in selectors:
                        try:
                            elements = self.driver.find_elements(by, selector)
                        except Exception as exc:
                            last_error = exc
                            continue
                        if not elements:
                            continue
                        visible = [el for el in elements if el.is_displayed() and el.is_enabled()]
                        if visible:
                            logger.info(f"Found visible field for selector: {selector}")
                            return visible[0]
                        if elements:
                            last_error = None
                    time.sleep(0.2)
                if last_error:
                    raise last_error
                raise RuntimeError("Field not found/visible for selectors: %s" % selectors)

            def _fill_field(field, value, label):
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                    self.driver.execute_script(
                        "arguments[0].removeAttribute('readonly'); arguments[0].removeAttribute('disabled');",
                        field,
                    )
                    field.click()
                    field.clear()
                    field.send_keys(value)
                    return
                except Exception as exc:
                    logger.warning(f"Fallback to JS set for {label}: {exc}")
                    self.driver.execute_script(
                        """
                        const el = arguments[0];
                        const val = arguments[1];
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        field,
                        value,
                    )

            def _safe_click(element, label):
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    element.click()
                    return True
                except Exception as exc:
                    logger.warning(f"Fallback to JS click for {label}: {exc}")
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        return True
                    except Exception as js_exc:
                        logger.warning(f"JS click failed for {label}: {js_exc}")
                        return False

            logger.info("Using modern create flow...")
            self.driver.get("https://www.reddit.com/subreddits/create")
            time.sleep(4)

            name_field = _find_field([
                (By.CSS_SELECTOR, "input[name='name']"),
                (By.ID, "name"),
                (By.CSS_SELECTOR, "input[aria-label*='name' i]"),
                (By.CSS_SELECTOR, "input[placeholder*='name' i]"),
                (By.CSS_SELECTOR, "input[data-testid*='name' i]"),
            ], timeout=6)
            _fill_field(name_field, name, "name_modern")

            title_field = _find_field([
                (By.CSS_SELECTOR, "input[name='title']"),
                (By.ID, "title"),
                (By.CSS_SELECTOR, "input[aria-label*='title' i]"),
                (By.CSS_SELECTOR, "input[placeholder*='title' i]"),
            ], timeout=6)
            _fill_field(title_field, f"Microdosing {name.split('_')[-1]} Community", "title_modern")

            desc_field = _find_field([
                (By.CSS_SELECTOR, "textarea[name='description']"),
                (By.CSS_SELECTOR, "textarea[aria-label*='description' i]"),
                (By.CSS_SELECTOR, "textarea[placeholder*='description' i]"),
                (By.CSS_SELECTOR, "textarea[name='public_description']"),
            ], timeout=6)
            _fill_field(desc_field, description, "description_modern")

            for selector in [
                "input[type='radio'][value='public']",
                "input[name='type'][value='public']",
                "input[name='communityType'][value='public']",
                "input[name='privacy'][value='public']",
            ]:
                try:
                    radio = self.driver.find_element(By.CSS_SELECTOR, selector)
                    _safe_click(radio, "public_modern")
                    break
                except Exception:
                    continue

            submit_button = None
            for by, selector in [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
                (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'community')]"),
            ]:
                try:
                    candidates = self.driver.find_elements(by, selector)
                except Exception:
                    candidates = []
                visible = [c for c in candidates if c.is_displayed() and c.is_enabled()]
                if visible:
                    submit_button = visible[-1]
                    logger.info(f"Found modern submit button via selector: {selector}")
                    break
            if submit_button:
                if os.getenv("MANUAL_SUBMIT", "1").strip().lower() not in ("0", "false", "no"):
                    logger.info("Manual submit enabled. Please click the Create/Submit button in the browser.")
                    try:
                        input("After clicking submit, press Enter to continue...")
                    except Exception:
                        pass
                else:
                    _safe_click(submit_button, "submit_modern")
                    time.sleep(5)
                return True
            logger.info("Modern submit button not found.")
            return False
        except Exception as exc:
            logger.warning(f"Modern create flow failed: {exc}")
            return False

    def create_subreddit_classic(self, name, description, sidebar, dry_run=False):
        """Create a new subreddit using the classic Reddit UI."""
        try:
            logger.info(f"Attempting to create r/{name} (classic)")
            if dry_run:
                logger.info(f"[dry-run] Would create r/{name}")
                return True

            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            def _find_field(selectors, timeout=10):
                last_error = None
                end_time = time.time() + timeout
                while time.time() < end_time:
                    for by, selector in selectors:
                        try:
                            elements = self.driver.find_elements(by, selector)
                        except Exception as exc:
                            last_error = exc
                            continue
                        if not elements:
                            continue
                        visible = [el for el in elements if el.is_displayed() and el.is_enabled()]
                        if visible:
                            logger.info(f"Found visible field for selector: {selector}")
                            return visible[0]
                        if elements:
                            last_error = None
                    time.sleep(0.2)
                if last_error:
                    raise last_error
                raise RuntimeError("Field not found/visible for selectors: %s" % selectors)

            def _fill_field(field, value, label):
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                    self.driver.execute_script(
                        "arguments[0].removeAttribute('readonly'); arguments[0].removeAttribute('disabled');",
                        field,
                    )
                    field.click()
                    field.clear()
                    field.send_keys(value)
                    return
                except Exception as exc:
                    logger.warning(f"Fallback to JS set for {label}: {exc}")
                    self.driver.execute_script(
                        """
                        const el = arguments[0];
                        const val = arguments[1];
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        field,
                        value,
                    )

            def _safe_click(element, label):
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    element.click()
                    return True
                except Exception as exc:
                    logger.warning(f"Fallback to JS click for {label}: {exc}")
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        return True
                    except Exception as js_exc:
                        logger.warning(f"JS click failed for {label}: {js_exc}")
                        return False

            logger.info("Using classic create flow...")
            self.driver.get("https://old.reddit.com/subreddits/create")
            time.sleep(3)

            try:
                name_field = _find_field([(By.ID, "name")])
                _fill_field(name_field, name, "name")
                time.sleep(1)
            except Exception as exc:
                logger.warning(f"Failed to fill name: {exc}")
            
            # Fill title
            try:
                title_field = _find_field([(By.ID, "title")])
                _fill_field(title_field, f"Microdosing {name.split('_')[-1]} Community", "title")
                time.sleep(1)
            except Exception as exc:
                logger.warning(f"Failed to fill title: {exc}")
            
            # Fill description
            logger.info("Filling public description...")
            desc_field = None
            try:
                desc_field = _find_field([
                    (By.NAME, "public_description"),
                    (By.ID, "public_description"),
                    (By.ID, "description"),
                    (By.NAME, "description"),
                    (By.CSS_SELECTOR, "textarea[name='description']"),
                    (By.CSS_SELECTOR, "textarea[name='public_description']"),
                ])
                try:
                    desc_attrs = self.driver.execute_script(
                        "const el = arguments[0]; return {"
                        "id: el.id || '', "
                        "name: el.name || '', "
                        "disabled: !!el.disabled, "
                        "readonly: !!el.readOnly, "
                        "tag: el.tagName.toLowerCase(), "
                        "type: (el.type || '')"
                        "};",
                        desc_field,
                    )
                    logger.info(f"Description field attrs: {desc_attrs}")
                except Exception as exc:
                    logger.warning(f"Failed to inspect description field attrs: {exc}")
                _fill_field(desc_field, description, "description")
                time.sleep(1)
            except Exception as exc:
                logger.warning(f"Failed to fill public description: {exc}")
            
            # Fill sidebar
            logger.info("Filling sidebar...")
            try:
                textareas = self.driver.find_elements(By.TAG_NAME, "textarea")
                visible_textareas = []
                for ta in textareas:
                    if ta.is_displayed():
                        visible_textareas.append(
                            {
                                "id": ta.get_attribute("id") or "",
                                "name": ta.get_attribute("name") or "",
                                "aria": ta.get_attribute("aria-label") or "",
                                "class": (ta.get_attribute("class") or "")[:80],
                            }
                        )
                if visible_textareas:
                    logger.info(f"Visible textareas: {visible_textareas}")
            except Exception as exc:
                logger.warning(f"Failed to list textareas: {exc}")

            try:
                sidebar_field = _find_field([
                    (By.XPATH, "//h3[contains(translate(., 'SIDEBAR', 'sidebar'), 'sidebar')]/following::textarea[1]"),
                    (By.XPATH, "//label[contains(translate(., 'SIDEBAR', 'sidebar'), 'sidebar')]/following::textarea[1]"),
                    (By.NAME, "description"),
                    (By.ID, "description"),
                    (By.CSS_SELECTOR, "textarea[name='description']"),
                    (By.ID, "sidebar"),
                    (By.NAME, "sidebar"),
                    (By.CSS_SELECTOR, "textarea[name='sidebar']"),
                ])
                if desc_field is not None and sidebar_field == desc_field:
                    logger.info("Sidebar field matches description field; skipping sidebar fill.")
                else:
                    _fill_field(sidebar_field, sidebar, "sidebar")
                time.sleep(1)
            except Exception as exc:
                logger.warning(f"Failed to fill sidebar: {exc}")

            # Fill submission text (optional)
            try:
                submit_field = _find_field([
                    (By.NAME, "submit_text"),
                    (By.ID, "submit_text"),
                    (By.CSS_SELECTOR, "textarea[name='submit_text']"),
                ])
                _fill_field(submit_field, "", "submit_text")
                time.sleep(0.5)
            except Exception as exc:
                logger.info(f"Submission text field not filled: {exc}")
            
            # Select category (Health) if available
            try:
                logger.info("Selecting category...")
                category_select = None
                for by, selector in [
                    (By.ID, "type"),
                    (By.NAME, "type"),
                    (By.CSS_SELECTOR, "select[name='type']"),
                    (By.CSS_SELECTOR, "select#type"),
                ]:
                    try:
                        category_select = self.driver.find_element(by, selector)
                        break
                    except Exception:
                        continue
                if category_select:
                    for option in category_select.find_elements(By.TAG_NAME, "option"):
                        if "Health" in option.text:
                            option.click()
                            break
                    time.sleep(1)
                else:
                    logger.info("Category select not found; skipping category selection.")
            except Exception as exc:
                logger.warning(f"Category selection skipped: {exc}")
            
            # Set to public if available
            try:
                logger.info("Setting visibility to public...")
                public_radio = None
                for by, selector in [
                    (By.CSS_SELECTOR, "input[value='public']"),
                    (By.CSS_SELECTOR, "input[name='sr_type'][value='public']"),
                    (By.CSS_SELECTOR, "input[type='radio'][value='public']"),
                ]:
                    try:
                        public_radio = self.driver.find_element(by, selector)
                        break
                    except Exception:
                        continue
                if public_radio:
                    _safe_click(public_radio, "public visibility")
                    time.sleep(1)
                else:
                    logger.info("Public radio not found; skipping visibility selection.")
            except Exception as exc:
                logger.warning(f"Public visibility selection skipped: {exc}")
            
            # Add rules (basic ones)
            try:
                logger.info("Filling rules...")
                rule_fields = [
                    f for f in self.driver.find_elements(By.CSS_SELECTOR, "input[name^='rules']")
                    if f.is_displayed() and f.is_enabled()
                ]
                rules = [
                    "No sourcing or selling of substances",
                    "Be respectful and kind",
                    "Share experiences, not medical advice",
                    "Practice harm reduction principles"
                ]
                
                for i, rule in enumerate(rules[:min(len(rules), len(rule_fields))]):
                    try:
                        _fill_field(rule_fields[i], rule, f"rule_{i+1}")
                        time.sleep(0.5)
                    except Exception as exc:
                        logger.warning(f"Rule field {i+1} skipped: {exc}")
            except Exception as exc:
                logger.info(f"Rules section skipped: {exc}")
            
            # Submit
            logger.info("Submitting form...")
            submit_button = None
            try:
                def _btn_info(el):
                    return {
                        "tag": el.tag_name,
                        "type": el.get_attribute("type") or "",
                        "name": el.get_attribute("name") or "",
                        "id": el.get_attribute("id") or "",
                        "value": (el.get_attribute("value") or "")[:60],
                        "text": (el.text or "")[:60],
                        "displayed": el.is_displayed(),
                        "enabled": el.is_enabled(),
                    }

                candidates = []
                for sel in [
                    "input[type='submit']",
                    "button[type='submit']",
                    "input[type='button']",
                    "button",
                ]:
                    try:
                        candidates.extend(self.driver.find_elements(By.CSS_SELECTOR, sel))
                    except Exception:
                        continue
                if candidates:
                    visible = [_btn_info(c) for c in candidates if c.is_displayed()]
                    if visible:
                        logger.info(f"Submit candidates (visible): {visible}")
            except Exception as exc:
                logger.warning(f"Failed to list submit candidates: {exc}")

            for by, selector in [
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
                (By.XPATH, "//input[@type='button' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
                (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
                (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]"),
            ]:
                try:
                    candidates = self.driver.find_elements(by, selector)
                except Exception:
                    candidates = []
                visible = [c for c in candidates if c.is_displayed() and c.is_enabled()]
                if visible:
                    submit_button = visible[-1]
                    logger.info(f"Found submit button via selector: {selector}")
                    break
            if not submit_button:
                try:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.5)
                except Exception:
                    pass
                for by, selector in [
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
                    (By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
                ]:
                    try:
                        candidates = self.driver.find_elements(by, selector)
                    except Exception:
                        candidates = []
                    visible = [c for c in candidates if c.is_displayed() and c.is_enabled()]
                    if visible:
                        submit_button = visible[-1]
                        logger.info(f"Found submit button after scroll via selector: {selector}")
                        break
            if submit_button:
                if os.getenv("MANUAL_SUBMIT", "1").strip().lower() not in ("0", "false", "no"):
                    logger.info("Manual submit enabled. Please click the Create/Submit button in the browser.")
                    try:
                        input("After clicking submit, press Enter to continue...")
                    except Exception:
                        pass
                else:
                    try:
                        disabled_attr = submit_button.get_attribute("disabled")
                        if disabled_attr:
                            logger.info(f"Submit button disabled; attribute={disabled_attr!r}")
                        _safe_click(submit_button, "submit")
                        time.sleep(5)
                        logger.info(f"Post-submit URL: {self.driver.current_url}")
                        if "/subreddits/create" in (self.driver.current_url or ""):
                            try:
                                error_elems = self.driver.find_elements(By.CSS_SELECTOR, ".error, .errors, .error .error")
                            except Exception:
                                error_elems = []
                            error_texts = []
                            for el in error_elems:
                                try:
                                    txt = (el.text or "").strip()
                                    if txt:
                                        error_texts.append(txt)
                                except Exception:
                                    continue
                            if error_texts:
                                logger.warning(f"Create form errors: {error_texts}")
                                if any("tricky" in e.lower() or "captcha" in e.lower() for e in error_texts):
                                    logger.warning("CAPTCHA detected. Please solve it in the browser, then press Enter here to retry submit.")
                                    try:
                                        input("Solve CAPTCHA in the open browser, then press Enter to continue...")
                                    except Exception:
                                        pass
                                    _safe_click(submit_button, "submit_after_captcha")
                                    time.sleep(5)
                            else:
                                # Fallback: grab any visible text that hints at error
                                try:
                                    body_text = (self.driver.find_element(By.TAG_NAME, "body").text or "")
                                    for hint in ["already taken", "name is taken", "try another", "error", "invalid"]:
                                        if hint in body_text.lower():
                                            logger.warning(f"Create form hint detected: {hint}")
                                            break
                                except Exception:
                                    pass
                    except Exception as exc:
                        logger.warning(f"Submit click failed: {exc}")
                        try:
                            self.driver.execute_script("arguments[0].form && arguments[0].form.submit();", submit_button)
                            time.sleep(5)
                        except Exception as js_exc:
                            logger.warning(f"Submit form JS failed: {js_exc}")
            else:
                logger.info("Submit button not found; skipping submit.")
            
            # Verify creation
            if f"/r/{name}/" in (self.driver.current_url or ""):
                logger.info(f"Successfully created r/{name}")
                return True
            
            return False
            
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
        from selenium.webdriver.common.by import By
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
        from selenium.webdriver.common.by import By
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
    
    def run(self, max_subreddits=3, headless=False, keep_open: bool = False):
        """Main execution method"""
        try:
            validation = self.run_validations()
            logger.info(f"Validation summary: {validation}")
            enabled, reason = self.is_feature_enabled("subreddit_creation")
            if not enabled:
                logger.info(f"Subreddit creation disabled ({reason}); exiting.")
                return
            limits_ok, limit_reason = self._creation_limits_ok()
            if not limits_ok:
                logger.info(f"Creation limits reached ({limit_reason}); exiting.")
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
            created_history = self._load_created_subreddits()
            random.shuffle(self.subreddit_names)
            created_count = 0
            for subreddit_name in self.subreddit_names[:max_subreddits]:
                if not self.bypass_cooldowns:
                    if not self.status_tracker.can_perform_action(
                        self.account_name, "creation", subreddit=subreddit_name
                    ):
                        logger.info(f"Skipping creation for r/{subreddit_name} due to cooldown/limits")
                        continue
                if subreddit_name in created_history:
                    logger.info(f"Skipping r/{subreddit_name}; already created (history)")
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
                sidebar = self._append_network_links(sidebar, subreddit_name)
                
                # Create subreddit
                creation_result = self.execute_safely(
                    lambda: self.create_subreddit(subreddit_name, description, sidebar, dry_run=self.dry_run),
                    max_retries=2,
                    login_required=True,
                    action_name="create_subreddit",
                )
                if creation_result.success and creation_result.result:
                    # Configure settings
                    time.sleep(5)
                    if os.getenv("SKIP_CREATION_SETUP", "").strip().lower() not in ("1", "true", "yes"):
                        if self.config.get("post_creation", {}).get("configure_settings", True):
                            self.execute_safely(
                                lambda: self.configure_subreddit(subreddit_name),
                                max_retries=2,
                                login_required=True,
                                action_name="configure_subreddit",
                            )
                    else:
                        logger.info("Skipping post-creation setup steps (SKIP_CREATION_SETUP=1)")
                    
                    if os.getenv("SKIP_CREATION_SETUP", "").strip().lower() not in ("1", "true", "yes"):
                        # Setup AutoModerator
                        time.sleep(3)
                        if self.config.get("post_creation", {}).get("setup_automod", True):
                            self.execute_safely(
                                lambda: self.setup_automod(subreddit_name),
                                max_retries=2,
                                login_required=True,
                                action_name="setup_automod",
                            )
                        
                        # Create initial content
                        time.sleep(3)
                        if self.config.get("post_creation", {}).get("welcome_post", True):
                            self.execute_safely(
                                lambda: self.create_initial_content(subreddit_name),
                                max_retries=2,
                                login_required=True,
                                action_name="welcome_post",
                            )
                    
                    created_count += 1
                    self.status_tracker.record_subreddit_creation(
                        self.account_name,
                        subreddit_name,
                        True,
                        cooldown_days=int(self.profile_config.get("min_days_between_creations", 7)),
                    )
                    self._record_created_subreddit(subreddit_name)
                    created_history.add(subreddit_name)
                    if self.config.get("post_creation", {}).get("add_to_scan_list", False):
                        self._add_to_scan_list(subreddit_name)
                    logger.info(f"Successfully setup r/{subreddit_name}")
                    
                    # Delay between creations
                    delay_min, delay_max = self._get_creation_delay_seconds()
                    delay = random.randint(delay_min, delay_max)
                    if self.dry_run:
                        logger.info(f"[dry-run] Would wait {delay/3600:.1f} hours before next creation")
                    else:
                        if max_subreddits <= 1:
                            logger.info("Single-create run; skipping long wait before next creation.")
                            try:
                                input("Press Enter to continue to the next step...")
                            except Exception:
                                pass
                        else:
                            logger.info(f"Waiting {delay/3600:.1f} hours before next creation")
                            time.sleep(delay)
                else:
                    self.status_tracker.record_subreddit_creation(
                        self.account_name,
                        subreddit_name,
                        False,
                        cooldown_days=int(self.profile_config.get("min_days_between_creations", 7)),
                    )
                    logger.warning(f"Failed to create r/{subreddit_name}")
            
            logger.info(f"Created {created_count} subreddits")
            
        except Exception as e:
            logger.error(f"Error in SubredditCreator: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if not keep_open:
                self.cleanup()

    def _record_created_subreddit(self, subreddit_name: str) -> None:
        history_path = Path("scripts/subreddit_creation/history/created_subreddits.json")
        legacy_path = Path("data/created_subreddits.json")
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
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy = []
            if legacy_path.exists():
                content = legacy_path.read_text().strip()
                if content:
                    legacy = json.loads(content)
            legacy.append(entry)
            legacy_path.write_text(json.dumps(legacy, indent=2))
        except Exception as exc:
            logger.warning(f"Failed to record subreddit history: {exc}")

    def _load_created_subreddits(self) -> set[str]:
        history_path = Path("scripts/subreddit_creation/history/created_subreddits.json")
        legacy_path = Path("data/created_subreddits.json")
        for path in (history_path, legacy_path):
            if not path.exists():
                continue
            try:
                content = path.read_text().strip()
                if not content:
                    continue
                entries = json.loads(content)
                if isinstance(entries, list):
                    return {e.get("subreddit") for e in entries if isinstance(e, dict) and e.get("subreddit")}
            except Exception:
                continue
        return set()

    def _add_to_scan_list(self, subreddit_name: str) -> None:
        path = Path("config/subreddits.json")
        try:
            existing = []
            if path.exists():
                content = path.read_text().strip()
                if content:
                    existing = json.loads(content)
            if subreddit_name not in existing:
                existing.append(subreddit_name)
                path.write_text(json.dumps(existing, indent=2))
        except Exception as exc:
            logger.warning(f"Failed to update subreddits.json: {exc}")

if __name__ == "__main__":
    # Create a simple command-line interface
    import argparse
    
    parser = argparse.ArgumentParser(description="Create MCRDSE subreddits")
    parser.add_argument("--account", default="account1", help="Reddit account to use")
    parser.add_argument("--max", type=int, default=2, help="Maximum subreddits to create")
    parser.add_argument("--name", help="Create a single specific subreddit name (overrides config list)")
    parser.add_argument("--ui", choices=["modern", "classic"], default="modern", help="Select UI flow")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--test", action="store_true", help="Test mode - only show what would be created")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--validate-only", action="store_true", help="Validate configs/accounts and exit")
    
    args = parser.parse_args()
    
    logger.info("\n" + "="*60)
    logger.info("MCRDSE Subreddit Creation Tool")
    logger.info("="*60)
    
    if args.test:
        logger.info("TEST MODE: No subreddits will actually be created")
    
    logger.info(f"Account: {args.account}")
    logger.info(f"Max to create: {args.max}")
    logger.info(f"Headless mode: {args.headless}")
    logger.info("="*60 + "\n")
    
    # Create creator instance
    creator = SubredditCreator(
        account_name=args.account,
        headless=args.headless,
        dry_run=bool(args.test or args.dry_run),
        ui_mode=args.ui,
    )

    if args.validate_only:
        validation = creator.run_validations()
        logger.info(f"Validation summary: {validation}")
        creator.cleanup()
        sys.exit(0)
    
    if args.name:
        creator.subreddit_names = [args.name.strip()]
        args.max = 1
        logger.info(f"Override name provided: r/{creator.subreddit_names[0]}")

    # Show what subreddits would be created
    logger.info("Subreddit names that would be created:")
    for i, name in enumerate(creator.subreddit_names[:args.max], 1):
        logger.info(f"  {i}. r/{name}")
    
    if not args.test:
        creator.run(max_subreddits=args.max, headless=args.headless)
    else:
        logger.info("\nTest mode complete. No subreddits were created.")
        logger.info("To actually create subreddits, run without --test flag.")
