# API Mode Scripts

Lightweight, step-by-step scripts that use PRAW. Each script handles errors by falling back to mock data so you can test without Reddit credentials.

- `bot_step1.py`: Authenticate and fetch a small batch of posts.
- `bot_step2_keywords.py`: Fetch posts and print only those matching the configured keywords.
- `bot_step3_replies.py`: Fetch + filter posts, suggest a reply, ask for human approval, optionally post, and log to `bot_logs.csv`.
- `bot_step4_metrics.py`: Read posted comment IDs from `bot_logs.csv` and record their score/replies in `bot_metrics.csv`.

Configuration:
- Load credentials from `config/credentials.env` (preferred) or `.env` in the repo root. Set `MOCK_MODE=1` to skip real API calls.
- Keywords/subreddits come from `config/keywords.json` and `config/subreddits.json`.
- Posting is off by default; enable with `ENABLE_POSTING=1` only after manual review and subreddit approval.
- Optional LLM replies use the OpenAI client against OpenRouter when `USE_LLM=1` and `OPENROUTER_API_KEY` are set (falls back to a stub reply if unavailable).

Related tooling:
- `scripts/night_scanner.py` provides scheduled, read-only scans (no posting) and logs matches to `logs/night_scan.csv`.
