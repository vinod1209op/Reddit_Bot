#!/usr/bin/env python3
"""
Unified Reddit Bot - Can use either PRAW API or Selenium
"""

import sys
import os
import time
import traceback
import signal
from pathlib import Path
from typing import Optional, Tuple, Any

# Setup signal handlers for graceful shutdown
def signal_handler(sig: int, frame: Any) -> None:
    """Handle Ctrl+C gracefully"""
    print("\n\n⚠️  Bot shutdown requested. Cleaning up...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Add project root to Python path (at beginning, not removing current dir)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def setup_imports() -> Tuple['ConfigManager', 'UnifiedLogger']:
    """Setup proper imports based on mode"""
    try:
        from shared.config_manager import ConfigManager
        from shared.logger import UnifiedLogger
        
        config = ConfigManager().load_env()
        logger = UnifiedLogger().get_logger()
        
        return config, logger
    except ImportError as e:
        print(f"Import error in setup_imports: {e}")
        print("\nMake sure you have __init__.py files in shared/ and other directories")
        raise

def run_selenium_mode(config):
    """Run using Selenium"""
    print("\n" + "="*50)
    print("Starting Selenium Mode")
    print("="*50)
    
    # Check if selenium is available
    try:
        from selenium import webdriver
        selenium_package_available = True
    except ImportError:
        selenium_package_available = False
        print("Error: Selenium package is not installed.")
        print("Install with: pip install selenium webdriver-manager undetected-chromedriver")
        return
    
    bot = None
    try:
        # Import Selenium bot
        from selenium_automation.main import RedditAutomation
        
        bot = RedditAutomation(config=config)
        print("Setting up browser...")
        if not bot.setup():
            print("✗ Browser setup failed!")
            return
        
        print("Logging in...")
        if bot.login():
            print("✓ Login successful!")
            
            # Run Selenium tasks
            print("\n" + "="*50)
            print("Running Selenium Tasks")
            print("="*50)

            # Auto-save cookies for next run (best-effort)
            try:
                if hasattr(bot, "save_login_cookies"):
                    bot.save_login_cookies()
                    print("✓ Session cookies saved for future runs.")
            except Exception as e:
                print(f"Could not save cookies automatically: {e}")
            
            # 1. Check messages
            print("\n1. Checking messages...")
            messages = bot.check_messages()
            print(f"   Found {len(messages)} relevant messages")
            
            # 2. Search for posts
            print("\n2. Searching for posts...")
            posts = bot.search_posts(limit=10, include_body=False, include_comments=False)
            print(f"   Found {len(posts)} posts")
            
            # Display found posts
            if posts:
                print("\n" + "-"*50)
                print("RECENT POSTS FOUND:")
                print("-"*50)
                for i, post in enumerate(posts[:5], 1):  # Show first 5
                    title = post.get('title', 'No title')
                    if len(title) > 60:
                        title = title[:57] + "..."
                    subreddit = post.get('subreddit', 'unknown')
                    url = post.get('url') or f"https://reddit.com/r/{subreddit}"
                    print(f"{i}. r/{subreddit}: {title}\n   {url}")
                print("-"*50)
            
            # 3. Ask user what to do next
            print("\n" + "="*50)
            print("SELENIUM MENU")
            print("="*50)
            print("What would you like to do?")
            print("1. View more posts")
            print("2. Search specific subreddit")
            print("3. Check messages again")
            print("4. Prefill a reply (Selenium, manual submit)")
            print("5. Keep browser open for manual use")
            print("6. Exit and close browser")
            
            while True:
                choice = input("\nEnter choice (1-6, default 5): ").strip() or "5"
                
                if choice == "1":
                    limit = input("How many posts to view? (default 20): ").strip()
                    limit = int(limit) if limit.isdigit() else 20
                    posts = bot.search_posts(limit=limit, include_body=False, include_comments=False)
                    print(f"Found {len(posts)} posts")
                    if posts:
                        for i, post in enumerate(posts[:10], 1):
                            title = post.get('title', 'No title')
                            if len(title) > 80:
                                title = title[:77] + "..."
                            url = post.get('url') or ""
                            print(f"{i}. {title}")
                            if url:
                                print(f"   {url}")
                
                elif choice == "2":
                    subreddit = input("Enter subreddit name (default 'microdosing'): ").strip() or "microdosing"
                    limit = input("How many posts? (default 15): ").strip()
                    limit = int(limit) if limit.isdigit() else 15
                    posts = bot.search_posts(subreddit=subreddit, limit=limit, include_body=False, include_comments=False)
                    print(f"Found {len(posts)} posts in r/{subreddit}")
                    if posts:
                        for i, post in enumerate(posts[:10], 1):
                            title = post.get('title', 'No title')
                            if len(title) > 80:
                                title = title[:77] + "..."
                            url = post.get('url') or ""
                            print(f"{i}. {title}")
                            if url:
                                print(f"   {url}")
                
                elif choice == "3":
                    print("Checking messages...")
                    messages = bot.check_messages()
                    print(f"Found {len(messages)} relevant messages")
                
                elif choice == "4":
                    url = input("Enter full post URL to prefill reply on: ").strip()
                    use_llm_choice = input("Use LLM to generate reply? (y/N): ").strip().lower() == "y"
                    reply_text = ""
                    if use_llm_choice:
                        use_page_context = input("Use page title/body as context? (y/N): ").strip().lower() == "y"
                        if use_page_context:
                            context = bot.fetch_post_context(url)
                            if not context:
                                print("Could not fetch page context; falling back to manual context.")
                                context = input("Enter brief context for the reply (optional): ").strip() or "Provide a concise, supportive, safe reply."
                        else:
                            context = input("Enter brief context for the reply (optional): ").strip() or "Provide a concise, supportive, safe reply."
                        llm_text = bot.generate_llm_reply(context)
                        if llm_text:
                            reply_text = llm_text
                            print("\nGenerated reply:\n")
                            print(reply_text)
                        else:
                            print("LLM generation unavailable; falling back to manual text.")
                    if not reply_text:
                        reply_text = input("Enter reply text to prefill (will NOT submit): ").strip()
                    result = bot.reply_to_post(url, reply_text, dry_run=True)
                    if result.get("success"):
                        print("Reply text filled in the browser. Please review and click submit manually.")
                    else:
                        print(f"Failed to prefill: {result.get('error', 'unknown error')}")
                
                elif choice == "5":
                    print("\n" + "="*50)
                    print("Browser will remain open for manual use.")
                    print("You can now use the browser manually.")
                    print("Close the browser window when done, or")
                    print("return here and choose option 5 to close.")
                    print("="*50 + "\n")
                    
                    # Keep browser open indefinitely
                    while True:
                        action = input("Enter 'close' to close browser, or press Enter to keep open: ").strip().lower()
                        if action == 'close':
                            break
                        else:
                            print("Browser still open. Enter 'close' when ready.")
                    break
                
                elif choice == "6":
                    print("Closing browser...")
                    break
                
                else:
                    print("Invalid choice. Please try again.")
            
        else:
            print("✗ Login failed!")
            
    except ImportError as e:
        print(f"Import error: {e}")
        print("\nTroubleshooting:")
        print("1. Check if selenium_automation/main.py exists")
        print("2. Check if selenium_automation/__init__.py exists")
        print("3. Run: pip install selenium webdriver-manager undetected-chromedriver")
    except KeyboardInterrupt:
        print("\n\nBot stopped by user.")
    except Exception as e:
        print(f"Error in Selenium mode: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if bot:
            bot.close()
        
def run_api_mode(config: 'ConfigManager') -> None:
    """Run using PRAW API"""
    print("\n" + "="*50)
    print("Starting API Mode (PRAW)")
    print("="*50)
    
    try:
        # Import PRAW modules
        import praw
        from api.bot_step3_replies import main as api_main
        
        # Check credentials
        if not config.api_creds.get("client_id") or not config.api_creds.get("client_secret"):
            print("Error: Missing API credentials in credentials.env")
            print("Please set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
            return
        
        print("Running API bot...")
        # Set environment variables for the API script
        # FIXED: Use setdefault to avoid overwriting existing env vars
        env_vars = {
            'REDDIT_CLIENT_ID': config.api_creds.get("client_id", ""),
            'REDDIT_CLIENT_SECRET': config.api_creds.get("client_secret", ""),
            'REDDIT_USERNAME': config.api_creds.get("username", ""),
            'REDDIT_PASSWORD': config.api_creds.get("password", ""),
            'REDDIT_USER_AGENT': config.api_creds.get("user_agent", "bot:microdosing_research:v1.0")
        }
        
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)
        
        # Run the API bot
        api_main()
        
    except ImportError:
        print("PRAW not installed. Install with: pip install praw prawcore")
        traceback.print_exc()
    except KeyboardInterrupt:
        print("\n\nAPI bot stopped by user.")
        raise
    except Exception as e:
        print(f"Error in API mode: {e}")
        traceback.print_exc()

def test_connection() -> None:
    """Test system connection and dependencies"""
    try:
        config, logger = setup_imports()
        config.print_summary()
        
        print("\n" + "="*50)
        print("Testing credentials and dependencies...")
        
        # Test credentials - using method that exists
        if (config.api_creds.get("client_id") and 
            config.api_creds.get("client_secret") and 
            config.api_creds.get("username") and 
            config.api_creds.get("password")):
            print("✓ API credentials are set")
        else:
            print("✗ Missing some API credentials")
        
        # Test Selenium
        try:
            from selenium import webdriver
            print("✓ Selenium package is installed")
        except ImportError:
            print("✗ Selenium package is NOT installed")
            
        # Test PRAW
        try:
            import praw
            print("✓ PRAW is installed")
        except ImportError:
            print("✗ PRAW is NOT installed")
        
        # Test our selenium module
        try:
            from selenium_automation.main import RedditAutomation
            print("✓ selenium_automation/main.py can be imported")
        except ImportError as e:
            print(f"✗ Cannot import selenium_automation/main.py: {e}")
        
        # Test our shared modules
        try:
            from shared.safety_checker import SafetyChecker
            print("✓ shared/safety_checker.py can be imported")
        except ImportError as e:
            print(f"✗ Cannot import shared/safety_checker.py: {e}")
            
        print("="*50)
    except Exception as e:
        print(f"Error during connection test: {e}")
        traceback.print_exc()

def interactive_mode() -> None:
    """Interactive menu"""
    config, logger = None, None
    
    try:
        config, logger = setup_imports()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        print("Please check your setup and try again.")
        return
    
    while True:
        print("\n" + "="*50)
        print("REDDIT BOT - INTERACTIVE MODE")
        print("="*50)
        print("1. Run Selenium Bot")
        print("2. Run API Bot (PRAW)")
        print("3. Test Connection & Dependencies")
        print("4. View Configuration")
        print("5. Exit")
        print("="*50)
        
        try:
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == "1":
                run_selenium_mode(config)
                
            elif choice == "2":
                run_api_mode(config)
                
            elif choice == "3":
                test_connection()
                
            elif choice == "4":
                config.print_summary()
                
            elif choice == "5":
                print("Exiting...")
                break
                
            else:
                print("Invalid choice. Please try again.")
                
        except KeyboardInterrupt:
            print("\n\nReturning to main menu...")
            continue
        except Exception as e:
            print(f"Error in interactive mode: {e}")
            traceback.print_exc()
            print("\nReturning to main menu...")

def validate_config(config: 'ConfigManager') -> bool:
    """Validate configuration before running"""
    print("\n" + "="*50)
    print("Configuration Validation")
    print("="*50)
    
    issues = []
    
    # Check if we have any login credentials
    has_reddit_creds = config.api_creds.get("username") and config.api_creds.get("password")
    has_google_creds = False
    
    # Check for Google credentials in config
    if hasattr(config, 'google_creds'):
        has_google_creds = config.google_creds.get("google_email") and config.google_creds.get("google_password")
    else:
        # Try to get from api_creds as fallback
        has_google_creds = config.api_creds.get("google_email") and config.api_creds.get("google_password")
    
    if not has_reddit_creds and not has_google_creds:
        issues.append("Missing login credentials. Need either Reddit username/password OR Google email/password")
    
    # Check essential directories
    required_dirs = ["config", "shared", "logs"]
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            issues.append(f"Missing directory: {dir_name}/")
    
    # Check essential config files (warn instead of error)
    recommended_files = [
        ("config/credentials.env", "credentials configuration"),
        ("config/keywords.json", "keywords configuration"),
        ("config/subreddits.json", "subreddits configuration")
    ]
    
    for file_path, description in recommended_files:
        full_path = project_root / file_path
        if not full_path.exists():
            print(f"⚠️  Warning: Missing {description} file: {file_path}")
    
    if issues:
        print("❌ Configuration issues found:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nPlease fix these issues before running the bot.")
        return False
    else:
        print("✅ Configuration validated successfully!")
        return True

def main() -> None:
    """Main function"""
    print("\n" + "="*50)
    print("REDDIT AUTOMATION BOT")
    print("="*50)
    
    try:
        # Setup
        config, logger = setup_imports()
        
        # Validate configuration
        if not validate_config(config):
            print("\nCannot proceed with invalid configuration.")
            print("Please fix the issues above and try again.")
            return
        
        # Show configuration
        config.print_summary()
        
        # Check if we should run in interactive mode
        print("\nChoose operation mode:")
        print("1. Interactive Mode (Recommended)")
        print("2. Auto-run Selenium")
        print("3. Auto-run API")
        print("4. Exit")
        
        try:
            mode_choice = input("\nEnter choice (1-4, default 1): ").strip() or "1"
            
            if mode_choice == "1":
                interactive_mode()
            elif mode_choice == "2":
                run_selenium_mode(config)
            elif mode_choice == "3":
                run_api_mode(config)
            elif mode_choice == "4":
                print("Exiting...")
                return
            else:
                print("Invalid choice. Running interactive mode...")
                interactive_mode()
                
        except KeyboardInterrupt:
            print("\n\nBot stopped by user.")
            
    except KeyboardInterrupt:
        print("\n\nBot stopped by user.")
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        print("\nTroubleshooting steps:")
        print("1. Make sure all directories have __init__.py files")
        print("2. Install dependencies: pip install -r requirements.txt")
        print("3. Check your credentials.env file")
        print("4. Run in test mode: python unified_bot.py (choose option 3)")
        traceback.print_exc()

if __name__ == "__main__":
    main()
