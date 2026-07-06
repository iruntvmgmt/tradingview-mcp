# Handoff: 2026-07-07 — verification pass on visible range, selectors, and GT_VP zero trades

**Agent:** Codex
**Mode:** read-only verification/planning pass, except this requested handoff doc
**Repo path:** `/Users/matt/Documents/TRADINGVIEW_MCP/tv-desktop-controller`
**Live app:** TradingView Desktop reachable on CDP port 8315 after elevated local-port access

## Scope

This session verified four externally reported findings against the current
repo and the live TradingView Desktop DOM. No code, config, recon JSON, or
status files were changed.

The only write performed was this handoff document.

## Evidence: live connection

CDP health check:

```json
{
  "connected": true,
  "target_id": "5AB7B3147E560F7205A63FA3A864D7AA",
  "eval_ok": true,
  "accessibility_permission": false,
  "tv_pid": 68725,
  "pine_editor_write_ready": false
}
```

Active page basics:

```json
{
  "url": "https://www.tradingview.com/chart/jzWwCCdX/",
  "title": "Live stock, index, futures, Forex and Bitcoin charts on TradingView",
  "iframes": 0,
  "tvGlobals": [
    "WIDGET_HOST",
    "TradingView",
    "ChartApiInstance",
    "TradingViewApi",
    "_exposed_chartWidgetCollection",
    "widgetbar",
    "footerWidget",
    "miniChartInstances"
  ]
}
```

The chart currently shows `XAUUSD` / `Gold Spot / U.S. Dollar`, timeframe
`15`, with `GT_VP_v9.9.6_STRAT` applied.

## Finding 1: `set_visible_range` is preset-only

Confirmed.

Current implementation in `core/services/backends/dom_backend.py`:

- `DomChartBackend.set_visible_range()` parses `start` and `end`, computes
  only `span_days`, then maps the span to one of:
  `date-range-tab-1D`, `date-range-tab-5D`, `date-range-tab-1M`,
  `date-range-tab-3M`, `date-range-tab-6M`, `date-range-tab-12M`,
  `date-range-tab-60M`, or `date-range-tab-ALL`.
- `_click_date_preset()` clicks `[data-name="date-ranges-menu"]`, then the
  chosen preset tab by `data-name`.
- The implementation does not use the requested absolute start/end dates
  after span calculation.

Live DOM evidence also showed the preset tabs:

```json
{
  "dataName": "date-ranges-tabs",
  "text": "1D 5D 1M 3M 6M YTD 1Y 5Y All"
}
```

Assessment for ADR-0010:

This is a hard blocker for ADR-0010's intended window discipline. The
controller validates explicit, non-overlapping train/validation/holdout
windows in config, but execution calls `chart.set_visible_range(start, end)`.
The current chart backend turns each window into a trailing preset measured
from "now", not into the configured calendar interval.

Example: train `2023-01-01` to `2023-06-30`, validation `2023-07-01` to
`2023-09-30`, and holdout `2023-10-01` to `2023-12-31` would become preset
spans such as 6M/3M/3M from the current date. That cannot express the
chronologically ordered, non-overlapping windows ADR-0010 requires.

No combination of the current preset buttons can express arbitrary historical
non-overlapping windows. Before a real `experiment_controller` run is
trusted, visible-range/date-range control needs a dedicated revisit.

## Finding 2: `backtest_run` stale selector status

Partially confirmed, with an important nuance.

Repo evidence:

`recon_findings.json` still has the reported stale selector:

```json
"tab_selectors": [
  "button[id=\"strategy-report-summary\"]",
  "button[role=\"tab\"][id=\"strategy-report-summary\"]"
]
```

`DomBacktestBackend.run()` still reads `backtest_run.detail.tab_selectors`
and clicks them.

Live DOM evidence:

```json
[
  {
    "role": "tab",
    "id": "Strategy report",
    "dataName": "light-tab-0",
    "ariaSelected": "true",
    "text": ""
  },
  {
    "role": "tab",
    "id": "List of Trades",
    "dataName": "light-tab-1",
    "ariaSelected": "false",
    "text": ""
  },
  {
    "role": "tab",
    "id": "strategy-report-summary",
    "dataName": "",
    "ariaSelected": "true",
    "text": "Overview"
  }
]
```

Selector counts:

