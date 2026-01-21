"""
Purpose: Scan within an existing Selenium session (read-only).
Constraints: Enforces read-only mode for scheduled runs.

# SAFETY GUARANTEE:
# This module MUST remain read-only. No reply or engagement logic is allowed here.
"""

# Imports
import logging
from pathlib import Path
from typing import Sequence, Set

from microdose_study_bot.reddit_selenium.main import RedditAutomation
from microdose_study_bot.core.safety.policies import enforce_readonly_env
from microdose_study_bot.core.utils.api_utils import matched_keywords
from microdose_study_bot.core.storage.scan_store import (
    add_scanned_post,
    add_to_queue,
    log_summary,
    normalize_reddit_url,
    save_seen,
    seen_key,
)

logger = logging.getLogger(__name__)


# Public API
def run_session_scan(
    *,
    driver,
    browser_manager,
    login_manager,
    config,
    subreddits: Sequence[str],
    keywords: Sequence[str],
    limit: int,
    queue_path: Path,
    summary_path: Path,
    run_queue_path: Path,
    run_summary_path: Path,
    scanned_path: Path,
    run_scanned_path: Path,
    seen: Set[str],
    seen_path: Path,
    run_id: str,
    account: str,
    tz_name: str,
    scan_window: str,
    mode: str = "selenium",
    sort: str = "new",
    time_range: str = "",
    page_offset: int = 0,
) -> None:
    enforce_readonly_env()
    bot = RedditAutomation(config=config)
    bot.driver = driver
    bot.browser_manager = browser_manager
    bot.login_manager = login_manager
    bot._sync_login_manager()

    subreddit_set = ",".join(subreddits)
    for subreddit in subreddits:
        logger.info(
            f"[{account or 'default'}] Scanning r/{subreddit} sort={sort}, time={time_range or 'none'}, page_offset={page_offset}"
        )
        posts = bot.search_posts(
            subreddit=subreddit,
            limit=limit,
            include_body=False,
            include_comments=False,
            sort=sort,
            time_range=time_range or None,
            page_offset=page_offset,
        )
        scanned_count = 0
        matched_count = 0

        for post in posts:
            info = {
                "id": post.get("id", ""),
                "subreddit": post.get("subreddit", subreddit),
                "title": post.get("title", ""),
                "body": post.get("body", ""),
                "url": normalize_reddit_url(post.get("url", "")),
            }
            key = seen_key(info)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            scanned_count += 1
            combined = f"{info['title']} {info['body']}".lower()
            hits = matched_keywords(combined, keywords)
            method = post.get("method", mode)
            add_scanned_post(
                scanned_path,
                run_id,
                account,
                tz_name,
                scan_window,
                mode,
                info,
                hits,
                method,
                scan_sort=sort,
                scan_time_range=time_range or "",
                scan_page_offset=page_offset,
                subreddit_set=subreddit_set,
            )
            add_scanned_post(
                run_scanned_path,
                run_id,
                account,
                tz_name,
                scan_window,
                mode,
                info,
                hits,
                method,
                scan_sort=sort,
                scan_time_range=time_range or "",
                scan_page_offset=page_offset,
                subreddit_set=subreddit_set,
            )
            if hits:
                matched_count += 1
                add_to_queue(
                    queue_path,
                    run_id,
                    account,
                    tz_name,
                    scan_window,
                    mode,
                    info,
                    hits,
                    method,
                    scan_sort=sort,
                    scan_time_range=time_range or "",
                    scan_page_offset=page_offset,
                    subreddit_set=subreddit_set,
                )
                add_to_queue(
                    run_queue_path,
                    run_id,
                    account,
                    tz_name,
                    scan_window,
                    mode,
                    info,
                    hits,
                    method,
                    scan_sort=sort,
                    scan_time_range=time_range or "",
                    scan_page_offset=page_offset,
                    subreddit_set=subreddit_set,
                )

        log_summary(
            summary_path,
            run_id,
            account,
            tz_name,
            scan_window,
            mode,
            subreddit,
            scanned_count,
            matched_count,
            scan_sort=sort,
            scan_time_range=time_range or "",
            scan_page_offset=page_offset,
            subreddit_set=subreddit_set,
        )
        log_summary(
            run_summary_path,
            run_id,
            account,
            tz_name,
            scan_window,
            mode,
            subreddit,
            scanned_count,
            matched_count,
            scan_sort=sort,
            scan_time_range=time_range or "",
            scan_page_offset=page_offset,
            subreddit_set=subreddit_set,
        )
        logger.info(
            f"[{account or 'default'}] r/{subreddit}: scanned {scanned_count}, matched {matched_count}"
        )
        save_seen(seen_path, seen)
