#!/bin/bash
# ── Launch TradingView Desktop with CDP remote debugging enabled ──────────────
# Uses the direct binary path (NOT `open -a`) so that --remote-debugging-port
# is passed correctly to the Electron process.
#
# Usage:
#   ./scripts/launch_tv_desktop.sh [port]
#
# The default port (8315) matches CDPConnectionManager.DEFAULT_CDP_PORT.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PORT="${1:-8315}"

# Find the binary path
APP_PATH="/Applications/TradingView.app/Contents/MacOS/TradingView"
if [ ! -f "$APP_PATH" ]; then
  APP_PATH="$HOME/Applications/TradingView.app/Contents/MacOS/TradingView"
fi

if [ ! -f "$APP_PATH" ]; then
  echo "❌ TradingView Desktop binary not found."
  echo "   Tried: /Applications/TradingView.app/Contents/MacOS/TradingView"
  echo "   Tried: $HOME/Applications/TradingView.app/Contents/MacOS/TradingView"
  exit 1
fi

# Kill any existing instance (so the new one gets the debugging port)
echo "🔪 Killing existing TradingView Desktop instances..."
pkill -9 -f "TradingView.app/Contents/MacOS/TradingView" 2>/dev/null || true
sleep 2

echo "🚀 Launching TradingView Desktop on CDP port $PORT..."
echo "   Binary: $APP_PATH"
echo ""
nohup "$APP_PATH" "--remote-debugging-port=$PORT" > /tmp/tv-desktop.log 2>&1 &
TV_PID=$!
echo "   PID: $TV_PID"

# Wait for the CDP port to become available
echo "   Waiting for CDP endpoint..."
for i in $(seq 1 15); do
  sleep 1
  if curl -s http://127.0.0.1:$PORT/json/version > /dev/null 2>&1; then
    echo ""
    echo "✅ TradingView Desktop is running with CDP on port $PORT"
    echo "   You can now use tv_recon_run() or tv_desktop_launch()"
    echo "   from the MCP server to connect."
    exit 0
  fi
  echo -n "."
done

echo ""
echo "⚠️  Timed out waiting for CDP port $PORT."
echo "   Check /tmp/tv-desktop.log for details."
