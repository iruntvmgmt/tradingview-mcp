"""ExperimentController — disciplined strategy iteration on top of verified
chart, settings, pinescript, and backtest controllers.

This is pure Python orchestration.  It calls existing verified controllers;
it does NO new DOM automation and does NOT need recon entries.

Architecture
------------

.. code-block:: text

    ExperimentController
     ├── chart_controller       (set_visible_range)
     ├── settings_controller    (read, write)
     ├── pinescript_controller  (read, write, compile, read_compile_errors)
     ├── backtest_controller    (run_strategy, wait_for_complete,
     │                            get_performance_summary, get_trade_list)
     ├── experiment_config      (loaded/validated JSON)
     └── experiment_log         (append-only JSONL audit trail)

State Machine
-------------

::

    [start_generation] → generation_started
          │
          ▼
    [run_iteration]    → iteration (train window, accepted/rejected)
          │
          ▼
    [run_validation_check] → validation_check (divergence gate)
          │
          ├── fail → [rollback] → rollback
          │
          ▼
    [run_holdout_check] → holdout_check (one-time gate, N-pass gate)
          │
          ▼
    [run_sensitivity_check] → sensitivity_check (noise-fit probe)

Every event is written to the append-only JSONL log.  The log is the
authoritative record — no in-memory state is trusted across calls.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.services.errors import (
    HoldoutAlreadyUsedError,
    MultipleChangesError,
    PrematureHoldoutError,
    WindowConfigurationError,
    WindowGuardError,
)
from core.services.experiment_log import ExperimentLog

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────
DEFAULT_CONFIG_PATH = Path(__file__).parents[2] / "experiment_config.json"
DEFAULT_LOG_PATH = Path(__file__).parents[2] / "logs" / "experiment_log.jsonl"
REPORT_PATH = Path(__file__).parents[2] / "docs" / "EXPERIMENT_LOG.md"

# ── Timeframe → minutes mapping (for bar-budget estimation) ───
_BAR_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1D": 1440,
    "1W": 10080,
    "1M": 43200,
}


# ═══════════════════════════════════════════════════════════════
# Config loader / validator
# ═══════════════════════════════════════════════════════════════

def load_experiment_config(path: Path | None = None) -> dict[str, Any]:
    """Load and validate ``experiment_config.json``.

    Returns the parsed config dict.  Raises ``WindowConfigurationError``
    if any date window check fails, ``WindowGuardError`` if bar-budget
    checks fail.
    """
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"experiment_config.json not found at {path}")

    with open(path) as f:
        config: dict[str, Any] = json.load(f)

    _validate_windows(config.get("windows", {}))
    _validate_bar_budget(config)
    return config


def _validate_windows(windows: dict[str, Any]) -> None:
    """Validate that train/validation/holdout windows are chronologically
    ordered with no overlaps.  Raises ``WindowConfigurationError`` on failure.
    """
    required = ("train", "validation", "holdout")
    dates: dict[str, tuple] = {}

    for name in required:
        w = windows.get(name, {})
        start_str = w.get("start", "")
        end_str = w.get("end", "")
        if not start_str or not end_str:
            raise WindowConfigurationError(
                f"Window '{name}' is missing 'start' or 'end'",
                details={"window": name, "config_snippet": str(w)},
            )
        try:
            s = datetime.strptime(start_str, "%Y-%m-%d")
            e = datetime.strptime(end_str, "%Y-%m-%d")
        except ValueError as exc:
            raise WindowConfigurationError(
                f"Window '{name}' has an unparseable date: {exc}",
                details={"window": name, "start": start_str, "end": end_str},
            ) from exc
        if s >= e:
            raise WindowConfigurationError(
                f"Window '{name}' start ({start_str}) is not before end ({end_str})",
                details={"window": name, "start": start_str, "end": end_str},
            )
        dates[name] = (s, e)

    # Check chronological order: train.end < validation.start < validation.end < holdout.start < holdout.end
    t_end, v_start, v_end, h_start, h_end = (
        dates["train"][1],
        dates["validation"][0],
        dates["validation"][1],
        dates["holdout"][0],
        dates["holdout"][1],
    )
    if t_end >= v_start:
        raise WindowConfigurationError(
            f"Train end ({t_end.date()}) is not before validation start ({v_start.date()}) — "
            f"windows must not overlap",
            details={"train.end": str(t_end.date()), "validation.start": str(v_start.date())},
        )
    if v_start >= v_end:
        raise WindowConfigurationError(
            f"Validation start ({v_start.date()}) is not before validation end ({v_end.date()})",
            details={"validation.start": str(v_start.date()), "validation.end": str(v_end.date())},
        )
    if v_end >= h_start:
        raise WindowConfigurationError(
            f"Validation end ({v_end.date()}) is not before holdout start ({h_start.date()}) — "
            f"windows must not overlap",
            details={"validation.end": str(v_end.date()), "holdout.start": str(h_start.date())},
        )
    if h_start >= h_end:
        raise WindowConfigurationError(
            f"Holdout start ({h_start.date()}) is not before holdout end ({h_end.date()})",
            details={"holdout.start": str(h_start.date()), "holdout.end": str(h_end.date())},
        )


def _validate_bar_budget(config: dict[str, Any]) -> None:
    """Check that configured windows are feasible under the TradingView
    tier's bar limit.

    Raises ``WindowGuardError`` if the full train→holdout intraday
    history envelope exceeds the bar budget.  Daily-or-higher timeframes
    skip the intraday check.
    """
    tier_cfg = config.get("tradingview_tier", {})
    tier = tier_cfg.get("tier", "free")
    bar_limit = tier_cfg.get("intraday_bar_limit", 5000)
    deep_enabled = tier_cfg.get("deep_backtesting_enabled", False)

    # If deep backtesting is enabled, skip bar-budget checks entirely
    if deep_enabled:
        return

    timeframe = config.get("timeframe", "")
    if not timeframe:
        raise WindowGuardError(
            "experiment_config.json is missing the required 'timeframe' field. "
            "Add e.g. \"timeframe\": \"1h\" to enable bar-budget validation.",
            details={"tier": tier},
        )

    bar_minutes = _BAR_MINUTES.get(timeframe)
    if bar_minutes is None:
        raise WindowGuardError(
            f"Unsupported timeframe '{timeframe}'. Supported: "
            f"{', '.join(sorted(_BAR_MINUTES.keys()))}",
            details={"timeframe": timeframe},
        )

    # Daily or higher — intraday bar limits don't apply in the same way;
    # skip the check (daily bars are not "intraday").
    if bar_minutes >= 1440:
        return

    windows = config.get("windows", {})
    try:
        envelope_start = datetime.strptime(windows["train"]["start"], "%Y-%m-%d")
        envelope_end = datetime.strptime(windows["holdout"]["end"], "%Y-%m-%d")
    except (KeyError, ValueError):
        return

    span_minutes = (envelope_end - envelope_start).total_seconds() / 60
    estimated_bars = int(span_minutes / bar_minutes)

    if estimated_bars > bar_limit:
        raise WindowGuardError(
            f"Configured train→holdout window envelope needs approximately "
            f"{estimated_bars} bars on {timeframe}, but TradingView tier "
            f"{tier} is configured for {bar_limit} intraday bars. Use a "
            f"shorter total experiment span, higher timeframe, or higher "
            f"TradingView tier.",
            details={
                "window": "train_to_holdout",
                "start": str(envelope_start.date()),
                "end": str(envelope_end.date()),
                "estimated_bars": estimated_bars,
                "bar_limit": bar_limit,
                "timeframe": timeframe,
                "tier": tier,
            },
        )


# ═══════════════════════════════════════════════════════════════
# Controller
# ═══════════════════════════════════════════════════════════════

class ExperimentController:
    """Orchestrates disciplined strategy iteration across train/validation/
    holdout windows, enforcing one-change-per-iteration, a divergence gate
    for validation, a one-time-only holdout check, and a sensitivity probe.

    Public methods
    --------------
    - ``start_generation(notes) -> generation_id``
    - ``run_iteration(generation_id, change_type, change, description) -> dict``
    - ``run_validation_check(generation_id) -> dict``
    - ``rollback(generation_id, to_iteration_num, reason) -> None``
    - ``run_holdout_check(generation_id) -> dict``
    - ``run_sensitivity_check(generation_id, param_name, current_value) -> dict``
    - ``report(generation_id) -> str``
    """

    def __init__(
        self,
        chart_controller,
        settings_controller,
        pinescript_controller,
        backtest_controller,
        config: dict[str, Any],
        log: ExperimentLog,
        *,
        strategy_name: str = "MA Cross Strategy",
    ) -> None:
        self._chart = chart_controller
        self._settings = settings_controller
        self._pine = pinescript_controller
        self._backtest = backtest_controller
        self._config = config
        self._log = log
        self._strategy_name = strategy_name
        self._windows = config["windows"]
        self._thresholds = config["thresholds"]
        self._mode = config.get("experiment_mode", "disciplined_live_experiment")
        _validate_windows(self._windows)
        _validate_bar_budget(config)

    # ── Window helpers ────────────────────────────────────────

    async def _set_window(self, window: str) -> None:
        """Set the chart's visible date range to *window*.

        Raises ``WindowGuardError`` if the chart backend does not support
        absolute date windows (ADR-0010 requirement).
        """
        self._assert_absolute_date_support()
        w = self._windows[window]
        await self._chart.set_visible_range(w["start"], w["end"])

    def _assert_absolute_date_support(self) -> None:
        """Raise ``WindowGuardError`` if the active chart backend cannot
        set exact absolute date windows — UNLESS experiment_mode is
        ``preset_smoke_test``, in which case only a warning is logged.

        ADR-0010 requires chronological, non-overlapping train/validation/
        holdout windows.  Preset-based backends (1D, 5D, 1M, etc.) silently
        produce approximate windows and must be rejected in disciplined mode.
        """
        mode = self._mode
        backend = getattr(self._chart, "_chart", None)
        if backend is None:
            if mode == "preset_smoke_test":
                logger.warning(
                    "Cannot determine chart backend capabilities — "
                    "preset_smoke_test mode proceeding without guard."
                )
                return
            raise WindowGuardError(
                "Cannot determine chart backend capabilities — "
                "chart controller has no '_chart' attribute.",
                details={"controller_type": type(self._chart).__name__},
            )
        if not hasattr(backend, "supports_absolute_visible_range"):
            if mode == "preset_smoke_test":
                logger.warning(
                    "Chart backend %s does not expose "
                    "supports_absolute_visible_range() — "
                    "preset_smoke_test mode proceeding.",
                    type(backend).__name__,
                )
                return
            raise WindowGuardError(
                f"Chart backend {type(backend).__name__} does not expose "
                f"'supports_absolute_visible_range()'. "
                f"ADR-0010 requires absolute date-window support.",
                details={"backend_type": type(backend).__name__},
            )
        if not backend.supports_absolute_visible_range():
            if mode == "preset_smoke_test":
                logger.warning(
                    "This chart backend only supports preset/trailing "
                    "date ranges (1D, 5D, 1M, ...). preset_smoke_test "
                    "mode: experiment results are NOT ADR-0010 compliant."
                )
                return
            raise WindowGuardError(
                "This chart backend only supports preset/trailing date ranges "
                "(1D, 5D, 1M, 3M, 6M, 1Y, 5Y, All). ADR-0010 requires exact "
                "absolute chronological windows. Live experiment execution is "
                "blocked until absolute date control is implemented for "
                "TradingView Desktop 3.2.0. See "
                "docs/adr/0010-experiment-window-discipline.md.",
                details={
                    "backend_type": type(backend).__name__,
                    "supports_absolute": False,
                },
            )

    # ── Backtest helpers ──────────────────────────────────────

    async def _run_backtest_and_summary(self) -> dict[str, Any]:
        """Run a backtest, wait for completion, return summary dict."""
        await self._backtest.run_strategy(self._strategy_name)
        await self._backtest.wait_for_complete()
        return await self._backtest.get_performance_summary()

    async def _get_trade_count(self) -> int:
        """Return the number of individual trades from the backtest."""
        trades = await self._backtest.get_trade_list()
        return len(trades) if isinstance(trades, list) else 0

    def _compute_accepted(self, metrics: dict[str, Any], trade_count: int) -> bool:
        """Apply threshold checks to decide if this iteration is statistically
        eligible to be considered (not a judgment of "good").

        Returns ``True`` if all three threshold checks pass.
        """
        t = self._thresholds
        pf = float(metrics.get("profit_factor", 0))
        dd = float(metrics.get("max_drawdown", 0))
        return pf >= t["min_profit_factor"] and dd <= t["max_acceptable_drawdown_pct"] and trade_count >= t["min_trades_for_significance"]

    # ── Public API ────────────────────────────────────────────

    async def start_generation(self, notes: str = "") -> str:
        """Snapshot current settings and Pine source as baseline.

        Generates a UUID-based generation_id.  Writes a
        ``generation_started`` event.  Returns the id.

        This is the ONLY way a generation begins — no implicit generation-zero.
        """
        generation_id = uuid.uuid4().hex[:12]

        # Snapshot current state
        settings = await self._settings.read(self._strategy_name)
        pine_source = await self._pine.read(self._strategy_name)
        import hashlib
        pine_hash = hashlib.sha256(pine_source.encode()).hexdigest()[:16]

        event: dict[str, Any] = {
            "event": "generation_started",
            "generation_id": generation_id,
            "baseline_settings": settings,
            "baseline_pine_hash": pine_hash,
            "notes": notes,
        }
        self._log.append_event(event)
        return generation_id

    async def run_iteration(
        self,
        generation_id: str,
        change_type: str,
        change: dict,
        description: str,
    ) -> dict[str, Any]:
        """Run one atomic strategy iteration on the TRAIN window.

        Parameters
        ----------
        generation_id:
            The generation this iteration belongs to.
        change_type:
            ``"settings"`` or ``"pinescript"``.
        change:
            For settings — dict with exactly one key (the param being changed).
            For pinescript — dict with ``{"new_code": str}``.
        description:
            Human-readable statement of what changed and why.  Required;
            empty/missing descriptions are rejected.

        Returns
        -------
        The iteration event dict (also appended to log).

        Raises
        ------
        MultipleChangesError
            If more than one field differs from current state, or zero differ.
        """
        # ── Validate description ──────────────────────────────
        if not description or not description.strip():
            raise MultipleChangesError(
                "description is required and must not be empty",
                details={"change_type": change_type},
            )

        # ── Compute iteration number ──────────────────────────
        gen_events = self._log.read_generation(generation_id)
        iteration_num = sum(1 for e in gen_events if e.get("event") == "iteration") + 1

        if change_type == "settings":
            # ── Settings: single-parameter change enforcement ─
            if not isinstance(change, dict) or len(change) != 1:
                raise MultipleChangesError(
                    f"Expected exactly 1 setting key in change dict, got {len(change) if isinstance(change, dict) else 'non-dict'}",
                    details={"change_keys": list(change.keys()) if isinstance(change, dict) else None},
                )
            param_name = next(iter(change))
            new_value = change[param_name]

            # Read current settings and check that exactly one differs
            current = await self._settings.read(self._strategy_name)
            diffs = {
                k: (current.get(k), change.get(k))
                for k in change
                if k not in current or current[k] != change[k]
            }
            if len(diffs) != 1:
                raise MultipleChangesError(
                    f"Expected exactly 1 setting field to differ from current state, found {len(diffs)}",
                    details={"change": change, "current": current, "diffs": diffs},
                )

            before_value = current.get(param_name)
            after_value = new_value

            # Apply the change
            await self._settings.write(self._strategy_name, change)

        elif change_type == "pinescript":
            # ── Pinescript: compile-first, reject on failure ──
            new_code = change.get("new_code", "")
            if not new_code or not isinstance(new_code, str) or not new_code.strip():
                raise MultipleChangesError(
                    "PineScript change must contain non-empty 'new_code' string",
                    details={"change": change},
                )

            # Read current source for before/after logging
            before_value = await self._pine.read(self._strategy_name)
            after_value = new_code

            # Write and compile
            await self._pine.write(self._strategy_name, new_code)
            compile_result = await self._pine.compile(self._strategy_name)

            if not compile_result.get("success"):
                errors = await self._pine.read_compile_errors()
                error_msgs = [e.get("message", str(e)) for e in errors] if errors else ["Unknown compile error"]
                iteration_event: dict[str, Any] = {
                    "event": "iteration",
                    "generation_id": generation_id,
                    "iteration_num": iteration_num,
                    "change_type": "pinescript",
                    "change_description": description,
                    "before_value": before_value[:200],
                    "after_value": new_code[:200],
                    "window": "train",
                    "metrics": {},
                    "trade_count": 0,
                    "accepted": False,
                    "reject_reason": f"Compile failed: {'; '.join(error_msgs)}",
                }
                self._log.append_event(iteration_event)
                return iteration_event

        else:
            raise MultipleChangesError(
                f"Unknown change_type: {change_type!r}. Must be 'settings' or 'pinescript'.",
                details={"change_type": change_type},
            )

        # ── Run backtest on TRAIN window ──────────────────────
        await self._set_window("train")
        metrics = await self._run_backtest_and_summary()
        trade_count = await self._get_trade_count()
        accepted = self._compute_accepted(metrics, trade_count)

        reject_reason = None
        if not accepted:
            reasons = []
            if float(metrics.get("profit_factor", 0)) < self._thresholds["min_profit_factor"]:
                reasons.append(f"profit_factor {metrics.get('profit_factor')} < min {self._thresholds['min_profit_factor']}")
            if float(metrics.get("max_drawdown", 0)) > self._thresholds["max_acceptable_drawdown_pct"]:
                reasons.append(f"max_drawdown {metrics.get('max_drawdown')} > max {self._thresholds['max_acceptable_drawdown_pct']}")
            if trade_count < self._thresholds["min_trades_for_significance"]:
                reasons.append(f"trade_count {trade_count} < min {self._thresholds['min_trades_for_significance']}")
            reject_reason = "; ".join(reasons) if reasons else "did not meet acceptance thresholds"

        iteration_event = {
            "event": "iteration",
            "generation_id": generation_id,
            "iteration_num": iteration_num,
            "change_type": change_type,
            "change_description": description,
            "before_value": before_value,
            "after_value": after_value,
            "window": "train",
            "metrics": metrics,
            "trade_count": trade_count,
            "accepted": accepted,
            "reject_reason": reject_reason,
        }
        self._log.append_event(iteration_event)
        return iteration_event

    async def run_validation_check(self, generation_id: str) -> dict[str, Any]:
        """Run a backtest on the VALIDATION window and compute divergence
        against the most recent train metrics.

        Returns a ``validation_check`` dict (also appended to log).

        If verdict is ``"fail"``, the dict includes
        ``recommended_rollback_to_iteration_num`` — the most recent prior
        iteration where a validation_check passed (or ``null`` if none exists).
        """
        # Get latest iteration's train metrics
        latest = self._log.latest_iteration(generation_id)
        if latest is None:
            raise ValueError(f"No iteration recorded for generation {generation_id}")

        train_metrics = latest.get("metrics", {})
        train_pf = float(train_metrics.get("profit_factor", 0))

        # Run backtest on VALIDATION window
        await self._set_window("validation")
        validation_metrics = await self._run_backtest_and_summary()
        validation_pf = float(validation_metrics.get("profit_factor", 0))

        # Compute divergence
        if train_pf > 0:
            divergence_pct = abs(train_pf - validation_pf) / train_pf * 100
        else:
            divergence_pct = 100.0 if validation_pf > 0 else 0.0

        verdict = "pass" if divergence_pct <= self._thresholds["divergence_threshold_pct"] else "fail"

        # Compute consecutive passes BEFORE appending anything — use the
        # log state as it exists prior to this check, then adjust for
        # this check's verdict.
        previous_consecutive = self._log.consecutive_validation_passes(generation_id)
        consecutive = previous_consecutive + 1 if verdict == "pass" else 0

        # Find recommended rollback point on fail (look at existing log
        # events only — this check hasn't been written yet, so the
        # "most recent prior pass" is unambiguous).
        recommended_rollback = None
        if verdict == "fail":
            gen_events = self._log.read_generation(generation_id)
            for e in reversed(gen_events):
                if (
                    e.get("event") == "validation_check"
                    and e.get("verdict") == "pass"
                    and e.get("at_iteration_num") is not None
                ):
                    recommended_rollback = e["at_iteration_num"]
                    break

        # Append exactly ONE validation_check event — no placeholder.
        validation_event: dict[str, Any] = {
            "event": "validation_check",
            "generation_id": generation_id,
            "at_iteration_num": latest.get("iteration_num"),
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "divergence_pct": round(divergence_pct, 2),
            "verdict": verdict,
            "consecutive_passes_after_this": consecutive,
        }
        if verdict == "fail":
            validation_event["recommended_rollback_to_iteration_num"] = recommended_rollback

        self._log.append_event(validation_event)
        return validation_event

    async def rollback(
        self, generation_id: str, to_iteration_num: int, reason: str
    ) -> None:
        """Re-apply the settings/Pine state from a specific iteration,
        actually reverting the live TradingView state.

        Appends a ``rollback`` event.
        """
        gen_events = self._log.read_generation(generation_id)
        target = None
        for e in gen_events:
            if e.get("event") == "iteration" and e.get("iteration_num") == to_iteration_num:
                target = e
                break

        if target is None:
            raise ValueError(
                f"No iteration_num={to_iteration_num} found in generation {generation_id}"
            )

        change_type = target.get("change_type")
        if change_type == "settings":
            after = target.get("after_value")
            if after is not None:
                # after_value for settings is a single key's value;
                # we need to find which param it was
                param_name = None
                for e2 in gen_events:
                    if e2.get("event") == "generation_started":
                        baseline = e2.get("baseline_settings", {})
                        for k, v in baseline.items():
                            if v != after:
                                param_name = k
                                break
                        break
                if param_name is None:
                    param_name = next(iter(target.get("before_value", {})), None) or "unknown"
                await self._settings.write(self._strategy_name, {param_name: after})
        elif change_type == "pinescript":
            after = target.get("after_value")
            if after:
                await self._pine.write(self._strategy_name, after)
                await self._pine.compile(self._strategy_name)

        self._log.append_event({
            "event": "rollback",
            "generation_id": generation_id,
            "rolled_back_to_iteration_num": to_iteration_num,
            "reason": reason,
        })

    async def run_holdout_check(self, generation_id: str) -> dict[str, Any]:
        """Run a backtest on the HOLDOUT window.

        This is the ONLY method in the entire class allowed to touch the
        holdout window.

        Raises
        ------
        HoldoutAlreadyUsedError
            If a holdout_check already exists for this generation.
        PrematureHoldoutError
            If consecutive validation passes < required threshold.
        """
        # ── Gate: one-time only ───────────────────────────────
        gen_events = self._log.read_generation(generation_id)
        for e in gen_events:
            if e.get("event") == "holdout_check":
                raise HoldoutAlreadyUsedError(
                    f"Holdout already checked for generation {generation_id}. "
                    f"To test again, start a new generation.",
                    details={"generation_id": generation_id},
                )

        # ── Gate: N consecutive validation passes required ────
        required = self._thresholds["validation_passes_required_before_holdout"]
        current = self._log.consecutive_validation_passes(generation_id)
        if current < required:
            raise PrematureHoldoutError(
                f"Holdout requires {required} consecutive validation passes; "
                f"generation {generation_id} has only {current}.",
                details={
                    "generation_id": generation_id,
                    "consecutive_passes": current,
                    "required_passes": required,
                },
            )

        # ── Run holdout backtest ──────────────────────────────
        await self._set_window("holdout")
        metrics = await self._run_backtest_and_summary()
        trade_count = await self._get_trade_count()
        passed = self._compute_accepted(metrics, trade_count)

        event: dict[str, Any] = {
            "event": "holdout_check",
            "generation_id": generation_id,
            "metrics": metrics,
            "passed_promotion_criteria": passed,
        }
        self._log.append_event(event)
        return event

    async def run_sensitivity_check(
        self, generation_id: str, param_name: str, current_value: float
    ) -> dict[str, Any]:
        """Probe whether *param_name* is fit to noise by nudging it
        ±sensitivity_swing_pct and measuring profit_factor delta.

        Runs on the TRAIN window.  Restores *current_value* before returning.
        Logs a ``sensitivity_check`` event (NOT an iteration).
        """
        swing_pct = self._thresholds["sensitivity_swing_pct"]
        max_pf_delta = self._thresholds["sensitivity_max_pf_delta_pct"]

        down_value = current_value * (1 - swing_pct / 100)
        up_value = current_value * (1 + swing_pct / 100)

        # Read fields to ensure we write correct types
        fields = await self._settings.list_fields(self._strategy_name)
        field_info: dict[str, Any] = {}
        for f in fields:
            if f.get("name") == param_name:
                field_info = f
                break

        is_int = field_info.get("type") == "int"
        if is_int:
            down_value = int(round(down_value))
            up_value = int(round(up_value))

        # ── Current PF on train ───────────────────────────────
        await self._set_window("train")
        metrics_current = await self._run_backtest_and_summary()
        pf_current = float(metrics_current.get("profit_factor", 0))

        # ── PF at value-down ──────────────────────────────────
        await self._settings.write(self._strategy_name, {param_name: down_value})
        metrics_down = await self._run_backtest_and_summary()
        pf_down = float(metrics_down.get("profit_factor", 0))

        # ── PF at value-up ────────────────────────────────────
        await self._settings.write(self._strategy_name, {param_name: up_value})
        metrics_up = await self._run_backtest_and_summary()
        pf_up = float(metrics_up.get("profit_factor", 0))

        # ── Restore current value ─────────────────────────────
        await self._settings.write(self._strategy_name, {param_name: current_value})

        # ── Compute delta ─────────────────────────────────────
        pf_values = [pf_down, pf_current, pf_up]
        pf_range = max(pf_values) - min(pf_values)
        pf_delta_pct = (pf_range / pf_current * 100) if pf_current > 0 else 0.0
        is_noise_fit = pf_delta_pct > max_pf_delta

        result: dict[str, Any] = {
            "event": "sensitivity_check",
            "generation_id": generation_id,
            "param_name": param_name,
            "pf_down": pf_down,
            "pf_current": pf_current,
            "pf_up": pf_up,
            "pf_delta_pct": round(pf_delta_pct, 2),
            "is_noise_fit": is_noise_fit,
        }
        self._log.append_event(result)
        return result

    def report(self, generation_id: str | None = None) -> str:
        """Generate a Markdown report of experiment activity and write it
        to ``docs/EXPERIMENT_LOG.md``.

        Follows the same conventions as ``docs/STATUS.md``: generated-file
        header, timestamp, tables.
        """
        if generation_id:
            gens = {generation_id: self._log.read_generation(generation_id)}
        else:
            gens = self._log.read_all_generations()

        lines: list[str] = []
        lines.append("# Experiment Log")
        lines.append("")
        lines.append(
            "> **Generated file — do not hand-edit.** Rebuilt from "
            "`logs/experiment_log.jsonl` by `ExperimentController.report()`."
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"")
        lines.append(f"Last generated: {now}")
        lines.append("")

        if not gens:
            lines.append("_No experiment activity recorded._")
            report_text = "".join(lines)
            REPORT_PATH.write_text(report_text)
            return report_text

        for gid, events in gens.items():
            lines.append(f"## Generation `{gid}`")
            lines.append("")

            # Summary counts
            started = next((e for e in events if e["event"] == "generation_started"), None)
            iterations = [e for e in events if e["event"] == "iteration"]
            accepted = [e for e in iterations if e.get("accepted")]
            rejected = [e for e in iterations if not e.get("accepted")]
            val_checks = [e for e in events if e["event"] == "validation_check"]
            holdout = next((e for e in events if e["event"] == "holdout_check"), None)
            sens = [e for e in events if e["event"] == "sensitivity_check"]
            rollbacks = [e for e in events if e["event"] == "rollback"]

            lines.append(f"| Metric | Value |")
            lines.append(f"|---|---|")
            if started:
                lines.append(f"| Started | {started.get('timestamp', '?')} |")
                lines.append(f"| Notes | {started.get('notes', '—')} |")
            lines.append(f"| Iterations | {len(iterations)} total ({len(accepted)} accepted, {len(rejected)} rejected) |")
            lines.append(f"| Validation checks | {len(val_checks)} |")
            lines.append(f"| Rollbacks | {len(rollbacks)} |")
            lines.append(f"| Holdout | {'✓ run' if holdout else 'not yet'} |")
            lines.append(f"| Sensitivity checks | {len(sens)} |")
            lines.append("")

            # ── Best validation-confirmed iteration ────────────────
            # Candidates must be (a) accepted, (b) not rolled back,
            # and (c) have at least one validation_check with
            # verdict == "pass" at or after that iteration_num.
            #
            # "Rolled back" means the iteration was the specific one
            # undone by a rollback event — NOT every iteration with a
            # higher number than the rollback target.  To determine
            # which iterations a rollback actually undid, we walk the
            # log in event order: for each rollback, the iterations
            # that existed at that moment are those whose iteration_num
            # is <= the highest iteration_num seen before the rollback.
            # The disqualified range is (target, highest_at_rollback_time].

            def _build_disqualified_set(
                events: list[dict],
            ) -> set[int]:
                """Return the set of iteration_nums that were undone by
                any rollback event in this generation.

                Only iterations that existed at the time of a rollback
                and whose num > the rollback target are disqualified.
                Iterations created AFTER a rollback are not affected.
                """
                disqualified: set[int] = set()
                highest_iter_seen = 0
                for e in events:
                    if e.get("event") == "iteration":
                        num = e.get("iteration_num")
                        if isinstance(num, int) and num > highest_iter_seen:
                            highest_iter_seen = num
                    elif e.get("event") == "rollback":
                        target = e.get("rolled_back_to_iteration_num")
                        if isinstance(target, int):
                            # Disqualify every iteration_num strictly
                            # greater than target and <= the highest
                            # iteration_num that existed when this
                            # rollback was recorded.
                            for n in range(target + 1, highest_iter_seen + 1):
                                disqualified.add(n)
                return disqualified

            disqualified_iter_nums = _build_disqualified_set(events)

            validation_passes_at = {
                vc["at_iteration_num"]
                for vc in val_checks
                if vc.get("verdict") == "pass"
            }

            def _is_confirmed(it: dict) -> bool:
                num = it["iteration_num"]
                return any(p >= num for p in validation_passes_at)

            def _is_rolled_back(it: dict) -> bool:
                return it["iteration_num"] in disqualified_iter_nums

            candidates = [
                it for it in accepted
                if not _is_rolled_back(it) and _is_confirmed(it)
            ]

            if candidates:
                best = max(
                    candidates,
                    key=lambda it: float(it.get("metrics", {}).get("profit_factor", 0)),
                )
                lines.append("### Best validation-confirmed iteration")
                lines.append("")
                lines.append(
                    "_Iterations that failed validation or were rolled back "
                    "are excluded from this selection even if their raw "
                    "train-window numbers looked better._"
                )
                lines.append("")
                lines.append("| Field | Value |")
                lines.append("|---|---|")
                lines.append(f"| Iteration # | {best['iteration_num']} |")
                lines.append(f"| Change | {best.get('change_description', '—')[:100]} |")
                m = best.get("metrics", {})
                for k, v in m.items():
                    lines.append(f"| {k} | {v} |")
                lines.append(f"| Trade count | {best.get('trade_count', '?')} |")
                lines.append("")
            else:
                lines.append("### Best validation-confirmed iteration")
                lines.append("")
                lines.append(
                    "_No accepted iteration has been validation-confirmed yet._"
                )
                lines.append("")

            # Validation history
            if val_checks:
                lines.append(f"### Validation history")
                lines.append("")
                lines.append(f"| # | At Iter | Divergence % | Verdict | Consecutive Passes |")
                lines.append(f"|---|---|---|---|---|")
                for i, vc in enumerate(val_checks, 1):
                    lines.append(
                        f"| {i} | {vc.get('at_iteration_num', '?')} "
                        f"| {vc.get('divergence_pct', '?')}% "
                        f"| **{vc.get('verdict', '?')}** "
                        f"| {vc.get('consecutive_passes_after_this', '?')} |"
                    )
                lines.append("")

            # Holdout
            if holdout:
                lines.append(f"### Holdout result")
                lines.append("")
                lines.append(f"| Field | Value |")
                lines.append(f"|---|---|")
                lines.append(f"| Passed | {holdout.get('passed_promotion_criteria', '?')} |")
                for k, v in holdout.get("metrics", {}).items():
                    lines.append(f"| {k} | {v} |")
                lines.append("")

            # Sensitivity flags
            noise_fits = [s for s in sens if s.get("is_noise_fit")]
            if noise_fits:
                lines.append(f"### ⚠️ Sensitivity flags (noise-fit risk)")
                lines.append("")
                for s in noise_fits:
                    lines.append(
                        f"- **{s['param_name']}**: PF delta {s['pf_delta_pct']}% "
                        f"(threshold: {self._thresholds['sensitivity_max_pf_delta_pct']}%). "
                        f"PF down={s['pf_down']:.2f}, current={s['pf_current']:.2f}, up={s['pf_up']:.2f}"
                    )
                lines.append("")

            lines.append("---")
            lines.append("")

        report_text = "\n".join(lines) + "\n"
        REPORT_PATH.write_text(report_text)
        return report_text
