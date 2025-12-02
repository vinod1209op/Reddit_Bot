# Ethics & Limitations

## Ethical Guardrails
- No medical or dosing advice; no encouragement of illegal activity.
- No links, product or brand promotion.
- Human approval required before posting; posting disabled by default.
- Low volume by design (approval cap, limited scans); respect subreddit rules and Reddit’s Responsible Builder Policy.
- Transparent intent: educational, harm-reduction-oriented, neutral tone; suggest professional help for personal guidance.

## Privacy & Data Handling
- Data stored locally in CSVs (`bot_logs.csv`, `bot_metrics.csv`); no external storage.
- Collected fields: post/comment IDs, titles, matched keywords, reply text, approval decisions, basic engagement (score/replies).
- No user PII collected beyond public Reddit content; avoid logging usernames.

## Model/Content Risks
- LLM output (when enabled) is constrained by a strict safety prompt; stub reply used as fallback.
- Human-in-the-loop mitigates inappropriate outputs; posting guard defaults to off.
- Keyword matching is simple; may surface irrelevant posts—requires mindful approval.

## Operational Limits
- API access may be restricted; mock mode allows development but does not exercise live behaviors.
- Rate/volume should remain low; add sleeps/throttling before scaling beyond small batches.
- Metrics script counts shallow replies (no deep `replace_more` to limit API load).

## Limitations & Future Mitigations
- Simple keyword matching (no semantic filtering); could add safer, context-aware filters later.
- No automatic subreddit rule parsing; human must verify fit and skip when unsure.
- Engagement metrics are basic (score, reply count); sentiment/quality not measured.
- No automated rollback/edits; rely on cautious approval and minimal volume.
