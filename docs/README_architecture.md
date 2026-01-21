# Architecture Overview

High-level system layout:
- `src/microdose_study_bot/reddit_api/`: PRAW-based scanning and reply drafting.
- `src/microdose_study_bot/reddit_selenium/`: Browser automation for manual login and prefill.
- `src/microdose_study_bot/core/`: Config, logging, safety checks, and utilities.
- `src/microdose_study_bot/orchestration/`: API/Selenium adapters and pipeline glue.
- `apps/streamlit/app.py`: Streamlit UI for human-in-the-loop workflow.
- `scripts/runners/humanized_night_scanner.py`: Scheduled, multi-account scanning.

For full details, see `information/DOCUMENT.md` and `information/REQUEST_AUTOMATION_DOC.md`.
