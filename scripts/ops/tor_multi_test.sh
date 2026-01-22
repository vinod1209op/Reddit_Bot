#!/bin/bash
set -euo pipefail

# Test each local Tor instance by fetching public IP via SOCKS.
# Optional: CHECK_URL=https://check.torproject.org/api/ip

CHECK_URL="${CHECK_URL:-https://check.torproject.org/api/ip}"

for port in 9050 9051 9052; do
  echo -n "Port $port: "
  if curl --socks5-hostname "127.0.0.1:$port" --max-time 10 "$CHECK_URL" 2>/dev/null; then
    echo ""
  else
    echo "Failed"
  fi
done
