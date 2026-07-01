# TradingView Desktop Controller — MCP Server

A standalone MCP server providing **autonomous programmatic control** over [TradingView Desktop](https://www.tradingview.com/desktop/) via Chrome DevTools Protocol (CDP).

## What It Does

This server exposes **37 MCP tools** that let an AI coding agent control TradingView Desktop as if a human were using it:

| Domain | Tools |
|--------|-------|
| **Chart** | Set symbol, set timeframe, read OHLCV data, apply/remove indicators |
| **Backtest** | Run strategy backtests, read performance summary, trade list, equity curve |
| **Alerts** | Create, edit, delete, and list price alerts |
| **Drawing** | Place trendlines, Fibonacci retracements, rectangles; remove/list drawings |
| **Orders** | Place paper trades (with safety gate), modify, cancel, read positions |
| **Replay** | Enter/step/exit Replay mode with state machine guards |
| **Settings** | Read and write indicator/strategy input values |
| **Pine Script** | Read/write source, compile, read errors, read Pine Logs |
| **Diagnostics** | Full health check across all 9 domains |

## Quick Start

### Prerequisites
- Python 3.12+
- [TradingView Desktop](https://www.tradingview.com/desktop/) installed

### Installation

```bash
# Clone and setup
cd tv-desktop-controller
python3.12 -m venv .venv
source .venv/bin/activate
pip install mcp websockets httpx click pytest pytest-asyncio
```

### Launch TradingView Desktop with Debug Port

```bash
# Option A: Launch script
./scripts/launch_tv_desktop.sh

# Option B: Manual launch
/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=8315
```

### Run Reconnaissance (first-time setup)

Before the server can control TV Desktop, it needs to discover the DOM selectors for each UI panel:

```bash
python -m core.services.recon --no-launch --port 8315
```

This guides you through a ~4-minute interaction sequence. The output is `recon_findings.json` — the configuration file that drives all backends.

### Start the MCP Server

```bash
python server.py
```

The server communicates over **stdio** — configure your MCP client to launch it.

### MCP Client Configuration

Add to your MCP client's config (e.g., Claude Desktop, VS Code Copilot):

```json
{
  "mcpServers": {
    "tv-desktop-controller": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/tv-desktop-controller"
    }
  }
}
```

## Safety Warnings

### 🤖 Paper Trading Only
All order operations (`tv_order_place`, `tv_order_modify`) are designed for **paper trading only**. They require an explicit `confirm=True` parameter — the `confirm` flag defaults to `False` and cannot be silently bypassed.

If TradingView Desktop is ever connected to a live broker, **do not enable order tools** without re-auditing the entire order flow.

### 🔒 Three-Layer Order Safety Gate
1. **MCP Tool** — `confirm` parameter defaults to `False`
2. **Controller** — `TVOrderController.place()` raises `OrderSubmissionBlocked` if not confirmed
3. **Backend** — `DomOrderBackend.place()` raises `OrderSubmissionBlocked` if not confirmed

### 🔄 Multi-Renderer Architecture
TV Desktop runs ~11 separate CDP targets (toast, new-tab, browser-api, etc.). The server uses scoring-based target selection to always connect to the **main chart page** at `tradingview.com/chart/...`. Do not change the target selection logic without verifying against the actual CDP targets.

## How It Works

```
MCP Client (Agent)
    ↕ MCP Protocol (stdio)
server.py (37 tool handlers)
    ↕
9 Domain Controllers (chart, backtest, alert, drawing, order, replay, settings, pinescript)
    ↕ Strategy Pattern
Backend Layer (DOM / JS / Network — selected at runtime from recon)
    ↕
cdp_connection.py (WebSocket → Chrome DevTools Protocol)
    ↕
TradingView Desktop (Electron app with --remote-debugging-port)
```

### Architecture Decisions
- **All DOM, no JS API** — Recon confirmed `window.tvWidget` and similar APIs don't exist. All 9 domains use DOM automation (Path C).
- **Stable selectors only** — TV Desktop uses hashed CSS class names that change per build. All selectors use `data-name`, `aria-label`, `role`, `data-qa-id`, and element IDs.
- **Factory pattern** — Each domain can switch between DOM/JS/Network at runtime by changing `recon_findings.json`. No controller code changes needed.

## Running Tests

```bash
# Unit tests (fast, no TV Desktop needed)
python -m pytest tests/ -v -m "not integration"

# Integration tests (requires live TV Desktop on port 8315)
python -m pytest tests/ -v -m integration

# Everything
python -m pytest tests/ -v
```

## Maintenance Protocol

If a TradingView Desktop update breaks something:

1. **`tv_diagnostics()`** — narrows breakage to a specific domain via health check
2. **`tv_recon_run()`** — re-runs the interactive recon session to update selectors
3. **Fix affected backend** — update selectors in `recon_findings.json` for the broken capability
4. **Commit updated recon** — `recon_findings.json` is tracked in git
5. **Re-verify order panel** — after any TV Desktop update, manually verify order selectors before trusting `confirmed=True`

## Project Structure

```
tv-desktop-controller/
├── server.py                    # MCP server entry point
├── recon_findings.json          # Capability classifications (committed)
├── core/services/
│   ├── cdp_connection.py        # CDP WebSocket transport
│   ├── dom_utils.py             # DOM automation primitives
│   ├── errors.py                # Typed error classes
│   ├── recon.py                 # Interactive recon tool
│   ├── *_controller.py          # 8 domain controllers
│   └── backends/
│       ├── base.py              # 9 abstract interfaces
│       ├── dom_backend.py       # DOM implementations
│       ├── js_backend.py        # JS stubs
│       └── network_backend.py   # Network stubs
├── scripts/
│   ├── launch_tv_desktop.sh     # TV Desktop launcher
│   └── dom_probe.py             # DOM probe helper
├── tests/                       # Unit + integration tests
└── docs/                        # Sprint plans + QA audits
```

## License

MIT
