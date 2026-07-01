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

- [ ] Repo scaffolded
- [ ] Sprint 1 — Foundation
- [ ] Sprint 2 — Backend Strategy
- [ ] Sprint 3 — Core Controllers
- [ ] Sprint 4 — Expansion Controllers
- [ ] Sprint 5 — Dev Controllers
- [ ] Sprint 6 — MCP Server + Integration

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| TradingView Desktop UI changes | Health checks on every domain; recon diff on update; selector fallback arrays |
| Live order accidentally submitted | `confirmed` gate at controller, backend, and tool level — three layers of defense |
| CDP protocol changes | Batch all CDP calls through one connection module; version-pin `websockets` |
| Published scripts can't use Pine Logs | Capability reports `CapabilityUnavailable` gracefully; recon documents the restriction |
