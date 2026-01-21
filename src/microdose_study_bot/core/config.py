import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

class ConfigManager:
    """Unified configuration for both API and Selenium methods"""
    
    def __init__(self):
        self.config_dir = Path(__file__).resolve().parents[3] / "config"
        self.config_dir.mkdir(exist_ok=True)
        
        # Initialize empty configs
        self.api_creds = {}
        self.selenium_settings = {}
        self.bot_settings = {}
        self.rate_limits = {}
        self.automation_settings = {}
        
        # Default configurations
        self.default_keywords = [
            "microdosing", "microdose", "psilocybin", "shrooms",
            "lsd", "psychedelic", "set and setting", "harm reduction"
        ]
        
        self.default_subreddits = ["test", "microdosing", "psilocybin"]
        self.default_rate_limits = {
            "comment": {"max_per_hour": 12, "min_interval": 300},
            "post": {"max_per_hour": 3, "min_interval": 1200}
        }
        
    def load_all(self):
        """Load all configurations"""
        self.load_env()
        self.load_subreddits()
        self.load_keywords()
        self.load_rate_limits()
        self.load_settings()
        return self
    
    def load_env(self):
        """Load environment variables for both methods"""
        from dotenv import load_dotenv
        
        # Try multiple env file locations
        env_files = [
            self.config_dir / "credentials.env",
            Path.cwd() / ".env",
            Path.home() / ".reddit_bot.env"
        ]
        
        loaded_file = None
        for env_file in env_files:
            if env_file.exists():
                load_dotenv(env_file)
                loaded_file = env_file
                break
        
        if loaded_file:
            print(f"✓ Loaded environment from: {loaded_file}")
        else:
            print("⚠️  No .env file found")
        
        # API credentials
        self.api_creds = {
            "client_id": os.getenv("REDDIT_CLIENT_ID", ""),
            "client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
            "username": os.getenv("REDDIT_USERNAME", ""),
            "password": os.getenv("REDDIT_PASSWORD", ""),
            "user_agent": os.getenv("REDDIT_USER_AGENT", "bot:reddit-automation:v1.0"),
        }
        
        # Selenium settings
        self.selenium_settings = {
            "headless": os.getenv("SELENIUM_HEADLESS", "False").lower() in ("true", "1"),
            "wait_time": int(os.getenv("SELENIUM_WAIT_TIME", "10")),
            "browser": os.getenv("BROWSER_TYPE", "chrome"),
            "chrome_binary": os.getenv("CHROME_BIN", ""),
            "chromedriver_path": os.getenv("CHROMEDRIVER_PATH", ""),
            "chromedriver_version": os.getenv("CHROMEDRIVER_VERSION", ""),
            "cookie_file": os.getenv("COOKIE_PATH", "data/cookies_account1.pkl"),
            "use_undetected": os.getenv("SELENIUM_USE_UNDETECTED", "1").lower() in ("true", "1", "yes", "y", "on"),
            "stealth_mode": os.getenv("SELENIUM_STEALTH", "1").lower() in ("true", "1", "yes", "y", "on"),
            "randomize_fingerprint": os.getenv("SELENIUM_RANDOMIZE_FINGERPRINT", "1").lower() in ("true", "1", "yes", "y", "on"),
        }
        
        # Bot settings
        self.bot_settings = {
            "mode": os.getenv("BOT_MODE", "selenium"),  # "selenium" or "api"
            "enable_posting": os.getenv("ENABLE_POSTING", "0") in ("1", "true"),
            "mock_mode": os.getenv("MOCK_MODE", "0") in ("1", "true"),
            "use_llm": os.getenv("USE_LLM", "0") in ("1", "true"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "human_approval": os.getenv("HUMAN_APPROVAL_MODE", "all"),
            "auto_submit_limit": int(os.getenv("SELENIUM_AUTO_SUBMIT_LIMIT", "0") or 0),
        }

        self.google_creds = {
            "google_email": os.getenv("GOOGLE_EMAIL", ""),
            "google_password": os.getenv("GOOGLE_PASSWORD", ""),
        }
        
        self.load_subreddits()
        self.load_keywords()
        
        return self
    
    def load_settings(self):
        """Load automation settings from settings.json"""
        settings_file = self.config_dir / "settings.json"
        
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    self.automation_settings = settings.get("automation", {})
                    self.safety_settings = settings.get("safety", {})
            except Exception as e:
                print(f"Error reading settings.json: {e}")
                self.automation_settings = {}
                self.safety_settings = {}
        else:
            print(f"⚠️  No settings.json found, using defaults")
            self.automation_settings = {}
            self.safety_settings = {}
        
        return self
    
    def load_rate_limits(self):
        """Load rate limits from rate_limits.json"""
        limits_file = self.config_dir / "rate_limits.json"
        
        if limits_file.exists():
            try:
                with open(limits_file, 'r') as f:
                    self.rate_limits = json.load(f)
            except Exception as e:
                print(f"Error reading rate_limits.json: {e}")
                self.rate_limits = self.default_rate_limits
        else:
            print(f"⚠️  No rate_limits.json found, using defaults")
            self.rate_limits = self.default_rate_limits
        
        return self
    
    def _load_json_list(self, filename: str, default: List[str]) -> List[str]:
        """Helper to load JSON list files"""
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            print(f"⚠️  Creating default {filename}")
            self.save_json(filepath, default)
            return default
        
        try:
            with open(filepath, 'r') as f:
                content = f.read().strip()
                if not content:
                    print(f"⚠️  Empty {filename}, using defaults")
                    return default
                
                data = json.loads(content)
                if isinstance(data, list):
                    return data
                else:
                    print(f"⚠️  Invalid format in {filename}, using defaults")
                    return default
                    
        except json.JSONDecodeError as e:
            print(f"Error reading {filename}: {e}. Using defaults.")
            return default
        except Exception as e:
            print(f"Unexpected error loading {filename}: {e}")
            return default
    
    def load_subreddits(self) -> List[str]:
        """Load subreddits from config"""
        self.bot_settings["subreddits"] = self._load_json_list(
            "subreddits.json", self.default_subreddits
        )
        return self.bot_settings["subreddits"]
    
    def load_keywords(self) -> List[str]:
        """Load keywords from config"""
        self.bot_settings["keywords"] = self._load_json_list(
            "keywords.json", self.default_keywords
        )
        return self.bot_settings["keywords"]

    def load_json(self, path: str, default: Any = None) -> Any:
        """Load JSON data from a file path (relative to repo root or config dir)."""
        if not path:
            return default

        path_obj = Path(path)
        if not path_obj.is_absolute():
            if path_obj.parts and path_obj.parts[0] == "config":
                path_obj = self.config_dir.parent / path_obj
            else:
                path_obj = self.config_dir / path_obj

        if not path_obj.exists():
            return default

        try:
            with path_obj.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {path_obj}: {e}")
            return default

    def load_activity_schedule(self):
        """Load activity schedule configuration"""
        return self.load_json('config/activity_schedule.json')

    def load_accounts_config(self):
        """Load multi-account configuration"""
        accounts_file = os.path.join(self.config_dir, 'accounts.json')
        if os.path.exists(accounts_file):
            with open(accounts_file, 'r') as f:
                accounts = json.load(f)
            
            # Load credentials from environment variables
            for account in accounts:
                email_var = account.get('email_env_var')
                password_var = account.get('password_env_var')
                
                if email_var and password_var:
                    account['email'] = os.getenv(email_var)
                    account['password'] = os.getenv(password_var)
            
            return accounts
        return []
    
    def save_json(self, filepath: Path, data: Any):
        """Save data to JSON file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ Saved config to: {filepath}")
        except Exception as e:
            print(f"✗ Failed to save {filepath}: {e}")
    
    def get_credentials_valid(self) -> bool:
        """Check if required credentials are present for selected mode"""
        mode = self.bot_settings.get("mode", "selenium")
        
        if mode == "api":
            # API mode requires Reddit API credentials
            required = ["client_id", "client_secret", "username", "password"]
            missing = [key for key in required if not self.api_creds.get(key)]
            
            if missing:
                print(f"Missing API credentials: {missing}")
                return False
            return True
        else:  # selenium mode
            # Selenium mode can use either Reddit or Google credentials
            has_reddit = self.api_creds.get("username") and self.api_creds.get("password")
            has_google = self.google_creds.get("google_email") and self.google_creds.get("google_password")
            
            if not has_reddit and not has_google:
                print("Selenium mode requires either Reddit username/password OR Google email/password")
                return False
            return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation"""
        # Check bot_settings first
        if key in self.bot_settings:
            return self.bot_settings[key]
        
        # Check api_creds
        if key in self.api_creds:
            return self.api_creds[key]
        
        # Check nested keys (e.g., "automation.headless_mode")
        if "." in key:
            parts = key.split(".")
            if parts[0] == "automation" and parts[1] in self.automation_settings:
                return self.automation_settings.get(parts[1], default)
            if parts[0] == "safety" and parts[1] in self.safety_settings:
                return self.safety_settings.get(parts[1], default)
        
        return default
    
    def print_summary(self):
        """Print configuration summary"""
        print("\n" + "="*50)
        print("Configuration Summary")
        print("="*50)
        
        # Bot settings
        print(f"Bot Mode: {self.bot_settings.get('mode', 'N/A')}")
        print(f"Posting enabled: {self.bot_settings.get('enable_posting', False)}")
        print(f"Mock mode: {self.bot_settings.get('mock_mode', False)}")
        print(f"LLM enabled: {self.bot_settings.get('use_llm', False)}")
        
        # Subreddits & Keywords
        subreddits = self.bot_settings.get("subreddits", [])
        keywords = self.bot_settings.get("keywords", [])
        print(f"\nSubreddits ({len(subreddits)}): {', '.join(subreddits[:5])}" + 
              ("..." if len(subreddits) > 5 else ""))
        print(f"Keywords ({len(keywords)}): {', '.join(keywords[:5])}" +
              ("..." if len(keywords) > 5 else ""))
        
        # Automation settings
        if self.automation_settings:
            print(f"\nAutomation Settings:")
            for key, value in self.automation_settings.items():
                print(f"  {key}: {value}")
        
        # Safety settings
        if getattr(self, "safety_settings", None):
            print(f"\nSafety Settings:")
            for key, value in self.safety_settings.items():
                print(f"  {key}: {value}")
        
        # Mask credentials for display
        print(f"\nCredentials:")
        for key, value in self.api_creds.items():
            if value and ('secret' in key or 'password' in key):
                masked = "***" + value[-3:] if len(value) > 3 else "***"
                print(f"  {key}: {masked}")
            elif value:
                masked = value[:10] + "..." if len(value) > 10 else value
                print(f"  {key}: {masked}")
            else:
                print(f"  {key}: (empty)")
        
        # Rate limits
        if self.rate_limits:
            print(f"\nRate Limits:")
            for action, limits in self.rate_limits.items():
                print(f"  {action}: {limits.get('max_per_hour', 'N/A')}/hour")
        
        print("="*50 + "\n")
