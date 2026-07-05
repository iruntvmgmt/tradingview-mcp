# Capability Status

> **Generated file — do not hand-edit.** Rebuilt from `recon_findings.json` + `docs/known_issues.json` by `scripts/generate_status.py`. To change what this file says, either fix the underlying code and re-run recon, or edit `docs/known_issues.json` and re-run the generator.

Last generated: 2026-07-05 08:19 UTC
Source: `recon_findings.json` (schema v2)

**17/33** capabilities recon-verified · **8** have open known issues that override that verification (see table).

## Capability matrix

| Capability | Path | Recon status | Real-world status | Open issues |
|---|---|---|---|---|
| `alert_create` | `dom` | verified | 🟢 Verified | — |
| `alert_delete` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `alert_edit` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `alert_list` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `backtest_equity_curve` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `backtest_run` | `dom` | verified | 🟢 Verified | — |
| `backtest_summary` | `dom` | verified | 🟢 Verified | — |
| `backtest_trade_list` | `dom` | unverified | 🔴 Known issue | 🟠 Individual trade records NOT AVAILABLE in TradingView Desktop 3.2.0 free tier. The Strategy Tester shows aggregated trade analysis (Trades analysis details tab: Outliers P&L, trade counts by type) but the individual trade list with per-trade Entry/Exit/P&L appears to require a paid TradingView plan (Upgrade to get full access to Strategy report data buttons found in the panel). The backtest_summary provides net_profit, sharpe, profit_factor, max_drawdown, avg_pnl, etc. which covers most evaluation needs. Individual trades not accessible via DOM. |
| `drawing_create` | `dom` | verified | 🟢 Verified | — |
| `drawing_list` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `drawing_remove` | `dom` | verified | 🟢 Verified | — |
| `indicator_apply` | `dom` | verified | 🟢 Verified | — |
| `indicator_remove` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `ohlcv_read` | `dom` | unverified | 🔴 Known issue | 🟠 Dead end on both implemented paths. DOM backend punts to network path with a CapabilityUnavailable; network backend's get_ohlcv also unconditionally raises CapabilityUnavailable despite its own docstring claiming OHLCV is the one thing the network path supports. No working OHLCV read exists. |
| `order_cancel` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `order_modify` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `order_place` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `order_status_read` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `pine_compile` | `dom` | verified | 🟢 Verified | — |
| `pine_compile_errors_read` | `dom` | verified | 🟢 Verified | — |
| `pine_logs_read` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `pine_read` | `dom` | verified | 🟢 Verified | — |
| `pine_write` | `dom` | verified | 🟢 Verified | — |
| `replay_enter` | `dom` | verified | 🟢 Verified | — |
| `replay_exit` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `replay_state_read` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `replay_step` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `screenshot` | `cdp` | verified | 🟢 Verified | — |
| `settings_list_fields` | `dom` | verified | 🟢 Verified | — |
| `settings_read` | `dom` | verified | 🟢 Verified | — |
| `settings_write` | `dom` | verified | 🟢 Verified | — |
| `symbol_control` | `dom` | verified | 🟢 Verified | — |
| `timeframe_control` | `dom` | verified | 🟢 Verified | — |

## Open issues (detail)

### 🟠 `backtest_trade_list` — Individual trade records NOT AVAILABLE in TradingView Desktop 3.2.0 free tier. The Strategy Tester shows aggregated trade analysis (Trades analysis details tab: Outliers P&L, trade counts by type) but the individual trade list with per-trade Entry/Exit/P&L appears to require a paid TradingView plan (Upgrade to get full access to Strategy report data buttons found in the panel). The backtest_summary provides net_profit, sharpe, profit_factor, max_drawdown, avg_pnl, etc. which covers most evaluation needs. Individual trades not accessible via DOM.

- **Severity:** major
- **Blocks primary goal:** no
- **Opened:** 2026-07-05
- **Detail:** docs/handoff/2026-07-05-pine-errors-and-trade-list.md

### 🟠 `ohlcv_read` — Dead end on both implemented paths. DOM backend punts to network path with a CapabilityUnavailable; network backend's get_ohlcv also unconditionally raises CapabilityUnavailable despite its own docstring claiming OHLCV is the one thing the network path supports. No working OHLCV read exists.

- **Severity:** major
- **Blocks primary goal:** no
- **Opened:** 2026-07-03
- **Detail:** docs/handoff/2026-07-03-audit-findings.md#ohlcv

## Test coverage caveat

All current automated tests (`tests/*.py`) mock `DomUtils` and `CDPConnection` at the boundary. They verify controller → backend dispatch is wired correctly; they do **not** verify that any selector actually matches a live TradingView Desktop DOM. A passing test suite is not evidence that a `dom` capability works in practice — only `recon_findings.json`'s `verified` flag (ideally backed by a manual live-session check) is. See `docs/adr/0003-integration-vs-unit-test-boundary.md`.
