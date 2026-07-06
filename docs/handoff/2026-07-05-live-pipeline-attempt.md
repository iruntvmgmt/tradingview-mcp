# Handoff: 2026-07-05 — First live-app pipeline attempt (plan + experiment) against GT_VP_v9.9.6_STRAT

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-05-experiment-controller.md`
**Branch / commit at session end:** `main`

## Session goal

Run the full PineFamilyPlanner → ExperimentController pipeline end-to-end
against GT_VP_v9.9.6_STRAT with real live backtests through TradingView
Desktop 3.2.0 — the first time these two components would be exercised
together against a live strategy.

## What was completed

### Step 1: Plan generation — SUCCESS ✅

- `PineFamilyPlanner.parse()` ran against the local fixture
  (`tests/fixtures/pine_scripts/GT_VP_v9.9.6_STRAT.pine`) — the
  canonical copy in the repo.
- Generated `docs/generation_plans/GT_VP_v9.9.6_STRAT_generation_plan.json`
  and companion `_plan.md`.
- **Results**: 209 inputs found, 13 families, 74 cosmetic excluded, 0
  unclassified, 1 coupling candidate.
- **Tier breakdown**:
  - `signal_generation`: 5 families (69 inputs total)
  - `entry_and_execution`: 2 families (12 inputs)
  - `session_and_timing`: 2 families (4 inputs)
  - `unordered`: 3 families (50 inputs) — including "God Tier Features"
    (31 inputs, not matching any tier keyword) and "Dynamic Binning
    System" (11 inputs)
- **Best family for scoped tuning**: 🔶 Fair Value Gaps (6 inputs,
  3 tunable: `fvg_extend_bars`, `fvg_threshold`, `fvg_max_active`)

### Plan review findings

| Finding | Severity | Action |
|---|---|---|
| God Tier Features (31 inputs) landed in `unordered` — "god" doesn't match any tier keyword, but this family clearly contains scoring/gating logic | Medium | Add "god" or "tier" to `_TIER2_KEYWORDS` (scoring_and_gating) |
| `_strict_long_ok` coupling between scoring_and_gating and entry_and_execution was NOT detected | Low | Known limitation per ADR-0011 — the coupling detector only finds same-line co-occurrences; `cie_state.high_conviction` and `_strict_long_ok` span different families and may not appear on the same source line |
| Coupling found: God Tier Features ↔ Auction Pattern Detection (`ghost_atr_filter` + `zz_atr_len` at line 2184) | Info | Real but expected coupling — these are both signal-generation families |
| No corrections to `known_overrides` were needed — the plan's automated output was mostly correct for this first pass | Good | The heuristics handled all 209 inputs without any obvious misclassifications |

### Corrections recommended for pine_family_planner.py

1. Add `"god"` and `"tier"` to `_TIER2_KEYWORDS` (scoring_and_gating) so
   "God Tier Features" lands in the right tier
2. Consider adding `"bin"` to `_TIER1_KEYWORDS` (signal_generation) so
   "Dynamic Binning System" doesn't go to `unordered`
3. The coupling detector needs enhancement to catch cross-function
   dependencies (e.g. `cie_state.high_conviction` used inside
   `_strict_long_ok`) — this is the known ADR-0011 limitation

## Live-app findings — blocked by three issues

### Issue 1: `set_visible_range` doesn't work on TV Desktop 3.2.0 🔴

`DomChartBackend.set_visible_range()` attempts to find
`window.TradingView`/`window.tvWidget`/`window.widget` inside an iframe,
but TV Desktop 3.2.0 renders the chart directly in the main page (zero
iframes). The actual chart API is at
`window._exposed_chartWidgetCollection.activeChartWidget`, but this
object has no `chart()`, `setVisibleRange()`, or any range-related
methods. The `ChartApiInstance` global also has no chart navigation
methods (it's a data/metadata API, not a visualization API).

**Action needed**: Find the correct internal API for setting the chart
visible range in TV Desktop 3.2.0, or use DOM automation (Alt+G "Go to
date" dialog) as a fallback.

### Issue 2: Backtest selector mismatch 🟡

The recon findings record `button[id="strategy-report-summary"]` as the
selector for the backtest Summary tab, but the actual tab id in TV
Desktop 3.2.0 is `"Strategy report"` (with a space). The tab buttons
also use `data-name="light-tab-0"` and `data-name="light-tab-1"` rather
than the expected id formats.

**Action needed**: Update `recon_findings.json` and
`DomBacktestBackend` selectors to match the actual DOM.

### Issue 3: GT_VP produced zero trades on SOL/USD 1m 🔴

The Strategy Tester panel opens and shows tabs ("Strategy report",
"List of Trades"), but the content displays:

> "This report requires trade data. The strategy report appears after
> the script makes even one trade. Ensure that the selected symbol and
> time interval are compatible with the strategy."

Date range: Jun 7, 2026 — Jul 5, 2026 (~1 month on 1m timeframe).
Paper trading with 50K USD initial capital. GT_VP is a multi-timeframe
strategy that likely requires specific timeframes (not 1m) or more
history to generate signals.

**Action needed**: Test GT_VP on a higher timeframe (15m or 1h) with
more history, or switch to a simpler strategy (MA Cross) for the first
pipeline validation as originally recommended in the experiment
controller handoff doc.

## Updated capability matrix impacts

| Capability | Status change | Details |
|---|---|---|
| `chart_set_visible_range` | New gap discovered | `DomChartBackend.set_visible_range` doesn't work on TV 3.2.0 — needs internal API discovery |
| `backtest_run` selectors | Recon mismatch | Tab id is "Strategy report" not "strategy-report-summary" |
| `experiment_controller` live | Not yet operational | Blocked by set_visible_range + zero-trade issues |

## Forward path

1. **Fix `set_visible_range`**: Explore `_exposed_chartWidgetCollection`
   deeper for chart navigation, or implement Alt+G dialog automation
2. **Update backtest selectors**: Match actual TV 3.2.0 DOM
3. **Find a working symbol/timeframe for GT_VP**: Test on BINANCE:ETHUSD.P
   (15m or 1h) with 2+ years of history — this was the confirmed-working
   setup from the MA Cross backtest verification session
4. **Or use MA Cross for first pipeline validation**: As originally
   recommended — it's simpler, verified to produce trades, and will
   exercise the experiment controller's state machine without the
   confounding factor of a 209-input strategy
5. **Run the full pipeline** with a real scoped single-family experiment
   once the blocking issues are resolved

## Cold-start prompt

```
Read docs/handoff/2026-07-05-live-pipeline-attempt.md and docs/adr/0010-experiment-window-discipline.md.
Pipeline attempted against GT_VP but blocked by: (1) set_visible_range doesn't work on TV Desktop,
(2) backtest tab selectors mismatch actual DOM, (3) GT_VP produced zero trades on SOL/USD 1m.
PineFamilyPlanner plan generation works perfectly — 209 inputs classified across 13 families.
Next: fix set_visible_range, update backtest selectors, test GT_VP on a higher timeframe or
use MA Cross for first pipeline validation.
```
