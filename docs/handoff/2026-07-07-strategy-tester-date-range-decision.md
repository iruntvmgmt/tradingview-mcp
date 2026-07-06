# Handoff: 2026-07-07 — Strategy Tester date-range decision: Free tier is preset-only, ADR-0010 blocked, two modes formalized

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-07-accessibility-alt-g-date-dialog.md`
**Branch / commit at session end:** `main`

## Investigation: Strategy Tester backtest period controls

### Live DOM evidence

The Strategy Tester toolbar (below the report tabs, above the content) has:

| Element | `data-qa` | Purpose |
|---|---|---|
| `[data-qa="date-range-menu"]` | Opens preset menu | Backtest period |
| `[data-qa="initial-capital"]` | Clickable | Account size |
| `[data-qa="bar-detalization"]` | Clickable | Report granularity |
| `[data-name="go-to-date"]` | Button in preset list | Opens Go to Date dialog (chart-only) |

The date range menu contains ONLY preset buttons:
```
1D, 5D, 1M, 3M, 6M, YTD, 1Y, 5Y, All
```

**Zero inputs** in the expanded date range area. Zero custom date fields.

### Free-tier capability confirmation

| Feature | Present? |
|---|---|
| Custom date range in Strategy Tester | ❌ No |
| Deep Backtesting | ❌ Not found in page |
| Properties/settings for backtest period | ❌ None |
| Go to Date dialog | ✅ Yes, but chart-only |
| Preset date ranges | ✅ 1D–All |

**The Strategy Tester's backtest calculation period is preset-only on
TradingView Free tier.** The Go to Date Custom range dialog exists but
only controls the chart canvas view, not the backtest period.

## Architecture decision: Two experiment modes

Since exact ADR-0010 date-window discipline cannot run on Free tier, two
modes are formalized in `experiment_config.json`:

### Mode 1: `disciplined_live_experiment` (default for production)
- Requires `supports_absolute_visible_range() == True`
- Raises `WindowGuardError` on preset-only backends
- Full ADR-0010 window discipline enforced
- **Blocked on TradingView Free tier** until a Premium plan or API update
  provides Strategy Tester custom date ranges

### Mode 2: `preset_smoke_test` (current config)
- Allows preset-only backends — logs warning, does not raise
- Intended for plumbing verification only (symbol change, backtest run,
  settings write, sensitivity check work correctly)
- Experiment results are explicitly NOT ADR-0010 compliant
- Guard still runs bar-budget checks and window chronological validation

### Implementation

- `experiment_config.json`: Added `experiment_mode` field (default: `preset_smoke_test`)
- `ExperimentController._assert_absolute_date_support()`: Checks mode before
  raising. In `preset_smoke_test`, logs warning and proceeds. In
  `disciplined_live_experiment`, raises `WindowGuardError`.
- `ExperimentController.__init__()`: Stores `self._mode`

## Files changed

| File | Change |
|---|---|
| `experiment_config.json` | Added `experiment_mode` field (`preset_smoke_test`) |
| `core/services/experiment_controller.py` | Mode-aware guard, logging import |

## Updated capability status

| Capability | Status |
|---|---|
| `chart_set_visible_range` | Still open — preset-only, Free-tier limitation confirmed |
| ADR-0010 live experiments | Blocked on Free tier (no Strategy Tester custom dates) |
| `preset_smoke_test` mode | Available for plumbing verification |
| `disciplined_live_experiment` mode | Blocked until Premium/deep backtesting available |

## Recommendation

The next code-changing session can now use `preset_smoke_test` mode to verify
the experiment_controller plumbing (symbol change, settings write, backtest
run, sensitivity check) with preset windows, while the guard prevents anyone
from mistaking preset results for ADR-0010 compliant experiments.

When a Premium TradingView plan is available:
1. Set `deep_backtesting_enabled: true` in config
2. Re-investigate Strategy Tester date controls (Premium may expose custom
   date pickers in the same date-range menu)
3. If custom dates are available, implement `set_visible_range` to use them
   and set `supports_absolute_visible_range() = True`
4. Switch `experiment_mode` to `disciplined_live_experiment`
