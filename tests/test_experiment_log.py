"""Tests for ExperimentLog — append-only JSONL persistence."""

import json
from pathlib import Path

import pytest

from core.services.experiment_log import ExperimentLog


@pytest.fixture
def tmp_log(tmp_path: Path) -> ExperimentLog:
    """Return an ExperimentLog pointed at a temp file."""
    return ExperimentLog(tmp_path / "experiment_log.jsonl")


class TestExperimentLog:
    """Unit tests for the append-only experiment log."""

    def test_append_event_adds_timestamp_if_missing(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        events = tmp_log.read_generation("g1")
        assert len(events) == 1
        assert "timestamp" in events[0]
        assert events[0]["event"] == "generation_started"

    def test_append_event_preserves_existing_timestamp(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1", "timestamp": "2025-01-01T00:00:00"})
        events = tmp_log.read_generation("g1")
        assert events[0]["timestamp"] == "2025-01-01T00:00:00"

    def test_read_generation_filters_correctly(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 1})
        tmp_log.append_event({"event": "generation_started", "generation_id": "g2"})
        tmp_log.append_event({"event": "iteration", "generation_id": "g2", "iteration_num": 1})

        g1 = tmp_log.read_generation("g1")
        assert len(g1) == 2
        assert all(e["generation_id"] == "g1" for e in g1)

    def test_read_all_generations(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 1})
        tmp_log.append_event({"event": "generation_started", "generation_id": "g2"})

        all_gens = tmp_log.read_all_generations()
        assert set(all_gens.keys()) == {"g1", "g2"}
        assert len(all_gens["g1"]) == 2
        assert len(all_gens["g2"]) == 1

    def test_latest_iteration_returns_none_when_no_iterations(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        assert tmp_log.latest_iteration("g1") is None

    def test_latest_iteration_returns_most_recent(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 1})
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 2})
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 3})

        latest = tmp_log.latest_iteration("g1")
        assert latest is not None
        assert latest["iteration_num"] == 3

    def test_consecutive_validation_passes_all_pass(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        for i in range(3):
            tmp_log.append_event({
                "event": "validation_check",
                "generation_id": "g1",
                "verdict": "pass",
                "at_iteration_num": i + 1,
            })
        assert tmp_log.consecutive_validation_passes("g1") == 3

    def test_consecutive_validation_passes_resets_on_fail(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        tmp_log.append_event({"event": "validation_check", "generation_id": "g1", "verdict": "pass", "at_iteration_num": 1})
        tmp_log.append_event({"event": "validation_check", "generation_id": "g1", "verdict": "pass", "at_iteration_num": 2})
        tmp_log.append_event({"event": "validation_check", "generation_id": "g1", "verdict": "fail", "at_iteration_num": 3})
        tmp_log.append_event({"event": "validation_check", "generation_id": "g1", "verdict": "pass", "at_iteration_num": 4})

        # After pass/pass/fail/pass, consecutive passes counting
        # backwards from most recent: pass at iter 4 is the only
        # consecutive pass before we hit a fail at iter 3.
        assert tmp_log.consecutive_validation_passes("g1") == 1

    def test_consecutive_validation_passes_empty_generation(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        assert tmp_log.consecutive_validation_passes("g1") == 0

    def test_consecutive_validation_passes_ignores_non_validation_events(self, tmp_log: ExperimentLog):
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 1})
        tmp_log.append_event({"event": "validation_check", "generation_id": "g1", "verdict": "pass", "at_iteration_num": 1})
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 2})
        tmp_log.append_event({"event": "validation_check", "generation_id": "g1", "verdict": "pass", "at_iteration_num": 2})

        assert tmp_log.consecutive_validation_passes("g1") == 2

    def test_append_only_no_rewrite(self, tmp_log: ExperimentLog):
        """Confirm there's no method that rewrites or deletes a prior line."""
        # Append-only means we can read, append, and read again —
        # old events persist.
        tmp_log.append_event({"event": "generation_started", "generation_id": "g1"})
        first_read = tmp_log.read_generation("g1")
        tmp_log.append_event({"event": "iteration", "generation_id": "g1", "iteration_num": 1})
        second_read = tmp_log.read_generation("g1")

        assert len(first_read) == 1
        assert len(second_read) == 2
        assert second_read[0]["event"] == "generation_started"  # first event still there

    def test_read_generation_file_not_found_returns_empty(self, tmp_log: ExperimentLog):
        """Reading from a log file that doesn't exist returns empty list."""
        # Don't write anything — just read
        assert tmp_log.read_generation("nonexistent") == []
        assert tmp_log.read_all_generations() == {}
