# Handoff: 2026-07-06 — set_visible_range partial fix (presets), GT_VP still zero trades, multiple selector mismatches found

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-05-live-pipeline-attempt.md`
**Branch / commit at session end:** `main`

## Session goal

Fix the two blockers from the previous session:
1. `set_visible_range` broken on TV Desktop 3.2.0
2. GT_VP producing zero trades

Then run a scoped experiment pipeline.

## What was fixed: set_visible_range ✅ (partial)

### Investigation findings

- **TV Desktop 3.2.0 has NO JS chart API for setVisibleRange**: The chart
  renders in the main page (zero iframes). `_exposed_chartWidgetCollection.
  activeChartWidget` only has `_listeners` and `_value` — no `chart()`,
  `setVisibleRange()`, or range methods.
- **No React fiber keys on DOM nodes** — React internals are not attached
  to DOM elements.
- **`widgetbar._models`** only have `visible` properties — no time/range
  navigation.
- **Chart time axis** is at `y=878, height=28` with class `chart-markup-
  table time-axis` — renders dates as SVG/canvas, not DOM text.

### Fix implemented: Strategy Tester preset tabs

`DomChartBackend.set_visible_range()` now uses the Strategy Tester's
date-range preset buttons instead of the non-existent JS API:

| Preset `data-name` | Duration | Activated by span |
|---|---|---|
| `date-range-tab-1D` | 1 day | ≤1 day |
| `date-range-tab-5D` | 5 days | ≤5 days |
| `date-range-tab-1M` | 1 month | ≤31 days |
| `date-range-tab-3M` | 3 months | ≤92 days |
| `date-range-tab-6M` | 6 months | ≤183 days |
| `date-range-tab-12M` | 1 year | ≤366 days |
| `date-range-tab-60M` | 5 years | ≤1826 days |
| `date-range-tab-ALL` | All history | >5 years |

**Verified**: Clicking "All" changed the Strategy Tester toolbar from
"Jun 7, 2026 — Jul 6, 2026" to "Dec 31, 1832 — Jun 30, 2026" (XAUUSD full
history).

### Limitation: presets only, no arbitrary dates

The preset-based approach cannot set specific train/validation/holdout
window boundaries. The experiment controller's window discipline is
therefore *approximate* — it uses the widest preset that covers the
requested span. For spans >5 years, it uses "All".

**Recommendation**: Accept this as a pragmatic workaround for now. The
presets (1Y, 5Y, All) provide reasonable window boundaries for most
strategies. A future session should explore:
- The date range picker that opens when clicking on the time axis
- Whether TV Desktop 3.2.0's internal API can be found by deeper
  exploration of the widgetbar configuration

## What wasn't fixed: GT_VP zero trades 🔴

### Tested combinations

| Symbol | Timeframe | Date Range | Result |
|---|---|---|---|
| SOL/USD (COINBASE) | 1m | Jun 7 – Jul 6, 2026 (~1M) | Zero trades |
| XAUUSD (OANDA) | 1m | Jun 7 – Jul 6, 2026 (~1M) | Zero trades |
| XAUUSD (OANDA) | 1m | Dec 31, 1832 – Jun 30, 2026 (ALL) | Zero trades |
| ETHUSD (BINANCE) | 1h | Attempted | set_symbol selector stale |

### Root cause hypothesis

GT_VP is a multi-timeframe strategy that likely requires:
- A specific set of timeframes (not just 1m)
- A liquid futures/forex symbol (not spot crypto on OANDA)
- The exact configuration from the GT_VP documentation

The confirmed working setup from previous sessions was **BINANCE:ETHUSD.P
on 15m or 1h** with MA Cross, not GT_VP.

## New selector mismatches discovered 🟡

### `set_symbol` — `input[data-name="symbol-search"]`

The symbol search input's `data-name` attribute doesn't match on TV 3.2.0.
The `DomChartBackend.set_symbol()` raises `SelectorResolutionError`.

**Action**: Find the correct selector for the symbol search input in TV
3.2.0 and update `recon_findings.json`.

## What the experiment pipeline needs next

1. **Fix `set_symbol` selector** — blocker for switching to a
   working symbol/timeframe
2. **Apply MA Cross strategy** (already verified to produce trades) on a
   working symbol/timeframe
3. **Run the scoped experiment** with one family/parameter using the
   preset-based date range control
4. **Investigate GT_VP's trading requirements** — what
   symbol/timeframe/configuration actually produces trades

## Cold-start prompt

```
Read docs/handoff/2026-07-06-set-visible-range-fix.md and
docs/handoff/2026-07-05-live-pipeline-attempt.md.
set_visible_range now works via Strategy Tester presets (1D-ALL).
GT_VP still produces zero trades on all tested combinations.
set_symbol selector is stale on TV 3.2.0.
Next: fix set_symbol selector, apply MA Cross, run scoped experiment.
```
