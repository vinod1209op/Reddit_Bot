#!/usr/bin/env python3
"""
Run subreddit creation, moderation, and posting in a single browser session.
Cookies/login persist across the entire run.
"""
import argparse
import sys

from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.logging import UnifiedLogger
from scripts.subreddit_creation.create_subreddits import SubredditCreator
from scripts.moderation.manage_moderation import SeleniumModerationManager
from scripts.content_scheduling.schedule_posts import MCRDSEPostScheduler

logger = UnifiedLogger("CombinedSessionManager").get_logger()


def main() -> None:
    parser = argparse.ArgumentParser(description="Combined session runner (creation → moderation → posting)")
    parser.add_argument("--account", required=True, help="Account name from config/accounts.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without executing")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--skip-creation", action="store_true", help="Skip subreddit creation")
    parser.add_argument("--skip-moderation", action="store_true", help="Skip moderation")
    parser.add_argument("--skip-posting", action="store_true", help="Skip posting")
    parser.add_argument("--max-create", type=int, default=None, help="Max subreddits to create")
    args = parser.parse_args()

    cfg = ConfigManager().load_all()

    logger.info("Starting combined session for %s", args.account)

    # Create session owner (handles browser + login)
    creator = SubredditCreator(
        account_name=args.account,
        headless=args.headless,
        dry_run=args.dry_run,
        ui_mode="modern",
        session=None,
        owns_session=True,
    )
    session = creator.export_session()

    try:
        if not args.skip_creation:
            logger.info("Step 1: Subreddit creation")
            creator.run(max_subreddits=args.max_create or 2, headless=args.headless)
        else:
            logger.info("Step 1: Subreddit creation skipped")

        if not args.skip_moderation:
            logger.info("Step 2: Moderation")
            moderator = SeleniumModerationManager(
                account_name=args.account,
                headless=args.headless,
                dry_run=args.dry_run,
                session=session,
                owns_session=False,
            )
            moderator.run_daily_moderation()
        else:
            logger.info("Step 2: Moderation skipped")

        if not args.skip_posting:
            logger.info("Step 3: Posting")
            scheduler = MCRDSEPostScheduler(
                account_name=args.account,
                headless=args.headless,
                dry_run=args.dry_run,
                session=session,
                owns_session=False,
            )
            scheduler.process_due_posts()
        else:
            logger.info("Step 3: Posting skipped")
    finally:
        creator.cleanup()


if __name__ == "__main__":
    main()
