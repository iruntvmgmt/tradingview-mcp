#!/usr/bin/env bash
# Launch TradingView Desktop with Chrome DevTools Protocol enabled.
# Usage: ./scripts/launch_tv_desktop.sh [port]
# Default port: 8315

set -euo pipefail

PORT="${1:-8315}"

# Detect OS and find TV Desktop executable
if [[ "$OSTYPE" == "darwin"* ]]; then
    CANDIDATES=(
        "/Applications/TradingView.app/Contents/MacOS/TradingView"
        "$HOME/Applications/TradingView.app/Contents/MacOS/TradingView"
    )
elif [[ "$OSTYPE" == "linux"* ]]; then
    CANDIDATES=(
        "tradingview"
        "/opt/tradingview/tradingview"
    )
else
    echo "Unsupported OS: $OSTYPE" >&2
    exit 1
fi

EXEC=""
for c in "${CANDIDATES[@]}"; do
    if [ -x "$c" ] || command -v "$c" &>/dev/null; then
        EXEC="$c"
        break
    fi
done

if [ -z "$EXEC" ]; then
    echo "ERROR: TradingView Desktop not found." >&2
    echo "Tried: ${CANDIDATES[*]}" >&2
    exit 1
fi

echo "Launching: $EXEC --remote-debugging-port=$PORT"
"$EXEC" --remote-debugging-port="$PORT" &
TV_PID=$!
echo "TV Desktop PID: $TV_PID (debug port: $PORT)"
echo "Press Ctrl+C to stop the MCP server and close TV Desktop."
wait $TV_PID
