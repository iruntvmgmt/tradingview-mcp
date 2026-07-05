"""Tests for ExperimentController — fully mocked, no live TradingView app.

Each test constructs the controller with mock chart/settings/pine/backtest
controllers and a real ExperimentLog in a temp directory, then verifies
state-machine behavior, error conditions, and threshold logic.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.errors import (
    HoldoutAlreadyUsedError,
    MultipleChangesError,
    PrematureHoldoutError,
    WindowConfigurationError,
)
from core.services.experiment_controller import (
    ExperimentController,
    _validate_windows,
    load_experiment_config,
)
from core.services.experiment_log import ExperimentLog

# ── Shared config fixture ──────────────────────────────────────

VALID_CONFIG = {
    "windows": {
        "train":      {"start": "2023-01-01", "end": "2024-01-01"},
        "validation": {"start": "2024-01-02", "end": "2024-06-01"},
        "holdout":    {"start": "2024-06-02", "end": "2024-12-01"},
    },
    "thresholds": {
        "min_trades_for_significance": 30,
        "max_acceptable_drawdown_pct": 20.0,
        "min_profit_factor": 1.2,
        "divergence_threshold_pct": 30.0,
        "validation_passes_required_before_holdout": 3,
        "sensitivity_swing_pct": 15.0,
        "sensitivity_max_pf_delta_pct": 40.0,
    },
}


# ── Helpers ────────────────────────────────────────────────────

def _make_mock_controller(cls_name: str, **methods):
    """Create an AsyncMock-based controller with the given async methods."""
    ctrl = MagicMock()
    for name, return_value in methods.items():
        setattr(ctrl, name, AsyncMock(return_value=return_value))
    return ctrl


def _make_controller(tmp_path: Path, config: dict | None = None, **overrides):
    """Build an ExperimentController with mock dependencies.

    All four controllers use AsyncMock.  The ExperimentLog writes to a
    temp file so tests can inspect the JSONL audit trail.
    """
    if config is None:
        config = VALID_CONFIG

    chart = _make_mock_controller("chart",
        set_visible_range=None,        # no-op
    )
    settings = _make_mock_controller("settings",
        read={},
        write=None,
        list_fields=[],
    )
    pine = _make_mock_controller("pine",
        read="// baseline code",
        write=None,
        compile={"success": True},
        read_compile_errors=[],
    )
    backtest = _make_mock_controller("backtest",
        run_strategy=None,
        wait_for_complete=True,
        get_performance_summary={
            "net_profit": 5000,
            "profit_factor": 1.8,
            "max_drawdown": 15.0,
            "sharpe": 1.2,
            "total_trades": 50,
        },
        get_trade_list=[{"trade_number": 1}] * 50,
    )

    # Apply overrides
    for name, ctrl in overrides.items():
        if name == "chart":
            chart = ctrl
        elif name == "settings":
            settings = ctrl
        elif name == "pine":
            pine = ctrl
        elif name == "backtest":
            backtest = ctrl

    log = ExperimentLog(tmp_path / "experiment_log.jsonl")
    return ExperimentController(chart, settings, pine, backtest, config, log)


# ═══════════════════════════════════════════════════════════════
# Config validation
# ═══════════════════════════════════════════════════════════════

class TestWindowValidation:
    def test_valid_windows_pass(self):
        _validate_windows(VALID_CONFIG["windows"])  # no exception

    def test_overlapping_train_validation_raises(self):
        bad = {
            "train":      {"start": "2023-01-01", "end": "2024-02-01"},
            "validation": {"start": "2024-01-15", "end": "2024-06-01"},
            "holdout":    {"start": "2024-06-02", "end": "2024-12-01"},
        }
        with pytest.raises(WindowConfigurationError) as exc:
            _validate_windows(bad)
        assert "not before" in str(exc.value)

    def test_overlapping_validation_holdout_raises(self):
        bad = {
            "train":      {"start": "2023-01-01", "end": "2024-01-01"},
            "validation": {"start": "2024-01-02", "end": "2024-07-01"},
            "holdout":    {"start": "2024-06-15", "end": "2024-12-01"},
        }
        with pytest.raises(WindowConfigurationError) as exc:
            _validate_windows(bad)
        assert "not before" in str(exc.value)

    def test_reversed_dates_raises(self):
        bad = {
            "train":      {"start": "2024-06-01", "end": "2023-01-01"},
            "validation": {"start": "2024-06-02", "end": "2024-12-01"},
            "holdout":    {"start": "2025-01-01", "end": "2025-06-01"},
        }
        with pytest.raises(WindowConfigurationError) as exc:
            _validate_windows(bad)
        assert "not before" in str(exc.value)

    def test_unparseable_date_raises(self):
        bad = {
            "train":      {"start": "not-a-date", "end": "2024-01-01"},
            "validation": {"start": "2024-01-02", "end": "2024-06-01"},
            "holdout":    {"start": "2024-06-02", "end": "2024-12-01"},
        }
        with pytest.raises(WindowConfigurationError):
            _validate_windows(bad)


# ═══════════════════════════════════════════════════════════════
# ExperimentController tests
# ═══════════════════════════════════════════════════════════════

class TestStartGeneration:
    @pytest.mark.asyncio
    async def test_returns_generation_id(self, tmp_path: Path):
        ctrl = _make_controller(tmp_path)
        gid = await ctrl.start_generation("test generation")
        assert isinstance(gid, str)
        assert len(gid) == 12

    @pytest.mark.asyncio
    async def test_writes_generation_started_event(self, tmp_path: Path):
        ctrl = _make_controller(tmp_path)
        gid = await ctrl.start_generation("baseline snapshot")
        events = ctrl._log.read_generation(gid)
        assert len(events) == 1
        assert events[0]["event"] == "generation_started"
        assert events[0]["notes"] == "baseline snapshot"

    @pytest.mark.asyncio
    async def test_snapshots_settings_and_pine(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        pine = _make_mock_controller("pine", read="// strategy() => ...", write=None, compile={"success": True}, read_compile_errors=[])
        ctrl = _make_controller(tmp_path, settings=settings, pine=pine)
        gid = await ctrl.start_generation()
        events = ctrl._log.read_generation(gid)
        assert events[0]["baseline_settings"] == {"length": 14}
        assert len(events[0]["baseline_pine_hash"]) == 16


class TestRunIteration:
    @pytest.mark.asyncio
    async def test_accepts_single_settings_change(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()
        result = await ctrl.run_iteration(gid, "settings", {"length": 21}, "Increase length to 21")
        assert result["accepted"] is True
        assert result["change_type"] == "settings"
        assert result["trade_count"] == 50

    @pytest.mark.asyncio
    async def test_multiple_settings_keys_raises(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14, "source": "close"}, write=None, list_fields=[])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={}, get_trade_list=[])
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        with pytest.raises(MultipleChangesError) as exc:
            await ctrl.run_iteration(gid, "settings", {"length": 21, "source": "hl2"}, "Two changes")
        assert "Expected exactly 1" in str(exc.value)
        # Verify backtest was NEVER called
        backtest.run_strategy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_zero_diff_settings_raises(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={}, get_trade_list=[])
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        with pytest.raises(MultipleChangesError) as exc:
            await ctrl.run_iteration(gid, "settings", {"length": 14}, "No change")
        assert "0" in str(exc.value) or "zero" in str(exc.value).lower()
        backtest.run_strategy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_compile_failure_aborts_before_backtest(self, tmp_path: Path):
        pine = _make_mock_controller("pine",
            read="// code", write=None,
            compile={"success": False},
            read_compile_errors=[{"message": "Syntax error at line 5"}])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={}, get_trade_list=[])
        ctrl = _make_controller(tmp_path, pine=pine, backtest=backtest)
        gid = await ctrl.start_generation()
        result = await ctrl.run_iteration(gid, "pinescript", {"new_code": "// broken"}, "Fix syntax")
        assert result["accepted"] is False
        assert "Syntax error" in str(result["reject_reason"])
        # Backtest must NOT have been called
        backtest.run_strategy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejected_when_below_thresholds(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={
                "profit_factor": 0.9,      # below 1.2
                "max_drawdown": 25.0,      # above 20%
            },
            get_trade_list=[{"trade_number": 1}] * 5,  # below 30
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        result = await ctrl.run_iteration(gid, "settings", {"length": 100}, "Bad change")
        assert result["accepted"] is False
        assert result["reject_reason"] is not None

    @pytest.mark.asyncio
    async def test_empty_description_rejected(self, tmp_path: Path):
        ctrl = _make_controller(tmp_path)
        gid = await ctrl.start_generation()
        with pytest.raises(MultipleChangesError):
            await ctrl.run_iteration(gid, "settings", {"length": 21}, "")

    @pytest.mark.asyncio
    async def test_iteration_num_increments(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()
        r1 = await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change 1")
        r2 = await ctrl.run_iteration(gid, "settings", {"length": 30}, "Change 2")
        assert r1["iteration_num"] == 1
        assert r2["iteration_num"] == 2


class TestValidationCheck:
    @pytest.mark.asyncio
    async def test_computes_divergence_correctly(self, tmp_path: Path):
        """Verify divergence_pct is the actual computed number, not just presence."""
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={
                "profit_factor": 1.8,
                "max_drawdown": 15.0,
                "total_trades": 50,
            },
            get_trade_list=[{"trade_number": 1}] * 50,
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Test change")

        # Override backtest to return different validation PF
        backtest.get_performance_summary.return_value = {
            "profit_factor": 1.26,   # 30% divergence from 1.8
            "max_drawdown": 15.0,
            "total_trades": 50,
        }
        result = await ctrl.run_validation_check(gid)
        # (1.8 - 1.26) / 1.8 * 100 = 30.0
        assert result["divergence_pct"] == pytest.approx(30.0, abs=0.1)
        assert result["verdict"] == "pass"  # 30.0 <= 30.0

    @pytest.mark.asyncio
    async def test_fail_when_divergence_exceeds_threshold(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={"profit_factor": 1.8, "max_drawdown": 15.0},
            get_trade_list=[{"trade_number": 1}] * 50,
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Test change")

        backtest.get_performance_summary.return_value = {
            "profit_factor": 0.9,     # 50% divergence from 1.8
            "max_drawdown": 15.0,
        }
        result = await ctrl.run_validation_check(gid)
        assert result["verdict"] == "fail"
        assert result["divergence_pct"] == pytest.approx(50.0, abs=0.1)

    # ── Regression: double-append bug ─────────────────────────

    @pytest.mark.asyncio
    async def test_exactly_one_event_appended_per_check(self, tmp_path: Path):
        """run_validation_check must append exactly ONE event to the log
        per call — no placeholder, no duplicate.  (Regression test for
        the double-append bug that corrupted consecutive-pass counts.)"""
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change")

        # Count validation_check events in the log before
        before = sum(1 for e in ctrl._log.read_generation(gid) if e["event"] == "validation_check")

        await ctrl.run_validation_check(gid)

        after = sum(1 for e in ctrl._log.read_generation(gid) if e["event"] == "validation_check")
        assert after == before + 1, (
            f"Expected exactly 1 validation_check event appended per call. "
            f"Before: {before}, After: {after} (expected {before + 1})"
        )

    @pytest.mark.asyncio
    async def test_consecutive_passes_equals_exactly_three_after_three_passes(self, tmp_path: Path):
        """After 3 genuine consecutive validation passes,
        consecutive_validation_passes() must return exactly 3, not 6.
        (Regression test for the double-append bug.)"""
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        # Each backtest returns PF=1.8 → divergence 0% → always "pass"
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={"profit_factor": 1.8, "max_drawdown": 15.0},
            get_trade_list=[{"trade_number": 1}] * 50,
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change")

        # Run 3 validation checks — all should be "pass"
        for i in range(3):
            await ctrl.run_validation_check(gid)

        assert ctrl._log.consecutive_validation_passes(gid) == 3, (
            f"Expected 3 consecutive passes after 3 pass calls, got "
            f"{ctrl._log.consecutive_validation_passes(gid)}"
        )

    @pytest.mark.asyncio
    async def test_pass_pass_fail_pass_returns_one(self, tmp_path: Path):
        """Controller-level parallel of the log-level pass/pass/fail/pass
        test.  After fail resets the streak, a subsequent pass must return
        exactly 1, not 3 or any other inflated count."""
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={"profit_factor": 1.8, "max_drawdown": 15.0},
            get_trade_list=[{"trade_number": 1}] * 50,
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change")

        # Pass #1
        await ctrl.run_validation_check(gid)
        # Pass #2
        await ctrl.run_validation_check(gid)
        # Fail — override backtest to force divergence > threshold
        backtest.get_performance_summary.return_value = {
            "profit_factor": 0.5,  # >30% divergence → fail
            "max_drawdown": 15.0,
        }
        await ctrl.run_validation_check(gid)
        # Pass #4 (after fail — streak should be 1, not 3)
        backtest.get_performance_summary.return_value = {
            "profit_factor": 1.8,  # back to pass territory
            "max_drawdown": 15.0,
        }
        await ctrl.run_validation_check(gid)

        assert ctrl._log.consecutive_validation_passes(gid) == 1, (
            f"After pass/pass/fail/pass, consecutive passes should be 1, "
            f"got {ctrl._log.consecutive_validation_passes(gid)}"
        )


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_reapplies_historical_settings(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "First change")
        await ctrl.run_iteration(gid, "settings", {"length": 30}, "Second change")

        await ctrl.rollback(gid, 1, "Overshot — going back")
        # settings.write should have been called with the rolled-back param
        # The rollback looks up iteration 1's after_value and writes it
        write_calls = settings.write.await_args_list
        # At least one write call with the rolled-back value
        found = False
        for call in write_calls:
            args = call.args
            if len(args) >= 2:
                if args[1].get("length") == 21:
                    found = True
                    break
        assert found, f"Rollback did not write length=21 back. Write calls: {write_calls}"

    @pytest.mark.asyncio
    async def test_rollback_writes_rollback_event(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change")

        await ctrl.rollback(gid, 1, "Test rollback")
        events = ctrl._log.read_generation(gid)
        rollback_events = [e for e in events if e["event"] == "rollback"]
        assert len(rollback_events) == 1
        assert rollback_events[0]["reason"] == "Test rollback"


class TestHoldoutCheck:
    @pytest.mark.asyncio
    async def test_raises_premature_when_insufficient_passes(self, tmp_path: Path):
        ctrl = _make_controller(tmp_path)
        gid = await ctrl.start_generation()

        with pytest.raises(PrematureHoldoutError) as exc:
            await ctrl.run_holdout_check(gid)
        assert "3" in str(exc.value)  # required
        assert "0" in str(exc.value)  # current

    @pytest.mark.asyncio
    async def test_raises_holdout_already_used(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()

        # Seed 3 consecutive passes
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change 1")
        for _ in range(3):
            ctrl._log.append_event({
                "event": "validation_check",
                "generation_id": gid,
                "verdict": "pass",
                "at_iteration_num": 1,
            })
        # Also seed a holdout_check event
        ctrl._log.append_event({
            "event": "holdout_check",
            "generation_id": gid,
            "metrics": {},
            "passed_promotion_criteria": True,
        })

        with pytest.raises(HoldoutAlreadyUsedError) as exc:
            await ctrl.run_holdout_check(gid)
        assert "already checked" in str(exc.value).lower() or "start a new generation" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_passes_when_gates_met(self, tmp_path: Path):
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Change")

        # Seed 3 consecutive validation passes
        for i in range(3):
            ctrl._log.append_event({
                "event": "validation_check",
                "generation_id": gid,
                "verdict": "pass",
                "at_iteration_num": 1,
            })

        result = await ctrl.run_holdout_check(gid)
        assert "passed_promotion_criteria" in result
        assert result["event"] == "holdout_check"


class TestSensitivityCheck:
    @pytest.mark.asyncio
    async def test_restores_current_value_after_probe(self, tmp_path: Path):
        settings = _make_mock_controller("settings",
            read={"length": 14}, write=None,
            list_fields=[{"name": "length", "type": "int", "current_value": 14}],
        )
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation()

        result = await ctrl.run_sensitivity_check(gid, "length", 14.0)

        # The LAST settings.write call must be restoring current_value
        last_call = settings.write.await_args_list[-1]
        _, kwargs = last_call
        if len(last_call.args) >= 2:
            last_value = last_call.args[1]
        else:
            last_value = kwargs.get("values", {})
        assert last_value.get("length") == 14, f"Last write should restore length=14, got {last_value}"

    @pytest.mark.asyncio
    async def test_detects_noise_fit(self, tmp_path: Path):
        """When PF swings widely, is_noise_fit should be True."""
        settings = _make_mock_controller("settings",
            read={"length": 14}, write=None,
            list_fields=[{"name": "length", "type": "int"}],
        )
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={"profit_factor": 1.5, "max_drawdown": 15.0},
            get_trade_list=[{"trade_number": 1}] * 50,
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()

        # Override to return different PFs for down/current/up
        pf_values = [0.5, 1.5, 2.5]  # wide swing
        call_count = [0]

        async def rotating_pf():
            val = pf_values[call_count[0] % len(pf_values)]
            call_count[0] += 1
            return {"profit_factor": val, "max_drawdown": 15.0}

        backtest.get_performance_summary = AsyncMock(side_effect=rotating_pf)

        result = await ctrl.run_sensitivity_check(gid, "length", 14.0)
        # pf_down=0.5, pf_current=1.5, pf_up=2.5 → range=2.0, delta=2.0/1.5*100=133.3%
        # That's > 40% threshold → noise_fit=True
        assert result["is_noise_fit"] is True
        assert result["pf_delta_pct"] > 40.0

    @pytest.mark.asyncio
    async def test_not_noise_fit_when_stable(self, tmp_path: Path):
        """When PF is stable across nudges, is_noise_fit should be False."""
        settings = _make_mock_controller("settings",
            read={"length": 14}, write=None,
            list_fields=[{"name": "length", "type": "float"}],
        )
        backtest = _make_mock_controller("backtest",
            run_strategy=None, wait_for_complete=True,
            get_performance_summary={"profit_factor": 1.80, "max_drawdown": 15.0},
            get_trade_list=[{"trade_number": 1}] * 50,
        )
        ctrl = _make_controller(tmp_path, settings=settings, backtest=backtest)
        gid = await ctrl.start_generation()
        result = await ctrl.run_sensitivity_check(gid, "length", 14.0)

        # All three PF values are the same → delta=0 → not noise
        assert result["is_noise_fit"] is False
        assert result["pf_delta_pct"] == pytest.approx(0.0, abs=0.01)


class TestReport:
    @pytest.mark.asyncio
    async def test_report_writes_to_docs(self, tmp_path: Path):
        """Report should produce a Markdown file at docs/EXPERIMENT_LOG.md."""
        settings = _make_mock_controller("settings", read={"length": 14}, write=None, list_fields=[])
        ctrl = _make_controller(tmp_path, settings=settings)
        gid = await ctrl.start_generation("test report")
        await ctrl.run_iteration(gid, "settings", {"length": 21}, "Test change")

        report_text = ctrl.report()
        assert "Generation" in report_text
        assert gid in report_text
        assert "Experiment Log" in report_text
