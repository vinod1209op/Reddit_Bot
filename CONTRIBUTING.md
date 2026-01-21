# Contributing

## Workflow
- Create a feature branch from `main`.
- Keep changes scoped and documented.
- Add or update tests when changing core behavior.

## Tests
- Unit/smoke tests: `python -m unittest discover -v tests`
  - Or `make test`

## Style
- Prefer clear, small functions.
- Keep logging structured and consistent (`UnifiedLogger`).
- Honor `.editorconfig` (whitespace, line endings).

## Safety
- Posting must remain off by default.
- Do not commit secrets or cookie files.
