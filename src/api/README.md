# API Mode Scripts (Shim)

This directory is a backward-compatibility shim. Use `src/microdose_study_bot/reddit_api/` for new work.

- `bot_step1.py` → `src/microdose_study_bot/reddit_api/bot_step1.py`
- `bot_step2_keywords.py` → `src/microdose_study_bot/reddit_api/bot_step2_keywords.py`
- `bot_step3_replies.py` → `src/microdose_study_bot/reddit_api/bot_step3_replies.py`
- `bot_step4_metrics.py` → `src/microdose_study_bot/reddit_api/bot_step4_metrics.py`

Configuration:
- Load credentials from `config/credentials.env` (preferred) or `.env` in the repo root. Set `MOCK_MODE=1` to skip real API calls.
- Keywords/subreddits come from `config/keywords.json` and `config/subreddits.json`.
- Posting is off by default; enable with `ENABLE_POSTING=1` only after manual review and subreddit approval.
- Optional LLM replies use the OpenAI client against OpenRouter when `USE_LLM=1` and `OPENROUTER_API_KEY` are set (falls back to a stub reply if unavailable).

Outputs:
- `bot_logs.csv`: log of matches and decisions for step 3.
- `bot_metrics.csv`: engagement metrics for posted comments (step 4).

Related tooling:
- `scripts/runners/night_scanner.py` provides scheduled, read-only scans (no posting) and queues matches to `logs/night_queue.json`.
