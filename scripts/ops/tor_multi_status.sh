#!/bin/bash
set -euo pipefail

# Show status for the local Tor instances (9050/9051/9052).

for i in 0 1 2; do
  PORT=$((9050 + i))
  PIDFILE="$HOME/.tor$i/tor.pid"
  if [ -f "$PIDFILE" ]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" >/dev/null 2>&1; then
      echo "Tor $i: running (pid $PID, port $PORT)"
    else
      echo "Tor $i: pid file exists but process is not running (pid $PID)"
    fi
  else
    echo "Tor $i: not running (no pid file)"
  fi
done

echo ""
echo "Listening ports:"
for port in 9050 9051 9052; do
  lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && echo "  $port: LISTEN" || echo "  $port: not listening"
done
