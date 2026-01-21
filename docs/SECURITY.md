# Security

## Secrets Handling
- Store secrets in `config/credentials.env` (gitignored) or platform secret managers.
- Never commit cookie files (`data/cookies_*.pkl`) or credential files.
- Supabase Storage cookies should be treated as sensitive secrets.

## Access Control
- Protect Streamlit with `STREAMLIT_APP_PASSWORD`.
- Keep posting disabled (`ENABLE_POSTING=0`) unless explicitly approved.

## Cookie Lifecycle
- Refresh cookies regularly and rotate if login challenges appear.
- Use least privilege: only service role keys in CI where required.

## Logging
- Logs should not contain user PII beyond post IDs and titles.
- Review `logs/` before sharing artifacts externally.
