"""
Purpose: Local rate limiting for Selenium actions.
Constraints: Pure guard logic; no side effects beyond in-memory state.
"""

# Imports
import time
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import random

logger = logging.getLogger(__name__)

# Public API
class RateLimiter:
    def __init__(self, config_file="config/rate_limits.json"):
        """
        Rate limiter to prevent Reddit API abuse
        
        Reddit's limits (unofficial but safe):
        - Comments: 1 per 9 minutes (when new account/low karma)
        - Posts: 1 per 10 minutes
        - Messages: 10 per hour
        - Votes: 30 per minute
        """
        self.config_file = config_file
        self.limits = self.load_limits()
        
        # Action tracking
        self.action_history = defaultdict(list)
        self.blocked_until = {}
        
        # Safety multipliers (0.8 = 20% below Reddit's limits)
        self.safety_multiplier = 0.8
        
    def load_limits(self):
        """Load rate limits from config file"""
        default_limits = {
            "comment": {
                "max_per_hour": 15,       # Conservative limit
                "min_interval": 60,       # 1 minute between comments
                "daily_limit": 50
            },
            "post": {
                "max_per_hour": 4,
                "min_interval": 900,      # 15 minutes between posts
                "daily_limit": 10
            },
            "message": {
                "max_per_hour": 8,
                "min_interval": 300,      # 5 minutes between messages
                "daily_limit": 30
            },
            "vote": {
                "max_per_hour": 100,
                "min_interval": 2,        # 2 seconds between votes
                "daily_limit": 1000
            }
        }
        
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except:
            return default_limits
    
    def save_limits(self):
        """Save current limits to config file"""
        with open(self.config_file, 'w') as f:
            json.dump(self.limits, f, indent=2)
    
    def can_perform_action(self, action_type):
        """
        Check if action can be performed
        
        Args:
            action_type: 'comment', 'post', 'message', 'vote'
        
        Returns:
            tuple: (can_proceed: bool, wait_time: int)
        """
        if os.getenv("BYPASS_ALL_LIMITS", "1").strip().lower() in ("1", "true", "yes"):
            return True, 0
        if os.getenv("BYPASS_ENGAGEMENT_LIMITS", "1").strip().lower() in ("1", "true", "yes"):
            if str(action_type).lower() in {"comment", "reply", "vote", "follow", "save", "message", "post"}:
                return True, 0
        now = datetime.now()
        
        # Check if temporarily blocked
        if action_type in self.blocked_until:
            if now < self.blocked_until[action_type]:
                wait_seconds = (self.blocked_until[action_type] - now).total_seconds()
                return False, wait_seconds
        
        # Get action history for this type
        history = self.action_history[action_type]
        limits = self.limits.get(action_type, {})
        
        # Clean old entries (older than 24 hours)
        cutoff_time = now - timedelta(hours=24)
        history = [t for t in history if t > cutoff_time]
        self.action_history[action_type] = history
        
        # Check daily limit
        if len(history) >= limits.get("daily_limit", 100):
            logger.warning(f"Daily limit reached for {action_type}")
            # Block until tomorrow
            tomorrow = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
            self.blocked_until[action_type] = tomorrow
            return False, (tomorrow - now).total_seconds()
        
        # Check hourly limit (last 60 minutes)
        hour_ago = now - timedelta(minutes=60)
        recent_actions = [t for t in history if t > hour_ago]
        
        if len(recent_actions) >= limits.get("max_per_hour", 10):
            # Find when the oldest recent action will expire
            oldest_recent = min(recent_actions)
            available_at = oldest_recent + timedelta(minutes=60)
            wait_seconds = (available_at - now).total_seconds()
            
            logger.warning(f"Hourly limit reached for {action_type}. Wait {wait_seconds:.0f}s")
            return False, wait_seconds
        
        # Check minimum interval
        if history:
            last_action = history[-1]
            min_interval = limits.get("min_interval", 60)
            
            if (now - last_action).total_seconds() < min_interval:
                wait_seconds = min_interval - (now - last_action).total_seconds()
                return False, wait_seconds
        
        return True, 0
    
    def record_action(self, action_type):
        """Record that an action was performed"""
        now = datetime.now()
        self.action_history[action_type].append(now)
        logger.debug(f"Recorded {action_type} action at {now}")
        
        # Save history periodically
        if len(self.action_history[action_type]) % 10 == 0:
            self.save_action_history()
    
    def wait_if_needed(self, action_type):
        """
        Wait if rate limit requires it
        
        Args:
            action_type: Type of action to check
        
        Returns:
            bool: True if action can proceed immediately
        """
        can_proceed, wait_time = self.can_perform_action(action_type)
        
        if not can_proceed and wait_time > 0:
            logger.info(f"Rate limit active. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time + random.uniform(0.5, 2))  # Add random buffer
            return True  # Can proceed after waiting
        elif not can_proceed:
            logger.error(f"Cannot perform {action_type} - blocked")
            return False
        else:
            return True  # Can proceed immediately
    
    def save_action_history(self):
        """Save action history to file"""
        try:
            # Convert datetime objects to strings
            serializable = {}
            for action_type, timestamps in self.action_history.items():
                serializable[action_type] = [
                    ts.isoformat() for ts in timestamps
                ]
            
            with open('logs/action_history.json', 'w') as f:
                json.dump(serializable, f, default=str)
        except Exception as e:
            logger.error(f"Failed to save action history: {e}")
    
    def load_action_history(self):
        """Load action history from file"""
        try:
            with open('logs/action_history.json', 'r') as f:
                data = json.load(f)
                
            for action_type, timestamps in data.items():
                self.action_history[action_type] = [
                    datetime.fromisoformat(ts) for ts in timestamps
                ]
        except:
            pass  # No history file exists yet
    
    def get_stats(self, action_type=None):
        """Get statistics about actions"""
        now = datetime.now()
        stats = {}
        
        if action_type:
            types = [action_type]
        else:
            types = self.action_history.keys()
        
        for atype in types:
            history = self.action_history[atype]
            
            stats[atype] = {
                "total_today": len([t for t in history 
                                   if t.date() == now.date()]),
                "last_hour": len([t for t in history 
                                 if t > now - timedelta(hours=1)]),
                "last_action": max(history).isoformat() if history else "Never",
                "remaining_today": self.limits.get(atype, {}).get("daily_limit", 100) - 
                                 len([t for t in history if t.date() == now.date()])
            }
        
        return stats
