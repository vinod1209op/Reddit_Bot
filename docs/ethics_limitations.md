# Ethics & Limitations

## Ethical Guardrails
- No medical or dosing advice; no microdosing protocols or schedules; no encouragement of illegal activity.
- No links, product or brand promotion.
- Human approval required before posting; posting disabled by default.
- Low volume by design (approval cap, limited scans); respect subreddit rules and Reddit’s Responsible Builder Policy.
- Transparent intent: educational, harm-reduction-oriented, neutral tone; suggest professional help for personal guidance.

## Privacy & Data Handling
- Data stored locally in CSVs and JSON (`bot_logs.csv`, `bot_metrics.csv`, `logs/night_scan_summary.csv`, `logs/night_queue.json`); no external storage.
- Collected fields: post/comment IDs, titles, matched keywords, reply text, approval decisions, basic engagement (score/replies).
- No user PII collected beyond public Reddit content; avoid logging usernames.

## Model/Content Risks
- LLM output (when enabled, via OpenRouter) is constrained by a strict safety prompt; stub reply used as fallback.
- Explicit guard against dosing guidance/protocols and illegal encouragement; human-in-the-loop mitigates inappropriate outputs; posting guard defaults to off.
- Keyword matching is simple; may surface irrelevant posts—requires mindful approval.

## Operational Limits
- API access may be restricted; mock mode allows development but does not exercise live behaviors.
- Rate/volume should remain low; add sleeps/throttling before scaling beyond small batches.
- Metrics script counts shallow replies (no deep `replace_more` to limit API load).
- Humanized browsing/engagement helpers (`selenium_automation/utils/human_simulator.py`, `selenium_automation/utils/engagement_actions.py`, `scripts/humanized_night_scanner.py`) are used for read-only activity windows; keep behaviors conservative and aligned with subreddit rules.
- No proxy rotation is implemented; any fingerprint randomization in Selenium helpers is experimental and not required for core use.

## Limitations & Future Mitigations
- Simple keyword matching (no semantic filtering); could add safer, context-aware filters later.
- No automatic subreddit rule parsing; human must verify fit and skip when unsure.
- Engagement metrics are basic (score, reply count); sentiment/quality not measured.
- No automated rollback/edits; rely on cautious approval and minimal volume.
