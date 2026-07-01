"""Replay controller — Replay mode lifecycle with state guards.

Wraps the ReplayBackend with an ``_in_replay`` state flag that prevents
invalid transitions (step/exit before enter, enter while already in replay).
"""

from typing import Any

from core.services.backends import build_replay_backend
from core.services.backends.base import ReplayBackend
from core.services.dom_utils import DomUtils
from core.services.errors import ReplayStateError


class TVReplayController:
    """Controls TradingView's Replay mode.

    State machine:
        idle → enter() → in_replay → step()/state() → exit() → idle
    """

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: ReplayBackend = build_replay_backend(
            recon, cdp, self._dom, allow_unverified
        )
        self._in_replay = False

    async def enter(self, start_bar: str | int) -> None:
        """Enter Replay mode starting at *start_bar*.

        Raises ``ReplayStateError`` if already in replay mode.
        """
        if self._in_replay:
            raise ReplayStateError(
                "Already in replay mode — call exit() first.",
                details={"start_bar": start_bar},
            )
        await self._backend.enter(start_bar)
        self._in_replay = True

    async def step(self, bars: int = 1) -> None:
        """Advance replay by N bars.

        Raises ``ReplayStateError`` if not in replay mode.
        """
        if not self._in_replay:
            raise ReplayStateError(
                "Not in replay mode — call enter() first.",
                details={"bars": bars},
            )
        await self._backend.step(bars)

    async def exit(self) -> None:
        """Exit Replay mode and return to live chart.

        Raises ``ReplayStateError`` if not in replay mode.
        """
        if not self._in_replay:
            raise ReplayStateError(
                "Not in replay mode — nothing to exit.",
            )
        await self._backend.exit()
        self._in_replay = False

    async def state(self) -> dict[str, Any]:
        """Read the current replay position and playing state."""
        return await self._backend.state()

    async def health_check(self) -> dict[str, Any]:
        return {"replay": await self._backend.health_check()}
