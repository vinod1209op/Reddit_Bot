# Slides Outline (Presentation)

1) Project Aim
- Harm-reduction, neutral educational Reddit bot with human approval.
- Research tool, not promotion; low volume, rule-abiding.

2) Safety & Ethics
- No medical/dosing advice, no illegal encouragement, no links/promos.
- Human-in-the-loop, low volume, respect subreddit rules and Reddit policies.

3) System Design
- Auth + mock fallback; keyword scan; reply generator (stub/optional LLM + safety prompt).
- Approval gate; posting guard (off by default); logging (bot_logs); metrics (bot_metrics).

4) Workflow
- Configure .env; mock vs live.
- Scan → suggest reply → human approves → (optional) post → log → later metrics check.

5) Results (fill in)
- Runs, volume, engagement (score/replies), notable patterns.
- Rejections and reasons; safety observations.

6) Limitations & Risks
- Simple keywording; manual approval burden; small sample; API access limits.
- Mitigations: strict prompt, dry-run default, caps, human oversight.

7) Next Steps
- Prompt/keyword refinement, richer metrics, possible semantic filters.
- Future ethics/policy adjustments based on observed edge cases.
