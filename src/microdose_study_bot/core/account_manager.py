"""
Account health and ban response manager.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self, status_file="data/account_status.json"):
        self.status_file = Path(status_file)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_data = self._load_status()
        self.cooldowns = {}  # account_name: resume_time
    
    def _load_status(self):
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load account status: {e}")
        return {}
    
    def _save_status(self):
        try:
            with open(self.status_file, 'w') as f:
                json.dump(self.status_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save account status: {e}")
    
    def update_status(self, account_name: str, status: str, details: str = ""):
        """Update account status and handle responses."""
        if account_name not in self.status_data:
            self.status_data[account_name] = {
                "current_status": "unknown",
                "history": [],
                "created": datetime.now().isoformat()
            }
        
        old_status = self.status_data[account_name].get("current_status", "unknown")
        self.status_data[account_name]["current_status"] = status
        self.status_data[account_name]["last_updated"] = datetime.now().isoformat()
        
        # Add to history
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "from": old_status,
            "to": status,
            "details": details
        }
        self.status_data[account_name]["history"].append(history_entry)
        
        # Keep history manageable
        if len(self.status_data[account_name]["history"]) > 50:
            self.status_data[account_name]["history"] = self.status_data[account_name]["history"][-50:]
        
        # Take action based on status
        self._take_action(account_name, status, details)
        
        self._save_status()
        logger.info(f"Account {account_name}: {old_status} → {status}")
    
    def _take_action(self, account_name: str, status: str, details: str):
        """Take appropriate action based on ban type."""
        if status == "suspended":
            # Permanent - stop using this account
            self.cooldowns[account_name] = None  # Never resume
            logger.error(f"Account {account_name} PERMANENTLY SUSPENDED. Removing from rotation.")
            
            # TODO: Send alert (email, Slack, etc.)
            # You could integrate with GitHub Actions notifications
            
        elif status == "rate_limited":
            # Temporary - add cooldown (4-12 hours)
            cooldown_hours = max(4, min(12, len(details.split())))  # Simple heuristic
            resume_time = datetime.now() + timedelta(hours=cooldown_hours)
            self.cooldowns[account_name] = resume_time.isoformat()
            logger.warning(f"Account {account_name} rate limited. Cooldown until {resume_time}")
            
        elif status == "captcha":
            # Short cooldown, might need manual intervention
            resume_time = datetime.now() + timedelta(hours=2)
            self.cooldowns[account_name] = resume_time.isoformat()
            logger.warning(f"Account {account_name} hit CAPTCHA. Cooldown 2 hours.")
    
    def can_use_account(self, account_name: str) -> bool:
        """Check if an account can be used now."""
        # Check if suspended
        if account_name in self.status_data:
            if self.status_data[account_name].get("current_status") == "suspended":
                return False
        
        # Check cooldown
        if account_name in self.cooldowns:
            resume_time = self.cooldowns[account_name]
            if resume_time is None:  # Permanent
                return False
            if isinstance(resume_time, str):
                resume_time = datetime.fromisoformat(resume_time)
            if datetime.now() < resume_time:
                logger.info(f"Account {account_name} still in cooldown until {resume_time}")
                return False
        
        return True
    
    def get_healthy_accounts(self, all_accounts: list) -> list:
        """Filter to only accounts that can be used right now."""
        healthy = []
        for account in all_accounts:
            account_name = account.get("name", "unknown")
            if self.can_use_account(account_name):
                healthy.append(account)
            else:
                logger.info(f"Skipping account {account_name} - not healthy")
        
        return healthy
    
    def get_status_report(self) -> dict:
        """Generate a status report for monitoring."""
        report = {
            "total_accounts": len(self.status_data),
            "active": 0,
            "suspended": 0,
            "rate_limited": 0,
            "in_cooldown": 0,
            "accounts": {}
        }
        
        for account_name, data in self.status_data.items():
            status = data.get("current_status", "unknown")
            report["accounts"][account_name] = status
            
            if status == "active":
                report["active"] += 1
            elif status == "suspended":
                report["suspended"] += 1
            elif status == "rate_limited":
                report["rate_limited"] += 1
            
            # Check cooldown
            if account_name in self.cooldowns:
                resume_time = self.cooldowns[account_name]
                if resume_time:
                    report["in_cooldown"] += 1
        
        return report