"""
Analyzes our own patterns for potential detection and suggests improvements.
"""

import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import hashlib

# Fix: Add missing import
from microdose_study_bot.core.logging import UnifiedLogger

class PatternAnalyzer:
    """Analyzes automation patterns and suggests anti-detection improvements."""
    
    def __init__(self, account_name: str, config_path: Optional[Path] = None):
        """Initialize the pattern analyzer for an account.
        
        Args:
            account_name: Name of the account being analyzed
            config_path: Optional path to custom configuration file
        """
        self.account_name = account_name
        self.logger = UnifiedLogger("PatternAnalyzer").get_logger()
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Pattern detection thresholds
        self.thresholds = self.config.get("thresholds", {
            "timing_regularity": 0.7,  # Above this = too regular
            "action_repetition": 0.6,   # Above this = too repetitive
            "session_consistency": 0.8, # Above this = too consistent
            "behavior_fingerprint": 0.9, # Above this = unique fingerprint detected
            "click_speed_variance": 0.3, # Below this = too consistent clicking
            "scroll_pattern_variance": 0.4 # Below this = too consistent scrolling
        })
        
        # Data storage
        self.analysis_file = Path(f"data/pattern_analysis_{account_name}.json")
        self.pattern_history = self.load_pattern_history()
        
        # Detection algorithms
        self.detection_models = self._initialize_detection_models()
        
        # Statistics
        self.total_analyses = len(self.pattern_history)
        self.last_risk_level = None
        
        self.logger.info(f"PatternAnalyzer initialized for {account_name} with {self.total_analyses} historical analyses")
    
    def _load_config(self, config_path: Optional[Path]) -> Dict[str, Any]:
        """Load configuration from file or use defaults.
        
        Args:
            config_path: Optional path to configuration file
            
        Returns:
            Configuration dictionary
        """
        if config_path and config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load pattern analyzer config from {config_path}: {e}. Using defaults.")
        
        # Default configuration
        return {
            "analysis_window": 20,  # Number of sessions to analyze for trends
            "save_frequency": 5,     # Save after every N analyses
            "alert_on_risk": ["critical", "high"],  # Risk levels that trigger alerts
            "enable_auto_mitigation": True,  # Automatically apply suggestions for high risk
            "reference_behavior": {  # Reference "average human" behavior patterns
                "avg_click_speed": 0.5,
                "avg_scroll_distance": 400,
                "browse_ratio": 0.4,
                "vote_ratio": 0.1,
                "comment_ratio": 0.05,
                "save_ratio": 0.03
            }
        }
    
    def analyze_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single session for detectable patterns.
        
        Args:
            session_data: Dictionary containing session data with keys:
                - session_id (optional): Unique session identifier
                - action_timestamps: List of ISO format timestamps for each action
                - action_sequence: List of action types
                - action_types: List of action type strings
                - click_speeds: List of click speed measurements
                - scroll_distances: List of scroll distances
                - session_duration: Duration of session in minutes
                
        Returns:
            Dictionary containing analysis results with:
                - session_id: Session identifier
                - timestamp: Analysis timestamp
                - scores: Dictionary of risk scores
                - risks: List of detected risks
                - suggestions: List of improvement suggestions
                - overall_risk: Overall risk level (low/medium/high/critical)
                - confidence: Confidence in analysis (0-1)
        """
        session_id = session_data.get("session_id") or hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]
        
        analysis = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "scores": {},
            "risks": [],
            "suggestions": [],
            "overall_risk": "low",
            "confidence": 0.5  # Default medium confidence
        }
        
        try:
            # 1. Check timing regularity
            timing_score, timing_confidence = self._analyze_timing_patterns(session_data)
            analysis["scores"]["timing_regularity"] = timing_score
            analysis["confidence"] = max(analysis["confidence"], timing_confidence)
            
            if timing_score > self.thresholds["timing_regularity"]:
                analysis["risks"].append("Regular timing patterns detected")
                analysis["suggestions"].append("Increase timing randomness with Markov delays")
            
            # 2. Check action repetition
            repetition_score, repetition_confidence = self._analyze_action_repetition(session_data)
            analysis["scores"]["action_repetition"] = repetition_score
            analysis["confidence"] = max(analysis["confidence"], repetition_confidence)
            
            if repetition_score > self.thresholds["action_repetition"]:
                analysis["risks"].append("Repetitive action patterns detected")
                analysis["suggestions"].append("Vary action sequences and add random actions")
            
            # 3. Check session consistency
            consistency_score, consistency_confidence = self._analyze_session_consistency(session_data)
            analysis["scores"]["session_consistency"] = consistency_score
            analysis["confidence"] = max(analysis["confidence"], consistency_confidence)
            
            if consistency_score > self.thresholds["session_consistency"]:
                analysis["risks"].append("Session patterns too consistent")
                analysis["suggestions"].append("Vary session length and start times")
            
            # 4. Behavioral fingerprint analysis
            fingerprint_score, fingerprint_confidence = self._calculate_behavioral_fingerprint(session_data)
            analysis["scores"]["behavior_fingerprint"] = fingerprint_score
            analysis["confidence"] = max(analysis["confidence"], fingerprint_confidence)
            
            if fingerprint_score > self.thresholds["behavior_fingerprint"]:
                analysis["risks"].append("Unique behavioral fingerprint detected")
                analysis["suggestions"].append("Switch behavioral personalities more frequently")
            
            # 5. Additional analyses
            if "click_speeds" in session_data and len(session_data["click_speeds"]) > 5:
                click_variance = self._analyze_click_speed_variance(session_data["click_speeds"])
                analysis["scores"]["click_speed_variance"] = click_variance
                if click_variance < self.thresholds["click_speed_variance"]:
                    analysis["risks"].append("Click speed patterns too consistent")
                    analysis["suggestions"].append("Vary click speed between actions")
            
            if "scroll_distances" in session_data and len(session_data["scroll_distances"]) > 5:
                scroll_variance = self._analyze_scroll_pattern_variance(session_data["scroll_distances"])
                analysis["scores"]["scroll_pattern_variance"] = scroll_variance
                if scroll_variance < self.thresholds["scroll_pattern_variance"]:
                    analysis["risks"].append("Scroll patterns too consistent")
                    analysis["suggestions"].append("Vary scroll distances and patterns")
            
            # Overall risk level with weighted scoring
            analysis["overall_risk"] = self._calculate_overall_risk(analysis["scores"])
            self.last_risk_level = analysis["overall_risk"]
            
            # Store analysis
            self.pattern_history.append(analysis)
            self.total_analyses += 1
            
            # Limit history size
            max_history = self.config.get("analysis_window", 20) * 5  # Keep 5x analysis window
            if len(self.pattern_history) > max_history:
                self.pattern_history = self.pattern_history[-max_history:]
            
            # Save periodically
            if self.total_analyses % self.config.get("save_frequency", 5) == 0:
                self.save_pattern_history()
            
            # Log analysis results
            if analysis["overall_risk"] in self.config.get("alert_on_risk", []):
                self.logger.warning(f"[{self.account_name}] High risk patterns detected: {analysis['overall_risk']}")
                for risk in analysis["risks"]:
                    self.logger.warning(f"  - {risk}")
            else:
                self.logger.info(f"[{self.account_name}] Session analysis: {analysis['overall_risk']} risk")
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing session {session_id}: {e}")
            # Return minimal analysis with error
            analysis["error"] = str(e)
            analysis["overall_risk"] = "unknown"
            return analysis
    
    def _analyze_timing_patterns(self, session_data: Dict[str, Any]) -> tuple[float, float]:
        """Analyze timing patterns for regularity.
        
        Returns:
            Tuple of (score, confidence) where:
                - score: 0-1 (higher = more regular/patterned)
                - confidence: 0-1 confidence in the score
        """
        if "action_timestamps" not in session_data or len(session_data["action_timestamps"]) < 5:
            return 0.5, 0.1  # Neutral score, low confidence for insufficient data
        
        try:
            timestamps = session_data["action_timestamps"]
            deltas = []
            
            # Calculate time between actions
            for i in range(1, len(timestamps)):
                try:
                    t1 = datetime.fromisoformat(timestamps[i-1])
                    t2 = datetime.fromisoformat(timestamps[i])
                    delta = (t2 - t1).total_seconds()
                    deltas.append(delta)
                except (ValueError, TypeError):
                    continue
            
            if len(deltas) < 3:
                return 0.5, 0.2
            
            # Calculate coefficient of variation (low = regular, high = irregular)
            mean_delta = np.mean(deltas)
            std_delta = np.std(deltas)
            
            if mean_delta == 0:
                return 1.0, 0.9  # Perfect regularity (bad), high confidence
            
            cv = std_delta / mean_delta
            
            # Calculate confidence based on data quality
            confidence = min(len(deltas) / 20.0, 1.0)  # More data = higher confidence
            
            # Convert to 0-1 score (1 = very regular, 0 = very irregular)
            # Human-like behavior has CV around 0.3-0.7
            if cv < 0.2:
                return 0.9, confidence  # Too regular
            elif cv > 1.0:
                return 0.1, confidence  # Too irregular
            else:
                return 1 - cv, confidence  # Invert so higher = more regular
                
        except Exception as e:
            self.logger.debug(f"Error in timing pattern analysis: {e}")
            return 0.5, 0.0  # Default score, no confidence
    
    def _analyze_action_repetition(self, session_data: Dict[str, Any]) -> tuple[float, float]:
        """Analyze action sequences for repetition."""
        if "action_sequence" not in session_data:
            return 0.5, 0.1
        
        sequence = session_data["action_sequence"]
        if len(sequence) < 4:
            return 0.5, 0.2
        
        try:
            # Check for repeating patterns using multiple methods
            
            # Method 1: Simple pattern repetition
            max_pattern_length = min(4, len(sequence) // 2)
            found_pattern = False
            pattern_score = 0.0
            
            for pattern_len in range(2, max_pattern_length + 1):
                patterns = []
                for i in range(0, len(sequence) - pattern_len + 1, pattern_len):
                    pattern = tuple(sequence[i:i+pattern_len])
                    patterns.append(pattern)
                
                # If all patterns are the same, we have repetition
                if len(set(patterns)) == 1:
                    found_pattern = True
                    pattern_strength = pattern_len / max_pattern_length
                    pattern_score = 0.5 + (pattern_strength * 0.5)
                    break
            
            if found_pattern:
                confidence = min(len(sequence) / 10.0, 1.0)
                return pattern_score, confidence
            
            # Method 2: Entropy analysis for randomness
            action_counts = {}
            for action in sequence:
                action_counts[action] = action_counts.get(action, 0) + 1
            
            entropy = 0.0
            total_actions = len(sequence)
            for count in action_counts.values():
                probability = count / total_actions
                entropy -= probability * np.log2(probability)
            
            max_entropy = np.log2(len(action_counts)) if action_counts else 0
            if max_entropy > 0:
                normalized_entropy = entropy / max_entropy
                # Low entropy = repetitive, high entropy = varied
                repetition_score = 1 - normalized_entropy
            else:
                repetition_score = 0.5
            
            confidence = min(len(sequence) / 15.0, 1.0)
            return repetition_score, confidence
            
        except Exception as e:
            self.logger.debug(f"Error in action repetition analysis: {e}")
            return 0.5, 0.0
    
    def _analyze_session_consistency(self, session_data: Dict[str, Any]) -> tuple[float, float]:
        """Analyze consistency across multiple sessions."""
        if len(self.pattern_history) < 3:
            return 0.5, 0.1
        
        try:
            # Get recent sessions (up to analysis_window)
            window_size = self.config.get("analysis_window", 20)
            recent_sessions = self.pattern_history[-window_size:]
            
            # Extract session lengths from recent analyses
            session_lengths = []
            for session_analysis in recent_sessions:
                if "session_duration" in session_data:
                    # Use current session if available
                    session_lengths.append(session_data["session_duration"])
                    break
                elif "scores" in session_analysis and "session_consistency" in session_analysis["scores"]:
                    # Estimate from previous analysis
                    pass  # Skip for now - we need actual session durations
            
            # If we have current session duration, compare with historical pattern
            if "session_duration" in session_data and len(self.pattern_history) >= 5:
                current_duration = session_data["session_duration"]
                
                # Get durations from previous sessions that have them
                historical_durations = []
                for analysis in self.pattern_history[-10:]:
                    if "session_duration" in analysis:
                        historical_durations.append(analysis["session_duration"])
                
                if len(historical_durations) >= 3:
                    # Calculate how similar current duration is to historical pattern
                    mean_historical = np.mean(historical_durations)
                    std_historical = np.std(historical_durations)
                    
                    if std_historical > 0:
                        # Z-score of current duration
                        z_score = abs(current_duration - mean_historical) / std_historical
                        # High z-score = unusual = good (not consistent)
                        # Low z-score = consistent with history = bad (too consistent)
                        consistency_score = 1 - min(z_score, 2.0) / 2.0  # Normalize to 0-1
                        confidence = min(len(historical_durations) / 10.0, 1.0)
                        return consistency_score, confidence
            
            return 0.5, 0.3  # Default with low confidence
            
        except Exception as e:
            self.logger.debug(f"Error in session consistency analysis: {e}")
            return 0.5, 0.0
    
    def _calculate_behavioral_fingerprint(self, session_data: Dict[str, Any]) -> tuple[float, float]:
        """Calculate how unique/identifiable our behavior pattern is."""
        try:
            fingerprint_features = []
            
            # Extract features that could create a fingerprint
            if "click_speeds" in session_data and session_data["click_speeds"]:
                avg_click_speed = np.mean(session_data["click_speeds"])
                fingerprint_features.append(avg_click_speed)
            
            if "scroll_distances" in session_data and session_data["scroll_distances"]:
                avg_scroll = np.mean(session_data["scroll_distances"])
                fingerprint_features.append(avg_scroll / 1000)  # Normalize
            
            if "action_types" in session_data and session_data["action_types"]:
                # Distribution of action types
                actions = session_data["action_types"]
                total = len(actions)
                
                # Calculate ratios for different action types
                action_ratios = {}
                for action_type in set(actions):
                    action_ratios[action_type] = actions.count(action_type) / total
                
                # Add most common action ratios
                common_actions = ["browse", "vote", "comment", "save"]
                for action in common_actions:
                    fingerprint_features.append(action_ratios.get(action, 0.0))
            
            # If we have enough features, calculate uniqueness
            if len(fingerprint_features) >= 3:
                reference = self.config.get("reference_behavior", {})
                ref_features = [
                    reference.get("avg_click_speed", 0.5),
                    reference.get("avg_scroll_distance", 400) / 1000,
                    reference.get("browse_ratio", 0.4),
                    reference.get("vote_ratio", 0.1),
                    reference.get("comment_ratio", 0.05),
                    reference.get("save_ratio", 0.03)
                ]
                
                # Calculate Mahalanobis-like distance (simplified)
                distances = []
                for i in range(min(len(fingerprint_features), len(ref_features))):
                    distance = abs(fingerprint_features[i] - ref_features[i])
                    distances.append(distance)
                
                avg_distance = np.mean(distances) if distances else 0
                
                # Calculate confidence based on feature count and data quality
                confidence = min(len(fingerprint_features) / 6.0, 1.0)
                
                # Higher distance = more unique fingerprint
                uniqueness_score = min(avg_distance * 2, 1.0)
                return uniqueness_score, confidence
            
            return 0.5, 0.2  # Default with low confidence
            
        except Exception as e:
            self.logger.debug(f"Error in behavioral fingerprint analysis: {e}")
            return 0.5, 0.0
    
    def _analyze_click_speed_variance(self, click_speeds: List[float]) -> float:
        """Analyze variance in click speeds."""
        if len(click_speeds) < 3:
            return 0.5
        
        try:
            cv = np.std(click_speeds) / np.mean(click_speeds) if np.mean(click_speeds) > 0 else 0
            return min(cv, 1.0)  # Cap at 1.0
        except:
            return 0.5
    
    def _analyze_scroll_pattern_variance(self, scroll_distances: List[int]) -> float:
        """Analyze variance in scroll patterns."""
        if len(scroll_distances) < 3:
            return 0.5
        
        try:
            # Calculate autocorrelation to detect patterns
            if len(scroll_distances) >= 5:
                # Simple pattern detection: check if distances alternate
                is_alternating = True
                for i in range(2, len(scroll_distances)):
                    if abs(scroll_distances[i] - scroll_distances[i-2]) > 100:
                        is_alternating = False
                        break
                
                if is_alternating:
                    return 0.1  # Very patterned
            
            cv = np.std(scroll_distances) / np.mean(scroll_distances) if np.mean(scroll_distances) > 0 else 0
            return min(cv, 1.0)
        except:
            return 0.5
    
    def _calculate_overall_risk(self, scores: Dict[str, float]) -> str:
        """Calculate overall risk level with weighted scoring."""
        if not scores:
            return "low"
        
        # Define weights for different risk factors
        weights = {
            "timing_regularity": 0.30,
            "action_repetition": 0.25,
            "behavior_fingerprint": 0.25,
            "session_consistency": 0.10,
            "click_speed_variance": 0.05,
            "scroll_pattern_variance": 0.05
        }
        
        # Calculate weighted average
        weighted_sum = 0.0
        total_weight = 0.0
        
        for score_name, score_value in scores.items():
            weight = weights.get(score_name, 0.05)  # Default weight for new scores
            weighted_sum += score_value * weight
            total_weight += weight
        
        if total_weight > 0:
            avg_score = weighted_sum / total_weight
        else:
            avg_score = np.mean(list(scores.values())) if scores else 0.5
        
        # Determine risk level
        if avg_score > 0.8:
            return "critical"
        elif avg_score > 0.6:
            return "high"
        elif avg_score > 0.4:
            return "medium"
        else:
            return "low"
    
    def get_recommendations(self, risk_level: str, scores: Optional[Dict[str, float]] = None) -> List[str]:
        """Get recommendations based on risk level and specific scores.
        
        Args:
            risk_level: Overall risk level (low/medium/high/critical)
            scores: Optional dictionary of individual risk scores for targeted recommendations
            
        Returns:
            List of recommendation strings
        """
        base_recommendations = {
            "critical": [
                "Immediately switch to conservative personality",
                "Add 24-hour cooldown period",
                "Randomize all timing patterns",
                "Consider account vacation (3-7 days)",
                "Review and adjust all automation settings",
                "Reduce daily activity by 50% for next week"
            ],
            "high": [
                "Increase behavioral diversity",
                "Add more random actions between scheduled ones",
                "Vary session start times by ±3 hours",
                "Use Markov delays for timing",
                "Consider short vacation (1-2 days)",
                "Switch to different personality for next 3 sessions"
            ],
            "medium": [
                "Minor timing adjustments needed",
                "Slightly increase action variety",
                "Monitor for pattern development",
                "Consider personality switch",
                "Add 1-2 random scrolls per session"
            ],
            "low": [
                "Patterns appear human-like",
                "Continue current strategies",
                "Regular monitoring recommended",
                "Consider occasional personality switch for diversity"
            ]
        }
        
        recommendations = base_recommendations.get(risk_level, ["Continue monitoring"])
        
        # Add targeted recommendations based on specific scores
        if scores:
            if scores.get("timing_regularity", 0) > 0.6:
                recommendations.append("Introduce random delays between 1-15 seconds")
            if scores.get("action_repetition", 0) > 0.5:
                recommendations.append("Shuffle action order in next session")
            if scores.get("behavior_fingerprint", 0) > 0.7:
                recommendations.append("Change browsing subreddit mix")
        
        return recommendations
    
    def load_pattern_history(self) -> List[Dict[str, Any]]:
        """Load pattern analysis history from file.
        
        Returns:
            List of historical analysis dictionaries
        """
        if not self.analysis_file.exists():
            return []
        
        try:
            with open(self.analysis_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate loaded data
            if isinstance(data, dict) and "pattern_history" in data:
                history = data["pattern_history"]
                if isinstance(history, list):
                    self.logger.info(f"Loaded {len(history)} historical analyses for {self.account_name}")
                    return history
            
            self.logger.warning(f"Invalid format in {self.analysis_file}")
            return []
            
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Failed to load pattern history for {self.account_name}: {e}")
            return []
    
    def save_pattern_history(self) -> bool:
        """Save pattern analysis history to file.
        
        Returns:
            True if save was successful, False otherwise
        """
        try:
            data = {
                "account": self.account_name,
                "pattern_history": self.pattern_history,
                "total_analyses": self.total_analyses,
                "last_risk_level": self.last_risk_level,
                "last_updated": datetime.now().isoformat(),
                "config": self.config
            }
            
            self.analysis_file.parent.mkdir(exist_ok=True, parents=True)
            with open(self.analysis_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            
            self.logger.debug(f"Saved pattern history for {self.account_name} ({len(self.pattern_history)} analyses)")
            return True
            
        except (IOError, TypeError) as e:
            self.logger.error(f"Failed to save pattern history for {self.account_name}: {e}")
            return False
    
    def _initialize_detection_models(self) -> Dict[str, str]:
        """Initialize detection models.
        
        Returns:
            Dictionary of model names and types
        """
        # Placeholder for ML models
        # In real implementation, this would load trained models
        
        return {
            "timing_model": "statistical_analysis",
            "behavior_model": "rule_based_pattern_detection",
            "fingerprint_model": "distance_metric_analysis",
            "consistency_model": "historical_comparison",
            "variance_model": "coefficient_of_variation"
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about analyzed patterns.
        
        Returns:
            Dictionary with analysis statistics
        """
        if not self.pattern_history:
            return {"total_analyses": 0, "risk_distribution": {}}
        
        # Calculate risk level distribution
        risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
        
        for analysis in self.pattern_history[-50:]:  # Last 50 analyses
            risk_level = analysis.get("overall_risk", "unknown")
            risk_counts[risk_level] = risk_counts.get(risk_level, 0) + 1
        
        # Calculate average scores for recent analyses
        recent_analyses = self.pattern_history[-10:]
        avg_scores = {}
        
        if recent_analyses:
            for score_name in ["timing_regularity", "action_repetition", "behavior_fingerprint"]:
                scores = [a.get("scores", {}).get(score_name, 0.5) for a in recent_analyses 
                         if "scores" in a and score_name in a["scores"]]
                if scores:
                    avg_scores[score_name] = np.mean(scores)
        
        return {
            "total_analyses": self.total_analyses,
            "recent_analyses": len(recent_analyses),
            "risk_distribution": risk_counts,
            "average_scores": avg_scores,
            "last_risk_level": self.last_risk_level,
            "detection_models": list(self.detection_models.keys())
        }
    
    def generate_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate a comprehensive risk report for the specified period.
        
        Args:
            days: Number of days to include in the report
            
        Returns:
            Dictionary containing the report
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Filter analyses from the specified period
        recent_analyses = []
        for analysis in self.pattern_history:
            try:
                timestamp = datetime.fromisoformat(analysis.get("timestamp", ""))
                if timestamp >= cutoff_date:
                    recent_analyses.append(analysis)
            except (ValueError, TypeError):
                continue
        
        if not recent_analyses:
            return {"error": f"No analyses found in the last {days} days"}
        
        # Calculate statistics
        risk_levels = [a.get("overall_risk", "unknown") for a in recent_analyses]
        risk_counts = {level: risk_levels.count(level) for level in set(risk_levels)}
        
        # Most common risks
        all_risks = []
        for analysis in recent_analyses:
            all_risks.extend(analysis.get("risks", []))
        
        from collections import Counter
        common_risks = Counter(all_risks).most_common(5)
        
        # Generate recommendations
        latest_risk = recent_analyses[-1].get("overall_risk", "low")
        recommendations = self.get_recommendations(latest_risk, recent_analyses[-1].get("scores", {}))
        
        return {
            "period_days": days,
            "total_sessions": len(recent_analyses),
            "risk_distribution": risk_counts,
            "most_common_risks": common_risks,
            "current_risk_level": latest_risk,
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat()
        }