#!/bin/bash
set -euo pipefail

# Stop the local Tor instances started by tor_multi_start.sh.

stopped_any=0
for i in 0 1 2; do
  PIDFILE="$HOME/.tor$i/tor.pid"
  if [ -f "$PIDFILE" ]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" >/dev/null 2>&1; then
      kill "$PID"
      echo "Stopped Tor instance $i (pid $PID)"
      stopped_any=1
    fi
    rm -f "$PIDFILE"
  fi
done

if [ "$stopped_any" -eq 0 ]; then
  echo "No Tor instances found to stop."
fi
