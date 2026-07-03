"""Chart controller — symbol, timeframe, OHLCV, indicators, screenshot.

Wraps the ChartBackend and IndicatorBackend behind a single controller
interface that MCP tools will call.
"""

from typing import Any

from core.services.backends import build_chart_backend, build_indicator_backend
from core.services.backends.base import ChartBackend, IndicatorBackend
from core.services.dom_utils import DomUtils


class TVChartController:
    """Controls the main chart: symbol, timeframe, indicators, screenshots."""

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._chart: ChartBackend = build_chart_backend(recon, cdp, self._dom, allow_unverified)
        self._indicator: IndicatorBackend = build_indicator_backend(
            recon, cdp, self._dom, allow_unverified
        )

    # ── Symbol ─────────────────────────────────────────────────

    async def set_symbol(self, symbol: str) -> None:
        """Change the chart symbol (e.g. 'AAPL', 'BTCUSD')."""
        await self._chart.set_symbol(symbol)

    async def set_timeframe(self, timeframe: str) -> None:
        """Change the chart timeframe (e.g. '1h', '4h', '1D')."""
        await self._chart.set_timeframe(timeframe)

    # ── OHLCV ──────────────────────────────────────────────────

    async def get_ohlcv(self, limit: int = 500) -> list[dict[str, Any]]:
        """Read OHLCV data from the chart."""
        return await self._chart.get_ohlcv(limit)

    # ── Indicators ─────────────────────────────────────────────

    async def add_indicator(self, pine_code: str, name: str) -> None:
        """Apply a Pine Script indicator to the chart."""
        await self._indicator.apply(pine_code, name)

    async def remove_indicator(self, name: str) -> None:
        """Remove an indicator from the chart by name."""
        await self._indicator.remove(name)

    # ── Screenshot ─────────────────────────────────────────────

    async def screenshot(self) -> bytes:
        """Capture the current chart view via CDP ``Page.captureScreenshot``.

        Sends the CDP command directly through the connection rather than
        via JS injection, since ``chrome.debugger`` is not available in
        the page context.
        """
        result = await self._cdp._send_command("Page.captureScreenshot", {
            "format": "png",
            "fromSurface": True,
        })
        data = result.get("data", "")
        if not data:
            raise RuntimeError("Page.captureScreenshot returned no image data")
        import base64
        return base64.b64decode(data)

    # ── Health ─────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """Health check aggregating chart + indicator backends."""
        return {
            "chart": await self._chart.health_check(),
            "indicator": await self._indicator.health_check(),
        }
