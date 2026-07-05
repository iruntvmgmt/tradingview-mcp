"""ExperimentLog — append-only JSONL persistence for experiment events.

Every event is written as one JSON line.  The file is never rewritten in
place and events are never deleted — this file IS the audit trail.

Only this module touches ``logs/experiment_log.jsonl`` directly.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExperimentLog:
    """Append-only JSONL log for experiment events.

    Usage::

        log = ExperimentLog(Path("logs/experiment_log.jsonl"))
        log.append_event({"event": "generation_started", ...})
        gen = log.read_generation("gen-001")
        passes = log.consecutive_validation_passes("gen-001")
    """

    def __init__(self, file_path: Path):
        self._path = file_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Write ─────────────────────────────────────────────────

    def append_event(self, event: dict[str, Any]) -> None:
        """Append a single event as one JSON line.

        If *event* does not already contain a ``timestamp`` key, one is
        added (ISO-8601 UTC).
        """
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self._path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    # ── Read ──────────────────────────────────────────────────

    def _all_events(self) -> list[dict[str, Any]]:
        """Read every event from the log file.

        Returns an empty list if the file does not exist (no events yet).
        Malformed lines are silently skipped so partial writes don't
        break downstream reads.
        """
        if not self._path.exists():
            return []
        events: list[dict[str, Any]] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def read_generation(self, generation_id: str) -> list[dict[str, Any]]:
        """Return all events for a single generation, in append order."""
        return [
            e
            for e in self._all_events()
            if e.get("generation_id") == generation_id
        ]

    def read_all_generations(self) -> dict[str, list[dict[str, Any]]]:
        """Return ``{generation_id: [events...]}`` for every generation."""
        result: dict[str, list[dict[str, Any]]] = {}
        for e in self._all_events():
            gid = e.get("generation_id")
            if gid:
                result.setdefault(gid, []).append(e)
        return result

    def latest_iteration(self, generation_id: str) -> dict[str, Any] | None:
        """Return the most recent ``iteration`` event for *generation_id*,
        or ``None`` if no iteration has been recorded yet.
        """
        iterations = [
            e
            for e in self._all_events()
            if e.get("event") == "iteration"
            and e.get("generation_id") == generation_id
        ]
        return iterations[-1] if iterations else None

    def consecutive_validation_passes(self, generation_id: str) -> int:
        """Count consecutive ``validation_check`` events with
        ``verdict == "pass"`` starting from the most recent and moving
        backwards until a ``"fail"`` (or start of generation) is hit.
        """
        events = self.read_generation(generation_id)
        count = 0
        for e in reversed(events):
            if e.get("event") != "validation_check":
                continue
            if e.get("verdict") == "pass":
                count += 1
            else:
                break  # hit a fail — stop counting backwards
        return count
