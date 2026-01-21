"""
Purpose: Simulate human-like browsing actions in Selenium sessions.
Constraints: No posting logic; timing-only helpers.
"""

# Imports
import random
import time
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import MoveTargetOutOfBoundsException

# Public API
class HumanSimulator:
    def __init__(self, driver, browser_manager=None):
        self.driver = driver
        self.browser_manager = browser_manager
    
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
    
    def read_post_sequence(self, post_element, read_time_factor=1.0):
        """Simulate reading a post naturally"""
        try:
            # Move mouse to post
            self.random_mouse_movements(post_element)
            
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
            
            # Occasionally upvote
            if random.random() > 0.8:  # 20% chance
                self.safe_upvote()
            
            # Go back or close
            if random.random() > 0.5:
                self.driver.back()
            else:
                # Close modal if applicable
                self.driver.execute_script("window.history.back();")
            
            time.sleep(random.uniform(1, 3))
            return True
            
        except Exception as e:
            print(f"Error in read_post_sequence: {e}")
            return False
    
    def safe_upvote(self):
        """Safely upvote current post (if enabled)"""
        try:
            upvote_buttons = self.driver.find_elements(By.CSS_SELECTOR, "div.arrow.up")
            if upvote_buttons and random.random() > 0.3:  # 70% chance to upvote if button found
                target = upvote_buttons[0]
                if self.browser_manager:
                    self.browser_manager.safe_click(self.driver, target)
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
            # Click the element first
            if self.browser_manager:
                self.browser_manager.safe_click(self.driver, element)
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
    
    def scroll_randomly(self):
        """Random scroll up and down"""
        # Scroll down
        scroll_down = random.randint(200, 600)
        self.driver.execute_script(f"window.scrollBy(0, {scroll_down});")
        time.sleep(random.uniform(0.5, 1.5))
        
        # Sometimes scroll up a bit
        if random.random() > 0.7:
            scroll_up = random.randint(50, 200)
            self.driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
            time.sleep(random.uniform(0.3, 0.8))
    
    def pause_thoughtfully(self):
        """Pause as if thinking or reading"""
        pause_time = random.expovariate(1.0/5)  # Mean 5 seconds
        pause_time = min(pause_time, 15)  # Cap at 15 seconds
        time.sleep(pause_time)
    
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
            comments_sections = self.driver.find_elements(By.CSS_SELECTOR, "div.comment")
            if comments_sections:
                # Scroll through first few comments
                for _ in range(random.randint(2, 5)):
                    self.driver.execute_script("window.scrollBy(0, 300);")
                    time.sleep(random.uniform(0.8, 1.5))
        except:
            pass
    
    def realistic_navigation(self, url):
        """Navigate to a URL with realistic delays"""
        # Add random delay before navigation (like thinking)
        time.sleep(random.uniform(1, 3))
        
        # Navigate
        self.driver.get(url)
        
        # Random delay after page load
        time.sleep(random.uniform(2, 5))
        
        # Random scroll to simulate reading
        self.scroll_randomly()
    
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
                self.driver.get("https://old.reddit.com")
                self.human_scroll(random.randint(3, 7))
                activities_log.append("browsed homepage")
                
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
                    self.read_post_sequence(target)
                    activities_log.append("read post")
            
            # Random delay between activities
            delay = random.expovariate(1.0/2)  # Mean 2 seconds
            delay = min(delay, 10)  # Cap at 10 seconds
            time.sleep(delay)
        
        return activities_log
