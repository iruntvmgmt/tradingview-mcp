"""
TVBacktestController — orchestrates backtest operations via backend delegation.

Single backend covers all four backtest capabilities (run, summary, trade list,
equity curve) since they all live in the same Strategy Tester panel.
"""

from __future__ import annotations

import asyncio
from typing import Any

from tradingview_mcp.core.services.backends import build_backtest_backend
from tradingview_mcp.core.services.backends.base import BacktestBackend
from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager
from tradingview_mcp.core.services.dom_utils import DomUtils
from tradingview_mcp.core.services.errors import BacktestTimeout


class TVBacktestController:
    """High-level backtest API.

    Usage::

        bt = TVBacktestController(cdp, recon)
        await bt.run_strategy("My Strategy")
        await bt.wait_for_complete()
        summary = await bt.get_performance_summary()
        trades = await bt.get_trade_list()
    """

    def __init__(
        self,
        cdp: CDPConnectionManager,
        recon: dict[str, Any],
        allow_unverified: bool = False,
    ) -> None:
        dom = DomUtils(cdp)
        self._backend: BacktestBackend = build_backtest_backend(
            recon, cdp, dom, allow_unverified
        )
        self.dom = dom

    async def run_strategy(self, name: str) -> None:
        """Trigger the Strategy Tester for an applied strategy."""
        await self._backend.run(name)

    async def wait_for_complete(
        self, timeout_s: float = 60.0
    ) -> None:
        """Poll DOM for loading indicator gone / results panel populated.

        Raises ``BacktestTimeout`` if the backtest does not complete within
        ``timeout_s`` seconds.
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                # Check if the backtest results are visible
                # (no loading spinner, overview tab has data)
                has_results = await self.dom.wait_until(
                    "document.querySelector('[class*=\"strategy-tester\"]') !== null"
                    " && document.querySelector('.loading-spinner, [class*=\"loading\"]') === null",
                    timeout_s=2.0,
                )
                if has_results:
                    # Try reading summary to confirm data is populated
                    summary = await self._backend.get_summary()
                    if summary and any(v is not None for v in summary.values()):
                        return
            except Exception:
                pass
            await asyncio.sleep(1.0)

        raise BacktestTimeout(
            f"Backtest did not complete within {timeout_s}s"
        )

    async def get_performance_summary(self) -> dict[str, Any]:
        """Get Overview tab metrics (net profit, win rate, profit factor, etc.)."""
        return await self._backend.get_summary()

    async def get_trade_list(self) -> list[dict[str, Any]]:
        """Get the full trade log from the Trades List tab."""
        return await self._backend.get_trade_list()

    async def get_equity_curve(self) -> list[dict[str, Any]] | None:
        """Get equity curve data points.

        Returns ``None`` if the equity curve is rendered as a canvas
        (the common case) rather than a numeric table.
        """
        return await self._backend.get_equity_curve()

    async def health_check(self) -> bool:
        """Check that the Strategy Tester panel is accessible."""
        return await self._backend.health_check()
