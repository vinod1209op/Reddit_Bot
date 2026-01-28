#!/usr/bin/env bash
set -euo pipefail

python3 scripts/ops/validate_configs.py
pytest -q tests/unit

set +e
pytest -q tests/integration
code=$?
set -e

if [ "$code" -eq 5 ]; then
  echo "No integration tests found; skipping."
  exit 0
fi

exit "$code"
