# ADR-0010: Experiment window discipline — train/validation/holdout split, divergence gate, one-time holdout, and sensitivity probes

**Status:** accepted
**Date:** 2026-07-05
**Author(s):** Sage (ai-team-dev)

## Context

`ExperimentController` (`core/services/experiment_controller.py`) is the
orchestration layer that runs disciplined strategy iteration on top of the
already-verified chart, settings, pinescript, and backtest controllers. It
does NO new DOM automation and does NOT need recon entries — it is pure
Python orchestration.

The controller enforces a three-window discipline (train → validation →
holdout) with explicit gates between stages. Every decision threshold comes
from `experiment_config.json` — zero magic numbers in the controller.

## Decision: Train / validation / holdout split

The three windows are chronologically ordered with no overlap, enforced at
startup by `_validate_windows()` in `experiment_controller.py`. The
validation is mechanical:

| Window | Purpose | Gate |
|---|---|---|
| **Train** | All iterations run here | None — always accessible |
| **Validation** | Divergence check (overfitting alarm) | None — can re-check indefinitely |
| **Holdout** | Final promotion gate | One-time per generation AND N consecutive validation passes required |

**Why validation is re-runnable but holdout is one-time:** Validation is a
diagnostic — you want to re-check it after a rollback to confirm the fix
worked. Holdout is the final exam — if you can peek at the holdout data
multiple times, you're implicitly training on it via parameter selection,
defeating the purpose of the split.

## Decision: Divergence as the overfitting signal

The validation check computes:

```
divergence_pct = |train_PF - validation_PF| / train_PF × 100
```

If `divergence_pct > divergence_threshold_pct` (default 30%), the verdict is
"fail" — the strategy is overfit to the training window. The return dict
includes a `recommended_rollback_to_iteration_num` pointing to the most
recent iteration where validation passed.

**Why profit_factor divergence, not equity-curve correlation or statistical
tests:** Profit factor is the single metric that directly answers "does this
strategy make money relative to its losses?" A strategy that overfits will
show a widening gap between train and validation PF before any other metric
signals trouble. More sophisticated overfitting tests (CSCV, PBO) require
per-trade reshuffling and are out of scope for a DOM-automation controller.

## Decision: Sensitivity checks are independent of window discipline

`run_sensitivity_check()` nudges a parameter ±15% (configurable) and
measures profit_factor delta on the TRAIN window only. If the PF delta
exceeds 40% (configurable), the parameter is flagged as `is_noise_fit` —
meaning the strategy's performance is sensitive to the exact parameter
value rather than being stable across a neighborhood.

**Why this matters independently of validation:** A parameter can pass
validation (train and validation PFs are similar) and still be fit to noise
if its neighborhood is a cliff: nudging it 15% in either direction
collapses performance. The sensitivity check catches parameters that are
"validation-stable but fragile" — a condition the divergence gate alone
would miss. A plateau-shaped parameter landscape is desirable; a
cliff-shaped one means the parameter value is over-optimized to the
specific training data even if it generalizes to the validation window.

## Decision: One change per iteration — enforced in code, not convention

`run_iteration()` raises `MultipleChangesError` if the `change` dict
contains more than one key (settings) or is empty/missing (pinescript).
This is NOT a style guideline — it ensures every iteration event in the
JSONL log has exactly one `before_value`/`after_value` pair, making the
audit trail unambiguous about cause and effect. If two parameters are
changed in one iteration and performance improves, you can't attribute the
improvement to either parameter individually.

## Decision: Compile-first for PineScript iterations

When `change_type` is `"pinescript"`, the controller writes the new code,
compiles it, and checks `pine_compile_errors_read()` BEFORE running a
backtest. If compilation fails, the iteration is logged with `accepted:
false` and the reason contains the compiler errors. No backtest is ever run
against broken code — this prevents the Strategy Tester from silently
reverting to the last valid state (which would produce a misleadingly
unchanged backtest result that looks like "no effect" when the real
explanation is "code didn't apply").

## Consequences

- **What this makes easier:** Strategy iteration now has a defined
  state machine with clear entry/exit criteria per stage. An agent can
  call `tv_experiment_start` → `tv_experiment_iterate` × N →
  `tv_experiment_validate` → `tv_experiment_rollback` (if needed) →
  `tv_experiment_holdout` → `tv_experiment_sensitivity` without needing
  to understand the window discipline or threshold logic — the controller
  enforces it mechanically.
- **What this makes harder:** The `set_visible_range` method on
  `DomChartBackend` relies on finding a `TradingView`/`tvWidget` global
  via CDP `Runtime.evaluate` — this is a JS-path approach (unlike the
  DOM-click approaches used by `set_symbol`/`set_timeframe`). If
  TradingView changes the widget variable name or removes it from the
  global scope, `set_visible_range` will silently fail (logged as a
  warning). This is an accepted risk — there is no known DOM-element
  alternative for programmatic date-range setting in TradingView
  Desktop.
- **When to revisit:** If a future TradingView Desktop version exposes a
  stable DOM path for date-range control (e.g., a date-range input with
  a `data-qa-id` attribute), `DomChartBackend.set_visible_range` should
  be rewritten to use that DOM path and this ADR should be updated to
  document the stable selectors.
