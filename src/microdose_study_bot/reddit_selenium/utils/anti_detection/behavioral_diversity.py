"""
Multiple personality patterns and behavioral switching to avoid detection.
"""

import random
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from microdose_study_bot.core.logging import UnifiedLogger

class BehavioralPersonality:
    """Represents a specific behavioral pattern for an account."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        
        # Click/scroll patterns
        self.click_speed = config.get("click_speed", "normal")  # slow/normal/fast
        self.scroll_pattern = config.get("scroll_pattern", "smooth")  # smooth/jerky/reader
        self.scroll_distance_range = config.get("scroll_distance_range", (300, 800))
        
        # Engagement patterns
        self.engagement_rate = config.get("engagement_rate", 0.3)  # Chance to engage
        self.comment_style = config.get("comment_style", "neutral")  # neutral/enthusiast/skeptic
        
        # Session patterns
        self.session_length_range = config.get("session_length_range", (10, 30))
        self.actions_per_minute_range = config.get("actions_per_minute_range", (2, 6))
        
        # Content preferences
        self.content_preferences = config.get("content_preferences", {
            "research": 0.4,
            "experience": 0.3,
            "question": 0.2,
            "other": 0.1
        })

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"BehavioralPersonality(name={self.name}, click_speed={self.click_speed}, engagement_rate={self.engagement_rate})"

    def get_random_scroll_distance(self) -> int:
        """Get a random scroll distance within the configured range."""
        return random.randint(self.scroll_distance_range[0], self.scroll_distance_range[1])

    def get_session_length(self) -> int:
        """Get a random session length within the configured range."""
        return random.randint(self.session_length_range[0], self.session_length_range[1])

    def get_actions_per_minute(self) -> float:
        """Get a random actions-per-minute rate within the configured range."""
        return random.uniform(self.actions_per_minute_range[0], self.actions_per_minute_range[1])


class PersonalitySwitcher:
    """Manages switching between multiple personality patterns."""
    
    def __init__(self, account_name: str, config_path: Optional[Path] = None):
        self.account_name = account_name
        self.logger = UnifiedLogger("PersonalitySwitcher").get_logger()
        
        # Load or create default personalities
        self.personalities = self._load_personalities(config_path)
        
        # Current state
        self.current_personality = None
        self.last_switch_time = None
        self.switch_history = []
        
        # Switching logic
        self.min_time_between_switches = timedelta(hours=6)
        self.switch_probability = 0.15  # 15% chance to switch per eligible session
        
        # Load account's personality history
        self.history_file = Path(f"data/behavioral_history_{account_name}.json")
        self.load_history()
    
    def _load_personalities(self, config_path: Optional[Path]) -> Dict[str, BehavioralPersonality]:
        """Load personality configurations from file or use defaults.
        
        Args:
            config_path: Optional path to personality configuration JSON file
            
        Returns:
            Dictionary of personality name to BehavioralPersonality object
        """
        configs: Dict[str, Any] = {}
        
        if config_path and config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
                self.logger.debug(f"Loaded personality config from {config_path}")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load personality config from {config_path}: {e}. Using defaults.")
                configs = self._get_default_personalities()
        else:
            configs = self._get_default_personalities()
        
        return {name: BehavioralPersonality(name, config) for name, config in configs.items()}
    
    def _get_default_personalities(self) -> Dict[str, Any]:
        """Get default personality configurations."""
        return {
            "cautious_reader": {
                "click_speed": "slow",
                "scroll_pattern": "reader",
                "scroll_distance_range": (200, 500),
                "engagement_rate": 0.2,
                "comment_style": "neutral",
                "session_length_range": (15, 25),
                "actions_per_minute_range": (1, 3),
                "content_preferences": {
                    "research": 0.6,
                    "experience": 0.2,
                    "question": 0.1,
                    "other": 0.1
                }
            },
            "enthusiastic_participant": {
                "click_speed": "normal",
                "scroll_pattern": "smooth",
                "scroll_distance_range": (400, 900),
                "engagement_rate": 0.5,
                "comment_style": "enthusiast",
                "session_length_range": (20, 40),
                "actions_per_minute_range": (3, 7),
                "content_preferences": {
                    "research": 0.3,
                    "experience": 0.4,
                    "question": 0.2,
                    "other": 0.1
                }
            },
            "quick_browser": {
                "click_speed": "fast",
                "scroll_pattern": "jerky",
                "scroll_distance_range": (600, 1200),
                "engagement_rate": 0.1,
                "comment_style": "skeptic",
                "session_length_range": (5, 15),
                "actions_per_minute_range": (5, 10),
                "content_preferences": {
                    "research": 0.2,
                    "experience": 0.3,
                    "question": 0.4,
                    "other": 0.1
                }
            }
        }
    
    def select_personality(self, force_switch: bool = False) -> BehavioralPersonality:
        """Select a personality for the current session.
        
        Args:
            force_switch: If True, force a personality switch regardless of timing
            
        Returns:
            The selected BehavioralPersonality object
        """
        # Check if we should switch
        should_switch = force_switch or self._should_switch_personality()
        
        if should_switch or not self.current_personality:
            # Select new personality (can be same as current for randomness)
            old_personality = self.current_personality.name if self.current_personality else None
            
            # Weighted selection (can add weights in config)
            available = list(self.personalities.keys())
            weights = [0.4, 0.4, 0.2]  # Prefer cautious and enthusiastic
            
            # Avoid quick switches to same personality
            if old_personality and len(available) > 1:
                available = [p for p in available if p != old_personality]
                weights = [0.5, 0.5] if len(available) == 2 else [1.0]
            
            selected_name = random.choices(available, weights=weights[:len(available)])[0]
            self.current_personality = self.personalities[selected_name]
            self.last_switch_time = datetime.now()
            
            # Log the switch
            self.logger.info(f"[{self.account_name}] Personality switched: {old_personality} → {selected_name}")
            
            # Record in history
            self.switch_history.append({
                "timestamp": datetime.now().isoformat(),
                "from": old_personality,
                "to": selected_name,
                "reason": "scheduled" if not force_switch else "forced"
            })
        
        return self.current_personality
    
    def _should_switch_personality(self) -> bool:
        """Determine if we should switch personality for this session.
        
        Returns:
            True if a personality switch should occur, False otherwise
        """
        # Check time since last switch
        if self.last_switch_time:
            time_since_switch = datetime.now() - self.last_switch_time
            if time_since_switch < self.min_time_between_switches:
                return False
        
        # Random chance to switch
        if random.random() < self.switch_probability:
            return True
        
        # If same personality used for > 7 sessions, force switch
        if len(self.switch_history) >= 7:
            recent = self.switch_history[-7:]
            recent_personalities = [entry.get("to") for entry in recent]
            if len(set(recent_personalities)) == 1:  # All same
                return True
        
        return False
    
    def get_behavior_for_action(self, action_type: str) -> Dict[str, Any]:
        """Get behavior parameters for a specific action based on current personality.
        
        Args:
            action_type: Type of action (vote, comment, browse, etc.)
            
        Returns:
            Dictionary of behavior parameters for the action
        """
        personality = self.current_personality or self.select_personality()
        
        # Base behavior template
        behavior = {
            "click_speed": personality.click_speed,
            "scroll_pattern": personality.scroll_pattern,
            "engagement_chance": personality.engagement_rate,
            "comment_style": personality.comment_style
        }
        
        # Action-specific adjustments
        if action_type == "vote":
            # More deliberate clicking for votes
            behavior["click_speed"] = "slow"
            behavior["engagement_chance"] = personality.engagement_rate * 0.7
            
        elif action_type == "comment":
            # Thoughtful for comments
            behavior["click_speed"] = "normal"
            if personality.comment_style == "enthusiast":
                behavior["typing_speed"] = "fast"
            elif personality.comment_style == "skeptic":
                behavior["typing_speed"] = "slow"
            else:
                behavior["typing_speed"] = "normal"
        
        return behavior
    
    def save_history(self) -> bool:
        """Save switching history to file.
        
        Returns:
            True if save was successful, False otherwise
        """
        try:
            data = {
                "account": self.account_name,
                "personalities": {name: pers.config for name, pers in self.personalities.items()},
                "switch_history": self.switch_history,
                "last_updated": datetime.now().isoformat()
            }
            
            self.history_file.parent.mkdir(exist_ok=True, parents=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"Saved behavioral history for {self.account_name}")
            return True
            
        except (IOError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to save behavioral history for {self.account_name}: {e}")
            return False
    
    def load_history(self) -> bool:
        """Load switching history from file.
        
        Returns:
            True if load was successful, False otherwise
        """
        if not self.history_file.exists():
            self.logger.debug(f"No behavioral history found for {self.account_name}")
            return False
            
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.switch_history = data.get("switch_history", [])
            
            # Find last switch time
            if self.switch_history:
                last_entry = self.switch_history[-1]
                self.last_switch_time = datetime.fromisoformat(last_entry["timestamp"])
                self.current_personality = self.personalities.get(
                    last_entry.get("to"),
                    list(self.personalities.values())[0]
                )
                
            self.logger.debug(f"Loaded behavioral history for {self.account_name}")
            return True
            
        except (IOError, json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Failed to load behavioral history for {self.account_name}: {e}")
            return False
    
    def get_current_personality_name(self) -> str:
        """Get the name of the current personality.
        
        Returns:
            Name of current personality, or "unknown" if not set
        """
        return self.current_personality.name if self.current_personality else "unknown"
    
    def get_switch_statistics(self) -> Dict[str, Any]:
        """Get statistics about personality switches.
        
        Returns:
            Dictionary with switch statistics
        """
        if not self.switch_history:
            return {"total_switches": 0, "recent_switches": 0, "most_used": None}
        
        total_switches = len(self.switch_history)
        
        # Most used personality in last 10 switches
        recent_personalities = [entry.get("to") for entry in self.switch_history[-10:]]
        if recent_personalities:
            most_used = max(set(recent_personalities), key=recent_personalities.count)
        else:
            most_used = None
        
        return {
            "total_switches": total_switches,
            "recent_switches": len(recent_personalities),
            "most_used_personality": most_used,
            "current_personality": self.get_current_personality_name()
        }