#!/bin/bash
set -euo pipefail

# Start three local Tor instances (9050/9051/9052).
# Optional overrides:
#   TOR_BIN=/path/to/tor
#   TOR_EXIT_NODES_0="us" TOR_EXIT_NODES_1="gb" TOR_EXIT_NODES_2="de"
#   TOR_STRICT_NODES=1

TOR_BIN_DEFAULT="/Users/vinodrongala/Downloads/tor-expert-bundle-macos-x86_64-15.0.4/tor/tor"
TOR_BIN="${TOR_BIN:-$TOR_BIN_DEFAULT}"
TOR_DIR="$(cd "$(dirname "$TOR_BIN")" && pwd)"
TOR_GEOIP="${TOR_GEOIP:-$TOR_DIR/geoip}"
TOR_GEOIP6="${TOR_GEOIP6:-$TOR_DIR/geoip6}"

if [ ! -x "$TOR_BIN" ]; then
  if command -v tor >/dev/null 2>&1; then
    TOR_BIN="tor"
  else
    echo "Tor binary not found."
    echo "Set TOR_BIN or install Tor. Example:"
    echo "  TOR_BIN=\"$TOR_BIN_DEFAULT\" $0"
    exit 1
  fi
fi

for i in 0 1 2; do
  PORT=$((9050 + i))
  DATADIR="$HOME/.tor$i"
  PIDFILE="$DATADIR/tor.pid"
  LOGFILE="$DATADIR/tor.log"

  mkdir -p "$DATADIR"
  chmod 700 "$DATADIR"

  EXIT_ENV="TOR_EXIT_NODES_$i"
  EXIT_NODES="${!EXIT_ENV:-}"
  STRICT_NODES="${TOR_STRICT_NODES:-0}"

  {
    echo "SocksPort 127.0.0.1:$PORT"
    echo "DataDirectory $DATADIR"
    echo "PidFile $PIDFILE"
    echo "Log notice file $LOGFILE"
    if [ -f "$TOR_GEOIP" ]; then
      echo "GeoIPFile $TOR_GEOIP"
    fi
    if [ -f "$TOR_GEOIP6" ]; then
      echo "GeoIPv6File $TOR_GEOIP6"
    fi
    if [ -n "$EXIT_NODES" ]; then
      echo "ExitNodes {$EXIT_NODES}"
      if [ "$STRICT_NODES" = "1" ]; then
        echo "StrictNodes 1"
      fi
    fi
  } > "$DATADIR/torrc"

  "$TOR_BIN" -f "$DATADIR/torrc" --RunAsDaemon 1
  echo "Started Tor on 127.0.0.1:$PORT (pid: $(cat "$PIDFILE" 2>/dev/null || echo "unknown"))"
done
