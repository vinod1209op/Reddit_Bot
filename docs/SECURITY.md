# Security

## Secrets Handling
- Store secrets in `config/credentials.env` (gitignored) or platform secret managers.
- Never commit cookie files (`data/cookies_*.pkl`) or credential files.
- Supabase Storage cookies should be treated as sensitive secrets.
- Use the least-privileged Supabase key for each environment (e.g., anon key for read-only Render; service role only in CI where writes are required).

## Access Control
- Protect Streamlit with `STREAMLIT_APP_PASSWORD`.
- Keep posting disabled (`ENABLE_POSTING=0`) unless explicitly approved.

## Cookie Lifecycle
- Refresh cookies regularly and rotate if login challenges appear.
- Use least privilege: only service role keys in CI where required.

## Logging
- Logs should not contain user PII beyond post IDs and titles.
- Review `logs/` before sharing artifacts externally.
