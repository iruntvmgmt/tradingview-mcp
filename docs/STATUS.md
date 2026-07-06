# Capability Status

> **Generated file — do not hand-edit.** Rebuilt from `recon_findings.json` + `docs/known_issues.json` by `scripts/generate_status.py`. To change what this file says, either fix the underlying code and re-run recon, or edit `docs/known_issues.json` and re-run the generator.

Last generated: 2026-07-06 16:53 UTC
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
| `backtest_run` | `dom` | verified | 🔴 Known issue | 🟠 recon_findings.json's selector for the backtest Summary tab (button[id="strategy-report-summary"]) does not match the actual DOM on TV Desktop 3.2.0, where the real tab id is "Strategy report" (with a space) and tabs use data-name="light-tab-0"/"light-tab-1" instead. backtest_run is currently marked verified:true in recon_findings.json but is running against a stale selector — the verified flag is unreliable for this capability until selectors are corrected and recon is rerun. |
| `backtest_summary` | `dom` | verified | 🟢 Verified | — |
| `backtest_trade_list` | `dom` | verified | 🟢 Verified | 🟡 Standing risk: parser relies on innerText line-position order, not stable selectors. A TV wording/line-order change could silently corrupt field mapping. Manual spot-check required after each TradingView Desktop update (see ADR-0009). |
| `chart_set_visible_range` | `dom` | unverified | ⚪ Unverified (untested against live app) | 🟡 Partial fix: set_visible_range now uses Strategy Tester date-range presets (1D/5D/1M/3M/6M/1Y/5Y/All via data-name attributes) instead of non-existent JS API. No arbitrary date boundaries — windows are approximate. TV Desktop 3.2.0 has zero iframes; _exposed_chartWidgetCollection.activeChartWidget has only _listeners/_value, no chart()/setVisibleRange(). React fiber keys not found on DOM nodes. |
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
| `symbol_control` | `dom` | verified | 🔴 Known issue | 🟠 DomChartBackend.set_symbol() fails on TV Desktop 3.2.0 — selector input[data-name="symbol-search"] does not match. The symbol search input's data-name attribute has changed in this version. |
| `timeframe_control` | `dom` | verified | 🟢 Verified | — |

## Open issues (detail)

### 🟠 `backtest_run` — recon_findings.json's selector for the backtest Summary tab (button[id="strategy-report-summary"]) does not match the actual DOM on TV Desktop 3.2.0, where the real tab id is "Strategy report" (with a space) and tabs use data-name="light-tab-0"/"light-tab-1" instead. backtest_run is currently marked verified:true in recon_findings.json but is running against a stale selector — the verified flag is unreliable for this capability until selectors are corrected and recon is rerun.

- **Severity:** major
- **Blocks primary goal:** yes
- **Opened:** 2026-07-05
- **Detail:** docs/handoff/2026-07-05-live-pipeline-attempt.md

### 🟡 `backtest_trade_list` — Standing risk: parser relies on innerText line-position order, not stable selectors. A TV wording/line-order change could silently corrupt field mapping. Manual spot-check required after each TradingView Desktop update (see ADR-0009).

- **Severity:** minor
- **Blocks primary goal:** no
- **Opened:** 2026-07-05
- **Detail:** docs/adr/0009-trade-list-text-position-parsing-fragility.md

### 🟡 `chart_set_visible_range` — Partial fix: set_visible_range now uses Strategy Tester date-range presets (1D/5D/1M/3M/6M/1Y/5Y/All via data-name attributes) instead of non-existent JS API. No arbitrary date boundaries — windows are approximate. TV Desktop 3.2.0 has zero iframes; _exposed_chartWidgetCollection.activeChartWidget has only _listeners/_value, no chart()/setVisibleRange(). React fiber keys not found on DOM nodes.

- **Severity:** minor
- **Blocks primary goal:** yes
- **Opened:** 2026-07-05
- **Detail:** docs/handoff/2026-07-05-live-pipeline-attempt.md

### 🟠 `ohlcv_read` — Dead end on both implemented paths. DOM backend punts to network path with a CapabilityUnavailable; network backend's get_ohlcv also unconditionally raises CapabilityUnavailable despite its own docstring claiming OHLCV is the one thing the network path supports. No working OHLCV read exists.

- **Severity:** major
- **Blocks primary goal:** no
- **Opened:** 2026-07-03
- **Detail:** docs/handoff/2026-07-03-audit-findings.md#ohlcv

### 🟠 `symbol_control` — DomChartBackend.set_symbol() fails on TV Desktop 3.2.0 — selector input[data-name="symbol-search"] does not match. The symbol search input's data-name attribute has changed in this version.

- **Severity:** major
- **Blocks primary goal:** yes
- **Opened:** 2026-07-06
- **Detail:** docs/handoff/2026-07-06-set-visible-range-fix.md

## Test coverage caveat

All current automated tests (`tests/*.py`) mock `DomUtils` and `CDPConnection` at the boundary. They verify controller → backend dispatch is wired correctly; they do **not** verify that any selector actually matches a live TradingView Desktop DOM. A passing test suite is not evidence that a `dom` capability works in practice — only `recon_findings.json`'s `verified` flag (ideally backed by a manual live-session check) is. See `docs/adr/0003-integration-vs-unit-test-boundary.md`.
