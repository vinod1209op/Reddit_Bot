#!/bin/bash
set -euo pipefail

TORRC="$HOME/Library/Application Support/TorBrowser-Data/Tor/torrc"
BACKUP="$TORRC.bak"

if [ ! -f "$TORRC" ]; then
  echo "torrc not found at $TORRC"
  exit 1
fi

cat <<'EOF' > "$TORRC"
ClientOnionAuthDir "/Users/vinodrongala/Library/Application Support/TorBrowser-Data/Tor/onion-auth"
DataDirectory "/Users/vinodrongala/Library/Application Support/TorBrowser-Data/Tor"
GeoIPFile "/Applications/Tor Browser.app/Contents/MacOS/Tor/geoip"
GeoIPv6File "/Applications/Tor Browser.app/Contents/MacOS/Tor/geoip6"
DisableNetwork 0

SocksPort 9050
SocksPort 9051
SocksPort 9052

ControlPort 9054
ControlPort 9055
ControlPort 9056

HashedControlPassword 16:1409D2383099232260DD5238EEC4747F64D405A8D8F90589B47CCD5F6F
MaxCircuitDirtiness 300
EOF

echo "torrc rewritten with multi-port config (3 SOCKS / 3 control ports)."
echo "Restart Tor Browser for the changes to take effect."
