# Contributing

## Workflow
- Create a feature branch from `main`.
- Keep changes scoped and documented.
- Add or update tests when changing core behavior.

## Tests
- Unit/smoke tests: `python -m unittest discover -v tests`

## Style
- Prefer clear, small functions.
- Keep logging structured and consistent (`UnifiedLogger`).

## Safety
- Posting must remain off by default.
- Do not commit secrets or cookie files.
