#!/bin/bash
set -euo pipefail

# Run humanized night scanner locally with proper PYTHONPATH.
# Usage:
#   scripts/ops/run_humanized_local.sh account1 9050

ACCOUNT="${1:-account1}"
TOR_PORT="${2:-}"

export PYTHONPATH="src:."
export USE_TOR_PROXY="1"
if [ -n "$TOR_PORT" ]; then
  export TOR_SOCKS_PORT="$TOR_PORT"
fi
export HUMANIZED_ACCOUNT_NAMES="$ACCOUNT"

python scripts/runners/humanized_night_scanner.py --force-run
