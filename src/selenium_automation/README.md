# Selenium Automation

Browser-based flows for Reddit using Selenium/undetected-chromedriver. Designed for manual login and cautious scraping.

Key pieces:
- `main.py` (`RedditAutomation`): orchestrates Selenium runs, uses `BrowserManager` for driver setup and per-action delays/scrolls, and uses `LoginManager` for cookie/Google/credential login.
- `login_manager.py` / `simple_login.py`: login helpers; `LoginManager` creates its own driver via `BrowserManager`.
- `utils/browser_manager.py`: driver creation (undetected-chromedriver when available), small action delays/scrolls, and optional fingerprint randomization (experimental).
- `utils/reply_helpers.py`: comment composer discovery/focus/fill helpers.
- `utils/message_processor.py` + `utils/response_generator.py`: keyword checks and reply templates for Selenium flows.
- `utils/rate_limiter.py`: local action limits for browser actions.
- `utils/security_manager.py`: placeholder stub (warns only).
- `utils/human_simulator.py` + `utils/engagement_actions.py`: experimental browsing/engagement helpers used by `scripts/runners/humanized_night_scanner.py` (not part of the main workflow).

Usage (manual login):
1) Install deps: `pip install -r requirements-selenium.txt` (or `requirements-streamlit.txt` if using the UI).
2) Run `python src/selenium_automation/main.py` (or via `apps/unified_bot.py` → Selenium mode).
3) When prompted, complete Google login in the opened browser and press Enter.
4) Use the interactive prompts to search posts or leave the browser open.

Notes:
- Headless mode is controlled via `SELENIUM_HEADLESS` (config/credentials.env).
- Cookie reuse is supported; set `COOKIE_PATH` to change the file (defaults to `cookies.pkl`).
- `search_posts(include_body=True, include_comments=True, comments_limit=3)` will click into each post (limited to the initial list) and try to capture body text and a few top-level comments; expect some misses when Reddit’s markup shifts.
- `reply_to_post(url, reply_text, dry_run=True)` will open the post and stage a reply; it defaults to dry-run. Flip `dry_run=False` only after manual review and with subreddit approval.
- In the unified menu, you can toggle body/comment capture when viewing/searching posts; results are deduped automatically.
- Optional LLM replies use the OpenAI client against OpenRouter when `USE_LLM=1` and `OPENROUTER_API_KEY` are set.
- `scripts/runners/night_scanner.py` can use Selenium in read-only mode and will exit if cookie login fails, to avoid age prompts.
- `scripts/runners/humanized_night_scanner.py` is experimental and not wired into the main flow; it depends on extra helpers and configs and should be treated as optional research-only code.
- Respect site rules: keep volume low, avoid automation that violates Reddit policies, and prefer manual approval for any posting.
