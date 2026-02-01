"""
Main coordinator for all anti-detection measures with real-time pattern feedback,
adaptive security levels, and graceful degradation.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple
import numpy as np

# Fixed imports
from microdose_study_bot.core.logging import UnifiedLogger
from .behavioral_diversity import PersonalitySwitcher
from .timing_obfuscation import MarkovDelayGenerator, VacationSimulator
from .pattern_analyzer import PatternAnalyzer

class DetectionEvasionCoordinator:
    """Coordinates all anti-detection measures for an account with real-time adaptation."""
    
    def __init__(self, account_name: str, account_config: Dict, activity_config: Dict):
        self.account_name = account_name
        self.account_config = account_config
        self.activity_config = activity_config
        
        # Initialize logger
        self.logger = UnifiedLogger("DetectionEvasionCoordinator").get_logger()
        
        # Load anti-detection config with validation
        self.security_config = self._load_security_config(activity_config)
        
        # Adaptive security levels (auto-adjust based on risk)
        self.security_levels = {
            "conservative": {"switch_probability": 0.10, "min_delay_multiplier": 1.3, "pattern_check_frequency": 0.5},
            "balanced": {"switch_probability": 0.15, "min_delay_multiplier": 1.0, "pattern_check_frequency": 0.3},
            "aggressive": {"switch_probability": 0.20, "min_delay_multiplier": 0.7, "pattern_check_frequency": 0.1}
        }
        self.current_security_level = "balanced"
        
        # Initialize components with error handling
        self.personality_switcher = None
        self.markov_delays = None
        self.vacation_simulator = None
        self.pattern_analyzer = None
        
        self._initialize_components()
        
        # Session state with enhanced tracking
        self.current_session_id = None
        self.session_start_time = None
        self.session_data = {
            "action_sequence": [],
            "action_timestamps": [],
            "click_speeds": [],
            "scroll_distances": [],
            "action_types": [],
            "behavior_parameters": []  # Store personality behavior for each action
        }
        
        # Real-time risk monitoring
        self.real_time_risks = []
        self.risk_thresholds = {
            "critical": 0.8,
            "high": 0.6,
            "medium": 0.4,
            "low": 0.2
        }
        
        # Adaptive behavior tracking
        self.adaptations_applied = []
        self.consecutive_high_risk_sessions = 0
        
        # State persistence
        self.state_file = Path(f"data/evasion_state_{account_name}.json")
        self.load_state()
        
        self.logger.info(f"DetectionEvasionCoordinator initialized for {account_name} with security level: {self.current_security_level}")
    
    def _load_security_config(self, activity_config: Dict) -> Dict[str, Any]:
        """Load and validate security configuration."""
        security_config = activity_config.get("security_evolution", {})
        
        # Load from dedicated security config file if specified
        config_path = security_config.get("config_path")
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                # Merge with activity config (file config takes precedence)
                security_config.update(file_config)
                self.logger.info(f"Loaded security config from {config_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load security config from {config_path}: {e}")
        
        # Set defaults for missing values
        defaults = {
            "behavioral_diversity": {"enabled": True, "switch_probability": 0.15},
            "timing_obfuscation": {"enabled": True},
            "pattern_analysis": {"enabled": True, "risk_thresholds": {}},
            "adaptive_security": {"enabled": True, "auto_adjust": True}
        }
        
        for key, default in defaults.items():
            if key not in security_config:
                security_config[key] = default
        
        return security_config
    
    def _initialize_components(self):
        """Initialize all anti-detection components with graceful degradation."""
        try:
            # Behavioral Diversity
            behavioral_config = self.security_config.get("behavioral_diversity", {})
            if behavioral_config.get("enabled", True):
                try:
                    personality_config_path = None
                    if "personality_configs" in behavioral_config:
                        # Save personality configs to temporary file if provided inline
                        temp_path = Path(f"data/temp_personality_{self.account_name}.json")
                        with open(temp_path, 'w', encoding='utf-8') as f:
                            json.dump(behavioral_config.get("personality_configs"), f)
                        personality_config_path = temp_path
                    
                    self.personality_switcher = PersonalitySwitcher(
                        account_name=self.account_name,
                        config_path=personality_config_path
                    )
                    self.logger.info(f"Behavioral diversity enabled for {self.account_name}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize personality switcher: {e}")
                    self.personality_switcher = None
            
            # Timing Obfuscation
            timing_config = self.security_config.get("timing_obfuscation", {})
            if timing_config.get("enabled", True):
                try:
                    self.markov_delays = MarkovDelayGenerator(
                        account_name=self.account_name,
                        config=timing_config
                    )
                    self.logger.info(f"Markov delays enabled for {self.account_name}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize Markov delays: {e}")
                    self.markov_delays = None
                
                # Vacation Simulator
                vacation_config = timing_config.get("vacation_simulation", {})
                if vacation_config.get("enabled", True):
                    try:
                        self.vacation_simulator = VacationSimulator(
                            account_name=self.account_name,
                            config=vacation_config
                        )
                        self.logger.info(f"Vacation simulation enabled for {self.account_name}")
                    except Exception as e:
                        self.logger.error(f"Failed to initialize vacation simulator: {e}")
                        self.vacation_simulator = None
            
            # Pattern Analyzer (always enabled for monitoring)
            try:
                self.pattern_analyzer = PatternAnalyzer(
                    account_name=self.account_name,
                    config_path=self.security_config.get("pattern_analysis", {}).get("config_path")
                )
                self.logger.info(f"Pattern analyzer enabled for {self.account_name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize pattern analyzer: {e}")
                # Create a minimal pattern analyzer if main one fails
                self.pattern_analyzer = None
            
            # Check if we have at least one working component
            working_components = [
                self.personality_switcher,
                self.markov_delays,
                self.vacation_simulator,
                self.pattern_analyzer
            ]
            working_count = sum(1 for comp in working_components if comp is not None)
            
            if working_count == 0:
                self.logger.warning("No anti-detection components initialized - using fallback mode")
            else:
                self.logger.info(f"Initialized {working_count}/4 anti-detection components")
                
        except Exception as e:
            self.logger.error(f"Critical error initializing anti-detection components: {e}")
            # Set all to None to prevent further errors
            self.personality_switcher = None
            self.markov_delays = None
            self.vacation_simulator = None
            self.pattern_analyzer = None
    
    def start_session(self) -> bool:
        """Start a new session with anti-detection measures and real-time monitoring."""
        try:
            # Check if account is on vacation
            if self.vacation_simulator and self.vacation_simulator.check_vacation():
                vacation_status = self.vacation_simulator.get_vacation_status()
                self.logger.info(f"[{self.account_name}] Account on vacation: {vacation_status}")
                return False
            
            # Generate session ID
            self.current_session_id = f"{self.account_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.session_start_time = datetime.now()
            
            # Apply adaptive security level adjustments
            self._apply_security_level_adjustments()
            
            # Select personality for this session (force switch if high risk)
            force_switch = self.consecutive_high_risk_sessions >= 2
            if self.personality_switcher:
                try:
                    personality = self.personality_switcher.select_personality(force_switch=force_switch)
                    if force_switch:
                        self.logger.warning(f"[{self.account_name}] Forcing personality switch due to {self.consecutive_high_risk_sessions} high risk sessions")
                    self.logger.info(f"[{self.account_name}] Using personality: {personality.name}")
                except Exception as e:
                    self.logger.error(f"Failed to select personality: {e}")
            
            # Start Markov timing with timezone adjustment
            if self.markov_delays:
                try:
                    self.markov_delays.start_session()
                    
                    # Adjust for timezone
                    timezone = self.account_config.get("timezone", "America/Los_Angeles")
                    offset = self._get_timezone_offset(timezone)
                    self.markov_delays.adjust_for_timezone(offset)
                    self.logger.debug(f"[{self.account_name}] Adjusted timing for timezone {timezone} (UTC{offset:+d})")
                except Exception as e:
                    self.logger.error(f"Failed to start Markov timing: {e}")
            
            # Reset session data with enhanced tracking
            self.session_data = {
                "session_id": self.current_session_id,
                "start_time": datetime.now().isoformat(),
                "action_sequence": [],
                "action_timestamps": [],
                "click_speeds": [],
                "scroll_distances": [],
                "action_types": [],
                "behavior_parameters": [],
                "delays_used": [],
                "real_time_risks": [],
                "security_level": self.current_security_level
            }
            
            # Clear real-time risks for new session
            self.real_time_risks = []
            
            self.logger.info(f"[{self.account_name}] Started session with anti-detection measures (Security: {self.current_security_level})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start session: {e}")
            return False
    
    def get_session_delay(self, action_type: str = None) -> float:
        """Get appropriate delay for current action with real-time adjustments."""
        try:
            base_delay = None
            
            if self.markov_delays:
                base_delay = self.markov_delays.get_next_delay(action_type)
            else:
                # Fallback to existing delay logic
                base_delay = random.uniform(2, 5)
            
            # Apply security level multiplier
            security_multiplier = self.security_levels[self.current_security_level]["min_delay_multiplier"]
            adjusted_delay = base_delay * security_multiplier
            
            # Add random jitter (±15%)
            jitter = random.uniform(0.85, 1.15)
            final_delay = adjusted_delay * jitter
            
            # Ensure minimum delay
            final_delay = max(0.5, final_delay)
            
            # Record delay for pattern analysis
            if self.current_session_id:
                self.session_data["delays_used"].append(final_delay)
            
            return final_delay
            
        except Exception as e:
            self.logger.error(f"Error getting session delay: {e}")
            # Fallback delay
            return random.uniform(2, 5)
    
    def get_behavior_for_action(self, action_type: str) -> Dict[str, Any]:
        """Get behavior parameters for an action based on current personality with risk adjustments."""
        try:
            behavior = {}
            
            if self.personality_switcher:
                behavior = self.personality_switcher.get_behavior_for_action(action_type)
                
                # Apply risk-based adjustments
                if self.real_time_risks:
                    latest_risk = self.real_time_risks[-1] if self.real_time_risks else None
                    if latest_risk and latest_risk.get("level") in ["high", "critical"]:
                        # Reduce engagement for high risk
                        if "engagement_chance" in behavior:
                            behavior["engagement_chance"] *= 0.5
                        # Slow down clicks
                        behavior["click_speed"] = "slow"
            else:
                # Default behavior
                behavior = {
                    "click_speed": "normal",
                    "scroll_pattern": "smooth",
                    "engagement_chance": 0.3,
                    "typing_speed": "normal"
                }
            
            # Add security level information
            behavior["security_level"] = self.current_security_level
            behavior["risk_adjusted"] = len(self.real_time_risks) > 0
            
            return behavior
            
        except Exception as e:
            self.logger.error(f"Error getting behavior for action: {e}")
            return {
                "click_speed": "normal",
                "scroll_pattern": "smooth",
                "engagement_chance": 0.3,
                "error": str(e)
            }
    
    def record_action(self, action_type: str, details: Dict = None) -> Optional[Dict[str, Any]]:
        """Record an action for pattern analysis with real-time risk assessment."""
        if not self.current_session_id:
            self.logger.warning("Cannot record action - no active session")
            return None
        
        try:
            # Record basic action data
            timestamp = datetime.now().isoformat()
            self.session_data["action_sequence"].append(action_type)
            self.session_data["action_timestamps"].append(timestamp)
            self.session_data["action_types"].append(action_type)
            
            # Record detailed metrics if provided
            if details:
                if "click_speed" in details:
                    # Convert click speed to numeric for analysis
                    speed_map = {"slow": 0.3, "normal": 0.6, "fast": 0.9}
                    numeric_speed = speed_map.get(details["click_speed"], 0.6)
                    self.session_data["click_speeds"].append(numeric_speed)
                
                if "scroll_distance" in details:
                    self.session_data["scroll_distances"].append(details["scroll_distance"])
                
                # Store behavior parameters
                self.session_data["behavior_parameters"].append({
                    "action_type": action_type,
                    "timestamp": timestamp,
                    "details": details
                })
            
            # Perform real-time pattern check (throttled)
            should_check = random.random() < self.security_levels[self.current_security_level]["pattern_check_frequency"]
            if should_check and self.pattern_analyzer and len(self.session_data["action_sequence"]) >= 3:
                mini_analysis = self._perform_real_time_analysis()
                if mini_analysis:
                    self.real_time_risks.append(mini_analysis)
                    
                    # Apply immediate mitigations for high risk
                    if mini_analysis.get("risk_level") in ["high", "critical"]:
                        self._apply_immediate_mitigation(mini_analysis)
                    
                    return mini_analysis
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error recording action: {e}")
            return None
    
    def _perform_real_time_analysis(self) -> Optional[Dict[str, Any]]:
        """Perform lightweight real-time pattern analysis."""
        try:
            if len(self.session_data["action_sequence"]) < 3:
                return None
            
            # Analyze action repetition
            recent_actions = self.session_data["action_sequence"][-10:] if len(self.session_data["action_sequence"]) >= 10 else self.session_data["action_sequence"]
            unique_actions = len(set(recent_actions))
            repetition_score = 1 - (unique_actions / len(recent_actions))
            
            # Analyze timing patterns if available
            timing_score = 0.5
            if len(self.session_data["action_timestamps"]) >= 3:
                try:
                    timestamps = self.session_data["action_timestamps"][-5:]
                    deltas = []
                    for i in range(1, len(timestamps)):
                        t1 = datetime.fromisoformat(timestamps[i-1])
                        t2 = datetime.fromisoformat(timestamps[i])
                        delta = (t2 - t1).total_seconds()
                        deltas.append(delta)
                    
                    if len(deltas) >= 2:
                        mean_delta = np.mean(deltas)
                        std_delta = np.std(deltas) if len(deltas) > 1 else 0
                        cv = std_delta / mean_delta if mean_delta > 0 else 0
                        timing_score = min(cv, 1.0) if cv > 0 else 0.1
                except:
                    timing_score = 0.5
            
            # Calculate composite risk score
            risk_score = (repetition_score * 0.6) + (timing_score * 0.4)
            
            # Determine risk level
            risk_level = "low"
            if risk_score > self.risk_thresholds["critical"]:
                risk_level = "critical"
            elif risk_score > self.risk_thresholds["high"]:
                risk_level = "high"
            elif risk_score > self.risk_thresholds["medium"]:
                risk_level = "medium"
            
            # Generate suggestions
            suggestions = []
            if repetition_score > 0.6:
                suggestions.append("Vary action types more frequently")
            if timing_score < 0.3:
                suggestions.append("Increase timing randomness")
            
            analysis = {
                "timestamp": datetime.now().isoformat(),
                "risk_score": round(risk_score, 3),
                "risk_level": risk_level,
                "repetition_score": round(repetition_score, 3),
                "timing_score": round(timing_score, 3),
                "suggestions": suggestions,
                "actions_analyzed": len(recent_actions)
            }
            
            # Log if high risk
            if risk_level in ["high", "critical"]:
                self.logger.warning(f"[{self.account_name}] Real-time risk detected: {risk_level} (score: {risk_score:.3f})")
            
            return analysis
            
        except Exception as e:
            self.logger.debug(f"Real-time analysis failed: {e}")
            return None
    
    def _apply_immediate_mitigation(self, analysis: Dict[str, Any]):
        """Apply immediate mitigation for high-risk patterns."""
        try:
            risk_level = analysis.get("risk_level")
            suggestions = analysis.get("suggestions", [])
            
            self.logger.info(f"[{self.account_name}] Applying immediate mitigation for {risk_level} risk")
            
            # Force personality switch
            if self.personality_switcher and "Vary action types" in " ".join(suggestions):
                old_personality = self.personality_switcher.get_current_personality_name()
                self.personality_switcher.select_personality(force_switch=True)
                new_personality = self.personality_switcher.get_current_personality_name()
                self.logger.info(f"  -> Switched personality: {old_personality} → {new_personality}")
            
            # Increase delays
            if self.markov_delays and "Increase timing randomness" in " ".join(suggestions):
                # Increase delay ranges by 50%
                current_ranges = getattr(self.markov_delays, 'delay_ranges', {
                    "short": (1, 3),
                    "medium": (4, 8),
                    "long": (9, 15)
                })
                increased_ranges = {
                    state: (min_d * 1.5, max_d * 1.5)
                    for state, (min_d, max_d) in current_ranges.items()
                }
                self.markov_delays.set_custom_delay_ranges(increased_ranges)
                self.logger.info(f"  -> Increased delay ranges by 50%")
            
            # Record adaptation
            self.adaptations_applied.append({
                "timestamp": datetime.now().isoformat(),
                "risk_level": risk_level,
                "suggestions": suggestions,
                "action": "immediate_mitigation"
            })
            
        except Exception as e:
            self.logger.error(f"Failed to apply immediate mitigation: {e}")
    
    def _apply_security_level_adjustments(self):
        """Adjust security level based on recent risk history."""
        adaptive_enabled = self.security_config.get("adaptive_security", {}).get("auto_adjust", True)
        if not adaptive_enabled:
            return
        
        # Check pattern history for recent risks
        if self.pattern_analyzer:
            try:
                stats = self.pattern_analyzer.get_statistics()
                risk_distribution = stats.get("risk_distribution", {})
                
                # Calculate recent high/critical risk percentage
                recent_total = sum(risk_distribution.values())
                high_risk_count = risk_distribution.get("high", 0) + risk_distribution.get("critical", 0)
                
                if recent_total > 0:
                    high_risk_percentage = high_risk_count / recent_total
                    
                    # Adjust security level
                    if high_risk_percentage > 0.5:  # >50% high risk
                        new_level = "conservative"
                    elif high_risk_percentage > 0.2:  # >20% high risk
                        new_level = "balanced"
                    else:
                        new_level = "aggressive"
                    
                    if new_level != self.current_security_level:
                        old_level = self.current_security_level
                        self.current_security_level = new_level
                        self.logger.info(f"[{self.account_name}] Security level adjusted: {old_level} → {new_level} (high risk: {high_risk_percentage:.1%})")
            except Exception as e:
                self.logger.debug(f"Failed to adjust security level: {e}")
    
    def end_session(self, success: bool = True) -> Optional[Dict[str, Any]]:
        """End the current session, analyze patterns, and save state."""
        if not self.current_session_id:
            self.logger.warning("Cannot end session - no active session")
            return None
        
        try:
            # Calculate session duration
            if self.session_start_time:
                duration = (datetime.now() - self.session_start_time).total_seconds() / 60  # in minutes
                self.session_data["session_duration"] = round(duration, 2)
            
            self.session_data["success"] = success
            self.session_data["end_time"] = datetime.now().isoformat()
            self.session_data["real_time_risks"] = self.real_time_risks
            self.session_data["adaptations_applied"] = self.adaptations_applied
            
            # Analyze session patterns if analyzer is available
            analysis = None
            if self.pattern_analyzer:
                analysis = self.pattern_analyzer.analyze_session(self.session_data)
                
                # Log analysis results
                risk_level = analysis.get("overall_risk", "unknown")
                risk_score = analysis.get("scores", {}).get("overall", 0.5)
                
                self.logger.info(f"[{self.account_name}] Session analysis: {risk_level.upper()} risk (score: {risk_score:.3f})")
                
                # Update consecutive high risk counter
                if risk_level in ["high", "critical"]:
                    self.consecutive_high_risk_sessions += 1
                    self.logger.warning(f"[{self.account_name}] {self.consecutive_high_risk_sessions} consecutive high risk sessions")
                    
                    # Log detailed risks
                    for risk in analysis.get("risks", []):
                        self.logger.warning(f"  Risk: {risk}")
                    
                    # Log suggestions
                    for suggestion in analysis.get("suggestions", []):
                        self.logger.info(f"  Suggestion: {suggestion}")
                    
                    # Auto-apply suggestions for critical risk
                    if risk_level == "critical" and self.security_config.get("pattern_analysis", {}).get("auto_mitigate", True):
                        self._auto_apply_suggestions(analysis)
                else:
                    self.consecutive_high_risk_sessions = 0
            else:
                self.logger.info(f"[{self.account_name}] Session completed (no pattern analysis available)")
            
            # End timing session
            if self.markov_delays:
                try:
                    self.markov_delays.end_session()
                except Exception as e:
                    self.logger.error(f"Failed to end Markov session: {e}")
            
            # Save personality state
            if self.personality_switcher:
                try:
                    self.personality_switcher.save_history()
                except Exception as e:
                    self.logger.error(f"Failed to save personality history: {e}")
            
            # Save coordinator state
            self.save_state()
            
            # Reset for next session (but keep session data for reporting)
            session_id = self.current_session_id
            session_data_copy = self.session_data.copy()
            
            self.current_session_id = None
            self.session_start_time = None
            self.real_time_risks = []
            self.adaptations_applied = []
            
            # Return enriched analysis
            if analysis:
                enriched_analysis = {
                    **analysis,
                    "session_id": session_id,
                    "security_level": self.current_security_level,
                    "consecutive_high_risk": self.consecutive_high_risk_sessions,
                    "adaptations_applied": len(self.adaptations_applied)
                }
                return enriched_analysis
            
            return {
                "session_id": session_id,
                "duration": session_data_copy.get("session_duration"),
                "actions": len(session_data_copy.get("action_sequence", [])),
                "security_level": self.current_security_level
            }
            
        except Exception as e:
            self.logger.error(f"Error ending session: {e}")
            return {"error": str(e)}
    
    def _auto_apply_suggestions(self, analysis: Dict[str, Any]):
        """Automatically apply suggestions for critical risk patterns."""
        try:
            suggestions = analysis.get("suggestions", [])
            self.logger.warning(f"[{self.account_name}] Auto-applying suggestions for critical risk")
            
            applied_suggestions = []
            
            for suggestion in suggestions:
                if "vacation" in suggestion.lower():
                    if self.vacation_simulator:
                        # Schedule immediate vacation
                        vacation_days = random.randint(3, 7)
                        start_time = datetime.now() + timedelta(hours=1)
                        self.vacation_simulator.schedule_vacation(start_time, vacation_days, "emergency_cooloff")
                        applied_suggestions.append(f"Scheduled {vacation_days}-day vacation")
                
                elif "switch personality" in suggestion.lower() and self.personality_switcher:
                    self.personality_switcher.select_personality(force_switch=True)
                    applied_suggestions.append("Forced personality switch")
                
                elif "reduce activity" in suggestion.lower():
                    # Adjust security level to conservative
                    self.current_security_level = "conservative"
                    applied_suggestions.append("Set security level to conservative")
            
            if applied_suggestions:
                self.logger.info(f"Applied suggestions: {', '.join(applied_suggestions)}")
                self.adaptations_applied.append({
                    "timestamp": datetime.now().isoformat(),
                    "reason": "critical_risk_auto_mitigation",
                    "suggestions_applied": applied_suggestions
                })
        
        except Exception as e:
            self.logger.error(f"Failed to auto-apply suggestions: {e}")
    
    def get_timezone_consistency(self) -> Dict[str, Any]:
        """Get timezone consistency information with enhanced analysis."""
        if not self.vacation_simulator:
            return {"error": "vacation_simulator_not_available"}
        
        try:
            timezone = self.account_config.get("timezone", "America/Los_Angeles")
            consistency = self.vacation_simulator.simulate_timezone_consistency(timezone)
            
            # Add session timing analysis
            if self.session_start_time:
                session_hour = self.session_start_time.hour
                local_hour = consistency.get("local_hour", session_hour)
                
                # Check if session time matches typical activity hours
                typical_active = 9 <= local_hour <= 22
                consistency["session_timing_appropriate"] = typical_active
                consistency["session_start_local_hour"] = local_hour
                consistency["recommendation"] = "Good timing" if typical_active else "Consider adjusting session times"
            
            return consistency
            
        except Exception as e:
            self.logger.error(f"Error getting timezone consistency: {e}")
            return {"error": str(e)}
    
    def _get_timezone_offset(self, timezone_str: str) -> int:
        """Convert timezone string to UTC offset with validation."""
        # Extended timezone offsets
        offsets = {
            "America/Los_Angeles": -8,
            "America/New_York": -5,
            "UTC": 0,
            "Europe/London": 0,
            "Europe/Berlin": 1,
            "Europe/Paris": 1,
            "Asia/Tokyo": 9,
            "Asia/Shanghai": 8,
            "Australia/Sydney": 11,
            "Australia/Melbourne": 11,
            "Pacific/Auckland": 13,
            "America/Chicago": -6,
            "America/Denver": -7,
            "America/Phoenix": -7
        }
        
        offset = offsets.get(timezone_str)
        if offset is None:
            self.logger.warning(f"Unknown timezone: {timezone_str}, defaulting to UTC")
            return 0
        
        return offset
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive anti-detection status report with actionable insights."""
        report = {
            "account": self.account_name,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "personality_switcher": bool(self.personality_switcher),
                "markov_delays": bool(self.markov_delays),
                "vacation_simulator": bool(self.vacation_simulator),
                "pattern_analyzer": bool(self.pattern_analyzer)
            },
            "current_state": {
                "security_level": self.current_security_level,
                "session_active": bool(self.current_session_id),
                "consecutive_high_risk_sessions": self.consecutive_high_risk_sessions,
                "recent_adaptations": len(self.adaptations_applied)
            }
        }
        
        # Add personality info
        if self.personality_switcher:
            try:
                personality_name = self.personality_switcher.get_current_personality_name()
                switch_stats = self.personality_switcher.get_switch_statistics()
                report["personality"] = {
                    "current": personality_name,
                    "switch_stats": switch_stats
                }
            except Exception as e:
                report["personality"] = {"error": str(e)}
        
        # Add vacation status
        if self.vacation_simulator:
            try:
                vacation_status = self.vacation_simulator.get_vacation_status()
                vacation_stats = self.vacation_simulator.get_vacation_statistics()
                report["vacation"] = {
                    "status": vacation_status,
                    "statistics": vacation_stats
                }
            except Exception as e:
                report["vacation"] = {"error": str(e)}
        
        # Add timing analysis
        if self.markov_delays:
            try:
                timing_analysis = self.markov_delays.analyze_patterns()
                report["timing"] = timing_analysis
            except Exception as e:
                report["timing"] = {"error": str(e)}
        
        # Add pattern analysis statistics
        if self.pattern_analyzer:
            try:
                pattern_stats = self.pattern_analyzer.get_statistics()
                report["patterns"] = pattern_stats
                
                # Add recent risk report
                recent_report = self.pattern_analyzer.generate_report(days=1)
                report["recent_risks"] = recent_report
            except Exception as e:
                report["patterns"] = {"error": str(e)}
        
        # Add real-time monitoring summary
        report["real_time_monitoring"] = {
            "risks_detected": len(self.real_time_risks),
            "recent_risk_level": self.real_time_risks[-1].get("risk_level") if self.real_time_risks else "none",
            "adaptations_applied": self.adaptations_applied[-5:] if self.adaptations_applied else []
        }
        
        # Generate actionable insights
        insights = self._generate_actionable_insights(report)
        report["actionable_insights"] = insights
        
        return report
    
    def _generate_actionable_insights(self, report: Dict[str, Any]) -> List[str]:
        """Generate actionable insights from status report."""
        insights = []
        
        # Check component health
        components = report.get("components", {})
        working_components = sum(1 for comp in components.values() if comp)
        if working_components < 4:
            insights.append(f"Only {working_components}/4 anti-detection components working. Check logs for errors.")
        
        # Check consecutive high risk
        high_risk_sessions = report["current_state"]["consecutive_high_risk_sessions"]
        if high_risk_sessions >= 2:
            insights.append(f"{high_risk_sessions} consecutive high risk sessions. Consider manual review.")
        
        # Check security level appropriateness
        current_level = report["current_state"]["security_level"]
        pattern_risks = report.get("patterns", {}).get("risk_distribution", {})
        high_risk_count = pattern_risks.get("high", 0) + pattern_risks.get("critical", 0)
        total_risks = sum(pattern_risks.values())
        
        if total_risks > 0:
            high_risk_percentage = high_risk_count / total_risks
            if high_risk_percentage > 0.5 and current_level != "conservative":
                insights.append(f"High risk percentage {high_risk_percentage:.1%} but security level is {current_level}. Consider switching to conservative.")
            elif high_risk_percentage < 0.2 and current_level == "conservative":
                insights.append(f"Low risk percentage {high_risk_percentage:.1%} but security level is conservative. Can switch to balanced.")
        
        # Check vacation frequency
        vacation_stats = report.get("vacation", {}).get("statistics", {})
        if vacation_stats:
            days_since_last = vacation_stats.get("days_since_last")
            if days_since_last is not None and days_since_last > 30:
                insights.append(f"No vacation in {days_since_last} days. Consider scheduling a vacation.")
        
        # If no insights, provide positive feedback
        if not insights:
            insights.append("All systems operating normally. Continue current strategy.")
        
        return insights
    
    def save_state(self) -> bool:
        """Save coordinator state to file for persistence."""
        try:
            data = {
                "account": self.account_name,
                "current_security_level": self.current_security_level,
                "consecutive_high_risk_sessions": self.consecutive_high_risk_sessions,
                "adaptations_applied": self.adaptations_applied[-20:],  # Keep recent
                "last_session_id": self.current_session_id,
                "security_config": self.security_config,
                "risk_thresholds": self.risk_thresholds,
                "last_updated": datetime.now().isoformat()
            }
            
            self.state_file.parent.mkdir(exist_ok=True, parents=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            
            self.logger.debug(f"Saved evasion state for {self.account_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save evasion state for {self.account_name}: {e}")
            return False
    
    def load_state(self) -> bool:
        """Load coordinator state from file."""
        if not self.state_file.exists():
            return False
            
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.current_security_level = data.get("current_security_level", "balanced")
            self.consecutive_high_risk_sessions = data.get("consecutive_high_risk_sessions", 0)
            self.adaptations_applied = data.get("adaptations_applied", [])
            
            # Update security config with saved values
            saved_config = data.get("security_config", {})
            self.security_config.update(saved_config)
            
            self.logger.info(f"Loaded evasion state for {self.account_name}")
            return True
            
        except Exception as e:
            self.logger.warning(f"Failed to load evasion state for {self.account_name}: {e}")
            return False
    
    def get_recommendations(self) -> List[str]:
        """Get active recommendations based on current state."""
        recommendations = []
        
        # Check if any components failed
        if not any([self.personality_switcher, self.markov_delays, self.vacation_simulator]):
            recommendations.append("All anti-detection components failed. Check logs and restart.")
        
        # Check for high consecutive risk
        if self.consecutive_high_risk_sessions >= 3:
            recommendations.append("Multiple consecutive high risk sessions. Consider manual review and possible account rest.")
        
        # Check if vacation is overdue
        if self.vacation_simulator:
            stats = self.vacation_simulator.get_vacation_statistics()
            days_since_last = stats.get("days_since_last", 999)
            if days_since_last > 45:
                recommendations.append(f"No vacation in {days_since_last} days. Schedule vacation soon.")
        
        # Check security level appropriateness
        if self.current_security_level == "aggressive" and self.consecutive_high_risk_sessions > 0:
            recommendations.append("Aggressive security level with high risk. Consider switching to balanced.")
        
        return recommendations
    
    def force_security_level(self, level: str) -> bool:
        """Force a specific security level (conservative/balanced/aggressive)."""
        if level not in self.security_levels:
            self.logger.error(f"Invalid security level: {level}")
            return False
        
        old_level = self.current_security_level
        self.current_security_level = level
        
        self.logger.info(f"[{self.account_name}] Security level forced: {old_level} → {level}")
        return True
    
    def emergency_shutdown(self) -> Dict[str, Any]:
        """Emergency shutdown of all anti-detection activities."""
        self.logger.warning(f"[{self.account_name}] EMERGENCY SHUTDOWN INITIATED")
        
        actions = []
        
        # Schedule immediate vacation
        if self.vacation_simulator:
            try:
                vacation_days = random.randint(7, 14)
                start_time = datetime.now() + timedelta(minutes=5)
                self.vacation_simulator.schedule_vacation(start_time, vacation_days, "emergency_shutdown")
                actions.append(f"Scheduled {vacation_days}-day emergency vacation")
            except Exception as e:
                actions.append(f"Failed to schedule vacation: {e}")
        
        # Set to maximum security
        self.current_security_level = "conservative"
        actions.append("Set security level to conservative")
        
        # Clear session data
        if self.current_session_id:
            self.current_session_id = None
            self.session_start_time = None
            actions.append("Terminated active session")
        
        # Save state
        self.save_state()
        
        return {
            "status": "emergency_shutdown_complete",
            "actions_taken": actions,
            "timestamp": datetime.now().isoformat()
        }