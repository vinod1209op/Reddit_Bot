"""
Purpose: Simulate human-like browsing actions in Selenium sessions.
Constraints: No posting logic; timing-only helpers.
"""

# Imports
import random
import time
import math
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import MoveTargetOutOfBoundsException, NoSuchElementException, StaleElementReferenceException

# Public API
class HumanSimulator:
    def __init__(self, driver, browser_manager=None):
        self.driver = driver
        self.browser_manager = browser_manager
        self.last_mouse_position = None  # Track last known mouse position (x, y)
        
    def human_scroll(self, scroll_times=3):
        """Random scroll patterns with human-like pauses"""
        for i in range(random.randint(1, scroll_times)):
            # Smooth scroll with random pattern
            scroll_amount = random.randint(200, 1000)
            self.driver.execute_script(f"""
                window.scrollBy({{
                    top: {scroll_amount},
                    behavior: 'smooth'
                }});
            """)
            
            # Random pause (exponential distribution for realism)
            pause_time = random.expovariate(1.0/3)  # Mean 3 seconds
            pause_time = min(pause_time, 8)  # Cap at 8 seconds
            time.sleep(pause_time)
            
            # Occasionally scroll up slightly (like real reading)
            if random.random() > 0.7:
                self.driver.execute_script("window.scrollBy(0, -150);")
                time.sleep(random.uniform(0.5, 1.5))
    
    def random_mouse_movements(self, element=None):
        """Create natural mouse movements"""
        try:
            actions = ActionChains(self.driver)
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
                max_x = max(1, int(window.get("width", 800)) - 5)
                max_y = max(1, int(window.get("height", 600)) - 5)
                actions.move_to_element_with_offset(
                    body,
                    random.randint(5, max_x),
                    random.randint(5, max_y),
                )

            for _ in range(random.randint(2, 5)):
                actions.move_by_offset(random.randint(-15, 15), random.randint(-10, 10))
                if random.random() > 0.6:
                    actions.pause(random.uniform(0.05, 0.2))
            actions.perform()
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
    
    def human_mouse_movement(self, target_element=None, intensity="medium"):
        """
        Simulate human-like mouse movement with Bezier curves
        intensity: "low", "medium", "high" - controls movement complexity
        """
        try:
            actions = ActionChains(self.driver)
            window_size = self.driver.get_window_size()
            window_width = window_size.get("width", 1920)
            window_height = window_size.get("height", 1080)
            
            # Determine movement complexity based on intensity
            if intensity == "low":
                num_points = random.randint(2, 3)
                max_offset = 20
            elif intensity == "high":
                num_points = random.randint(5, 8)
                max_offset = 80
            else:  # medium
                num_points = random.randint(3, 5)
                max_offset = 40
            
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
                    
                    # Create Bezier curve points
                    points = self._generate_bezier_curve(
                        start_x, start_y, 
                        target_x, target_y,
                        num_control_points=num_points
                    )
                    
                    # Move through points with variable speed
                    for i, (x, y) in enumerate(points):
                        if i == 0:
                            # First movement from current position
                            actions.move_by_offset(x - start_x, y - start_y)
                        else:
                            # Subsequent movements
                            actions.move_by_offset(x - points[i-1][0], y - points[i-1][1])
                        
                        # Variable speed (slower near target)
                        progress = i / len(points)
                        pause_time = random.uniform(0.001, 0.003) * (1 + progress * 2)
                        actions.pause(pause_time)
                    
                    # Update last known position
                    self.last_mouse_position = (target_x, target_y)
                    
                except Exception as e:
                    # Fallback to simple movement
                    actions.move_to_element(target_element)
            
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
                    actions.pause(random.uniform(0.05, 0.2))
                    
                    current_x, current_y = next_x
                
                self.last_mouse_position = (current_x, current_y)
            
            actions.perform()
            time.sleep(random.uniform(0.1, 0.3))  # Small pause after movement
            
        except Exception as e:
            # Fallback to existing method
            self.random_mouse_movements(target_element)
    
    def mouse_wander(self, duration_seconds=3):
        """Random mouse wandering during idle/reading time"""
        try:
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
            while time.time() - start_time < duration_seconds:
                # Small, subtle movements
                dx = random.randint(-15, 15)
                dy = random.randint(-10, 10)
                
                new_x = current_x + dx
                new_y = current_y + dy
                
                # Keep within bounds
                new_x = max(20, min(window_width - 20, new_x))
                new_y = max(20, min(window_height - 20, new_y))
                
                actions.move_by_offset(dx, dy)
                actions.pause(random.uniform(0.1, 0.5))
                
                current_x, current_y = new_x
            
            actions.perform()
            self.last_mouse_position = (current_x, current_y)
            
        except Exception as e:
            pass  # Silent fail for wandering
    
    def _generate_bezier_curve(self, start_x, start_y, end_x, end_y, num_control_points=3):
        """Generate points along a Bezier curve"""
        points = []
        
        # Create control points
        control_points = []
        for i in range(num_control_points):
            # Distribute control points between start and end
            t = (i + 1) / (num_control_points + 1)
            cx = start_x + (end_x - start_x) * t + random.randint(-100, 100)
            cy = start_y + (end_y - start_y) * t + random.randint(-80, 80)
            control_points.append((cx, cy))
        
        # Generate points along the curve
        num_steps = 20
        for i in range(num_steps + 1):
            t = i / num_steps
            
            # Quadratic Bezier (can be extended to higher order)
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
    
    def simulate_navigation_error(self, driver):
        """
        Simulate human browsing errors:
        - Wrong clicks (clicks near but not on target)
        - Unnecessary back/forward
        - Accidental refresh
        - Scroll too far
        Returns: True if error was simulated
        """
        try:
            error_type = random.choices(
                ["wrong_click", "unnecessary_back", "accidental_refresh", "scroll_error", "none"],
                weights=[0.3, 0.25, 0.2, 0.2, 0.05]  # 5% chance of no error
            )[0]
            
            if error_type == "none":
                return False
            
            if error_type == "wrong_click":
                success = self._simulate_wrong_click(driver)
                if success:
                    self.navigation_error_count += 1
                    print(f"⚠️ [HumanSim] Navigation error: wrong click (total: {self.navigation_error_count})")
                return success
            
            elif error_type == "unnecessary_back":
                current_url = driver.current_url
                driver.back()
                time.sleep(random.uniform(1, 3))
                driver.forward()
                time.sleep(random.uniform(1, 2))
                self.navigation_error_count += 1
                print(f"⚠️ [HumanSim] Navigation error: unnecessary back/forward (total: {self.navigation_error_count})")
                return True
            
            elif error_type == "accidental_refresh":
                driver.refresh()
                time.sleep(random.uniform(2, 4))
                self.navigation_error_count += 1
                print(f"⚠️ [HumanSim] Navigation error: accidental refresh (total: {self.navigation_error_count})")
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
                print(f"⚠️ [HumanSim] Navigation error: overscroll correction (total: {self.navigation_error_count})")
                return True
            
        except Exception as e:
            return False
        
        return False
    
    def _simulate_wrong_click(self, driver):
        """Click on a nearby but wrong element"""
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
            
            # Move mouse to wrong element with human-like movement
            self.human_mouse_movement(wrong_element, intensity="low")
            time.sleep(random.uniform(0.2, 0.5))
            
            try:
                wrong_element.click()
                time.sleep(random.uniform(2, 4))
                
                # Check if we navigated away
                if driver.current_url != original_url:
                    # Go back to original page
                    driver.back()
                    time.sleep(random.uniform(1, 2))
                
                self.log(f"Simulated wrong click on element")
                return True
                
            except Exception:
                # Element might not be clickable
                return False
                
        except Exception as e:
            self.log(f"Wrong click simulation failed: {e}")
            return False
    
    def log(self, message):
        """Helper for logging"""
        try:
            print(f"[HumanSimulator] {message}")
        except:
            pass
    
    def read_post_sequence(self, post_element, read_time_factor=1.0):
        """Simulate reading a post naturally"""
        try:
            if not self.driver:
                return False
            # Move mouse to post with human-like movement
            self.human_mouse_movement(post_element, intensity="medium")
            
            # Click on post (use browser_manager if available)
            if self.browser_manager:
                self.browser_manager.safe_click(self.driver, post_element)
            else:
                post_element.click()
                
            time.sleep(random.uniform(0.8, 1.5))
            
            # Simulate reading time (longer for longer posts)
            base_read_time = random.uniform(8, 25) * read_time_factor
            time.sleep(base_read_time)
            
            # Scroll through comments randomly
            self.human_scroll(scroll_times=random.randint(2, 5))
            
            # Mouse wander while reading (30% chance)
            if random.random() < 0.3:
                self.mouse_wander(random.uniform(2, 5))
            
            # Occasionally upvote
            if random.random() > 0.8:  # 20% chance
                self.safe_upvote()
            
            # Go back or close
            if self.driver:
                if random.random() > 0.5:
                    self.driver.back()
                else:
                    self.driver.execute_script("window.history.back();")
            
            time.sleep(random.uniform(1, 3))
            return True
            
        except Exception as e:
            print(f"Error in read_post_sequence: {e}")
            return False
    
    def safe_upvote(self):
        """Safely upvote current post (if enabled)"""
        try:
            upvote_buttons = driver.find_elements(By.CSS_SELECTOR, "div.arrow.up")
            if upvote_buttons and random.random() > 0.3:  # 70% chance to upvote if button found
                target = upvote_buttons[0]
                
                # Add mouse movement before clicking
                self.human_mouse_movement(target, intensity="low")
                time.sleep(random.uniform(0.1, 0.3))
                
                if self.browser_manager:
                    self.browser_manager.safe_click(driver, target)
                else:
                    target.click()
                time.sleep(random.uniform(0.2, 0.5))
                return True
        except Exception as e:
            pass  # Silently fail if can't vote
        return False
    
    def human_like_typing(self, element, text):
        """Type text with human-like delays and occasional mistakes"""
        try:
            # Click the element first with mouse movement
            self.human_mouse_movement(element, intensity="low")
            time.sleep(random.uniform(0.1, 0.3))
            
            if self.browser_manager:
                self.browser_manager.safe_click(driver, element)
            else:
                element.click()
                
            time.sleep(random.uniform(0.1, 0.3))
            
            # Clear field
            element.clear()
            time.sleep(random.uniform(0.1, 0.2))
            
            # Type character by character with random delays
            for char in text:
                element.send_keys(char)
                
                # Variable typing speed
                time.sleep(random.uniform(0.05, 0.15))
                
                # Occasional "typing mistakes" and corrections (2% chance)
                if random.random() > 0.98:
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(random.uniform(0.1, 0.3))
                    element.send_keys(char)  # Re-type the correct character
                    time.sleep(random.uniform(0.2, 0.4))
            
            time.sleep(random.uniform(0.1, 0.3))
            return True
            
        except Exception as e:
            print(f"Human typing failed: {e}")
            # Fallback: just send keys
            try:
                element.clear()
                element.send_keys(text)
                return True
            except:
                return False
    
    def simulate_reading_time(self, text_length_chars=500):
        """Simulate reading time based on text length"""
        # Average reading speed: 200-300 words per minute
        # Let's estimate: 250 words per minute = ~1250 characters per minute
        words = max(1, text_length_chars / 5)  # Rough estimate: 5 chars per word
        reading_time_minutes = words / 250  # 250 wpm
        reading_time_seconds = reading_time_minutes * 60
        
        # Add randomness and cap
        reading_time_seconds = reading_time_seconds * random.uniform(0.7, 1.3)
        reading_time_seconds = min(reading_time_seconds, 120)  # Cap at 2 minutes
        reading_time_seconds = max(reading_time_seconds, 3)    # Minimum 3 seconds
        
        return reading_time_seconds
    
    def random_browsing_behavior(self, subreddit=None):
        """Simulate random browsing behavior"""
        actions = [
            self.scroll_randomly,
            self.pause_thoughtfully,
            self.check_other_posts,
            self.view_comments_section
        ]
        
        # Perform 2-4 random actions
        num_actions = random.randint(2, 4)
        for _ in range(num_actions):
            action = random.choice(actions)
            action()
            time.sleep(random.uniform(1, 3))
            
            # Mouse wander between actions (20% chance)
            if random.random() < 0.2:
                self.mouse_wander(random.uniform(1, 3))
    
    def scroll_randomly(self):
        """Random scroll up and down"""
        # Scroll down
        scroll_down = random.randint(200, 600)
        driver.execute_script(f"window.scrollBy(0, {scroll_down});")
        time.sleep(random.uniform(0.5, 1.5))
        
        # Sometimes scroll up a bit
        if random.random() > 0.7:
            scroll_up = random.randint(50, 200)
            driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
            time.sleep(random.uniform(0.3, 0.8))
    
    def pause_thoughtfully(self):
        """Pause as if thinking or reading"""
        pause_time = random.expovariate(1.0/5)  # Mean 5 seconds
        pause_time = min(pause_time, 15)  # Cap at 15 seconds
        time.sleep(pause_time)
        
        # Mouse wander during pause (40% chance)
        if random.random() < 0.4:
            self.mouse_wander(min(3, pause_time / 2))
    
    def check_other_posts(self):
        """Glance at other posts"""
        # This could be implemented to click on related posts
        # For now, just scroll to see other posts
        self.scroll_randomly()
    
    def view_comments_section(self):
        """Scroll through comments section"""
        # Find comments section and scroll through it
        try:
            # Try to find comments
            comments_sections = driver.find_elements(By.CSS_SELECTOR, "div.comment")
            if comments_sections:
                # Scroll through first few comments
                for _ in range(random.randint(2, 5)):
                    driver.execute_script("window.scrollBy(0, 300);")
                    time.sleep(random.uniform(0.8, 1.5))
        except:
            pass
    
    def realistic_navigation(self, url):
        """Navigate to a URL with realistic delays"""
        # Add random delay before navigation (like thinking)
        time.sleep(random.uniform(1, 3))
        
        # Navigate
        driver.get(url)
        
        # Random delay after page load
        time.sleep(random.uniform(2, 5))
        
        # Random scroll to simulate reading
        self.scroll_randomly()
        
        # Mouse wander after navigation (30% chance)
        if random.random() < 0.3:
            self.mouse_wander(random.uniform(1, 3))
    
    def simulate_human_session(self, duration_minutes=15):
        """Simulate a complete human browsing session"""
        start_time = time.time()
        session_end = start_time + (duration_minutes * 60)
        
        activities_log = []
        
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
                driver.get("https://old.reddit.com")
                self.human_scroll(random.randint(3, 7))
                activities_log.append("browsed homepage")
                
            elif activity_type == "read_post":
                # Try to find and read a post
                posts = driver.find_elements(By.CSS_SELECTOR, "div.thing")
                if posts:
                    post = random.choice(posts[:5])
                    target = None
                    try:
                        target = post.find_element(By.CSS_SELECTOR, "a.title")
                    except Exception:
                        target = post
                    self.read_post_sequence(target)
                    activities_log.append("read post")
            
            # Simulate navigation error (3% chance per activity)
            if random.random() < 0.03:
                if self.simulate_navigation_error(driver):
                    activities_log.append("navigation error")
            
            # Mouse wander between activities (25% chance)
            if random.random() < 0.25:
                self.mouse_wander(random.uniform(1, 4))
            
            # Random delay between activities
            delay = random.expovariate(1.0/2)  # Mean 2 seconds
            delay = min(delay, 10)  # Cap at 10 seconds
            time.sleep(delay)
        
        return activities_log


# Global driver reference for backward compatibility
driver = None

# For backward compatibility
def set_driver(d):
    global driver
    driver = d