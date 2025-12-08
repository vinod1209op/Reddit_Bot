# Selenium Automation

Browser-based flows for Reddit using Selenium/undetected-chromedriver. Designed for manual login and cautious scraping.

Key pieces:
- `main.py` (`RedditAutomation`): sets up the browser, walks through manual Google login, checks messages, and scrapes recent posts via `search_posts()`.
- `login_manager.py` / `simple_login.py`: helpers for Google OAuth or manual login/cookie reuse.
- `utils/`: browser helpers, message keyword checks, rate limiting, placeholder security manager.

Usage (manual login):
1) Install deps: `pip install -r requirements.txt` (needs `selenium`, `webdriver-manager`, `undetected-chromedriver`).
2) Run `python selenium_automation/main.py` (or via `unified_bot.py` → Selenium mode).
3) When prompted, complete Google login in the opened browser and press Enter.
4) Use the interactive prompts to search posts or leave the browser open.

Notes:
- Headless mode is controlled via `SELENIUM_HEADLESS` (config/credentials.env).
- `search_posts(include_body=True, include_comments=True, comments_limit=3)` will click into each post (limited to the initial list) and try to capture body text and a few top-level comments; expect some misses when Reddit’s markup shifts.
- `reply_to_post(url, reply_text, dry_run=True)` will open the post and stage a reply; it defaults to dry-run. Flip `dry_run=False` only after manual review and with subreddit approval.
- In the unified menu, you can toggle body/comment capture when viewing/searching posts; results are deduped automatically.
- Respect site rules: keep volume low, avoid automation that violates Reddit policies, and prefer manual approval for any posting.
