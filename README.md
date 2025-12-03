# MicrodoseStudyBot (Academic Case Study)

## What this is
- A small research bot to explore AI-assisted, harm-reduction-oriented replies on Reddit with a mandatory human-in-the-loop.
- Not a marketing or growth bot. Low volume, rule-abiding, neutral, and focused on general education.

## Tech stack
- Python
- PRAW (Reddit API)
- python-dotenv for configuration
- Optional: OpenAI client for reply generation (stubbed fallback included)

## Safety constraints
- No medical or dosing advice; no encouragement of illegal activity.
- No links or product/brand promotion.
- Human approval required before posting; posting is disabled by default.
- Keep volume low (approval cap per run); respect subreddit rules and Reddit policies.
- Mock mode available to test without API access.

## Setup
1) Install deps (within your venv):
   ```bash
   pip install praw python-dotenv
   # Optional LLM support:
   pip install openai
   ```
2) Fill `.env` with Reddit credentials:
   - `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT` (descriptive)
   - Optional toggles:
     - `MOCK_MODE=1` to force mock data (no API calls)
     - `ENABLE_POSTING=1` to allow replies (keep off for dry-run)
     - `USE_LLM=1` + `OPENAI_API_KEY` to try LLM replies (falls back to stub if unavailable)
     - `RUN_ID` to tag runs in logs

## How to run (by step)
- Step 1 (auth + basic read):  
  `python bot_step1.py`
- Step 2 (keyword scan):  
  `python bot_step2_keywords.py`
- Step 3 (keyword scan + suggested reply + human approval + logging; posting off by default):  
  `python bot_step3_replies.py`
- Step 4 (metrics; checks posted comments’ score/replies; skips in mock mode):  
  `python bot_step4_metrics.py`

## Logs / data
- `bot_logs.csv`: per match/reply attempt (run_id, mode, subreddit, post_id, title, matched_keywords, reply_text, approved, posted, comment_id, error).
- `bot_metrics.csv`: per posted comment check (timestamp_checked_utc, run_id, subreddit, post_id, comment_id, title, matched_keywords, score, replies_count, error).