```json
{
  "staleSummary": 4,
  "idStrategyReport": 1,
  "lightTab0": 1,
  "lightTab1": 1
}
```

Correction to the external finding:

The real top-level Strategy Tester tabs are still
`id="Strategy report"` / `data-name="light-tab-0"` and
`id="List of Trades"` / `data-name="light-tab-1"`, as previously reported.
However, the old `button[id="strategy-report-summary"]` selector is not
absent from the live DOM. It exists four times as nested "Overview" tabs
inside the Strategy report content. That means the selector is stale for
opening/selecting the Strategy Tester report tab, but it may still resolve
to an unrelated nested tab. This is worse than a clean miss because it can
create false confidence.

## Finding 3: `set_symbol` is broken on TV 3.2.0 DOM

Confirmed.

Repo evidence:

`recon_findings.json` currently has:

```json
"selectors": [
  "button[data-name=\"header-toolbar-symbol-search\"]",
  "button[class*=\"apply-common-tooltip\"]:has(span[class*=\"ticker\"])",
  "button[class*=\"button-JQZ\"]"
],
"symbol_search_input_selectors": [
  "input[data-name=\"symbol-search\"]",
  "input[placeholder*=\"Search\"]"
]
```

Live evidence before opening the symbol dialog:

```json
{
  "staleInputCount": 0,
  "searchInputs": []
}
```

Clicking the current repo's primary opener selector returned no target:

```json
"clicked_symbol_button": null
```

Current live opener candidates include:

```json
{
  "id": "header-toolbar-symbol-search",
  "dataName": "",
  "text": "XAUUSD",
  "rect": { "x": 55.98958206176758, "y": 5, "w": 127.99478912353516, "h": 27.99479103088379 }
}
```

and the chart legend symbol title:

```json
{
  "aria": "Change symbol",
  "text": "Gold Spot / U.S. Dollar",
  "rect": { "x": 86.796875, "y": 48.3984375, "w": 161.39321899414062, "h": 19.16666603088379 }
}
```

After clicking the live `aria="Change symbol"` element, the real search input
was:

```json
{
  "type": "text",
  "dataName": "",
  "placeholder": "Symbol, ISIN, or CUSIP",
  "role": "searchbox",
  "autocomplete": "off",
  "value": "XAUUSD",
  "classes": "search-lANubSc2 search-k2RBvLVM upperCase-k2RBvLVM",
  "visible": { "x": 1036.8228759765625, "y": 554.9635620117188, "w": 689.53125, "h": 23.997394561767578 }
}
```

The dialog itself:

```json
{
  "role": "dialog",
  "dataName": "symbol-search-items-dialog",
  "dialogName": "Symbol search",
  "text": "Symbol search Close menu All Stocks Funds Futures Forex Crypto Indices Bonds Economy Options More ..."
}
```

So the live input no longer has `data-name="symbol-search"` and the fallback
`input[placeholder*="Search"]` also does not match because the placeholder is
`Symbol, ISIN, or CUSIP`.

## Finding 4: GT_VP zero-trade investigation did not test internal gates

Confirmed.

The previous handoff tested symbols/timeframes/history length, but I found no
evidence that it read or varied GT_VP's own gating inputs.

Current live `settings_read` evidence:

The normal `settings_read` path against `GT_VP_v9.9.6_STRAT` returned 71
fields. A scroll-aware read of the dialog still collected 71 fields from the
live Inputs tab, with scroll container:

```json
{
  "scrollHeight": 9486,
  "clientHeight": 1430,
  "max": 8056,
  "step": 786
}
```

Relevant current values actually read from the live dialog:

```json
{
  "Entry Strictness": "Normal",
  "ATR Stop Multiplier": "1",
  "Level Buffer ATR": "0.1",
  "MA Filter Mode": "Off",
  "Ghost Trail Min ATR Move": "0.05",
  "LVN Threshold": "0.15",
  "Fast Lane Threshold (vs max vol)": "0.15",
  "Imbalance Threshold": "3",
  "Volume Threshold (StdDev)": "2",
  "Tier Strength Threshold": "2",
  "FA Min Penetration ATR": "0.08",
  "FA Displacement ATR": "0.25",
  "ZZ ATR Length": "14",
  "ZZ ATR Reversal Multiplier": "1.5",
  "ZZ Sweep Rejection %": "0.6",
  "Sweep Min Penetration ATR": "0.08",
  "Sweep Displacement ATR": "0.25",
  "Sweep Confirm Window": "2",
  "Sweep Cooldown Bars": "10",
  "FVG Min Size (ATR multiplier)": "0.3",
  "Prune Threshold (StdDev)": "5"
}
```

