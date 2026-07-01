"""
Network-based backend implementations.

Intercept XHR/WebSocket frames via the CDP Network domain to read
streaming data (e.g. OHLCV).  Only functional after recon confirms
the network message shapes.
"""

from __future__ import annotations

from typing import Any

from tradingview_mcp.core.services.backends.base import ChartBackend
from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager
from tradingview_mcp.core.services.dom_utils import DomUtils


class NetworkChartBackend(ChartBackend):
    """Read OHLCV by intercepting WebSocket frames containing candle data."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def set_symbol(self, symbol: str) -> None:
        # Symbol changes must be done via DOM or JS — network can't initiate
        from tradingview_mcp.core.services.backends.dom_backend import DomChartBackend
        dom_backend = DomChartBackend(self.cdp, self.dom, self.detail)
        await dom_backend.set_symbol(symbol)

    async def set_timeframe(self, tf: str) -> None:
        from tradingview_mcp.core.services.backends.dom_backend import DomChartBackend
        dom_backend = DomChartBackend(self.cdp, self.dom, self.detail)
        await dom_backend.set_timeframe(tf)

    async def get_ohlcv(self, limit: int = 500) -> list[dict[str, Any]]:
        # Network-based OHLCV capture requires recon to identify WS message shape.
        # Until then, this raises NotImplementedError.
        raise NotImplementedError(
            "Network-based OHLCV reading requires running tv_recon_run() "
            "first to identify WebSocket message shapes."
        )

    async def health_check(self) -> bool:
        # Network health check: can we reach the CDP browser at all?
        try:
            await self.cdp.execute_js("1+1")
            return True
        except Exception:
            return False
