# Slides Outline (Presentation)

1) Project Aim
- Harm-reduction, neutral educational Reddit bot focused on microdosing/psychedelic discussions with human approval.
- Research tool, not promotion; low volume, rule-abiding.

2) Safety & Ethics
- No medical/dosing advice or microdosing protocols; no illegal encouragement; no links/promos.
- Human-in-the-loop, low volume, respect subreddit rules and Reddit policies.

3) System Design
- Auth + mock fallback; keyword scan (microdosing/psychedelic terms); reply generator (stub/optional LLM via OpenRouter + strict safety prompt).
- Approval gate; posting guard (off by default); logging (bot_logs); metrics (bot_metrics).
- Selenium path: manual Google login, scrape subreddit /new pages; optional body/comment capture; reply helper with dry-run default; Streamlit UI for search + prefill.
- Scheduled humanized scans (read-only): `scripts/runners/humanized_night_scanner.py` + `config/activity_schedule.json` + `config/accounts.json` → queues matches, summary counts, and a review queue across multiple accounts.

4) Workflow
- Configure `config/credentials.env` (or `.env`); mock vs live; target subs/keywords.
- Scan → suggest reply → human approves → (optional) post → log → later metrics check.
- Optional humanized scan window → review queue next day → manual decision.

5) Results (fill in)
- Runs, volume, engagement (score/replies), notable patterns in microdosing topics.
- Rejections and reasons; safety observations (avoiding dosing guidance, legal considerations).

6) Limitations & Risks
- Simple keywording; manual approval burden; small sample; API access limits.
- Mitigations: strict prompt, dry-run default, caps, human oversight.

7) Next Steps
- Prompt/keyword refinement, richer metrics (sentiment), possible semantic filters.
- Future ethics/policy adjustments based on observed edge cases.
