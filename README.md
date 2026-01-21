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
   # All dependencies are in requirements.txt
   ```
2) Fill `config/credentials.env` (preferred) or `.env` in the repo root (see `config/env/.env.example` for templates):
   - Required for API mode: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT` (descriptive)
   - Optional for Selenium login: `GOOGLE_EMAIL`, `GOOGLE_PASSWORD`
   - Optional toggles:
     - `MOCK_MODE=1` to force mock data (no API calls)
     - `ENABLE_POSTING=1` to allow replies (keep off for dry-run)
     - `USE_LLM=1` + `OPENROUTER_API_KEY` to try LLM replies (falls back to stub if unavailable)
     - `RUN_ID` to tag runs in logs
     - `SELENIUM_AUTO_SUBMIT_LIMIT` to cap Streamlit auto-submit per session
     - `SEARCH_CACHE_TTL` (seconds) to cache Streamlit search results (0 disables)
   - Supabase (Streamlit DB mode + cookie sync):
     - `SUPABASE_URL`, `SUPABASE_ANON_KEY`
     - `SUPABASE_SERVICE_ROLE_KEY` (required for uploads and cookie sync)
     - `SUPABASE_BUCKET` (Storage bucket)
     - `SUPABASE_COOKIES_ACCOUNT1_PATH` (cookie file path for Streamlit; default `cookies_account1.pkl`)
   - Optional OpenRouter headers:
     - `OPENROUTER_BASE_URL`, `OPENAI_HTTP_REFERER`, `OPENAI_X_TITLE`
3) (Optional) Configure humanized scheduled scanning in `config/activity_schedule.json`:
   - Define `time_windows` + `timezone` for early morning and late night runs.
   - Enable/disable `allow_voting`, `allow_saving`, and `allow_following` (read-only scanning stays default).
   - Configure accounts in `config/accounts.json` (cookies paths, profiles).
   - Legacy read-only scanning still uses `config/schedule.json` (manual only).

## How to run (by step)
Official operator entrypoints:
- UI: `streamlit run apps/streamlit/app.py`
- CLI: `python apps/cli/microdose_bot.py`

Internal/dev scripts (use for debugging or tests):
- `src/microdose_study_bot/reddit_api/bot_step1.py`
- `src/microdose_study_bot/reddit_api/bot_step2_keywords.py`
- `src/microdose_study_bot/reddit_api/bot_step3_replies.py`
- `src/microdose_study_bot/reddit_api/bot_step4_metrics.py`
- `src/microdose_study_bot/reddit_selenium/main.py`

- Step 1 (auth + basic read):  
  `python src/microdose_study_bot/reddit_api/bot_step1.py`
- Step 2 (keyword scan):  
  `python src/microdose_study_bot/reddit_api/bot_step2_keywords.py`
- Step 3 (keyword scan + suggested reply + human approval + logging; posting off by default):  
  `python src/microdose_study_bot/reddit_api/bot_step3_replies.py`
- Step 4 (metrics; checks posted comments’ score/replies; skips in mock mode):  
  `python src/microdose_study_bot/reddit_api/bot_step4_metrics.py`
- Selenium mode (manual login, scraping, optional reply staging):  
  `python apps/cli/microdose_bot.py` → choose “Run Selenium Bot”, complete manual Google login, then use the menu to search posts. You can toggle body/comments capture in the prompts. Posting via Selenium is only manual: you must enter the post URL, reply text, and confirm; keep it dry-run unless you have moderator approval.
- Streamlit UI (manual prefill, optional auto-submit):  
  `streamlit run apps/streamlit/app.py` → start the browser, search, draft a reply, and prefill in the live browser. Set `STREAMLIT_APP_PASSWORD` to gate access. Auto-submit is available but should be used only with approval and strict limits (cap with `SELENIUM_AUTO_SUBMIT_LIMIT`).
- Humanized night scanner (read-only, scheduled):  
  `python scripts/runners/humanized_night_scanner.py` → runs within `config/activity_schedule.json` windows, rotates accounts in `config/accounts.json`, and performs non-comment engagement (if enabled). Posting remains off by default.
- Legacy night scanner (manual only):  
  `python scripts/runners/night_scanner.py` → read-only scan with `config/schedule.json` windows; not scheduled by default.

## Convenience commands
- `make test`
- `make run-ui`
- `make run-cli`
- `make scan-night`
- `make scan-humanized`

## Pre-commit (optional)
```
pre-commit install
pre-commit run --all-files
```

## GitHub Actions (humanized scheduled scan)
To run scheduled, read-only humanized scans in GitHub Actions (using `.github/workflows/humanized_scan.yml`):
- Store a `cookies_bundle.zip` (zip of `data/cookies_*.pkl`) in Supabase Storage.
- Set GitHub Actions secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`, and optional `SUPABASE_COOKIES_PATH` (default `cookies/cookies_bundle.zip`).
- The workflow downloads the bundle at start and uploads refreshed cookies after the run via `scripts/ops/supabase_cookies_sync.py`.
- Review/adjust the cron schedule in `.github/workflows/humanized_scan.yml` to match your desired time windows (cron is UTC; update for DST as needed).
- Trigger the workflow once manually in GitHub Actions to verify cookies and Chromium setup.
- The legacy `selenium_readonly_scan.yml` is manual-only unless you add schedules.

## Logs / data
- `bot_logs.csv`: per match/reply attempt (run_id, mode, subreddit, post_id, title, matched_keywords, reply_text, approved, posted, comment_id, error).
- `bot_metrics.csv`: per posted comment check (timestamp_checked_utc, run_id, subreddit, post_id, comment_id, title, matched_keywords, score, replies_count, error).
- `data/post_state.json`: Streamlit UI state for submitted/ignored posts.
- `logs/night_scan_summary.csv`: per-subreddit scan summary counts.
- `logs/night_queue.json`: review queue of matched posts.

## Repo map
- `src/microdose_study_bot/reddit_api/`: PRAW-based steps (auth, keyword scan, human-approved replies, metrics) with mock fallbacks.
- `src/microdose_study_bot/reddit_selenium/`: Browser-based helper for manual Google login and subreddit scraping.
- `src/microdose_study_bot/core/`: Config loader, logging, and safety utilities used by both modes.
- `config/`: Keywords/subreddits, rate limits, and credentials template.
- `config/accounts.json` + `config/activity_schedule.json`: multi-account, scheduled humanized scanning (read-only by default).
- `config/schedule.json`: legacy time windows for `scripts/runners/night_scanner.py` (manual only).
- `apps/streamlit/app.py`: Streamlit UI to search and prefill replies using Selenium.
- `scripts/runners/night_scanner.py`: legacy read-only scanning with logs, summary, and queue (manual only by default).
- `scripts/runners/humanized_night_scanner.py`: scheduled multi-account activity runner (read-only by default).
- `scripts/one_time/cleanup_logs.py`: optional helper to trim old log files (keeps recent by age/count).

## Docs
- `docs/README_architecture.md`: architecture overview.
- `docs/RUNBOOK.md`: operational runbook.
- `docs/SECURITY.md`: security notes.
- `docs/ADR/`: architecture decisions.

## Repo tooling
- `.editorconfig`: whitespace/line-ending rules.
- `Makefile`: convenience commands (test/run/scan).
