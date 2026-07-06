# Capability Status

> **Generated file — do not hand-edit.** Rebuilt from `recon_findings.json` + `docs/known_issues.json` by `scripts/generate_status.py`. To change what this file says, either fix the underlying code and re-run recon, or edit `docs/known_issues.json` and re-run the generator.

Last generated: 2026-07-06 18:40 UTC
Source: `recon_findings.json` (schema v2)

**19/35** capabilities recon-verified · **12** have open known issues that override that verification (see table).

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
| `backtest_trade_list` | `dom` | verified | 🟢 Verified | 🟡 Standing risk: parser relies on innerText line-position order, not stable selectors. A TV wording/line-order change could silently corrupt field mapping. Manual spot-check required after each TradingView Desktop update (see ADR-0009). |
| `chart_set_visible_range` | `dom` | unverified | ⚪ Unverified (untested against live app) | 🟡 Open: set_visible_range still uses Strategy Tester date-range presets (1D/5D/1M/3M/6M/1Y/5Y/All via data-name attributes), not absolute dates. This cannot satisfy ADR-0010 non-overlapping train/validation/holdout windows. TV Desktop 3.2.0 has zero iframes; _exposed_chartWidgetCollection.activeChartWidget has only _listeners/_value, no chart()/setVisibleRange(). Alt+G/date-picker investigation still needed. |
| `drawing_create` | `dom` | verified | 🟢 Verified | — |
| `drawing_list` | `dom` | unverified | ⚪ Unverified (untested against live app) | — |
| `drawing_remove` | `dom` | verified | 🟢 Verified | — |
| `experiment_report` | `orchestration` | verified | 🟢 Verified | — |
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

### 🟡 `backtest_trade_list` — Standing risk: parser relies on innerText line-position order, not stable selectors. A TV wording/line-order change could silently corrupt field mapping. Manual spot-check required after each TradingView Desktop update (see ADR-0009).

- **Severity:** minor
- **Blocks primary goal:** no
- **Opened:** 2026-07-05
- **Detail:** docs/adr/0009-trade-list-text-position-parsing-fragility.md

### 🟡 `chart_set_visible_range` — Open: set_visible_range still uses Strategy Tester date-range presets (1D/5D/1M/3M/6M/1Y/5Y/All via data-name attributes), not absolute dates. This cannot satisfy ADR-0010 non-overlapping train/validation/holdout windows. TV Desktop 3.2.0 has zero iframes; _exposed_chartWidgetCollection.activeChartWidget has only _listeners/_value, no chart()/setVisibleRange(). Alt+G/date-picker investigation still needed.

- **Severity:** minor
- **Blocks primary goal:** yes
- **Opened:** 2026-07-05
- **Detail:** docs/handoff/2026-07-07-fix-blockers.md#absolute-date-window-control

### 🟠 `ohlcv_read` — Dead end on both implemented paths. DOM backend punts to network path with a CapabilityUnavailable; network backend's get_ohlcv also unconditionally raises CapabilityUnavailable despite its own docstring claiming OHLCV is the one thing the network path supports. No working OHLCV read exists.

- **Severity:** major
- **Blocks primary goal:** no
- **Opened:** 2026-07-03
- **Detail:** docs/handoff/2026-07-03-audit-findings.md#ohlcv

## Test coverage caveat

All current automated tests (`tests/*.py`) mock `DomUtils` and `CDPConnection` at the boundary. They verify controller → backend dispatch is wired correctly; they do **not** verify that any selector actually matches a live TradingView Desktop DOM. A passing test suite is not evidence that a `dom` capability works in practice — only `recon_findings.json`'s `verified` flag (ideally backed by a manual live-session check) is. See `docs/adr/0003-integration-vs-unit-test-boundary.md`.
