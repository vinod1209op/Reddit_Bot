# Runbook

This runbook captures operational tasks for running and maintaining MicrodoseStudyBot in local and CI environments.

## Daily Operations
- Verify scheduled scans in GitHub Actions complete within the time window.
- Check `logs/` artifacts or Supabase uploads for scan summaries and queue files.
- Review the Streamlit UI for queued posts and state consistency (`data/post_state.json`).

## Local Run (Selenium + Streamlit)
1) Start Streamlit: `streamlit run apps/streamlit/app.py`
2) Enter the UI password (`STREAMLIT_APP_PASSWORD`), then start/reconnect the browser.
3) Search posts, draft replies, and prefill. Keep auto-submit off unless approved.

## CI Run (Humanized Scan)
1) Ensure Supabase Storage has the latest per-account cookies (`data/cookies_account*.pkl`) at the paths set by `SUPABASE_COOKIES_ACCOUNT*_PATH`.
2) Trigger `.github/workflows/humanized_scan.yml`.
3) Confirm cookies downloaded and scan logs uploaded.

## Cookie Rotation
- Local: run `python scripts/one_time/capture_cookies.py` and refresh `data/cookies_*.pkl`.
- CI: upload updated per-account cookie files to Supabase Storage, or allow the workflow to upload refreshed cookies after the run.

## Automation Guide
- See `information/REQUEST_AUTOMATION_DOC.md` for the most complete automation overview.

## Incident Checks
- Selenium login failures: verify cookies are valid and Supabase download is working.
- Timeouts in GitHub Actions: reduce session length or ensure only one account runs per time window.
- Click intercepted errors: see `src/microdose_study_bot/reddit_selenium/utils/browser_manager.py` for retry logic.

## Log Locations
- `logs/night_scan_summary.csv`: scan summaries
- `logs/night_queue.json`: queue of matched posts
- `logs/runs/<run_id>/`: per-run snapshots
