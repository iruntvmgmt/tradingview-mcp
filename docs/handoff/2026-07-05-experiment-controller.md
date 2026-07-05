# Handoff: 2026-07-05 — ExperimentController built end-to-end (train/validation/holdout discipline, divergence gate, sensitivity probes)

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-05-pine-errors-and-trade-list.md`
**Branch / commit at session end:** `main`

## What was built

`ExperimentController` — the pure-Python orchestration layer that runs
disciplined strategy iteration on top of the already-verified chart,
settings, pinescript, and backtest controllers.

### Files created

| File | Purpose |
|------|---------|
| `experiment_config.json` | User-tunable windows + thresholds. Zero hardcoded values in controller code. |
| `core/services/experiment_log.py` | Append-only JSONL audit trail (`ExperimentLog` class). No other file touches `logs/experiment_log.jsonl` directly. |
| `core/services/experiment_controller.py` | State machine: start_generation → run_iteration → run_validation_check → rollback → run_holdout_check → run_sensitivity_check → report. Includes `_validate_windows()` startup validator. |
| `tests/test_experiment_log.py` | 12 tests: append, read, filter, consecutive_validation_passes (pass/pass/fail/pass → 1, not 3), append-only verification. |
| `tests/test_experiment_controller.py` | 20 tests: all required cases from the build spec including MultipleChangesError before backtest, compile-failure abort, divergence computation, PrematureHoldoutError message, HoldoutAlreadyUsedError, rollback re-apply, sensitivity restore. |
| `docs/adr/0010-experiment-window-discipline.md` | Documents why train/validation/holdout, why divergence is the overfitting signal, why one-change-per-iteration, why compile-first, and why sensitivity checks matter independently. |
| `docs/EXPERIMENT_LOG.md` | Generated Markdown report (same conventions as `docs/STATUS.md`). |

### Files modified

| File | Change |
|------|--------|
| `core/services/errors.py` | Added `WindowConfigurationError`, `MultipleChangesError`, `HoldoutAlreadyUsedError`, `PrematureHoldoutError` |
| `core/services/backends/base.py` | Added `set_visible_range` abstract method to `ChartBackend` |
| `core/services/backends/dom_backend.py` | Implemented `DomChartBackend.set_visible_range` via CDP `Runtime.evaluate` calling TradingView chart API |
| `core/services/backends/js_backend.py` | Added `set_visible_range` stub to `JsChartBackend` |
| `core/services/backends/network_backend.py` | Added `set_visible_range` stub to `NetworkChartBackend` |
| `core/services/chart_controller.py` | Added `TVChartController.set_visible_range` |
| `server.py` | Constructed `ExperimentController` + `ExperimentLog` at import time. Registered 7 MCP tools: `tv_experiment_start`, `tv_experiment_iterate`, `tv_experiment_validate`, `tv_experiment_rollback`, `tv_experiment_holdout`, `tv_experiment_sensitivity`, `tv_experiment_report`. |

### Verification status

- **All mock tests pass:** 107 tests (was 69 + 38 new), 0 failures
- **No live-app smoke run** — the experiment layer calls existing verified controllers; there is no new DOM automation. The one exception is `set_visible_range` on `DomChartBackend`, which uses CDP `Runtime.evaluate` to call the TradingView chart API — this has not been tested against a live TV Desktop session.
- **set_visible_range risk:** The JS implementation searches for `window.TradingView`, `window.tvWidget`, or `window.widget` in the chart iframe. If none are found, it logs a warning but does not raise — the experiment layer has no way to confirm the date range was actually set. A future TV Desktop session should test that `set_visible_range("2023-01-01", "2024-01-01")` actually changes the chart's visible range.

### Design decisions

1. **3-window chronological order enforced at startup** — `_validate_windows()` checks train.end < validation.start < validation.end < holdout.start < holdout.end with no overlap. Raises `WindowConfigurationError` with specific message on failure.

2. **One change per iteration** — enforced by `MultipleChangesError` in code, not convention. Makes the audit trail unambiguous about cause and effect.

3. **Compile-first for PineScript** — `run_iteration` with `change_type="pinescript"` compiles before backtesting and aborts with `accepted=False` on failure. No backtest is run against broken code.

4. **Holdout is one-time per generation** — `HoldoutAlreadyUsedError` on second call. Additionally gated by `validation_passes_required_before_holdout` consecutive passes.

5. **Sensitivity checks don't count as iterations** — they're diagnostic probes that nudge a parameter ±swing%, measure PF delta, restore the original value, and log a `sensitivity_check` event (not an `iteration` event).

6. **All thresholds from `experiment_config.json`** — profit_factor, max_drawdown, min_trades, divergence_pct, sensitivity_swing_pct, sensitivity_max_pf_delta_pct, validation_passes_required_before_holdout — zero magic numbers in `experiment_controller.py`.

### Things that need a live-app test

| Thing | How to test |
|-------|-------------|
| `set_visible_range` | Open TV Desktop, verify chart date range changes after calling with known dates |
| `ExperimentController` end-to-end | Apply MA Cross Strategy on ETHUSD 1h, call `tv_experiment_start`, iterate a parameter, validate, holdout, sensitivity — verify all backtest results are real numbers, not mock returns |

## Cold-start prompt

```
Read docs/handoff/2026-07-05-experiment-controller.md, docs/adr/0010-experiment-window-discipline.md, and docs/STATUS.md.
ExperimentController is built with 38 tests passing.
Next: live-app smoke test of set_visible_range, or tackle remaining
unverified capabilities (alert_*, drawing_list, order_*, replay_*,
backtest_equity_curve).
```
