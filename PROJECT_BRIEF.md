# TradingView Desktop Controller — MCP Server

## 1. Project Overview

An MCP (Model Context Protocol) server that provides autonomous, programmatic control over TradingView Desktop — an Electron wrapper around the tradingview.com web app. Uses Chrome DevTools Protocol (CDP) for DOM automation, JS injection, and network interception to control every major feature of the app.

## 2. Architecture

```
MCP Client (Agent) ↔ MCP Server (server.py) ↔ Domain Controllers ↔ Backend Strategy Pattern ↔ CDP Connection → TradingView Desktop
```

- **MCP Layer:** `server.py` registers all `@mcp.tool()` handlers with startup validation
- **Controller Layer:** One class per domain — handles business logic, state guards, error mapping
- **Backend Layer:** Strategy pattern — each capability resolves at runtime to A (JS), B (Network), or C (DOM) based on recon findings
- **Transport Layer:** `cdp_connection.py` wraps CDP via `websockets` library

## 3. Domains (9 total)

| # | Domain | Capabilities | Default Path |
|---|--------|-------------|-------------|
| 1 | **Chart** | symbol_control, timeframe_control, ohlcv_read | Mixed (DOM + Network) |
| 2 | **Indicators/Scripts** | indicator_apply, indicator_remove | DOM |
| 3 | **Backtest** | backtest_run, backtest_summary, backtest_trade_list, backtest_equity_curve | DOM |
| 4 | **Alerts** | alert_create, alert_edit, alert_delete, alert_list | DOM |
| 5 | **Drawing Tools** | drawing_create, drawing_remove, drawing_list | DOM |
| 6 | **Order Panel** | order_place, order_modify, order_cancel, order_status_read | DOM |
| 7 | **Replay Mode** | replay_enter, replay_step, replay_exit, replay_state_read | DOM |
| 8 | **Strategy Settings** | settings_list_fields, settings_read, settings_write | DOM |
| 9 | **Pine Script Dev** | pine_read, pine_write, pine_compile, pine_compile_errors_read, pine_logs_read | DOM |

## 4. Key Principles

- **Recon-first:** Every capability is empirically classified (A/B/C) before any controller code is written
- **No hardcoded selectors:** All selectors live in `recon_findings.json` and are injected at runtime
- **Safety-first:** Order panel requires explicit `confirmed=True` — never silently submit real orders
- **No SDK assumptions:** TV Desktop is NOT the embeddable Charting Library; verify every JS path
- **Comprehensive diagnostics:** `tv_diagnostics()` reports health of all 9 domains at once

## 5. Technology Stack

- **Runtime:** Python 3.11+
- **MCP Framework:** `mcp` (official SDK)
- **CDP Transport:** `websockets` (WebSocket → Chrome DevTools Protocol)
- **Testing:** `pytest` with mocked backends
- **Config:** `recon_findings.json` — schema v2, generated and committed

## 6. Sprint Plan

| Sprint | Focus | Output |
|--------|-------|--------|
| **Sprint 1** | Foundation | pyproject.toml, cdp_connection.py, errors.py, dom_utils.py, recon.py → recon_findings.json |
| **Sprint 2** | Backend Strategy | All backend interfaces + concrete classes + factory functions + tests |
| **Sprint 3** | Core Controllers | ChartController, BacktestController + tests |
| **Sprint 4** | Expansion Controllers | AlertController, DrawingController, OrderController, ReplayController + tests |
| **Sprint 5** | Dev Controllers | SettingsController, PineScriptController + tests |
| **Sprint 6** | MCP Server + Integration | server.py, all tool registrations, integration tests, scripts, README |

## 7. Current Status

- [x] Sprint 1 — Foundation
- [x] Sprint 2 — Backend Strategy
- [x] Sprint 3 — Core Controllers
- [x] Sprint 4 — Expansion Controllers
- [x] Sprint 5 — Dev Controllers
- [x] Sprint 6 — MCP Server + Integration

### 7.1 Capability Verification Matrix (2026-07-01)

Verified against live TradingView Desktop (NQ 5-min, WaveTrend MAX v5.8).

