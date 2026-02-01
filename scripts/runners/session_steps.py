#!/usr/bin/env python3
"""
Interactive session runner: pick steps (creation/moderation/posting) and repeat.
Keeps one browser/login session alive until you exit.
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime

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
    # Limits are always bypassed for testing in this runner.
    args = parser.parse_args()

    logger.info("Starting interactive session for %s", args.account)
    import os
    os.environ["BYPASS_CREATION_LIMITS"] = "1"
    os.environ["BYPASS_CREATION_COOLDOWN"] = "1"
    os.environ["BYPASS_POSTING_LIMITS"] = "1"
    os.environ["BYPASS_MODERATION_LIMITS"] = "1"
    os.environ["BYPASS_MODERATION_COOLDOWN"] = "1"
    os.environ["BYPASS_MODERATOR_CHECK"] = "1"

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
            print("4) Engagement")
            print("5) Exit")
            choice = input("Select option (1-5): ").strip()

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
                print("3) Refresh sidebar network links")
                print("4) Back to main menu")
                mod_choice = input("Select option (1-4): ").strip()
                if mod_choice == "1":
                    sub = input("Subreddit to set up (default Mental_Health_Hub): ").strip() or "Mental_Health_Hub"
                    moderator.setup_complete_moderation(sub)
                elif mod_choice == "2":
                    subs_raw = input("Comma-separated subreddits (default Mental_Health_Hub): ").strip()
                    subs = [s.strip() for s in subs_raw.split(",") if s.strip()] or ["Mental_Health_Hub"]
                    moderator.run_daily_moderation(subs)
                elif mod_choice == "3":
                    subs_raw = input("Comma-separated subreddits for sidebar refresh (default MindWellBeing, ClinicalMicrodosingHu, Mental_Health_Hub): ").strip()
                    subs = [s.strip() for s in subs_raw.split(",") if s.strip()] or ["MindWellBeing", "ClinicalMicrodosingHu", "Mental_Health_Hub"]
                    results = moderator.refresh_sidebar_network_links(subs)
                    print(f"Sidebar refresh results: {results}")
                elif mod_choice == "4":
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
                print("3) Seed network content (Phase 3)")
                print("4) Run content discovery (local queue)")
                print("5) Schedule weekly digests")
                print("6) Generate A/B report")
                print("7) Generate KPI dashboard")
                print("8) Schedule A/B title variations")
                print("9) Back to main menu")
                post_choice = input("Select option (1-9): ").strip()
                if post_choice == "1":
                    schedule = scheduler.load_schedule()
                    if not schedule:
                        print("Schedule is empty. Generate posts now?")
                        count_raw = input("How many posts to generate? (default 5): ").strip()
                        days_raw = input("Schedule across how many days? (default 7): ").strip()
                        count = int(count_raw) if count_raw else 5
                        days = int(days_raw) if days_raw else 7
                        scheduler.generate_scheduled_posts(count, days)
                    # Check if anything is due; if not, optionally fast-forward earliest post
                    due = scheduler.check_due_posts()
                    if not due:
                        earliest = min(
                            schedule,
                            key=lambda p: p.get("scheduled_for", "9999-12-31"),
                            default=None,
                        )
                        if earliest:
                            ans = input("No posts are due. Make the next scheduled post due now and process? (y/N): ").strip().lower()
                            if ans == "y":
                                earliest["scheduled_for"] = datetime.now().isoformat()
                                scheduler.save_schedule(schedule)
                                print(f"Fast-forwarded {earliest.get('id','?')} to now.")
                        else:
                            print("No posts scheduled; nothing to process.")
                    processed = scheduler.process_due_posts()
                    print(f"Processed {processed} post(s).")
                elif post_choice == "2":
                    subreddit = input("Subreddit (blank = auto): ").strip() or None
                    post_type = input("Post type (discussion/question/resource/experience/news): ").strip().lower() or "discussion"
                    post = scheduler.generate_post_from_template(post_type, subreddit=subreddit)
                    post["scheduled_for"] = scheduler.generate_scheduled_time().isoformat()
                    # Force immediate submit
                    scheduler.submit_post(post)
                elif post_choice == "3":
                    days_raw = input("Seed across how many days? (default 30): ").strip()
                    count_raw = input("Posts per subreddit? (blank = use network default): ").strip()
                    days = int(days_raw) if days_raw else 30
                    count = int(count_raw) if count_raw else None
                    targets = ["MindWellBeing", "ClinicalMicrodosingHu", "Mental_Health_Hub"]
                    seeded = scheduler.seed_network_content(
                        count_per_subreddit=count,
                        days=days,
                        subreddits=targets,
                    )
                    print(f"Seeded posts per subreddit: {seeded}")
                elif post_choice == "4":
                    max_raw = input("Max items from discovery queue? (default 5): ").strip()
                    max_items = int(max_raw) if max_raw else 5
                    created = scheduler.run_content_discovery(max_items=max_items)
                    print(f"Created {created} posts from discovery queue.")
                elif post_choice == "5":
                    weeks_raw = input("Weeks ahead to schedule? (default 4): ").strip()
                    weeks = int(weeks_raw) if weeks_raw else 4
                    count = scheduler.schedule_weekly_digest(weeks_ahead=weeks)
                    print(f"Scheduled {count} weekly digests.")
                elif post_choice == "6":
                    limit_raw = input("Report max rows? (default 100): ").strip()
                    limit = int(limit_raw) if limit_raw else 100
                    summary = scheduler.generate_ab_report(limit=limit)
                    print(f"Report generated: {summary.get('total_ab_posts', 0)} rows")
                elif post_choice == "7":
                    dashboard = scheduler.generate_kpi_dashboard()
                    print(f"KPI dashboard generated: posts={dashboard.get('posts', {})}")
                elif post_choice == "8":
                    post_type = input("Post type for A/B (discussion/question/resource/experience/news): ").strip().lower() or "discussion"
                    variations_raw = input("How many title variations? (default 3): ").strip()
                    variations = int(variations_raw) if variations_raw else 3
                    posts = scheduler.schedule_ab_title_variations(post_type, variations=variations)
                    print(f"Scheduled {len(posts)} A/B variants.")
                elif post_choice == "9":
                    continue
                else:
                    print("Invalid choice. Returning to main menu.")
            elif choice == "4":
                from scripts.engagement.engagement_program import EngagementProgram
                program = EngagementProgram()
                print("\nEngagement options:")
                print("1) Generate comment replies")
                print("2) Schedule monthly events")
                print("3) Generate recognition report")
                print("4) Generate cross-platform promo queues")
                print("5) Generate Reddit internal promo queue")
                print("6) Back to main menu")
                eng_choice = input("Select option (1-6): ").strip()
                if eng_choice == "1":
                    count_raw = input("How many replies? (default 3): ").strip()
                    count = int(count_raw) if count_raw else 3
                    replies = program.generate_comment_replies(count=count)
                    print("Replies:")
                    for r in replies:
                        print(f"- {r}")
                elif eng_choice == "2":
                    months_raw = input("Months ahead to schedule? (default 2): ").strip()
                    months = int(months_raw) if months_raw else 2
                    subs = ["MindWellBeing", "ClinicalMicrodosingHu", "Mental_Health_Hub"]
                    scheduler = scheduler or MCRDSEPostScheduler(
                        account_name=args.account,
                        headless=args.headless,
                        dry_run=args.dry_run,
                        session=session,
                        owns_session=False,
                    )
                    count = program.schedule_monthly_events(scheduler, subs, months_ahead=months)
                    print(f"Scheduled {count} monthly events.")
                elif eng_choice == "3":
                    report = program.generate_recognition_report(
                        Path("scripts/content_scheduling/schedule/post_schedule.json")
                    )
                    print(f"Recognition report generated with {len(report.get('featured_posts', []))} items.")
                elif eng_choice == "4":
                    from scripts.promotion.cross_platform_export import export as promo_export
                    result = promo_export()
                    print(f"Cross-platform queue generated: {result}")
                elif eng_choice == "5":
                    from scripts.promotion.reddit_internal_queue import generate as internal_export
                    result = internal_export()
                    print(f"Internal promo queue generated: {result.get('items', [])}")
                elif eng_choice == "6":
                    continue
                else:
                    print("Invalid choice. Returning to main menu.")
            elif choice == "5":
                break
            else:
                print("Invalid choice. Please choose 1-5.")
    finally:
        creator.cleanup()


if __name__ == "__main__":
    main()
