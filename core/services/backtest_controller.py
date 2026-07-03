"""Backtest controller — run strategies, read results, poll for completion.

Wraps the BacktestBackend with polling logic for ``wait_for_complete()``
and aggregates health checks.
"""

import asyncio
from typing import Any

from core.services.backends import build_backtest_backend
from core.services.backends.base import BacktestBackend
from core.services.dom_utils import DomUtils

# Default polling interval and timeout
POLL_INTERVAL_SEC = 1.0
DEFAULT_TIMEOUT_SEC = 120.0


class TVBacktestController:
    """Controls the Strategy Tester: run, read results, poll."""

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: BacktestBackend = build_backtest_backend(
            recon, cdp, self._dom, allow_unverified
        )

    async def run_strategy(self, name: str) -> None:
        """Trigger a backtest run for the given strategy name."""
        await self._backend.run(name)

    async def wait_for_complete(self, timeout: float = DEFAULT_TIMEOUT_SEC) -> bool:
        """Poll until the backtest finishes or *timeout* expires.

        Returns ``True`` if the backtest completed, ``False`` if timed out.
        Uses the backend's ``health_check()`` as a proxy for completion
        (the Strategy Tester panel changes state when the run finishes).
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            ok = await self._backend.health_check()
            if ok:
                return True
            await asyncio.sleep(POLL_INTERVAL_SEC)
        return False

    async def get_performance_summary(self) -> dict[str, Any]:
        """Read the backtest performance summary (net profit, win rate, etc.)."""
        return await self._backend.get_summary()

    async def get_trade_list(self) -> list[dict[str, Any]]:
        """Read the list of individual trades from the completed backtest."""
        return await self._backend.get_trade_list()

    async def get_equity_curve(self) -> list[dict[str, Any]]:
        """Read the equity curve data points."""
        return await self._backend.get_equity_curve()

    async def health_check(self) -> dict[str, Any]:
        """Health check for the backtest domain."""
        return {
            "backtest": await self._backend.health_check(),
        }
