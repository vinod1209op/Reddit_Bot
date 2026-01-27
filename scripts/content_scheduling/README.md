# Content Scheduling

Entry point:
- `scripts/content_scheduling/schedule_posts.py`

Key inputs:
- `config/post_scheduling.json`
- `scripts/content_scheduling/templates/post_templates.json`

Outputs:
- `scripts/content_scheduling/schedule/post_schedule.json`
- `scripts/content_scheduling/schedule/backups/`

Notes:
- Uses `RedditAutomationBase` for browser/login/cleanup.
