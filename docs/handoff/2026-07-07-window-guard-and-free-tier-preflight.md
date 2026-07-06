# Handoff: 2026-07-07 — Window guard and Free-tier bar-budget preflight layer

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-07-fix-blockers.md`
**Branch / commit at session end:** `main`

## What was built

A safety/preflight layer that prevents `ExperimentController` from silently
running invalid ADR-0010 experiments on TradingView Free tier or with
preset-only date windows.

### 1. Backend capability signaling

Added `supports_absolute_visible_range() -> bool` to:

| Backend | Returns | Reason |
|---|---|---|
| `DomChartBackend` | `False` | TV 3.2.0 only supports preset date ranges (1D–All) |
| `JsChartBackend` | `False` | Stub — JS API not available |
| `NetworkChartBackend` | `False` | Stub — network path doesn't control chart view |
| `ChartBackend` (ABC) | Abstract | All backends must declare their capability |

### 2. ExperimentController execution guard

`_assert_absolute_date_support()` in `ExperimentController` checks the
chart backend's capability before any window-based operation. Raises
`WindowGuardError` with a clear message if the backend can't set absolute
dates.

Called from `_set_window()`, which is invoked by `run_iteration`,
`run_validation_check`, `run_holdout_check`, and `run_sensitivity_check`.

**Error message example:**
```
WindowGuardError: This chart backend only supports preset/trailing date
ranges (1D, 5D, 1M, 3M, 6M, 1Y, 5Y, All). ADR-0010 requires exact
absolute chronological windows. Live experiment execution is blocked
until absolute date control is implemented for TradingView Desktop 3.2.0.
See docs/adr/0010-experiment-window-discipline.md.
```

### 3. Free-tier bar budget checks

New `experiment_config.json` fields:

```json
{
  "timeframe": "15m",
  "tradingview_tier": {
    "tier": "free",
    "intraday_bar_limit": 5000,
    "deep_backtesting_enabled": false
  }
}
```

`_validate_bar_budget()` runs both at config load time and during direct
`ExperimentController(...)` construction:
- Requires `timeframe` field (raises `WindowGuardError` if missing)
- Supports 1m, 5m, 15m, 30m, 1h, 4h, 1D, 1W, 1M timeframes
- Daily-or-higher timeframes skip intraday bar checks
- `deep_backtesting_enabled: true` skips all bar-budget checks
- Estimates the full train-start → holdout-end history envelope:
  `envelope_minutes / bar_minutes`
- Rejects the experiment when the total envelope exceeds
  `intraday_bar_limit`

**Example pass:**
```
15m, 15-day train→holdout envelope → ~1,440 bars → under 5,000 limit → OK
```

**Example fail:**
```
WindowGuardError: Configured train→holdout window envelope needs
approximately 9792 bars on 15m, but TradingView tier free is configured
for 5000 intraday bars. Use a shorter total experiment span, higher
timeframe, or higher TradingView tier.
```

### 4. New error type

`WindowGuardError` in `core/services/errors.py` — distinct from
`WindowConfigurationError` (which is for misordered/overlapping windows).

## Tests added/updated

| Test | What it verifies |
|---|---|
| `test_backend_without_absolute_date_support_blocks_live_experiment` | `WindowGuardError` raised when `supports_absolute_visible_range()` returns False |
| `test_backend_with_absolute_date_support_proceeds` | No error when backend supports absolute dates |
| `test_feasible_intraday_window_passes` | 15m, ~15-day envelope, ~1,440 bars → passes |
| `test_total_intraday_envelope_fails_even_when_individual_windows_are_short` | Full train→holdout envelope is checked, not each window in isolation |
| `test_infeasible_intraday_window_fails` | 1m, 2 years, ~1M bars → fails with 5000 and 1m in message |
| `test_missing_timeframe_fails` | Missing `timeframe` → `WindowGuardError` |
| `test_daily_timeframe_skips_intraday_check` | 1D, 15-year window → passes (skips intraday) |
| `test_deep_backtesting_enabled_skips_check` | `deep_backtesting_enabled: true` → skips all checks |
| `test_controller_init_runs_bar_budget_validation` | Direct controller construction cannot bypass the guard |
| `test_dom_chart_does_not_support_absolute_visible_range` | DOM backend declares no exact date support |

## Remaining blockers

- **Absolute date control**: Still not implemented. TV 3.2.0 has no JS
  `setVisibleRange` API. Presets only.
- **GT_VP zero trades**: Still unresolved. Not investigated this session.

## Files changed

| File | Change |
|---|---|
| `core/services/backends/base.py` | Added `supports_absolute_visible_range` to `ChartBackend` ABC |
| `core/services/backends/dom_backend.py` | Implemented → returns `False` |
| `core/services/backends/js_backend.py` | Implemented → returns `False` |
| `core/services/backends/network_backend.py` | Implemented → returns `False` |
| `core/services/errors.py` | Added `WindowGuardError` |
| `core/services/experiment_controller.py` | Added `_validate_bar_budget()`, `_assert_absolute_date_support()`, guard in `_set_window()`, `_BAR_MINUTES` mapping |
| `experiment_config.json` | Added `timeframe`, `tradingview_tier` section; default is a feasible 4h Free-tier envelope |
| `tests/test_experiment_controller.py` | Added guard/bar-budget tests, updated VALID_CONFIG and _make_controller |
| `tests/test_backends.py` | Added backend capability coverage |
| `docs/known_issues.json` | Updated `chart_set_visible_range` entry |
| `docs/STATUS.md` | Regenerated |

## Cold-start prompt

```
Read docs/handoff/2026-07-07-window-guard-and-free-tier-preflight.md.
Window guard and Free-tier bar budget preflight layer built — experiment
controller now refuses to run with preset-only backends or infeasible
intraday train→holdout envelopes.
Absolute date control still not implemented — remains the primary blocker
for live ADR-0010 experiments.
```
