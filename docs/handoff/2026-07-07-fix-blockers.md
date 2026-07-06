# Handoff: 2026-07-07 — set_symbol and backtest_run selectors fixed; absolute date-window remains preset-only

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-06-set-visible-range-fix.md` (verification pass)
**Branch / commit at session end:** `main`

## What was fixed

### Fix 1: set_symbol ✅

**Before**: `DomChartBackend.set_symbol()` used `dom.click()` (CDP mouse
events) which didn't reliably trigger TradingView's React click handlers.
The `input[data-name="symbol-search"]` selector didn't match TV 3.2.0.

**After**: Rewritten to use JS `.click()` on the opener button
(`button#header-toolbar-symbol-search`, which has `id` not `data-name`),
then set the searchbox value via native setter and dispatch Enter key.

**Live evidence**: XAUUSD → BINANCE:ETHUSD.P confirmed:
```
BEFORE: XAUUSD
AFTER: ETHUSD.P
```

**Recon updated**: `symbol_control.detail.symbol_search_input_selectors` →
`input[role="searchbox"][placeholder*="Symbol"]`

### Fix 2: backtest_run tab selectors ✅

**Before**: `recon_findings.json` had `button[id="strategy-report-summary"]`
which only matches a nested Overview sub-tab, not the top-level Strategy
Tester tab.

**After**: Updated to `button[role="tab"][id="Strategy report"][data-name="light-tab-0"]`.

**Live evidence**: Tab click confirmed — "Strategy report" tab (aria-selected="true"),
"Overview" text found in body at index 1691.

**Recon updated**: `backtest_run.detail.tab_selectors`

## What was NOT fixed

### Absolute date-window control 🔴

The `set_visible_range` method still uses Strategy Tester presets
(1D/5D/1M/3M/6M/1Y/5Y/All). Live evidence confirmed the preset approach
works (5Y preset → "Jul 31, 2020 — Jun 30, 2026"), but:

- It cannot express the non-overlapping train/validation/holdout windows
  that ADR-0010 requires.
- All presets are relative to "now" (trailing windows), not absolute
  calendar intervals.

**Explored and rejected**:
- TV Desktop 3.2.0 has NO chart JS API — `_exposed_chartWidgetCollection.
  activeChartWidget` has only `_listeners`/`_value`
- No React fiber keys on DOM nodes
- Chart time axis renders dates as SVG/canvas, not text

**Pending investigation**: Alt+G "Go to date" dialog, date range picker on
time axis click.

**Guard status**: The `chart_set_visible_range` entry in
`recon_findings.json` explicitly states "absolute_date_support: NOT SUPPORTED".
The `experiment_controller` should not be trusted to run ADR-0010 windows
until this is resolved.

### GT_VP zero trades 🔴

Tested on ETHUSD 15m with 5Y history (Jul 2020 – Jun 2026) — still zero
trades. "Script execution: 1" but "Net Profit" not found in body text.
Strategy Tester Overview tab opens but shows empty/no-trade state.

The known_issues.json `gt_vp_strategy_signal_generation` entry remains
open.

## Capability status changes

| Capability | Before | After |
|---|---|---|
| `symbol_control` selectors | major/open (stale) | fixed |
| `backtest_run` selectors | major/open (stale) | fixed |
| `chart_set_visible_range` | minor/open (presets) | minor/open (still preset-only) |
| GT_VP trades | minor/open | minor/open (still zero) |

## Cold-start prompt

```
Read docs/handoff/2026-07-07-fix-blockers.md and docs/handoff/2026-07-07-verification-pass.md.
set_symbol and backtest_run selectors fixed and verified live.
Absolute date-window control still preset-only — ADR-0010 cannot run yet.
GT_VP still zero trades. Next: Alt+G investigation or date range picker exploration.
```
