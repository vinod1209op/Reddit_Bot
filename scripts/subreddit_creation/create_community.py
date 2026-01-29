#!/usr/bin/env python3
"""
Create a community using the modern Reddit UI (wizard flow).
Note: CAPTCHA challenges must be solved manually if they appear.
"""

import argparse
import time
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from microdose_study_bot.core.logging import UnifiedLogger
from scripts.subreddit_creation.create_subreddits import SubredditCreator

logger = UnifiedLogger("CommunityCreator").get_logger()


def _wait_seconds(seconds: float) -> None:
    time.sleep(seconds)


def _find_visible(driver, selectors, timeout=10):
    end_time = time.time() + timeout
    last_error = None
    while time.time() < end_time:
        for by, selector in selectors:
            try:
                elements = driver.find_elements(by, selector)
            except Exception as exc:
                last_error = exc
                continue
            if not elements:
                continue
            visible = [el for el in elements if el.is_displayed() and el.is_enabled()]
            if visible:
                return visible[0]
        _wait_seconds(0.2)
    if last_error:
        raise last_error
    raise RuntimeError(f"Element not found for selectors: {selectors}")


def _safe_click(driver, element, label):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        element.click()
        return True
    except Exception as exc:
        logger.warning(f"Fallback to JS click for {label}: {exc}")
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as js_exc:
            logger.warning(f"JS click failed for {label}: {js_exc}")
            return False


