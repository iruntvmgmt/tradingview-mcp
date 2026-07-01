#!/bin/bash
# ── Launch TradingView Desktop with CDP remote debugging enabled ──────────────
# This script must be used BEFORE running tv_desktop_launch() or tv_recon_run()
# so that the CDP connection can attach to a port already open.
#
# Usage:
#   ./scripts/launch_tv_desktop.sh [port]
#
# The default port (8315) matches CDPConnectionManager.DEFAULT_CDP_PORT.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PORT="${1:-8315}"
APP_PATH="/Applications/TradingView.app"

if [ ! -d "$APP_PATH" ]; then
  # Try user Applications folder
  APP_PATH="$HOME/Applications/TradingView.app"
fi

if [ ! -d "$APP_PATH" ]; then
  echo "❌ TradingView Desktop not found at /Applications/TradingView.app"
  echo "   Please install it or update the APP_PATH in this script."
  exit 1
fi

echo "🚀 Launching TradingView Desktop on CDP port $PORT..."
echo "   App: $APP_PATH"
echo ""
echo "⚠️  After the app opens, run tv_recon_run() or tv_desktop_launch()"
echo "   from the MCP server to connect to this instance."
echo ""

open -a "$APP_PATH" --args "--remote-debugging-port=$PORT"

echo "✅ TradingView Desktop launched with --remote-debugging-port=$PORT"
echo "   (It may take a few seconds for the CDP endpoint to become available.)"
