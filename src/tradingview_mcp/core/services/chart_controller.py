"""
TVChartController — orchestrates chart-level operations via backend delegation.

The controller never branches on ``path`` — that decision was made once by
the factory functions at construction time.
"""

from __future__ import annotations

from typing import Any

from tradingview_mcp.core.services.backends import (
    build_chart_backend,
    build_indicator_backend,
)
from tradingview_mcp.core.services.backends.base import (
    ChartBackend,
    IndicatorBackend,
)
from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager
from tradingview_mcp.core.services.dom_utils import DomUtils


class TVChartController:
    """High-level chart control API.

    Usage::

        ctrl = TVChartController(cdp, recon)
        await ctrl.set_symbol("XAUUSD")
        await ctrl.set_timeframe("1h")
        await ctrl.add_indicator(pine_code, "My Strategy")
        ohlcv = await ctrl.get_ohlcv(limit=100)
        png = await ctrl.screenshot()
    """

    def __init__(
        self,
        cdp: CDPConnectionManager,
        recon: dict[str, Any],
        allow_unverified: bool = False,
    ) -> None:
        dom = DomUtils(cdp)
        self.cdp = cdp
        self._symbol_backend: ChartBackend = build_chart_backend(
            "symbol_control", recon, cdp, dom, allow_unverified
        )
        self._timeframe_backend: ChartBackend = build_chart_backend(
            "timeframe_control", recon, cdp, dom, allow_unverified
        )
        self._ohlcv_backend: ChartBackend = build_chart_backend(
            "ohlcv_read", recon, cdp, dom, allow_unverified
        )
        self._indicator_backend: IndicatorBackend = build_indicator_backend(
            recon, cdp, dom, allow_unverified
        )

    async def set_symbol(self, symbol: str) -> None:
        """Change the active chart symbol (e.g. ``XAUUSD``, ``BTCUSDT``)."""
        await self._symbol_backend.set_symbol(symbol)

    async def set_timeframe(self, tf: str) -> None:
        """Change the chart timeframe (e.g. ``1m``, ``5m``, ``1h``, ``1D``)."""
        await self._timeframe_backend.set_timeframe(tf)

    async def add_indicator(self, pine_code: str, name: str) -> None:
        """Add a Pine Script indicator/strategy to the chart.

        Delegates to the indicator backend, which for the DOM path
        reuses existing Pine editor open/paste/Add-to-Chart automation.
        """
        await self._indicator_backend.add(pine_code, name)

    async def remove_indicator(self, name: str) -> None:
        """Remove an indicator/strategy from the chart by name."""
        await self._indicator_backend.remove(name)

    async def get_ohlcv(self, limit: int = 500) -> list[dict[str, Any]]:
        """Read OHLCV data from the active chart."""
        return await self._ohlcv_backend.get_ohlcv(limit)

    async def screenshot(self) -> bytes:
        """Capture the current chart as a PNG via CDP ``Page.captureScreenshot``."""
        page = await self.cdp._ensure_page()
        return await page.screenshot(type="png")

    async def health_check(self) -> dict[str, bool]:
        """Check that all backends' selectors/JS paths still resolve."""
        return {
            "symbol_control": await self._symbol_backend.health_check(),
            "timeframe_control": await self._timeframe_backend.health_check(),
            "ohlcv_read": await self._ohlcv_backend.health_check(),
            "indicator_apply": await self._indicator_backend.health_check(),
        }
