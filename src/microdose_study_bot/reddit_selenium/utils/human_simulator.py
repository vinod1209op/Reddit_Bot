"""
Purpose: Simulate human-like browsing actions in Selenium sessions with anti-detection measures.
Constraints: No posting logic; timing-only helpers with behavioral diversity integration.
"""

import random
import time
import math
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import MoveTargetOutOfBoundsException, NoSuchElementException, StaleElementReferenceException

class HumanSimulator:
    def __init__(self, driver, browser_manager=None, detection_evasion_coordinator=None):
        self.driver = driver
        self.browser_manager = browser_manager
        self.detection_evasion_coordinator = detection_evasion_coordinator
        
        self.last_mouse_position = None  # Track last known mouse position (x, y)
        self.navigation_error_count = 0
        
        # Behavioral tracking for pattern analysis
        self.behavior_metrics = {
            'click_speeds': [],
            'scroll_distances': [],
            'mouse_movements': [],
            'reading_times': [],
            'action_timestamps': []
        }
        
        # Current behavior profile
        self.current_behavior_profile = {
            'click_speed': 'normal',
            'scroll_pattern': 'smooth',
            'mouse_intensity': 'medium',
            'engagement_rate': 0.3,
            'typing_speed': 'normal'
        }
        
        # Initialize with anti-detection behavior if coordinator is available
        if detection_evasion_coordinator:
            self._update_behavior_from_anti_detection()
        
        self.logger = self._get_logger()
    
    def _get_logger(self):
        """Get logger instance."""
        try:
            from microdose_study_bot.core.logging import UnifiedLogger
            return UnifiedLogger("HumanSimulator").get_logger()
        except ImportError:
            import logging
            logging.basicConfig(level=logging.INFO)
            return logging.getLogger("HumanSimulator")
    
    def _update_behavior_from_anti_detection(self):
        """Update current behavior profile from anti-detection coordinator."""
        if not self.detection_evasion_coordinator:
            return
        
        try:
            # Get behavior parameters for generic action
            behavior = self.detection_evasion_coordinator.get_behavior_for_action("browse")
            
            # Update current profile
            self.current_behavior_profile.update({
                'click_speed': behavior.get('click_speed', 'normal'),
                'scroll_pattern': behavior.get('scroll_pattern', 'smooth'),
                'mouse_intensity': self._map_click_speed_to_intensity(behavior.get('click_speed', 'normal')),
                'engagement_rate': behavior.get('engagement_chance', 0.3),
                'typing_speed': behavior.get('typing_speed', 'normal'),
                'security_level': behavior.get('security_level', 'balanced')
            })
            
        except Exception as e:
            self.logger.debug(f"Failed to update behavior from anti-detection: {e}")
    
    def _map_click_speed_to_intensity(self, click_speed: str) -> str:
        """Map click speed to mouse movement intensity."""
        mapping = {
            'slow': 'low',
            'normal': 'medium',
            'fast': 'high'
        }
        return mapping.get(click_speed, 'medium')
    
    def _record_behavior_metric(self, metric_type: str, value: Any):
        """Record behavior metrics for pattern analysis."""
        try:
            timestamp = datetime.now().isoformat()
            self.behavior_metrics['action_timestamps'].append(timestamp)
            
            if metric_type == 'click_speed':
                # Convert click speed string to numeric value
                speed_map = {'slow': 0.3, 'normal': 0.6, 'fast': 0.9}
                numeric_value = speed_map.get(value, 0.6)
                self.behavior_metrics['click_speeds'].append(numeric_value)
            
            elif metric_type == 'scroll_distance':
                self.behavior_metrics['scroll_distances'].append(value)
            
            elif metric_type == 'mouse_movement':
                self.behavior_metrics['mouse_movements'].append(value)
            
            elif metric_type == 'reading_time':
                self.behavior_metrics['reading_times'].append(value)
            
            # Send to anti-detection coordinator if available
            if self.detection_evasion_coordinator and metric_type in ['click_speed', 'scroll_distance']:
                self.detection_evasion_coordinator.record_action("browse", {
                    metric_type: value,
                    "timestamp": timestamp
                })
                
        except Exception as e:
            self.logger.debug(f"Failed to record behavior metric: {e}")
    
    def human_scroll(self, scroll_times: Optional[int] = None, behavior_profile: Optional[Dict[str, Any]] = None) -> List[int]:
        """Random scroll patterns with human-like pauses and behavior-based adjustments."""
        if behavior_profile:
            scroll_pattern = behavior_profile.get('scroll_pattern', self.current_behavior_profile['scroll_pattern'])
        else:
            scroll_pattern = self.current_behavior_profile['scroll_pattern']
        
        if scroll_times is None:
            # Determine scroll times based on behavior profile
            if scroll_pattern == 'reader':
                scroll_times = random.randint(3, 6)
            elif scroll_pattern == 'jerky':
                scroll_times = random.randint(1, 3)
            else:  # smooth
                scroll_times = random.randint(2, 4)
        
        scroll_distances = []
        
        for i in range(scroll_times):
            # Determine scroll amount based on scroll pattern
            if scroll_pattern == 'reader':
                scroll_amount = random.randint(150, 400)
            elif scroll_pattern == 'jerky':
                scroll_amount = random.randint(500, 1200)
            else:  # smooth
                scroll_amount = random.randint(300, 800)
            
            # Smooth scroll with random pattern
            self.driver.execute_script(f"""
                window.scrollBy({{
                    top: {scroll_amount},
                    behavior: 'smooth'
                }});
            """)
            
            scroll_distances.append(scroll_amount)
            
            # Record scroll distance for pattern analysis
            self._record_behavior_metric('scroll_distance', scroll_amount)
            
            # Random pause (exponential distribution for realism) adjusted by behavior
            base_pause_mean = 3.0  # Mean 3 seconds
            if behavior_profile and behavior_profile.get('engagement_rate'):
                # Higher engagement = longer pauses (more reading)
                engagement_factor = behavior_profile['engagement_rate'] * 2
                base_pause_mean *= max(0.5, engagement_factor)
            
            pause_time = random.expovariate(1.0 / base_pause_mean)
            pause_time = min(pause_time, 10)  # Cap at 10 seconds
            time.sleep(pause_time)
            
            # Occasionally scroll up slightly (like real reading)
            if random.random() > 0.7:
                back_scroll = random.randint(50, 200)
                self.driver.execute_script(f"window.scrollBy(0, -{back_scroll});")
                time.sleep(random.uniform(0.5, 1.5))
                scroll_distances.append(-back_scroll)
        
        return scroll_distances
    
    def random_mouse_movements(self, element=None, behavior_profile: Optional[Dict[str, Any]] = None):
        """Create natural mouse movements with behavior-based intensity."""
        try:
            actions = ActionChains(self.driver)
            
            if behavior_profile:
                mouse_intensity = behavior_profile.get('mouse_intensity', self.current_behavior_profile['mouse_intensity'])
            else:
                mouse_intensity = self.current_behavior_profile['mouse_intensity']
            
            if element:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                        element,
                    )
                except Exception:
                    pass
                
                size = element.size or {}
                width = max(int(size.get("width", 1)), 1)
                height = max(int(size.get("height", 1)), 1)
                
                # Adjust movement range based on intensity
                if mouse_intensity == 'low':
                    max_x = max(1, min(width - 1, 50))
                    max_y = max(1, min(height - 1, 50))
                elif mouse_intensity == 'high':
                    max_x = max(1, min(width - 1, 120))
                    max_y = max(1, min(height - 1, 120))
                else:  # medium
                    max_x = max(1, min(width - 1, 80))
                    max_y = max(1, min(height - 1, 80))
                
                actions.move_to_element_with_offset(
                    element,
                    random.randint(1, max_x),
                    random.randint(1, max_y),
                )
            else:
                body = self.driver.find_element(By.TAG_NAME, "body")
                window = self.driver.get_window_size()
                
                # Adjust movement range based on intensity
                if mouse_intensity == 'low':
                    max_x = max(1, int(window.get("width", 800)) - 5)
                    max_y = max(1, int(window.get("height", 600)) - 5)
                    movement_range = 10
                elif mouse_intensity == 'high':
                    max_x = max(1, int(window.get("width", 800)) - 5)
                    max_y = max(1, int(window.get("height", 600)) - 5)
                    movement_range = 25
                else:  # medium
                    max_x = max(1, int(window.get("width", 800)) - 5)
                    max_y = max(1, int(window.get("height", 600)) - 5)
                    movement_range = 15
                
                actions.move_to_element_with_offset(
                    body,
                    random.randint(5, max_x),
                    random.randint(5, max_y),
                )

            # Number of micro-movements based on intensity
            if mouse_intensity == 'low':
                num_movements = random.randint(1, 3)
            elif mouse_intensity == 'high':
                num_movements = random.randint(4, 7)
            else:  # medium
                num_movements = random.randint(2, 5)
            
            for _ in range(num_movements):
                actions.move_by_offset(
                    random.randint(-movement_range, movement_range),
                    random.randint(-movement_range // 2, movement_range // 2)
                )
                if random.random() > 0.6:
                    actions.pause(random.uniform(0.05, 0.2))
            
            actions.perform()
            
            # Record mouse movement
            self._record_behavior_metric('mouse_movement', {
                'intensity': mouse_intensity,
                'movements': num_movements
            })
            
        except MoveTargetOutOfBoundsException:
            try:
                fallback = ActionChains(self.driver)
                if element:
                    fallback.move_to_element(element)
                else:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    fallback.move_to_element(body)
                fallback.perform()
            except Exception:
                pass
    
    def human_mouse_movement(self, target_element=None, intensity: Optional[str] = None, 
                           behavior_profile: Optional[Dict[str, Any]] = None):
        """
        Simulate human-like mouse movement with Bezier curves and behavior-based adjustments.
        
        Args:
            target_element: Optional target element to move to
            intensity: Override intensity ("low", "medium", "high")
            behavior_profile: Behavior profile for anti-detection integration
        """
        try:
            if behavior_profile:
                effective_intensity = intensity or behavior_profile.get('mouse_intensity', self.current_behavior_profile['mouse_intensity'])
            else:
                effective_intensity = intensity or self.current_behavior_profile['mouse_intensity']
            
            actions = ActionChains(self.driver)
            window_size = self.driver.get_window_size()
            window_width = window_size.get("width", 1920)
            window_height = window_size.get("height", 1080)
            
            # Determine movement complexity based on intensity
            if effective_intensity == "low":
                num_points = random.randint(2, 3)
                max_offset = 20
                curve_smoothness = 0.3
            elif effective_intensity == "high":
                num_points = random.randint(5, 8)
                max_offset = 80
                curve_smoothness = 0.7
            else:  # medium
                num_points = random.randint(3, 5)
                max_offset = 40
                curve_smoothness = 0.5
            
            # If we have a target element, move to it with natural curve
            if target_element:
                try:
                    # Get element position
                    location = target_element.location_once_scrolled_into_view
                    size = target_element.size
                    target_x = location['x'] + size['width'] // 2
                    target_y = location['y'] + size['height'] // 2
                    
                    # Start from random position on screen
                    start_x = random.randint(100, window_width - 100)
                    start_y = random.randint(100, window_height - 100)
                    
                    # Create Bezier curve points with behavior-based smoothness
                    points = self._generate_bezier_curve(
                        start_x, start_y, 
                        target_x, target_y,
                        num_control_points=num_points,
                        smoothness=curve_smoothness
                    )
                    
                    # Move through points with variable speed
                    for i, (x, y) in enumerate(points):
                        if i == 0:
                            # First movement from current position
                            actions.move_by_offset(x - start_x, y - start_y)
                        else:
                            # Subsequent movements
                            actions.move_by_offset(x - points[i-1][0], y - points[i-1][1])
                        
                        # Variable speed (slower near target) adjusted by click speed
                        progress = i / len(points)
                        base_pause = 0.002
                        
                        if behavior_profile:
                            click_speed = behavior_profile.get('click_speed', 'normal')
                            if click_speed == 'slow':
                                base_pause *= 1.5
                            elif click_speed == 'fast':
                                base_pause *= 0.7
                        
                        pause_time = base_pause * (1 + progress * 2)
                        actions.pause(pause_time)
                    
                    # Update last known position
                    self.last_mouse_position = (target_x, target_y)
                    
                except Exception as e:
                    # Fallback to simple movement
                    actions.move_to_element(target_element)
                    self.logger.debug(f"Human mouse movement fallback: {e}")
            
            else:
                # Random wandering movement
                if self.last_mouse_position:
                    current_x, current_y = self.last_mouse_position
                else:
                    current_x, current_y = window_width // 2, window_height // 2
                
                for _ in range(num_points):
                    # Generate next point with random offset
                    next_x = current_x + random.randint(-max_offset, max_offset)
                    next_y = current_y + random.randint(-max_offset, max_offset)
                    
                    # Ensure within bounds
                    next_x = max(50, min(window_width - 50, next_x))
                    next_y = max(50, min(window_height - 50, next_y))
                    
                    actions.move_by_offset(next_x - current_x, next_y - current_y)
                    
                    # Pause based on intensity
                    if effective_intensity == 'low':
                        actions.pause(random.uniform(0.1, 0.3))
                    elif effective_intensity == 'high':
                        actions.pause(random.uniform(0.05, 0.15))
                    else:
                        actions.pause(random.uniform(0.08, 0.2))
                    
                    current_x, current_y = next_x
                
                self.last_mouse_position = (current_x, current_y)
            
            actions.perform()
            
            # Record click speed if available from behavior profile
            if behavior_profile and 'click_speed' in behavior_profile:
                self._record_behavior_metric('click_speed', behavior_profile['click_speed'])
            
            # Small pause after movement based on intensity
            if effective_intensity == 'low':
                time.sleep(random.uniform(0.2, 0.4))
            elif effective_intensity == 'high':
                time.sleep(random.uniform(0.05, 0.15))
            else:
                time.sleep(random.uniform(0.1, 0.3))
            
        except Exception as e:
            # Fallback to existing method
            self.logger.debug(f"Human mouse movement failed: {e}")
            self.random_mouse_movements(target_element, behavior_profile)
    
    def mouse_wander(self, duration_seconds: Optional[float] = None, behavior_profile: Optional[Dict[str, Any]] = None):
        """Random mouse wandering during idle/reading time with behavior-based adjustments."""
        try:
            if duration_seconds is None:
                # Determine duration based on engagement rate
                if behavior_profile:
                    engagement_rate = behavior_profile.get('engagement_rate', 0.3)
                    # Higher engagement = more focused = less wandering
                    base_duration = 2.0
                    duration_seconds = base_duration * (1 - engagement_rate * 0.5)
                else:
                    duration_seconds = random.uniform(1, 4)
            
            actions = ActionChains(self.driver)
            window_size = self.driver.get_window_size()
            window_width = window_size.get("width", 1920)
            window_height = window_size.get("height", 1080)
            
            # Start from current position or center
            if self.last_mouse_position:
                current_x, current_y = self.last_mouse_position
            else:
                current_x, current_y = window_width // 2, window_height // 2
            
            start_time = time.time()
            
            # Adjust movement frequency based on behavior
            if behavior_profile:
                mouse_intensity = behavior_profile.get('mouse_intensity', 'medium')
                if mouse_intensity == 'low':
                    movement_interval = 0.8
                elif mouse_intensity == 'high':
                    movement_interval = 0.3
                else:
                    movement_interval = 0.5
            else:
                movement_interval = 0.5
            
            next_movement_time = start_time + movement_interval
            
            while time.time() - start_time < duration_seconds:
                if time.time() >= next_movement_time:
                    # Small, subtle movements
                    if behavior_profile and behavior_profile.get('mouse_intensity') == 'high':
                        dx = random.randint(-20, 20)
                        dy = random.randint(-15, 15)
                    else:
                        dx = random.randint(-15, 15)
                        dy = random.randint(-10, 10)
                    
                    new_x = current_x + dx
                    new_y = current_y + dy
                    
                    # Keep within bounds
                    new_x = max(20, min(window_width - 20, new_x))
                    new_y = max(20, min(window_height - 20, new_y))
                    
                    actions.move_by_offset(dx, dy)
                    
                    # Pause based on intensity
                    if behavior_profile and behavior_profile.get('mouse_intensity') == 'low':
                        actions.pause(random.uniform(0.3, 0.7))
                    else:
                        actions.pause(random.uniform(0.1, 0.5))
                    
                    current_x, current_y = new_x
                    next_movement_time = time.time() + movement_interval
            
            actions.perform()
            self.last_mouse_position = (current_x, current_y)
            
        except Exception as e:
            self.logger.debug(f"Mouse wander failed: {e}")
    
    def _generate_bezier_curve(self, start_x: int, start_y: int, end_x: int, end_y: int, 
                              num_control_points: int = 3, smoothness: float = 0.5) -> List[Tuple[int, int]]:
        """Generate points along a Bezier curve with adjustable smoothness."""
        points = []
        
        # Create control points with smoothness adjustment
        control_points = []
        for i in range(num_control_points):
            # Distribute control points between start and end
            t = (i + 1) / (num_control_points + 1)
            
            # Base position along line
            base_x = start_x + (end_x - start_x) * t
            base_y = start_y + (end_y - start_y) * t
            
            # Add randomness scaled by smoothness (lower smoothness = more random)
            randomness_scale = 100 * (1 - smoothness)
            cx = base_x + random.randint(-int(randomness_scale), int(randomness_scale))
            cy = base_y + random.randint(-int(randomness_scale * 0.8), int(randomness_scale * 0.8))
            
            control_points.append((cx, cy))
        
        # Generate points along the curve
        num_steps = 20
        for i in range(num_steps + 1):
            t = i / num_steps
            
            # Quadratic Bezier interpolation
            if len(control_points) == 1:
                # Simple quadratic
                x = (1-t)**2 * start_x + 2*(1-t)*t * control_points[0][0] + t**2 * end_x
                y = (1-t)**2 * start_y + 2*(1-t)*t * control_points[0][1] + t**2 * end_y
            else:
                # Use first control point for simplicity
                x = (1-t)**2 * start_x + 2*(1-t)*t * control_points[0][0] + t**2 * end_x
                y = (1-t)**2 * start_y + 2*(1-t)*t * control_points[0][1] + t**2 * end_y
            
            points.append((int(x), int(y)))
        
        return points
    
    def simulate_navigation_error(self, driver, behavior_profile: Optional[Dict[str, Any]] = None) -> bool:
        """
        Simulate human browsing errors with behavior-based probability.
        
        Returns: True if error was simulated
        """
        try:
            # Base error probability
            base_error_prob = 0.08
            
            # Adjust based on behavior profile
            if behavior_profile:
                # Cautious personalities make fewer errors
                engagement_rate = behavior_profile.get('engagement_rate', 0.3)
                if engagement_rate < 0.25:  # Very cautious
                    base_error_prob *= 0.5
                elif engagement_rate > 0.6:  # Enthusiastic
                    base_error_prob *= 1.5
            
            error_type = random.choices(
                ["wrong_click", "unnecessary_back", "accidental_refresh", "scroll_error", "none"],
                weights=[base_error_prob * 0.4, base_error_prob * 0.3, 
                        base_error_prob * 0.2, base_error_prob * 0.1, 
                        1 - base_error_prob]
            )[0]
            
            if error_type == "none":
                return False
            
            if error_type == "wrong_click":
                success = self._simulate_wrong_click(driver, behavior_profile)
                if success:
                    self.navigation_error_count += 1
                return success
            
            elif error_type == "unnecessary_back":
                current_url = driver.current_url
                driver.back()
                time.sleep(random.uniform(1, 3))
                driver.forward()
                time.sleep(random.uniform(1, 2))
                self.navigation_error_count += 1
                return True
            
            elif error_type == "accidental_refresh":
                driver.refresh()
                time.sleep(random.uniform(2, 4))
                self.navigation_error_count += 1
                return True
            
            elif error_type == "scroll_error":
                # Scroll too far, then correct
                scroll_amount = random.randint(400, 800)
                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                time.sleep(random.uniform(0.5, 1.5))
                
                # Scroll back slightly
                correction = random.randint(100, 300)
                driver.execute_script(f"window.scrollBy(0, -{correction});")
                time.sleep(random.uniform(0.3, 0.8))
                
                self.navigation_error_count += 1
                return True
            
        except Exception as e:
            self.logger.debug(f"Navigation error simulation failed: {e}")
            return False
        
        return False
    
    def _simulate_wrong_click(self, driver, behavior_profile: Optional[Dict[str, Any]] = None) -> bool:
        """Click on a nearby but wrong element with behavior-based adjustments."""
        try:
            # Find all clickable elements
            clickables = driver.find_elements(By.CSS_SELECTOR, 
                                             "a, button, [role='button'], [onclick]")
            
            if len(clickables) < 2:
                return False
            
            # Get current URL before error
            original_url = driver.current_url
            
            # Choose a random wrong element (not the first one)
            wrong_element = random.choice(clickables[1:min(5, len(clickables))])

            # Skip elements without size/location or not visible
            try:
                if not wrong_element.is_displayed():
                    return False
                rect = wrong_element.rect or {}
                if rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
                    return False
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", wrong_element)
            except Exception:
                return False
            
            # Move mouse to wrong element with human-like movement
            self.human_mouse_movement(wrong_element, behavior_profile=behavior_profile)
            
            # Adjust click delay based on behavior
            if behavior_profile and behavior_profile.get('click_speed') == 'slow':
                time.sleep(random.uniform(0.4, 0.8))
            else:
                time.sleep(random.uniform(0.2, 0.5))
            
            try:
                wrong_element.click()
                
                # Wait time based on behavior
                if behavior_profile and behavior_profile.get('engagement_rate') > 0.5:
                    time.sleep(random.uniform(3, 5))  # Enthusiastic users explore longer
                else:
                    time.sleep(random.uniform(2, 4))
                
                # Check if we navigated away
                if driver.current_url != original_url:
                    # Go back to original page
                    driver.back()
                    time.sleep(random.uniform(1, 2))
                
                self.logger.debug("Simulated wrong click on element")
                return True
                
            except Exception:
                # Element might not be clickable
                return False
                
        except Exception as e:
            self.logger.debug(f"Wrong click simulation failed: {e}")
            return False

    
    def read_post_sequence(self, post_element, read_time_factor: float = 1.0, 
                          behavior_profile: Optional[Dict[str, Any]] = None) -> bool:
        """Simulate reading a post naturally with behavior-based adjustments."""
        try:
            if not self.driver:
                return False
            
            # Update behavior if coordinator is available
            if self.detection_evasion_coordinator and not behavior_profile:
                behavior_profile = self.detection_evasion_coordinator.get_behavior_for_action("view")
            
            # Move mouse to post with behavior-based intensity
            if behavior_profile:
                mouse_intensity = behavior_profile.get('mouse_intensity', 'medium')
            else:
                mouse_intensity = self.current_behavior_profile['mouse_intensity']
            
            self.human_mouse_movement(post_element, intensity=mouse_intensity, behavior_profile=behavior_profile)
            
            # Click on post (use browser_manager if available)
            if self.browser_manager:
                self.browser_manager.safe_click(self.driver, post_element)
            else:
                post_element.click()
                
            # Click delay based on behavior
            if behavior_profile and behavior_profile.get('click_speed') == 'slow':
                time.sleep(random.uniform(1.0, 2.0))
            else:
                time.sleep(random.uniform(0.8, 1.5))
            
            # Simulate reading time (longer for longer posts) adjusted by engagement
            base_read_time = random.uniform(8, 25)
            
            if behavior_profile:
                engagement_rate = behavior_profile.get('engagement_rate', 0.3)
                # Higher engagement = longer reading
                engagement_multiplier = 0.5 + engagement_rate
                base_read_time *= engagement_multiplier
            
            base_read_time *= read_time_factor
            time.sleep(base_read_time)
            
            # Record reading time for pattern analysis
            self._record_behavior_metric('reading_time', base_read_time)
            
            # Scroll through comments randomly with behavior-based pattern
            if behavior_profile:
                self.human_scroll(behavior_profile=behavior_profile)
            else:
                self.human_scroll(scroll_times=random.randint(2, 5))
            
            # Mouse wander while reading (probability based on behavior)
            wander_probability = 0.3
            if behavior_profile and behavior_profile.get('engagement_rate') < 0.25:
                wander_probability = 0.5  # Cautious readers wander more
            
            if random.random() < wander_probability:
                wander_duration = random.uniform(2, 5)
                self.mouse_wander(wander_duration, behavior_profile)
            
            # Occasionally upvote (probability based on engagement rate)
            upvote_probability = 0.2
            if behavior_profile:
                upvote_probability = behavior_profile.get('engagement_rate', 0.3) * 0.7
            
            if random.random() < upvote_probability:
                self.safe_upvote(behavior_profile)
            
            # Go back or close
            if self.driver:
                if random.random() > 0.5:
                    self.driver.back()
                else:
                    self.driver.execute_script("window.history.back();")
            
            time.sleep(random.uniform(1, 3))
            return True
            
        except Exception as e:
            self.logger.debug(f"Error in read_post_sequence: {e}")
            return False
    
    def safe_upvote(self, behavior_profile: Optional[Dict[str, Any]] = None) -> bool:
        """Safely upvote current post with behavior-based adjustments."""
        try:
            upvote_buttons = self.driver.find_elements(By.CSS_SELECTOR, "div.arrow.up")
            
            if upvote_buttons:
                # Determine upvote probability based on engagement rate
                upvote_probability = 0.7
                if behavior_profile:
                    engagement_rate = behavior_profile.get('engagement_rate', 0.3)
                    upvote_probability = 0.3 + engagement_rate * 0.4
                
                if random.random() < upvote_probability:
                    target = upvote_buttons[0]
                    
                    # Add mouse movement before clicking with behavior-based intensity
                    self.human_mouse_movement(target, behavior_profile=behavior_profile)
                    
                    # Click delay based on behavior
                    if behavior_profile and behavior_profile.get('click_speed') == 'slow':
                        time.sleep(random.uniform(0.2, 0.4))
                    else:
                        time.sleep(random.uniform(0.1, 0.3))
                    
                    if self.browser_manager:
                        self.browser_manager.safe_click(self.driver, target)
                    else:
                        target.click()
                    
                    # Post-click delay
                    if behavior_profile and behavior_profile.get('engagement_rate') > 0.5:
                        time.sleep(random.uniform(0.3, 0.6))  # Enthusiastic users pause after voting
                    else:
                        time.sleep(random.uniform(0.2, 0.5))
                    
                    return True
        except Exception as e:
            self.logger.debug(f"Upvote failed: {e}")
        
        return False
    
    def human_like_typing(self, element, text: str, behavior_profile: Optional[Dict[str, Any]] = None) -> bool:
        """Type text with human-like delays and occasional mistakes with behavior-based adjustments."""
        try:
            # Click the element first with mouse movement
            self.human_mouse_movement(element, behavior_profile=behavior_profile)
            
            # Click delay based on behavior
            if behavior_profile and behavior_profile.get('click_speed') == 'slow':
                time.sleep(random.uniform(0.2, 0.4))
            else:
                time.sleep(random.uniform(0.1, 0.3))
            
            if self.browser_manager:
                self.browser_manager.safe_click(self.driver, element)
            else:
                element.click()
                
            time.sleep(random.uniform(0.1, 0.3))
            
            # Clear field
            element.clear()
            time.sleep(random.uniform(0.1, 0.2))
            
            # Determine typing speed from behavior
            if behavior_profile:
                typing_speed = behavior_profile.get('typing_speed', 'normal')
                if typing_speed == 'slow':
                    base_delay = (0.1, 0.2)
                    mistake_probability = 0.03
                elif typing_speed == 'fast':
                    base_delay = (0.03, 0.08)
                    mistake_probability = 0.01
                else:  # normal
                    base_delay = (0.05, 0.15)
                    mistake_probability = 0.02
            else:
                base_delay = (0.05, 0.15)
                mistake_probability = 0.02
            
            # Type character by character with random delays
            for char in text:
                element.send_keys(char)
                
                # Variable typing speed
                time.sleep(random.uniform(*base_delay))
                
                # Occasional "typing mistakes" and corrections
                if random.random() < mistake_probability:
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(random.uniform(0.1, 0.3))
                    element.send_keys(char)  # Re-type the correct character
                    time.sleep(random.uniform(0.2, 0.4))
            
            time.sleep(random.uniform(0.1, 0.3))
            return True
            
        except Exception as e:
            self.logger.debug(f"Human typing failed: {e}")
            # Fallback: just send keys
            try:
                element.clear()
                element.send_keys(text)
                return True
            except:
                return False
    
    def simulate_reading_time(self, text_length_chars: int = 500, behavior_profile: Optional[Dict[str, Any]] = None) -> float:
        """Simulate reading time based on text length with behavior-based adjustments."""
        # Average reading speed: 200-300 words per minute
        # Let's estimate: 250 words per minute = ~1250 characters per minute
        words = max(1, text_length_chars / 5)  # Rough estimate: 5 chars per word
        reading_time_minutes = words / 250  # 250 wpm
        
        # Adjust based on behavior profile
        if behavior_profile:
            engagement_rate = behavior_profile.get('engagement_rate', 0.3)
            # Higher engagement = slower, more careful reading
            reading_time_minutes *= (0.8 + engagement_rate * 0.4)
        
        reading_time_seconds = reading_time_minutes * 60
        
        # Add randomness and cap
        reading_time_seconds = reading_time_seconds * random.uniform(0.7, 1.3)
        reading_time_seconds = min(reading_time_seconds, 180)  # Cap at 3 minutes
        reading_time_seconds = max(reading_time_seconds, 5)    # Minimum 5 seconds
        
        return reading_time_seconds
    
    def random_browsing_behavior(self, subreddit=None, behavior_profile: Optional[Dict[str, Any]] = None):
        """Simulate random browsing behavior with behavior-based adjustments."""
        actions = [
            lambda: self.scroll_randomly(behavior_profile),
            lambda: self.pause_thoughtfully(behavior_profile),
            lambda: self.check_other_posts(behavior_profile),
            lambda: self.view_comments_section(behavior_profile)
        ]
        
        # Determine number of actions based on engagement
        if behavior_profile:
            engagement_rate = behavior_profile.get('engagement_rate', 0.3)
            num_actions = int(2 + engagement_rate * 4)  # 2-6 actions
        else:
            num_actions = random.randint(2, 4)
        
        for _ in range(num_actions):
            action = random.choice(actions)
            action()
            time.sleep(random.uniform(1, 3))
            
            # Mouse wander between actions (probability based on behavior)
            wander_probability = 0.2
            if behavior_profile and behavior_profile.get('mouse_intensity') == 'high':
                wander_probability = 0.4
            
            if random.random() < wander_probability:
                self.mouse_wander(behavior_profile=behavior_profile)
    
    def scroll_randomly(self, behavior_profile: Optional[Dict[str, Any]] = None):
        """Random scroll up and down with behavior-based adjustments."""
        # Scroll down
        if behavior_profile:
            scroll_pattern = behavior_profile.get('scroll_pattern', 'smooth')
            if scroll_pattern == 'reader':
                scroll_down = random.randint(150, 400)
            elif scroll_pattern == 'jerky':
                scroll_down = random.randint(500, 900)
            else:  # smooth
                scroll_down = random.randint(300, 600)
        else:
            scroll_down = random.randint(200, 600)
        
        self.driver.execute_script(f"window.scrollBy(0, {scroll_down});")
        
        # Record scroll distance
        self._record_behavior_metric('scroll_distance', scroll_down)
        
        # Pause based on behavior
        if behavior_profile and behavior_profile.get('engagement_rate') > 0.5:
            time.sleep(random.uniform(1.0, 2.0))
        else:
            time.sleep(random.uniform(0.5, 1.5))
        
        # Sometimes scroll up a bit
        if random.random() > 0.7:
            scroll_up = random.randint(50, 200)
            self.driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
            time.sleep(random.uniform(0.3, 0.8))
            
            # Record scroll distance
            self._record_behavior_metric('scroll_distance', -scroll_up)
    
    def pause_thoughtfully(self, behavior_profile: Optional[Dict[str, Any]] = None):
        """Pause as if thinking or reading with behavior-based adjustments."""
        # Base pause time
        if behavior_profile:
            engagement_rate = behavior_profile.get('engagement_rate', 0.3)
            base_pause_mean = 5.0 * (0.5 + engagement_rate)  # 2.5-7.5 seconds mean
        else:
            base_pause_mean = 5.0
        
        pause_time = random.expovariate(1.0 / base_pause_mean)
        pause_time = min(pause_time, 20)  # Cap at 20 seconds
        time.sleep(pause_time)
        
        # Mouse wander during pause (probability based on behavior)
        wander_probability = 0.4
        if behavior_profile and behavior_profile.get('mouse_intensity') == 'high':
            wander_probability = 0.6
        
        if random.random() < wander_probability:
            self.mouse_wander(min(3, pause_time / 2), behavior_profile)
    
    def check_other_posts(self, behavior_profile: Optional[Dict[str, Any]] = None):
        """Glance at other posts with behavior-based adjustments."""
        self.scroll_randomly(behavior_profile)
    
    def view_comments_section(self, behavior_profile: Optional[Dict[str, Any]] = None):
        """Scroll through comments section with behavior-based adjustments."""
        try:
            # Find comments
            comments_sections = self.driver.find_elements(By.CSS_SELECTOR, "div.comment")
            if comments_sections:
                # Scroll through first few comments
                scrolls = random.randint(2, 5)
                for _ in range(scrolls):
                    scroll_distance = 300
                    self.driver.execute_script(f"window.scrollBy(0, {scroll_distance});")
                    
                    # Record scroll distance
                    self._record_behavior_metric('scroll_distance', scroll_distance)
                    
                    # Pause based on behavior
                    if behavior_profile and behavior_profile.get('engagement_rate') > 0.5:
                        time.sleep(random.uniform(1.0, 2.0))
                    else:
                        time.sleep(random.uniform(0.8, 1.5))
        except Exception as e:
            self.logger.debug(f"View comments section failed: {e}")
    
    def realistic_navigation(self, url: str, behavior_profile: Optional[Dict[str, Any]] = None):
        """Navigate to a URL with realistic delays and behavior-based adjustments."""
        # Add random delay before navigation (like thinking)
        if behavior_profile and behavior_profile.get('click_speed') == 'slow':
            time.sleep(random.uniform(2, 4))
        else:
            time.sleep(random.uniform(1, 3))
        
        # Navigate
        self.driver.get(url)
        
        # Random delay after page load
        if behavior_profile and behavior_profile.get('engagement_rate') > 0.5:
            time.sleep(random.uniform(3, 6))
        else:
            time.sleep(random.uniform(2, 5))
        
        # Random scroll to simulate reading
        self.scroll_randomly(behavior_profile)
        
        # Mouse wander after navigation (probability based on behavior)
        wander_probability = 0.3
        if behavior_profile and behavior_profile.get('mouse_intensity') == 'high':
            wander_probability = 0.5
        
        if random.random() < wander_probability:
            self.mouse_wander(random.uniform(1, 3), behavior_profile)
    
    def simulate_human_session(self, duration_minutes: int = 15, behavior_profile: Optional[Dict[str, Any]] = None):
        """Simulate a complete human browsing session with behavior-based adjustments."""
        start_time = time.time()
        session_end = start_time + (duration_minutes * 60)
        
        activities_log = []
        
        # Update behavior if coordinator is available
        if self.detection_evasion_coordinator and not behavior_profile:
            behavior_profile = self.detection_evasion_coordinator.get_behavior_for_action("browse")
        
        while time.time() < session_end:
            # Choose a random activity
            activity_type = random.choice([
                "browse_homepage",
                "view_subreddit",
                "read_post",
                "scroll_comments",
                "check_profile",
                "search_topic"
            ])
            
            if activity_type == "browse_homepage":
                self.driver.get("https://old.reddit.com")
                scroll_distances = self.human_scroll(behavior_profile=behavior_profile)
                activities_log.append(f"browsed homepage (scrolled {sum(scroll_distances)}px)")
                
            elif activity_type == "read_post":
                # Try to find and read a post
                posts = self.driver.find_elements(By.CSS_SELECTOR, "div.thing")
                if posts:
                    post = random.choice(posts[:5])
                    target = None
                    try:
                        target = post.find_element(By.CSS_SELECTOR, "a.title")
                    except Exception:
                        target = post
                    
                    if self.read_post_sequence(target, behavior_profile=behavior_profile):
                        activities_log.append("read post")
            
            # Simulate navigation error (probability based on behavior)
            error_probability = 0.03
            if behavior_profile and behavior_profile.get('engagement_rate') < 0.25:
                error_probability = 0.05  # Cautious users make more errors?
            
            if random.random() < error_probability:
                if self.simulate_navigation_error(self.driver, behavior_profile):
                    activities_log.append("navigation error")
            
            # Mouse wander between activities (probability based on behavior)
            wander_probability = 0.25
            if behavior_profile and behavior_profile.get('mouse_intensity') == 'high':
                wander_probability = 0.4
            
            if random.random() < wander_probability:
                self.mouse_wander(random.uniform(1, 4), behavior_profile)
            
            # Random delay between activities
            if behavior_profile:
                engagement_rate = behavior_profile.get('engagement_rate', 0.3)
                base_delay_mean = 2.0 * (1.5 - engagement_rate)  # 1-3 seconds mean
            else:
                base_delay_mean = 2.0
            
            delay = random.expovariate(1.0 / base_delay_mean)
            delay = min(delay, 15)  # Cap at 15 seconds
            time.sleep(delay)
        
        return activities_log
    
    def get_behavior_metrics(self) -> Dict[str, Any]:
        """Get collected behavior metrics for pattern analysis."""
        return {
            'metrics': self.behavior_metrics,
            'navigation_errors': self.navigation_error_count,
            'current_profile': self.current_behavior_profile,
            'timestamp': datetime.now().isoformat()
        }
    
    def update_behavior_profile(self, profile: Dict[str, Any]):
        """Update the current behavior profile."""
        self.current_behavior_profile.update(profile)
        self.logger.debug(f"Updated behavior profile: {self.current_behavior_profile}")


# Global driver reference for backward compatibility
driver = None

# For backward compatibility
def set_driver(d):
    global driver
    driver = d