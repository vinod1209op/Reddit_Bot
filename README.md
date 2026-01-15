# MicrodoseStudyBot (Academic Case Study)

## What this is
- A small research bot to explore AI-assisted, harm-reduction-oriented replies on Reddit with a mandatory human-in-the-loop.
- Not a marketing or growth bot. Low volume, rule-abiding, neutral, and focused on general education.

## Tech stack
- Python
- PRAW (Reddit API)
- python-dotenv for configuration
- Optional: OpenAI client configured for OpenRouter reply generation (stubbed fallback included)
- Optional: Selenium for manual browser automation
- Optional: Streamlit UI for manual prefill workflow

## Safety constraints
- No medical or dosing advice; no encouragement of illegal activity.
- No links or product/brand promotion.
- Human approval required before posting; posting is disabled by default.
- Keep volume low (approval cap per run); respect subreddit rules and Reddit policies.
- Mock mode available to test without API access.

## Setup
1) Install deps (within your venv):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   # Optional extras:
   pip install -r requirements-llm.txt
   pip install -r requirements-selenium.txt
   pip install -r requirements-streamlit.txt
   ```
2) Fill `config/credentials.env` (preferred) or `.env` in the repo root:
   - Required for API mode: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT` (descriptive)
   - Optional for Selenium login: `GOOGLE_EMAIL`, `GOOGLE_PASSWORD`
   - Optional toggles:
     - `MOCK_MODE=1` to force mock data (no API calls)
     - `ENABLE_POSTING=1` to allow replies (keep off for dry-run)
     - `USE_LLM=1` + `OPENROUTER_API_KEY` to try LLM replies (falls back to stub if unavailable)
     - `RUN_ID` to tag runs in logs
     - `SELENIUM_AUTO_SUBMIT_LIMIT` to cap Streamlit auto-submit per session
     - `SEARCH_CACHE_TTL` (seconds) to cache Streamlit search results (0 disables)
   - Optional OpenRouter headers:
     - `OPENROUTER_BASE_URL`, `OPENAI_HTTP_REFERER`, `OPENAI_X_TITLE`
3) (Optional) Configure scheduled scanning in `config/schedule.json`:
   - Define `scan_windows` and `timezone` for read-only night scans.
   - Set `mode`, `limit`, `summary_path`, and `queue_path` if needed.

## How to run (by step)
- Step 1 (auth + basic read):  
  `python api/bot_step1.py`
- Step 2 (keyword scan):  
  `python api/bot_step2_keywords.py`
- Step 3 (keyword scan + suggested reply + human approval + logging; posting off by default):  
  `python api/bot_step3_replies.py`
- Step 4 (metrics; checks posted comments’ score/replies; skips in mock mode):  
  `python api/bot_step4_metrics.py`
- Selenium mode (manual login, scraping, optional reply staging):  
  `python unified_bot.py` → choose “Run Selenium Bot”, complete manual Google login, then use the menu to search posts. You can toggle body/comments capture in the prompts. Posting via Selenium is only manual: you must enter the post URL, reply text, and confirm; keep it dry-run unless you have moderator approval.
- Streamlit UI (manual prefill, optional auto-submit):  
  `streamlit run streamlit_app.py` → start the browser, search, draft a reply, and prefill in the live browser. Set `STREAMLIT_APP_PASSWORD` to gate access. Auto-submit is available but should be used only with approval and strict limits (cap with `SELENIUM_AUTO_SUBMIT_LIMIT`).
- Night scanner (read-only, scheduled):  
  `python scripts/night_scanner.py` → scans within configured windows and queues matches; no replies or posting.

## GitHub Actions (read-only Selenium scan)
To run scheduled, read-only Selenium scans in GitHub Actions (using `.github/workflows/selenium_readonly_scan.yml`):
- Add a GitHub Actions secret named `REDDIT_COOKIES_BASE64` that contains a base64-encoded cookie file (example commands):
  - macOS: `base64 -b 0 cookies.pkl > /tmp/reddit_cookies.b64`
  - Linux: `base64 -w 0 cookies.pkl > /tmp/reddit_cookies.b64`
  - Copy the file contents into the Actions secret value.
- Review/adjust the cron schedule in `.github/workflows/selenium_readonly_scan.yml` to match your desired time windows (cron is UTC; update for DST as needed).
- Trigger the workflow once manually in GitHub Actions to verify cookies and Chromium setup.

## Logs / data
- `bot_logs.csv`: per match/reply attempt (run_id, mode, subreddit, post_id, title, matched_keywords, reply_text, approved, posted, comment_id, error).
- `bot_metrics.csv`: per posted comment check (timestamp_checked_utc, run_id, subreddit, post_id, comment_id, title, matched_keywords, score, replies_count, error).
- `data/post_state.json`: Streamlit UI state for submitted/ignored posts.
- `logs/night_scan_summary.csv`: per-subreddit scan summary counts.
- `logs/night_queue.json`: review queue of matched posts.

## Repo map
- `api/`: PRAW-based steps (auth, keyword scan, human-approved replies, metrics) with mock fallbacks.
- `selenium_automation/`: Browser-based helper for manual Google login and subreddit scraping.
- `shared/`: Config loader, logging, and safety utilities used by both modes.
- `config/`: Keywords/subreddits, rate limits, and credentials template.
- `config/accounts.json` + `config/activity_schedule.json`: experimental multi-account activity configs (not used by the main flow).
- `config/schedule.json`: time windows and settings for read-only scheduled scanning.
- `streamlit_app.py`: Streamlit UI to search and prefill replies using Selenium.
- `scripts/night_scanner.py`: read-only scheduled scanning with logs, summary, and queue.
- `scripts/humanized_night_scanner.py`: experimental multi-account activity runner; not part of the main workflow and may require extra wiring.
- `scripts/cleanup_logs.py`: optional helper to trim old log files (keeps recent by age/count).

## Experimental (not wired into main flow)
- `scripts/humanized_night_scanner.py` uses `config/accounts.json` + `config/activity_schedule.json` and the helpers in `selenium_automation/utils/human_simulator.py` and `selenium_automation/utils/engagement_actions.py`. It is not part of the main workflow and may require additional wiring before use.
