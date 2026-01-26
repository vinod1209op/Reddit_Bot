"""
Purpose: Safety checks for Reddit bot operations.
"""

# Imports
import re
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

# Constants

# Public API
class SafetyChecker:
    """Checks for safety and compliance before any bot action"""
    
    def __init__(self, config):
        self.config = config
        self.action_history = []
        self.last_action_time = {}
        self.max_history_size = 1000
        
    def can_perform_action(self, action_type: str, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check if an action can be performed based on rate limits and safety rules
        
        Returns: (allowed: bool, reason: str)
        """
        # Get rate limits for this action type
        rate_limits = self.config.rate_limits.get(action_type, {})
        
        # Check rate limits
        if not self._check_rate_limit(action_type, rate_limits):
            return False, f"Rate limit exceeded for {action_type}"
        
        # Check time since last same action
        if not self._check_action_cooldown(action_type, rate_limits):
            return False, f"Cooldown period for {action_type} not elapsed"
        
        # Check daily limits
        if not self._check_daily_limit(action_type, rate_limits):
            return False, f"Daily limit for {action_type} exceeded"
        
        # Check for unsafe content
        if target and not self._check_content_safety(target):
            return False, "Content failed safety checks"
        
        return True, "Action allowed"
    
    def _check_rate_limit(self, action_type: str, limits: Dict) -> bool:
        """Check hourly rate limit"""
        max_per_hour = limits.get("max_per_hour", 0)
        if max_per_hour <= 0:
            return True  # No limit
        
        # Count actions in last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_actions = [
            a for a in self.action_history 
            if a["type"] == action_type and a["timestamp"] > one_hour_ago
        ]
        
        return len(recent_actions) < max_per_hour
    
    def _check_action_cooldown(self, action_type: str, limits: Dict) -> bool:
        """Check minimum interval between same actions"""
        min_interval = limits.get("min_interval", 0)
        if min_interval <= 0:
            return True
        
        last_time = self.last_action_time.get(action_type)
        if not last_time:
            return True
        
        elapsed = (datetime.now() - last_time).total_seconds()
        return elapsed >= min_interval
    
    def _check_daily_limit(self, action_type: str, limits: Dict) -> bool:
        """Check daily action limit"""
        daily_limit = limits.get("daily_limit", 0)
        if daily_limit <= 0:
            return True
        
        # Count actions today
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_actions = [
            a for a in self.action_history 
            if a["type"] == action_type and a["timestamp"] > today
        ]
        
        return len(today_actions) < daily_limit
    
    def _check_content_safety(self, content: str) -> bool:
        """Check if content is safe to post"""
        # Check for personal information
        personal_info_patterns = [
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone numbers
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b\d{5}(?:[-\s]\d{4})?\b',  # ZIP codes
        ]
        
        for pattern in personal_info_patterns:
            if re.search(pattern, content):
                return False
        
        # Check for harmful content
        harmful_keywords = [
            "kill yourself", "harm yourself", "suicide method",
            "illegal drug source", "buy drugs", "sell drugs",
        ]
        
        content_lower = content.lower()
        for keyword in harmful_keywords:
            if keyword in content_lower:
                return False
        
        return True
    
    def record_action(self, action_type: str, target: Optional[str] = None, success: bool = True):
        """Record an action for history tracking"""
        action_record = {
            "timestamp": datetime.now(),
            "type": action_type,
            "target": target[:100] if target else None,  # Truncate for storage
            "success": success
        }
        
        self.action_history.append(action_record)
        self.last_action_time[action_type] = datetime.now()
        
        # Trim history if too large
        if len(self.action_history) > self.max_history_size:
            self.action_history = self.action_history[-self.max_history_size:]
    
    def get_action_stats(self) -> Dict:
        """Get statistics about bot actions"""
        stats = {
            "total_actions": len(self.action_history),
            "successful_actions": sum(1 for a in self.action_history if a["success"]),
            "failed_actions": sum(1 for a in self.action_history if not a["success"]),
            "actions_by_type": {},
            "recent_actions": self.action_history[-10:] if self.action_history else []
        }
        
        # Count by type
        for action in self.action_history:
            action_type = action["type"]
            stats["actions_by_type"][action_type] = stats["actions_by_type"].get(action_type, 0) + 1
        
        return stats
