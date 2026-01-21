# Shared Utilities (Shim)

This directory is a backward-compatibility shim. Use `src/microdose_study_bot/core/` and `src/microdose_study_bot/orchestration/` for new work.

- `config_manager.py` → `src/microdose_study_bot/core/config.py`
- `logger.py` → `src/microdose_study_bot/core/logging.py`
- `safety_checker.py` → `src/microdose_study_bot/core/safety/checker.py`
- `api_selenium_adapter.py` → `src/microdose_study_bot/orchestration/adapters.py`
- `src/microdose_study_bot/reddit_selenium/utils/security_manager.py` (placeholder): stub; extend before relying on it for enforcement.

Expectations:
- Place `.env`/`credentials.env` in `config/` for secrets; keep them out of version control.
- Prefer the SafetyChecker for gating actions and keep volume low when posting or messaging.
- `config/schedule.json` is used by `scripts/runners/night_scanner.py` for read-only scan windows.
