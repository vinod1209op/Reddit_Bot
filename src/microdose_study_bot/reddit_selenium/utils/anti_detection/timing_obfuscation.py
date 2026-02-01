"""
Markov chain-based delays and vacation simulation for realistic timing patterns.
"""

import random
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np

# Fix: Add missing import
from microdose_study_bot.core.logging import UnifiedLogger

class MarkovDelayGenerator:
    """Generate non-patterned delays using Markov chains for realistic timing."""
    
    def __init__(self, account_name: str, config: Optional[Dict[str, Any]] = None):
        """Initialize the Markov delay generator.
        
        Args:
            account_name: Name of the account for state tracking
            config: Optional configuration dictionary
        """
        self.account_name = account_name
        self.logger = UnifiedLogger("MarkovDelayGenerator").get_logger()
        
        # Validate and load configuration
        self.config = config or {}
        self._validate_config()
        
        # Markov chain states
        self.states = ["short", "medium", "long"]
        
        # State transition matrix
        self.transition_matrix = self.config.get("transition_matrix", {
            "short": {"short": 0.4, "medium": 0.4, "long": 0.2},
            "medium": {"short": 0.3, "medium": 0.4, "long": 0.3},
            "long": {"short": 0.2, "medium": 0.3, "long": 0.5}
        })
        
        # Delay ranges for each state (in seconds)
        self.delay_ranges = self.config.get("delay_ranges", {
            "short": (1, 3),
            "medium": (4, 8),
            "long": (9, 15)
        })
        
        # Action-specific adjustments
        self.action_adjustments = self.config.get("action_adjustments", {
            "login": 1.5,
            "navigation": 1.5,
            "scroll": 0.8,
            "view": 0.8,
            "vote": 1.2,
            "comment": 1.3,
            "save": 1.1,
            "follow": 1.1,
            "browse": 0.9
        })
        
        # Current state
        self.current_state = "medium"
        self.state_history = []
        
        # Session patterns
        self.session_start_time = None
        self.delays_this_session = []
        
        # Timezone adjustment
        self.timezone_offset = 0
        self.hour_adjustments = {
            "night": (1.3, 1.7),      # 0-6: slower
            "morning": (0.9, 1.2),    # 6-9: medium
            "day": (0.8, 1.2),        # 9-18: faster
            "evening": (1.0, 1.4),    # 18-22: medium-slow
            "late_night": (1.4, 2.0)  # 22-0: slowest
        }
        
        # Load/save state
        self.state_file = Path(f"data/timing_state_{account_name}.json")
        self.load_state()
        
        self.logger.info(f"MarkovDelayGenerator initialized for {account_name}")
    
    def _validate_config(self) -> None:
        """Validate configuration parameters."""
        # Ensure transition matrix is valid
        if "transition_matrix" in self.config:
            for state, transitions in self.config["transition_matrix"].items():
                total = sum(transitions.values())
                if abs(total - 1.0) > 0.01:  # Allow small floating point errors
                    self.logger.warning(f"Transition probabilities for state {state} sum to {total}, normalizing")
                    # Normalize the probabilities
                    for next_state in transitions:
                        transitions[next_state] /= total
        
        # Ensure delay ranges are valid
        if "delay_ranges" in self.config:
            for state, (min_delay, max_delay) in self.config["delay_ranges"].items():
                if min_delay < 0 or max_delay < min_delay:
                    self.logger.error(f"Invalid delay range for state {state}: ({min_delay}, {max_delay})")
                    # Reset to defaults
                    self.config["delay_ranges"] = {
                        "short": (1, 3),
                        "medium": (4, 8),
                        "long": (9, 15)
                    }
                    break
    
    def get_next_delay(self, action_type: Optional[str] = None) -> float:
        """Get the next delay based on Markov chain and action type.
        
        Args:
            action_type: Type of action (login, navigation, scroll, etc.)
            
        Returns:
            Delay in seconds
        """
        # Transition to next state based on current state probabilities
        next_state_probs = self.transition_matrix[self.current_state]
        
        # Add slight randomness to transition probabilities
        randomized_probs = self._randomize_probabilities(next_state_probs)
        
        # Select next state
        next_state = random.choices(
            list(randomized_probs.keys()),
            weights=list(randomized_probs.values())
        )[0]
        
        # Get base delay for the state
        base_min, base_max = self.delay_ranges[next_state]
        
        # Apply time-of-day adjustment
        hour_adjustment = self._get_hour_adjustment()
        base_min *= hour_adjustment[0]
        base_max *= hour_adjustment[1]
        
        # Apply action-specific adjustment
        action_adjustment = self.action_adjustments.get(action_type, 1.0)
        
        # Calculate final delay with some randomness
        if action_type in ["login", "navigation"]:
            # More variable delays for significant actions
            base_delay = random.uniform(base_min * 1.2, base_max * 1.8)
        else:
            base_delay = random.uniform(base_min, base_max)
        
        final_delay = base_delay * action_adjustment
        
        # Ensure delay is within reasonable bounds
        final_delay = max(0.5, min(final_delay, 60.0))  # Between 0.5s and 60s
        
        # Record the transition
        self.state_history.append({
            "timestamp": datetime.now().isoformat(),
            "from": self.current_state,
            "to": next_state,
            "delay": final_delay,
            "action": action_type,
            "hour_adjustment": hour_adjustment,
            "action_adjustment": action_adjustment
        })
        
        # Update current state
        self.current_state = next_state
        
        # Keep only recent history (last 200 transitions)
        if len(self.state_history) > 200:
            self.state_history = self.state_history[-200:]
        
        # Record for session analysis
        if self.session_start_time:
            self.delays_this_session.append(final_delay)
        
        self.logger.debug(f"[{self.account_name}] Delay: {final_delay:.2f}s (state: {next_state}, action: {action_type})")
        return final_delay
    
    def _randomize_probabilities(self, probabilities: Dict[str, float]) -> Dict[str, float]:
        """Add small random variations to transition probabilities."""
        randomized = {}
        total = 0.0
        
        for state, prob in probabilities.items():
            # Add ±10% random variation
            variation = random.uniform(0.9, 1.1)
            randomized[state] = max(0.01, prob * variation)  # Ensure minimum probability
            total += randomized[state]
        
        # Normalize to sum to 1
        for state in randomized:
            randomized[state] /= total
        
        return randomized
    
    def _get_hour_adjustment(self) -> Tuple[float, float]:
        """Get time-of-day adjustment factors based on current hour."""
        hour = (datetime.utcnow().hour + self.timezone_offset) % 24
        
        if 0 <= hour < 6:
            return self.hour_adjustments["night"]
        elif 6 <= hour < 9:
            return self.hour_adjustments["morning"]
        elif 9 <= hour < 18:
            return self.hour_adjustments["day"]
        elif 18 <= hour < 22:
            return self.hour_adjustments["evening"]
        else:  # 22-24
            return self.hour_adjustments["late_night"]
    
    def analyze_patterns(self) -> Dict[str, Any]:
        """Analyze our timing patterns for potential detection.
        
        Returns:
            Dictionary with timing pattern analysis
        """
        if len(self.state_history) < 10:
            return {"status": "insufficient_data", "message": "Need at least 10 recorded delays"}
        
        try:
            # Calculate statistics from recent history
            recent_history = self.state_history[-50:]
            delays = [entry["delay"] for entry in recent_history]
            states = [entry["to"] for entry in recent_history]
            actions = [entry["action"] for entry in recent_history if entry["action"]]
            
            # Basic statistics
            mean_delay = np.mean(delays)
            median_delay = np.median(delays)
            std_delay = np.std(delays)
            cv_delay = std_delay / mean_delay if mean_delay > 0 else 0
            
            # State distribution
            state_counts = {state: states.count(state) for state in self.states}
            state_distribution = {state: count / len(states) for state, count in state_counts.items()}
            
            # Action distribution
            action_counts = {}
            for action in actions:
                action_counts[action] = action_counts.get(action, 0) + 1
            
            action_distribution = {action: count / len(actions) for action, count in action_counts.items()}
            
            # Pattern analysis
            pattern_score = self._calculate_pattern_score(recent_history)
            predictability_score = self._calculate_predictability_score()
            
            # Detect anomalies
            anomalies = self._detect_anomalies(delays, states)
            
            analysis = {
                "status": "analysis_complete",
                "statistics": {
                    "mean_delay_seconds": round(mean_delay, 2),
                    "median_delay_seconds": round(median_delay, 2),
                    "std_delay_seconds": round(std_delay, 2),
                    "coefficient_of_variation": round(cv_delay, 3),
                    "total_delays_analyzed": len(delays)
                },
                "state_distribution": {state: round(prob, 3) for state, prob in state_distribution.items()},
                "action_distribution": {action: round(prob, 3) for action, prob in action_distribution.items()},
                "pattern_scores": {
                    "pattern_score": round(pattern_score, 3),  # Lower is better
                    "predictability_score": round(predictability_score, 3),  # Lower is better
                    "overall_risk": "high" if pattern_score > 0.7 else "medium" if pattern_score > 0.5 else "low"
                },
                "anomalies": anomalies,
                "recommendations": self._generate_recommendations(pattern_score, cv_delay, state_distribution)
            }
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing patterns: {e}")
            return {"status": "error", "error": str(e)}
    
    def _calculate_pattern_score(self, recent_history: List[Dict]) -> float:
        """Calculate how patterned/regular our timing is (lower is better)."""
        if len(recent_history) < 5:
            return 1.0
        
        try:
            # Extract delays and state sequences
            delays = [entry["delay"] for entry in recent_history]
            states = [entry["to"] for entry in recent_history]
            
            # 1. Check for repeating state patterns
            state_pattern_variety = len(set(states)) / len(self.states)
            
            # 2. Check delay variance (coefficient of variation)
            mean_delay = np.mean(delays)
            std_delay = np.std(delays)
            delay_variance = std_delay / mean_delay if mean_delay > 0 else 0
            
            # 3. Check for autocorrelation in delays
            if len(delays) >= 10:
                # Simple autocorrelation at lag 1
                lag1_corr = np.corrcoef(delays[:-1], delays[1:])[0, 1] if not np.isnan(np.corrcoef(delays[:-1], delays[1:])[0, 1]) else 0
                autocorrelation_score = abs(lag1_corr)
            else:
                autocorrelation_score = 0.5
            
            # 4. Check state transition patterns
            transition_patterns = []
            for i in range(1, len(states)):
                transition_patterns.append(f"{states[i-1]}_{states[i]}")
            
            transition_variety = len(set(transition_patterns)) / (len(self.states) ** 2) if transition_patterns else 0.5
            
            # Combined score (0-1, lower is less patterned/more human-like)
            score = (
                (1 - state_pattern_variety) * 0.2 +
                (1 - min(delay_variance, 1)) * 0.3 +
                autocorrelation_score * 0.3 +
                (1 - transition_variety) * 0.2
            )
            
            return min(max(score, 0.0), 1.0)
            
        except Exception as e:
            self.logger.debug(f"Error calculating pattern score: {e}")
            return 0.5
    
    def _calculate_predictability_score(self) -> float:
        """Calculate how predictable the Markov chain behavior is."""
        try:
            # Analyze transition matrix for predictability
            predictability = 0.0
            for state, transitions in self.transition_matrix.items():
                max_prob = max(transitions.values())
                # Higher max probability = more predictable
                predictability += max_prob
            
            avg_predictability = predictability / len(self.states)
            return avg_predictability
            
        except Exception as e:
            self.logger.debug(f"Error calculating predictability score: {e}")
            return 0.5
    
    def _detect_anomalies(self, delays: List[float], states: List[str]) -> List[Dict]:
        """Detect anomalies in timing patterns."""
        anomalies = []
        
        try:
            # 1. Check for unusually long or short delays
            if delays:
                mean_delay = np.mean(delays)
                std_delay = np.std(delays)
                
                for i, delay in enumerate(delays[-10:]):  # Check last 10 delays
                    if std_delay > 0:
                        z_score = abs(delay - mean_delay) / std_delay
                        if z_score > 3.0:  # More than 3 standard deviations
                            anomalies.append({
                                "type": "extreme_delay",
                                "index": len(delays) - 10 + i,
                                "delay": round(delay, 2),
                                "z_score": round(z_score, 2),
                                "message": f"Delay of {delay:.2f}s is {z_score:.1f} standard deviations from mean"
                            })
            
            # 2. Check for state stagnation (same state too many times)
            if len(states) >= 10:
                recent_states = states[-10:]
                if len(set(recent_states)) == 1:  # All same state
                    anomalies.append({
                        "type": "state_stagnation",
                        "state": recent_states[0],
                        "count": 10,
                        "message": f"State '{recent_states[0]}' persisted for 10 consecutive delays"
                    })
            
            # 3. Check for pattern repetition
            if len(delays) >= 6:
                # Simple pattern detection: check if last 3 delays form a pattern
                pattern = delays[-6:-3]
                recent = delays[-3:]
                
                if len(pattern) == 3 and len(recent) == 3:
                    # Check if pattern repeats
                    pattern_diff = [pattern[i+1] - pattern[i] for i in range(2)]
                    recent_diff = [recent[i+1] - recent[i] for i in range(2)]
                    
                    if (abs(pattern_diff[0] - recent_diff[0]) < 0.5 and 
                        abs(pattern_diff[1] - recent_diff[1]) < 0.5):
                        anomalies.append({
                            "type": "pattern_repetition",
                            "pattern": [round(d, 2) for d in pattern],
                            "repetition": [round(d, 2) for d in recent],
                            "message": "Delay pattern repeated in last 6 actions"
                        })
            
        except Exception as e:
            self.logger.debug(f"Error detecting anomalies: {e}")
        
        return anomalies
    
    def _generate_recommendations(self, pattern_score: float, cv_delay: float, 
                                 state_distribution: Dict[str, float]) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        if pattern_score > 0.7:
            recommendations.append("High pattern detection risk - increase Markov chain randomness")
            recommendations.append("Consider adding more states to the Markov chain")
        
        if cv_delay < 0.3:
            recommendations.append("Delay variance too low - increase variation in delay ranges")
        
        if cv_delay > 1.5:
            recommendations.append("Delay variance too high - reduce extreme delay variations")
        
        # Check state distribution balance
        for state, prob in state_distribution.items():
            if prob > 0.6:
                recommendations.append(f"State '{state}' overused ({prob:.0%}) - adjust transition probabilities")
            elif prob < 0.1:
                recommendations.append(f"State '{state}' underused ({prob:.0%}) - increase transition probabilities")
        
        if not recommendations:
            recommendations.append("Timing patterns appear human-like - continue current strategy")
        
        return recommendations
    
    def adjust_for_timezone(self, timezone_offset: int) -> None:
        """Adjust timing patterns based on timezone offset from UTC.
        
        Args:
            timezone_offset: Timezone offset from UTC in hours
        """
        self.timezone_offset = timezone_offset
        self.logger.info(f"[{self.account_name}] Adjusted timing for timezone offset: {timezone_offset} hours")
    
    def set_custom_delay_ranges(self, delay_ranges: Dict[str, Tuple[float, float]]) -> None:
        """Set custom delay ranges for Markov states.
        
        Args:
            delay_ranges: Dictionary mapping state names to (min, max) delay ranges
        """
        for state, (min_delay, max_delay) in delay_ranges.items():
            if state in self.delay_ranges:
                if 0 <= min_delay <= max_delay:
                    self.delay_ranges[state] = (min_delay, max_delay)
                else:
                    self.logger.warning(f"Invalid delay range for state {state}: ({min_delay}, {max_delay})")
        
        self.logger.info(f"[{self.account_name}] Updated delay ranges: {self.delay_ranges}")
    
    def start_session(self) -> None:
        """Mark the start of a new session."""
        self.session_start_time = datetime.now()
        self.delays_this_session = []
        self.logger.debug(f"[{self.account_name}] Started new timing session")
    
    def end_session(self) -> None:
        """Mark the end of a session and save state."""
        if self.session_start_time:
            session_duration = (datetime.now() - self.session_start_time).total_seconds()
            self.logger.debug(f"[{self.account_name}] Session ended after {session_duration:.1f}s with {len(self.delays_this_session)} delays")
        
        self.save_state()
    
    def save_state(self) -> bool:
        """Save current Markov state to file.
        
        Returns:
            True if save was successful, False otherwise
        """
        try:
            data = {
                "account": self.account_name,
                "current_state": self.current_state,
                "state_history": self.state_history[-100:],  # Keep only recent
                "delays_this_session": self.delays_this_session,
                "timezone_offset": self.timezone_offset,
                "config": {
                    "delay_ranges": self.delay_ranges,
                    "transition_matrix": self.transition_matrix,
                    "action_adjustments": self.action_adjustments
                },
                "last_updated": datetime.now().isoformat()
            }
            
            self.state_file.parent.mkdir(exist_ok=True, parents=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            
            self.logger.debug(f"Saved timing state for {self.account_name}")
            return True
            
        except (IOError, TypeError) as e:
            self.logger.error(f"Failed to save timing state for {self.account_name}: {e}")
            return False
    
    def load_state(self) -> bool:
        """Load Markov state from file.
        
        Returns:
            True if load was successful, False otherwise
        """
        if not self.state_file.exists():
            self.logger.debug(f"No timing state found for {self.account_name}")
            return False
            
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.current_state = data.get("current_state", "medium")
            self.state_history = data.get("state_history", [])
            self.timezone_offset = data.get("timezone_offset", 0)
            
            # Load configuration if present
            config = data.get("config", {})
            if "delay_ranges" in config:
                self.delay_ranges = config["delay_ranges"]
            if "transition_matrix" in config:
                self.transition_matrix = config["transition_matrix"]
            if "action_adjustments" in config:
                self.action_adjustments = config["action_adjustments"]
            
            self.logger.info(f"Loaded timing state for {self.account_name}")
            return True
            
        except (json.JSONDecodeError, IOError, KeyError) as e:
            self.logger.warning(f"Failed to load timing state for {self.account_name}: {e}")
            return False


class VacationSimulator:
    """Simulate vacation periods (inactivity) for accounts to appear more human-like."""
    
    def __init__(self, account_name: str, config: Optional[Dict[str, Any]] = None):
        """Initialize the vacation simulator.
        
        Args:
            account_name: Name of the account
            config: Optional configuration dictionary
        """
        self.account_name = account_name
        self.logger = UnifiedLogger("VacationSimulator").get_logger()
        
        # Load configuration
        self.config = config or {}
        self._validate_config()
        
        # Vacation configuration
        self.vacation_probability = self.config.get("vacation_probability", 0.05)  # 5% chance
        self.min_days_between_vacations = self.config.get("min_days_between_vacations", 21)
        self.vacation_length_range = self.config.get("vacation_length_range", (2, 7))  # days
        self.vacation_types = self.config.get("vacation_types", {
            "weekend_trip": {"probability": 0.4, "length_range": (2, 3)},
            "business_trip": {"probability": 0.2, "length_range": (3, 5)},
            "family_visit": {"probability": 0.25, "length_range": (4, 7)},
            "holiday": {"probability": 0.15, "length_range": (5, 10)}
        })
        
        # Current state
        self.on_vacation = False
        self.vacation_type = None
        self.vacation_start = None
        self.vacation_end = None
        self.last_vacation_end = None
        self.next_vacation_check = None
        
        # Vacation history
        self.vacation_history = []
        
        # Timezone consistency
        self.account_timezone = "America/Los_Angeles"
        
        # Load/save state
        self.vacation_file = Path(f"data/vacation_state_{account_name}.json")
        self.load_state()
        
        self.logger.info(f"VacationSimulator initialized for {account_name}")
    
    def _validate_config(self) -> None:
        """Validate vacation configuration."""
        if "vacation_probability" in self.config:
            prob = self.config["vacation_probability"]
            if not 0 <= prob <= 1:
                self.logger.warning(f"Invalid vacation probability: {prob}, using default 0.05")
                self.config["vacation_probability"] = 0.05
        
        if "vacation_length_range" in self.config:
            min_len, max_len = self.config["vacation_length_range"]
            if min_len < 1 or max_len < min_len:
                self.logger.warning(f"Invalid vacation length range: ({min_len}, {max_len}), using default (2, 7)")
                self.config["vacation_length_range"] = (2, 7)
    
    def check_vacation(self) -> bool:
        """Check if account should be on vacation and update state.
        
        Returns:
            True if account is currently on vacation, False otherwise
        """
        now = datetime.now()
        
        # If currently on vacation, check if it's over
        if self.on_vacation and self.vacation_end:
            if now >= self.vacation_end:
                self._end_vacation()
                return False
            return True
        
        # Not on vacation, check if we should start one
        if self._should_start_vacation(now):
            self._start_vacation(now)
            return True
        
        return False
    
    def _should_start_vacation(self, now: datetime) -> bool:
        """Determine if we should start a vacation.
        
        Args:
            now: Current datetime
            
        Returns:
            True if vacation should start, False otherwise
        """
        # Check if we're already scheduled for a vacation check
        if self.next_vacation_check and now < self.next_vacation_check:
            return False
        
        # Check minimum days since last vacation
        if self.last_vacation_end:
            days_since_last = (now - self.last_vacation_end).days
            if days_since_last < self.min_days_between_vacations:
                # Schedule next check after minimum interval
                next_check_days = self.min_days_between_vacations - days_since_last
                self.next_vacation_check = now + timedelta(days=next_check_days)
                return False
        
        # Random chance based on probability
        if random.random() < self.vacation_probability:
            return True
        
        # After extended activity, increase probability
        if self.last_vacation_end:
            days_active = (now - self.last_vacation_end).days
            if days_active >= 30:
                # Linearly increase probability after 30 days
                extra_days = days_active - 30
                increased_prob = min(0.5, self.vacation_probability * (1 + extra_days / 30))
                
                if random.random() < increased_prob:
                    self.logger.info(f"[{self.account_name}] Forcing vacation after {days_active} days of continuous activity")
                    return True
        
        # Schedule next check in 3-7 days
        next_check_days = random.randint(3, 7)
        self.next_vacation_check = now + timedelta(days=next_check_days)
        
        return False
    
    def _start_vacation(self, start_time: datetime) -> None:
        """Start a vacation period.
        
        Args:
            start_time: When the vacation starts
        """
        # Select vacation type
        vacation_type = self._select_vacation_type()
        length_range = self.vacation_types[vacation_type]["length_range"]
        
        # Determine vacation length
        if vacation_type == "weekend_trip":
            # Start on Friday, end on Sunday/Monday
            vacation_days = random.randint(*length_range)
            # Adjust to start on a Friday (5)
            start_time = self._adjust_to_weekday(start_time, 5)
        elif vacation_type == "business_trip":
            # Typically Monday-Friday
            vacation_days = random.randint(*length_range)
            start_time = self._adjust_to_weekday(start_time, 1)  # Monday
        else:
            vacation_days = random.randint(*length_range)
        
        self.vacation_type = vacation_type
        self.vacation_start = start_time
        self.vacation_end = start_time + timedelta(days=vacation_days)
        self.on_vacation = True
        
        self.logger.info(f"[{self.account_name}] Starting {vacation_type} vacation for {vacation_days} days")
        
        # Record in history
        self.vacation_history.append({
            "start": start_time.isoformat(),
            "end": self.vacation_end.isoformat(),
            "days": vacation_days,
            "type": vacation_type,
            "reason": "scheduled"
        })
        
        self.save_state()
    
    def _select_vacation_type(self) -> str:
        """Select a vacation type based on probabilities."""
        types = list(self.vacation_types.keys())
        probabilities = [self.vacation_types[t]["probability"] for t in types]
        
        # Normalize probabilities
        total = sum(probabilities)
        normalized = [p / total for p in probabilities]
        
        return random.choices(types, weights=normalized)[0]
    
    def _adjust_to_weekday(self, date: datetime, target_weekday: int) -> datetime:
        """Adjust a date to the nearest target weekday (0=Monday, 6=Sunday)."""
        current_weekday = date.weekday()
        days_diff = (target_weekday - current_weekday) % 7
        
        # Don't adjust more than 3 days
        if days_diff > 3:
            days_diff -= 7
        
        return date + timedelta(days=days_diff)
    
    def _end_vacation(self) -> None:
        """End the current vacation."""
        self.on_vacation = False
        self.last_vacation_end = datetime.now()
        self.vacation_start = None
        self.vacation_end = None
        self.vacation_type = None
        
        # Schedule next check in 1-2 weeks
        next_check_days = random.randint(7, 14)
        self.next_vacation_check = datetime.now() + timedelta(days=next_check_days)
        
        self.logger.info(f"[{self.account_name}] Vacation ended")
        self.save_state()
    
    def get_vacation_status(self) -> Dict[str, Any]:
        """Get current vacation status.
        
        Returns:
            Dictionary with vacation status information
        """
        if not self.on_vacation:
            return {
                "on_vacation": False,
                "last_vacation": self.vacation_history[-1] if self.vacation_history else None,
                "days_since_last": (datetime.now() - self.last_vacation_end).days if self.last_vacation_end else None,
                "next_check": self.next_vacation_check.isoformat() if self.next_vacation_check else None
            }
        
        remaining = (self.vacation_end - datetime.now()).total_seconds()
        return {
            "on_vacation": True,
            "type": self.vacation_type,
            "started": self.vacation_start.isoformat(),
            "ends": self.vacation_end.isoformat(),
            "remaining_hours": round(remaining / 3600, 1),
            "remaining_days": round(remaining / 86400, 1),
            "progress": round((datetime.now() - self.vacation_start).total_seconds() / 
                             (self.vacation_end - self.vacation_start).total_seconds() * 100, 1)
        }
    
    def simulate_timezone_consistency(self, account_timezone: str) -> Dict[str, Any]:
        """Ensure vacation periods align with account's timezone patterns.
        
        Args:
            account_timezone: IANA timezone string
            
        Returns:
            Dictionary with timezone consistency analysis
        """
        self.account_timezone = account_timezone
        
        # Timezone offsets (simplified)
        timezone_offsets = {
            "America/Los_Angeles": -8,
            "America/New_York": -5,
            "UTC": 0,
            "Europe/London": 0,
            "Europe/Berlin": 1,
            "Asia/Tokyo": 9,
            "Australia/Sydney": 11
        }
        
        offset = timezone_offsets.get(account_timezone, 0)
        hour = (datetime.utcnow().hour + offset) % 24
        
        # Activity patterns based on local time
        if 9 <= hour <= 17:  # Work hours
            active_likelihood = "high"
            typical_activity = "browsing, commenting"
        elif 18 <= hour <= 22:  # Evening
            active_likelihood = "medium"
            typical_activity = "casual browsing, voting"
        elif 23 <= hour or hour <= 8:  # Night
            active_likelihood = "low"
            typical_activity = "minimal or none"
        else:
            active_likelihood = "medium"
            typical_activity = "varied"
        
        # Check if current activity matches timezone
        current_hour_ok = 9 <= hour <= 22  # Reasonable activity hours
        
        return {
            "timezone": account_timezone,
            "local_hour": hour,
            "utc_offset": offset,
            "active_likelihood": active_likelihood,
            "typical_activity": typical_activity,
            "current_hour_appropriate": current_hour_ok,
            "recommendation": "Reduce activity" if hour < 6 or hour > 23 else "Normal activity"
        }
    
    def get_vacation_statistics(self) -> Dict[str, Any]:
        """Get statistics about vacation patterns.
        
        Returns:
            Dictionary with vacation statistics
        """
        if not self.vacation_history:
            return {"total_vacations": 0, "average_length": 0, "most_common_type": None}
        
        total_vacations = len(self.vacation_history)
        total_days = sum(v["days"] for v in self.vacation_history)
        average_length = total_days / total_vacations
        
        # Type distribution
        type_counts = {}
        for vacation in self.vacation_history:
            v_type = vacation.get("type", "unknown")
            type_counts[v_type] = type_counts.get(v_type, 0) + 1
        
        most_common_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None
        
        # Recent vacations (last 6 months)
        six_months_ago = datetime.now() - timedelta(days=180)
        recent_vacations = [v for v in self.vacation_history 
                           if datetime.fromisoformat(v["start"]) >= six_months_ago]
        
        return {
            "total_vacations": total_vacations,
            "recent_vacations": len(recent_vacations),
            "average_length_days": round(average_length, 1),
            "most_common_type": most_common_type,
            "type_distribution": type_counts,
            "days_since_last": (datetime.now() - self.last_vacation_end).days if self.last_vacation_end else None,
            "currently_on_vacation": self.on_vacation
        }
    
    def schedule_vacation(self, start_date: datetime, length_days: int, 
                         vacation_type: str = "planned") -> bool:
        """Manually schedule a vacation.
        
        Args:
            start_date: When the vacation should start
            length_days: Length of vacation in days
            vacation_type: Type of vacation
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        if self.on_vacation:
            self.logger.warning(f"[{self.account_name}] Cannot schedule vacation while already on vacation")
            return False
        
        if start_date < datetime.now():
            self.logger.warning(f"[{self.account_name}] Cannot schedule vacation in the past")
            return False
        
        self.vacation_type = vacation_type
        self.vacation_start = start_date
        self.vacation_end = start_date + timedelta(days=length_days)
        self.on_vacation = True
        
        self.vacation_history.append({
            "start": start_date.isoformat(),
            "end": self.vacation_end.isoformat(),
            "days": length_days,
            "type": vacation_type,
            "reason": "manual"
        })
        
        self.logger.info(f"[{self.account_name}] Manually scheduled {vacation_type} vacation for {length_days} days starting {start_date}")
        self.save_state()
        return True
    
    def save_state(self) -> bool:
        """Save vacation state to file.
        
        Returns:
            True if save was successful, False otherwise
        """
        try:
            data = {
                "account": self.account_name,
                "on_vacation": self.on_vacation,
                "vacation_type": self.vacation_type,
                "vacation_start": self.vacation_start.isoformat() if self.vacation_start else None,
                "vacation_end": self.vacation_end.isoformat() if self.vacation_end else None,
                "last_vacation_end": self.last_vacation_end.isoformat() if self.last_vacation_end else None,
                "next_vacation_check": self.next_vacation_check.isoformat() if self.next_vacation_check else None,
                "account_timezone": self.account_timezone,
                "vacation_history": self.vacation_history[-20:],  # Keep recent
                "config": self.config,
                "last_updated": datetime.now().isoformat()
            }
            
            self.vacation_file.parent.mkdir(exist_ok=True, parents=True)
            with open(self.vacation_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            
            self.logger.debug(f"Saved vacation state for {self.account_name}")
            return True
            
        except (IOError, TypeError) as e:
            self.logger.error(f"Failed to save vacation state for {self.account_name}: {e}")
            return False
    
    def load_state(self) -> bool:
        """Load vacation state from file.
        
        Returns:
            True if load was successful, False otherwise
        """
        if not self.vacation_file.exists():
            self.logger.debug(f"No vacation state found for {self.account_name}")
            return False
            
        try:
            with open(self.vacation_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.on_vacation = data.get("on_vacation", False)
            self.vacation_type = data.get("vacation_type")
            
            if data.get("vacation_start"):
                self.vacation_start = datetime.fromisoformat(data["vacation_start"])
            if data.get("vacation_end"):
                self.vacation_end = datetime.fromisoformat(data["vacation_end"])
            if data.get("last_vacation_end"):
                self.last_vacation_end = datetime.fromisoformat(data["last_vacation_end"])
            if data.get("next_vacation_check"):
                self.next_vacation_check = datetime.fromisoformat(data["next_vacation_check"])
            
            self.account_timezone = data.get("account_timezone", "America/Los_Angeles")
            self.vacation_history = data.get("vacation_history", [])
            
            # Load configuration if present
            if "config" in data:
                self.config.update(data["config"])
            
            self.logger.info(f"Loaded vacation state for {self.account_name}")
            return True
            
        except (json.JSONDecodeError, IOError, KeyError, ValueError) as e:
            self.logger.warning(f"Failed to load vacation state for {self.account_name}: {e}")
            return False