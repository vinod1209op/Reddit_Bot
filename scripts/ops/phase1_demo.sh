#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="logs/phase1_demo"
mkdir -p "$LOG_DIR"

stamp="$(date +%Y%m%d_%H%M%S)"
logfile="$LOG_DIR/phase1_demo_$stamp.log"

{
  echo "=== Phase 1 Demo: $(date) ==="
  echo
  echo "[1/3] Subreddit creation (dry-run + validate-only)"
  python3 scripts/subreddit_creation/create_subreddits.py --dry-run --validate-only
  echo
  echo "[2/3] Content scheduling (dry-run + validate-only)"
  python3 scripts/content_scheduling/schedule_posts.py --dry-run --validate-only
  echo
  echo "[3/3] Moderation (dry-run + validate-only)"
  python3 scripts/moderation/manage_moderation.py --dry-run --validate-only
  echo
  echo "=== Phase 1 Demo Complete ==="
} | tee "$logfile"

echo "\nSaved log: $logfile"
