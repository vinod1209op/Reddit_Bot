#!/bin/bash
set -euo pipefail

# Wrapper: start multiple Tor instances and test them.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/tor_multi_start.sh"
"$SCRIPT_DIR/tor_multi_test.sh"
