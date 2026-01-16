from pathlib import Path
from typing import Sequence, Set

from selenium_automation.main import RedditAutomation
from shared.api_utils import matched_keywords
from shared.scan_store import (
    add_to_queue,
    log_summary,
    normalize_reddit_url,
    save_seen,
    seen_key,
)


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
    seen: Set[str],
    seen_path: Path,
    run_id: str,
    account: str,
    tz_name: str,
    scan_window: str,
    mode: str = "selenium",
) -> None:
    bot = RedditAutomation(config=config)
    bot.driver = driver
    bot.browser_manager = browser_manager
    bot.login_manager = login_manager
    bot._sync_login_manager()

    for subreddit in subreddits:
        posts = bot.search_posts(subreddit=subreddit, limit=limit, include_body=False, include_comments=False)
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
            if hits:
                matched_count += 1
                method = post.get("method", mode)
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
        )
        save_seen(seen_path, seen)
