#!/usr/bin/env bash
# Start proxy in live mode and run verification
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$WEB_DIR"

PORT="${PORT:-3000}"

if [[ ! -f config.js ]]; then
  cp config.example.js config.js
  echo "Created config.js from example — edit useLiveAgents and zalopay.bankBin before demo"
fi

if ! grep -q 'useLiveAgents: true' config.js 2>/dev/null; then
  echo "NOTE: Set useLiveAgents: true in config.js for live agent mode"
fi

if grep -q 'bankBin: ""' config.js 2>/dev/null; then
  echo "WARNING: zalopay.bankBin is empty in config.js — fill NAPAS BIN for VietQR settlement"
fi

echo "Starting proxy on http://127.0.0.1:$PORT ..."
python3 proxy.py &
PROXY_PID=$!

cleanup() {
  kill "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2

if ! curl -sf "http://127.0.0.1:$PORT/" >/dev/null; then
  echo "ERROR: Proxy failed to start on port $PORT"
  exit 1
fi

echo ""
bash scripts/verify_live.sh "http://127.0.0.1:$PORT"

echo ""
echo "Proxy running at http://127.0.0.1:$PORT (PID $PROXY_PID)"
echo "Press Ctrl+C to stop"
wait "$PROXY_PID"
