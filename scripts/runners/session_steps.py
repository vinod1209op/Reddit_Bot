#!/usr/bin/env python3
"""
Interactive session runner: pick steps (creation/moderation/posting) and repeat.
Keeps one browser/login session alive until you exit.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from microdose_study_bot.core.logging import UnifiedLogger
from scripts.subreddit_creation.create_subreddits import SubredditCreator
from scripts.moderation.manage_moderation import SeleniumModerationManager
from scripts.content_scheduling.schedule_posts import MCRDSEPostScheduler

logger = UnifiedLogger("SessionSteps").get_logger()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive session runner (reusable steps)")
    parser.add_argument("--account", required=True, help="Account name from config/accounts.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--bypass-creation-limits", action="store_true", help="Bypass creation limits/cooldowns")
    parser.add_argument("--bypass-posting-limits", action="store_true", help="Bypass posting limits/rate limits")
    args = parser.parse_args()

    logger.info("Starting interactive session for %s", args.account)
    if args.bypass_creation_limits:
        import os
        os.environ["BYPASS_CREATION_LIMITS"] = "1"
        os.environ["BYPASS_CREATION_COOLDOWN"] = "1"
    if args.bypass_posting_limits:
        import os
        os.environ["BYPASS_POSTING_LIMITS"] = "1"

    # Start a session with creation (owns browser/login)
    creator = SubredditCreator(
        account_name=args.account,
        headless=args.headless,
        dry_run=args.dry_run,
        ui_mode="modern",
        session=None,
        owns_session=True,
    )
    session = creator.export_session()

    moderator = None
    scheduler = None
    try:
        while True:
            print("\nChoose a step:")
            print("1) Subreddit creation")
            print("2) Moderation")
            print("3) Posting")
            print("4) Exit")
            choice = input("Select option (1-4): ").strip()

            if choice == "1":
                max_raw = input("Max subreddits to create (blank = default 2): ").strip()
                max_create = int(max_raw) if max_raw else 2
                import os
                os.environ["SKIP_CREATION_SETUP"] = "1"
                creator.run(max_subreddits=max_create, headless=args.headless, keep_open=True)
            elif choice == "2":
                if moderator is None:
                    moderator = SeleniumModerationManager(
                        account_name=args.account,
                        headless=args.headless,
                        dry_run=args.dry_run,
                        session=session,
                        owns_session=False,
                    )
                print("\nModeration options:")
                print("1) Setup moderation (AutoMod, flairs, rules)")
                print("2) Daily moderation (queues)")
                print("3) Back to main menu")
                mod_choice = input("Select option (1-3): ").strip()
                if mod_choice == "1":
                    moderator.setup_complete_moderation("Mental_Health_Hub")
                elif mod_choice == "2":
                    moderator.run_daily_moderation(["Mental_Health_Hub"])
                elif mod_choice == "3":
                    continue
                else:
                    print("Invalid choice. Returning to main menu.")
            elif choice == "3":
                if scheduler is None:
                    scheduler = MCRDSEPostScheduler(
                        account_name=args.account,
                        headless=args.headless,
                        dry_run=args.dry_run,
                        session=session,
                        owns_session=False,
                    )
                print("\nPosting options:")
                print("1) Process due scheduled posts")
                print("2) Post now (create one post immediately)")
                print("3) Back to main menu")
                post_choice = input("Select option (1-3): ").strip()
                if post_choice == "1":
                    schedule = scheduler.load_schedule()
                    if not schedule:
                        print("Schedule is empty. Generate posts now?")
                        count_raw = input("How many posts to generate? (default 5): ").strip()
                        days_raw = input("Schedule across how many days? (default 7): ").strip()
                        count = int(count_raw) if count_raw else 5
                        days = int(days_raw) if days_raw else 7
                        scheduler.generate_scheduled_posts(count, days)
                    scheduler.process_due_posts()
                elif post_choice == "2":
                    subreddit = input("Subreddit (blank = auto): ").strip() or None
                    post_type = input("Post type (discussion/question/resource/experience/news): ").strip().lower() or "discussion"
                    post = scheduler.generate_post_from_template(post_type, subreddit=subreddit)
                    post["scheduled_for"] = scheduler.generate_scheduled_time().isoformat()
                    # Force immediate submit
                    scheduler.submit_post(post)
                elif post_choice == "3":
                    continue
                else:
                    print("Invalid choice. Returning to main menu.")
            elif choice == "4":
                break
            else:
                print("Invalid choice. Please choose 1-4.")
    finally:
        creator.cleanup()


if __name__ == "__main__":
    main()