| Domain | Tool | Status | V-Evidence |
|--------|------|--------|-----------|
| Chart | `tv_set_symbol` | ✅ | Symbol header text detection via `title-YTFIJ62h` |
| Chart | `tv_set_timeframe` | ✅ | Active interval button via `isActive-U9b0TAs4` |
| Chart | `tv_get_chart_data` | ❌ | Needs network WebSocket interception |
| Chart | `tv_apply_script` | ⚠️ | Editor open + paste + Add-to-Chart coded; untested E2E |
| Chart | `tv_remove_indicator` | ⚠️ | Selector-dependent |
| Chart | `tv_screenshot` | ✅ | CDP `Page.captureScreenshot` → 584KB PNG verified |
| Backtest | `tv_run_backtest` | ⚠️ | Tab click works; trigger from strategy panel untested |
| Backtest | `tv_get_backtest_summary` | ✅ | `extract_innertext_map` → 8 metrics (Sharpe 0.193, trades, CAGR, DD%) |
| Backtest | `tv_get_backtest_trades` | ❌ | SVG virtual scroller — no DOM path |
| Backtest | `tv_get_backtest_equity_curve` | ❌ | SVG-only, no DOM extraction |
| Alerts | `tv_alert_create` | ⚠️ | Dialog open/close; condition fields untested |
| Alerts | `tv_alert_edit` | ⚠️ | Selector-dependent |
| Alerts | `tv_alert_delete` | ⚠️ | Selector-dependent |
| Alerts | `tv_alert_list` | ⚠️ | Panel selector unverified |
| Drawing | `tv_drawing_create` | ⚠️ | Toolbar selectors populated; canvas click works |
| Drawing | `tv_drawing_remove` | ⚠️ | Selector-dependent |
| Drawing | `tv_drawing_list` | ⚠️ | Panel selector unverified |
| Orders | `tv_order_place` | ⚠️ | Safety gates ✅; order ticket DOM untested |
| Orders | `tv_order_modify` | ⚠️ | Selector-dependent |
| Orders | `tv_order_cancel` | ⚠️ | Selector-dependent |
| Orders | `tv_order_status` | ⚠️ | Panel selector unverified |
| Replay | `tv_replay_enter` | ✅ | Button click + state machine guards ✅ |
| Replay | `tv_replay_step` | ⚠️ | Step button unverified |
| Replay | `tv_replay_exit` | ⚠️ | Exit button unverified |
| Replay | `tv_replay_state` | ⚠️ | Text format may vary |
| Settings | `tv_settings_list_fields` | ✅ | Gear click + dialog text extraction |
| Settings | `tv_settings_read` | ✅ | Dialog text read |
| Settings | `tv_settings_write` | ✅ | Dialog + type + Apply click |
| Pine Script | `tv_pine_read` | ⚠️ | Scroll+textarea → ~360 chars. Hard Monaco limit. |
| Pine Script | `tv_pine_write` | ⚠️ | Focus + textarea.value + input event |
| Pine Script | `tv_pine_compile` | ⚠️ | Button click; result parsing untested |
| Pine Script | `tv_pine_compile_errors` | ❌ | Console not DOM-accessible |
| Pine Script | `tv_pine_logs` | ❌ | Panel selectors unverified |
| Diagnostics | `tv_diagnostics` | ✅ | 9-domain health check |

**Legend**: ✅ Verified Working | ⚠️ Coded, Untested E2E | ❌ Unavailable (hard limit)

### 7.2 Hard Limitations (2026-07-01)

| Limitation | Root Cause | Impact |
|-----------|------------|--------|
| Full Pine source read | Monaco virtual scroller; textarea holds ~360 chars max; `window.monaco` undefined; React Fiber keys absent | Cannot read full 463-line source via CDP. Use local file as ground truth. |
| Strategy Tester trade list | SVG-rendered virtual scroller | Cannot extract per-trade PnL/timing |
| Equity curve data | SVG `<path>` elements only | Cannot read curve values |
| OHLCV data | Network WebSocket protocol not reverse-engineered | Cannot read chart bar data |
| Pine compile errors | Console rendered as Monaco decorations, not DOM | Cannot parse error messages |
| Pine Logs | Panel uses virtual scroller + SVG | Cannot read log entries |

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| TradingView Desktop UI changes | Health checks on every domain; recon diff on update; selector fallback arrays |
| Live order accidentally submitted | `confirmed` gate at controller, backend, and tool level — three layers of defense |
| CDP protocol changes | Batch all CDP calls through one connection module; version-pin `websockets` |
| Published scripts can't use Pine Logs | Capability reports `CapabilityUnavailable` gracefully; recon documents the restriction |

### 8.1 Bug Fixes Applied (2026-07-01, Sprint Hardening)

The following critical/high-severity bugs were fixed in a dedicated hardening pass:

| Area | Bug | Fix |
|------|-----|-----|
| `dom_utils.py` | Missing `import json` (crashes `extract_table`) | Added import |
| `dom_utils.py` | JS injection via naive `.replace("'", "\\'")` in 10 methods | Replaced with `json.dumps()` |
| `dom_utils.py` | `extract_text` can't read `<input>`/`<textarea>` values | Added `.tagName` check, returns `.value` for form elements |
| `dom_utils.py` | `extract_innertext_map` ignores `timeout` parameter | Added polling loop with deadline |
| `dom_utils.py` | Regex can't match negative numbers | Added `-?` prefix to regex |
| `cdp_connection.py` | Pending futures hang forever on WS crash | Rejected with `CDPConnectionError` on disconnect |
| `cdp_connection.py` | Reader task not awaited after cancel | Proper `await` with `CancelledError` handling |
| `cdp_connection.py` | Stale state leaks on connection retry | Cleanup in `except` block |
| `dom_backend.py` | `sl`/`tp` ignored in `place()` | Now types into stop-loss/take-profit fields |
| `dom_backend.py` | JS injection in `apply()` | Replaced `.replace()` with `json.dumps()` |

See `docs/sprint-hardening/done.md` for full details.