Source-code context from
`tests/fixtures/pine_scripts/GT_VP_v9.9.6_STRAT.pine`:

- `Entry Strictness` has options `Loose`, `Normal`, `Strict`; live is
  `Normal`.
- `_strict_long_ok` and `_strict_short_ok` only impose the
  `cie_state.high_conviction or cie_state.score >= 70` condition when
  strictness is `Strict`. With live `Entry Strictness = Normal`, that
  specific strict-only score gate is not active.
- Normal mode still requires signal-specific CIE gates, directional flow, and
  underlying setup conditions:
  `_sweep_gate_*`, `_vp_gate_*`, `_struct_gate_*`, `_flow_*`, profile state,
  failed auction / sweep / POC / structure conditions.
- ATR and threshold values are nontrivial: e.g. `ZZ ATR Reversal Multiplier =
  1.5`, `ZZ Sweep Rejection % = 0.6`, `Imbalance Threshold = 3`,
  `Volume Threshold (StdDev) = 2`.

Assessment:

The live settings are not in the strictest possible entry mode, so the
specific `_strict_long_ok` high-conviction/score>=70 coupling is unlikely to
be the whole zero-trade explanation in the current chart state.

But zero trades remains very plausibly explained by GT_VP's internal gating,
because Normal mode still requires multiple independent gates and event
conditions. The settings evidence does not support concluding that the problem
is only symbol/timeframe/history availability. A proper GT_VP investigation
should include controlled read-only diagnosis first, then a code-changing or
settings-changing follow-up only after selectors are stable.

## Other mismatches / cautions

- `STATUS.md` says `symbol_control` recon status is verified, but live DOM
  confirms the current selectors are stale.
- `STATUS.md` says `backtest_run` recon status is verified, but live DOM shows
  the stored selector targets nested Overview tabs, not the current top-level
  Strategy Tester tabs.
- `settings_read` is useful but incomplete for GT_VP coverage: the strategy
  planner sees 209 inputs, while live settings collection currently returns 71
  rows. This may be TradingView dialog rendering/grouping behavior, or a
  limitation in the field collector. Treat `settings_read` verified status as
  scoped to currently visible/collectable Inputs rows, not full GT_VP schema
  coverage.
- CDP health reported `accessibility_permission: false`, so Pine editor
  write/read paths that require macOS Accessibility are currently not ready
  in this live app state.

## Recommendation for the next code-changing session

Priority order:

1. Fix `set_symbol` first. It is a hard practical blocker for controlled live
   tests because the current opener and input selectors are stale. Update recon
   and backend behavior around the current `id="header-toolbar-symbol-search"`
   / `aria="Change symbol"` opener candidates and
   `input[role="searchbox"][placeholder="Symbol, ISIN, or CUSIP"]`.

2. Fix `backtest_run` selectors next. Use the top-level Strategy Tester tabs
   (`button[role="tab"][id="Strategy report"][data-name="light-tab-0"]` and
   `button[role="tab"][id="List of Trades"][data-name="light-tab-1"]`) rather
   than nested `strategy-report-summary` Overview tabs. Re-run live recon after
   patching because the stale selector still exists and can falsely pass.

3. Run a dedicated visible-range/date-range investigation before trusting
   `experiment_controller` for ADR-0010. The current preset approach is fine
   for quick manual smoke tests, but not for real train/validation/holdout
   discipline. Investigate the date picker, time-axis Go To Date flow, Strategy
   Tester custom range controls, or deeper internal APIs.

4. Only after symbol/backtest selectors are fixed, investigate GT_VP gates.
   Start read-only: confirm `Enable Strategy Orders`, full strategy properties,
   active symbol/timeframe, and whether settings collection can enumerate all
   209 inputs. Then run a controlled settings experiment in a code-changing
   session: compare Normal vs Loose, inspect which signal families are enabled,
   and test whether relaxing CIE/sweep/ATR thresholds produces any trades.

For first pipeline validation, use a known trade-producing simple strategy
after selector fixes. Do not use GT_VP as the first proof of
`experiment_controller`; its internal gating is too confounding.
