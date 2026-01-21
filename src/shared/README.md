# Shared Utilities

Common helpers used by both API and Selenium flows.

- `config_manager.py`: loads credentials (`config/credentials.env`), keywords/subreddits, rate limits, and automation settings; prints a summarized view. Includes experimental loaders for `config/accounts.json` and `config/activity_schedule.json` used by the humanized runner.
- `logger.py`: unified logger that writes daily rotating files to `logs/` and streams INFO+ to stdout (`ENABLE_JSON_LOGGING` and `CONSOLE_LOG_LEVEL` are supported).
- `safety_checker.py`: rate limit and content checks; returns allow/deny with reasons.
- `api_selenium_adapter.py`: thin adapter to choose API vs Selenium at runtime; currently uses direct PRAW and `selenium_automation.main`.
- `src/selenium_automation/utils/security_manager.py` (placeholder): stub; extend before relying on it for enforcement.

Expectations:
- Place `.env`/`credentials.env` in `config/` for secrets; keep them out of version control.
- Prefer the SafetyChecker for gating actions and keep volume low when posting or messaging.
- `config/schedule.json` is used by `scripts/runners/night_scanner.py` for read-only scan windows.
