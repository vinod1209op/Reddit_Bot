# Selenium Automation (Shim)

This directory is a backward-compatibility shim. Use `src/microdose_study_bot/reddit_selenium/` for new work.

Browser-based flows for Reddit using Selenium/undetected-chromedriver. Designed for manual login and cautious scraping.

Key pieces (new location):
- `src/microdose_study_bot/reddit_selenium/main.py` (`RedditAutomation`)
- `src/microdose_study_bot/reddit_selenium/login.py` / `simple_login.py`
- `src/microdose_study_bot/reddit_selenium/utils/browser_manager.py`
- `src/microdose_study_bot/reddit_selenium/utils/reply_helpers.py`
- `src/microdose_study_bot/reddit_selenium/utils/message_processor.py` + `response_generator.py`
- `src/microdose_study_bot/reddit_selenium/utils/rate_limiter.py`
- `src/microdose_study_bot/reddit_selenium/utils/security_manager.py` (placeholder stub)
- `src/microdose_study_bot/reddit_selenium/utils/human_simulator.py` + `engagement_actions.py`

Usage (manual login):
1) Install deps: `pip install -r requirements-selenium.txt` (or `requirements-streamlit.txt` if using the UI).
2) Run `python src/microdose_study_bot/reddit_selenium/main.py` (or via `apps/cli/microdose_bot.py` → Selenium mode).
3) When prompted, complete Google login in the opened browser and press Enter.
4) Use the interactive prompts to search posts or leave the browser open.

Notes:
- Headless mode is controlled via `SELENIUM_HEADLESS` (config/credentials.env).
- Cookie reuse is supported; set `COOKIE_PATH` to change the file (defaults to the app setting).
- `search_posts(include_body=True, include_comments=True, comments_limit=3)` will click into each post (limited to the initial list) and try to capture body text and a few top-level comments; expect some misses when Reddit’s markup shifts.
- `reply_to_post(url, reply_text, dry_run=True)` will open the post and stage a reply; it defaults to dry-run. Flip `dry_run=False` only after manual review and with subreddit approval.
- In the unified menu, you can toggle body/comment capture when viewing/searching posts; results are deduped automatically.
- Optional LLM replies use the OpenAI client against OpenRouter when `USE_LLM=1` and `OPENROUTER_API_KEY` are set.
- `scripts/runners/night_scanner.py` can use Selenium in read-only mode and will exit if cookie login fails, to avoid age prompts.
- `scripts/runners/humanized_night_scanner.py` is the scheduled multi-account runner; keep engagement actions conservative and optional.
- Respect site rules: keep volume low, avoid automation that violates Reddit policies, and prefer manual approval for any posting.