def _fill_field(driver, element, value, label):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        driver.execute_script(
            "arguments[0].removeAttribute('readonly'); arguments[0].removeAttribute('disabled');",
            element,
        )
        element.click()
        element.clear()
        element.send_keys(value)
        return
    except Exception as exc:
        logger.warning(f"Fallback to JS set for {label}: {exc}")
        driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            """,
            element,
            value,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a community using the modern Reddit UI.")
    parser.add_argument("--account", default="account1", help="Account name from config/accounts.json")
    parser.add_argument("--name", required=True, help="Community name (3-21 chars, no spaces)")
    parser.add_argument("--title", default="", help="Community title")
    parser.add_argument("--description", default="", help="Short community description")
    parser.add_argument("--topic", default="Science", help="Topic label to select in the wizard")
    parser.add_argument("--type", default="public", choices=["public", "restricted", "private"], help="Community type")
    parser.add_argument("--mature", action="store_true", help="Mark as 18+")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--manual-submit", action="store_true", help="Pause before final submit")
    parser.add_argument("--url", default="https://www.reddit.com/subreddits/create", help="Create flow URL")
    args = parser.parse_args()

    creator = SubredditCreator(account_name=args.account, headless=args.headless, dry_run=False, ui_mode="modern")
    if not creator.driver:
        creator._setup_browser()
    if not getattr(creator, "logged_in", False):
        login_result = creator._login_with_fallback()
        if not login_result.success:
            logger.error("Login failed; aborting.")
            creator.cleanup()
            return

    driver = creator.driver
    if not driver:
        logger.error("No browser driver available.")
        return

    logger.info("Opening Reddit home and clicking Start a community...")
    driver.get("https://www.reddit.com/")
    _wait_seconds(4)
    try:
        # Try to open left navigation if collapsed.
        try:
            nav_btn = _find_visible(driver, [
                ("css selector", "button[aria-label*='Open navigation' i]"),
                ("css selector", "button[aria-label*='Open left' i]"),
                ("css selector", "button[aria-label*='Menu' i]"),
            ], timeout=2)
            _safe_click(driver, nav_btn, "open_nav")
            _wait_seconds(1)
        except Exception:
            pass

        start_btn = _find_visible(driver, [
            ("xpath", "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'start a community')]"),
            ("xpath", "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create a community')]"),
            ("xpath", "//span[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'start a community')]/ancestor::button"),
            ("xpath", "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'start a community')]"),
            ("css selector", "a[href*='subreddits/create']"),
            ("css selector", "a[href*='community/create']"),
            ("css selector", "button[data-testid*='community' i]"),
            ("css selector", "[aria-label*='Start a community' i]"),
        ], timeout=6)
        _safe_click(driver, start_btn, "start_community")
        _wait_seconds(3)
    except Exception as exc:
        logger.warning(f"Start a community button not found: {exc}")
        logger.info("Falling back to direct community create URL...")
        candidate_urls = [
            args.url,
            "https://www.reddit.com/community/create",
            "https://new.reddit.com/subreddits/create",
        ]
        for url in candidate_urls:
            driver.get(url)
            _wait_seconds(3)
            current = (driver.current_url or "").lower()
            page = (driver.page_source or "").lower()
            if "old.reddit.com/subreddits/create" in current or "create a subreddit" in page:
                logger.info(f"Detected classic create page at {current}; trying next URL...")
                continue
            break

    # Step 1: pick a topic
    try:
        topic_btn = _find_visible(driver, [
            ("xpath", f"//button[contains(., '{args.topic}')]"),
            ("xpath", f"//span[contains(., '{args.topic}')]/ancestor::button"),
        ], timeout=5)
        _safe_click(driver, topic_btn, "topic")
    except Exception as exc:
        logger.warning(f"Topic selection skipped: {exc}")
    try:
        next_btn = _find_visible(driver, [
            ("xpath", "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]"),
        ], timeout=3)
        _safe_click(driver, next_btn, "next_after_topic")
        _wait_seconds(2)
    except Exception:
        pass

    # Step 2: choose type + mature
    try:
        type_btn = _find_visible(driver, [
            ("xpath", f"//div[contains(., '{args.type.capitalize()}')]/ancestor::label"),
            ("xpath", f"//span[contains(., '{args.type.capitalize()}')]/ancestor::label"),
            ("xpath", f"//label[contains(., '{args.type.capitalize()}')]"),
        ], timeout=5)
        _safe_click(driver, type_btn, "type")
    except Exception as exc:
        logger.warning(f"Type selection skipped: {exc}")
    if args.mature:
        try:
            mature_toggle = _find_visible(driver, [
                ("xpath", "//label[contains(., 'Mature')]/following::input[1]"),
                ("xpath", "//input[@type='checkbox' and contains(@aria-label, 'Mature')]"),
            ], timeout=3)
            _safe_click(driver, mature_toggle, "mature")
        except Exception as exc:
            logger.warning(f"Mature toggle skipped: {exc}")
    try:
        next_btn = _find_visible(driver, [
            ("xpath", "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]"),
        ], timeout=3)
        _safe_click(driver, next_btn, "next_after_type")
        _wait_seconds(2)
    except Exception:
        pass

    # Step 3: name + description
    try:
        name_field = _find_visible(driver, [
            ("css selector", "input[name='name']"),
            ("css selector", "input[aria-label*='Community name' i]"),
            ("css selector", "input[placeholder*='Community name' i]"),
        ], timeout=6)
        _fill_field(driver, name_field, args.name, "name")
    except Exception as exc:
        logger.warning(f"Name field skipped: {exc}")

    if args.title:
        try:
            title_field = _find_visible(driver, [
                ("css selector", "input[name='title']"),
                ("css selector", "input[aria-label*='Title' i]"),
            ], timeout=4)
            _fill_field(driver, title_field, args.title, "title")
        except Exception as exc:
            logger.warning(f"Title field skipped: {exc}")

    if args.description:
        try:
            desc_field = _find_visible(driver, [
                ("css selector", "textarea[name='description']"),
                ("css selector", "textarea[aria-label*='Description' i]"),
            ], timeout=6)
            _fill_field(driver, desc_field, args.description, "description")
        except Exception as exc:
            logger.warning(f"Description field skipped: {exc}")

    if args.manual_submit:
        input("Review the form in the browser, then press Enter to submit...")

    # Submit
    try:
        submit_btn = _find_visible(driver, [
            ("xpath", "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create')]"),
            ("css selector", "button[type='submit']"),
        ], timeout=5)
        _safe_click(driver, submit_btn, "submit")
    except Exception as exc:
        logger.warning(f"Submit step skipped: {exc}")

    _wait_seconds(5)
    logger.info("Create flow complete. Check the browser for CAPTCHA or errors.")


if __name__ == "__main__":
    main()
