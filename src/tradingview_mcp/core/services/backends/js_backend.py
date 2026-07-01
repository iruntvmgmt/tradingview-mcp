"""
JS-based backend implementations.

These use ``cdp.execute_js()`` to call internal TradingView JS APIs
directly — the fastest path when it works.  Only functional after
recon confirms the JS globals exist.
"""

from __future__ import annotations

from typing import Any

from tradingview_mcp.core.services.backends.base import (
    ChartBackend,
    IndicatorBackend,
    BacktestBackend,
)
from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager
from tradingview_mcp.core.services.dom_utils import DomUtils


class JsChartBackend(ChartBackend):
    """Chart control via direct JS API calls."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def set_symbol(self, symbol: str) -> None:
        # Try common JS API patterns
        code = f"""
        () => {{
            const apis = [
                () => window.tvWidget?.activeChart()?.setSymbol('{symbol}'),
                () => window.TradingViewApi?.setSymbol('{symbol}'),
                () => {{ throw new Error('no api'); }}
            ];
            for (const fn of apis) {{
                try {{ const r = fn(); if (r !== undefined) return r; }} catch(e) {{}}
            }}
            return false;
        }}
        """
        await self.cdp.execute_js(code)

    async def set_timeframe(self, tf: str) -> None:
        tf_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
                  "1h": "60", "2h": "120", "4h": "240",
                  "1D": "D", "1W": "W", "1M": "M"}
        mapped = tf_map.get(tf, tf)
        code = f"""
        () => {{
            const apis = [
                () => window.tvWidget?.activeChart()?.setResolution('{mapped}'),
                () => window.TradingViewApi?.setResolution('{mapped}'),
                () => {{ throw new Error('no api'); }}
            ];
            for (const fn of apis) {{
                try {{ const r = fn(); if (r !== undefined) return r; }} catch(e) {{}}
            }}
            return false;
        }}
        """
        await self.cdp.execute_js(code)

    async def get_ohlcv(self, limit: int = 500) -> list[dict[str, Any]]:
        code = f"""
        () => {{
            const apis = [
                () => window.tvWidget?.activeChart()?.getPanes()?.[0]?.getDataSource()?.getBars({limit}),
                () => {{ throw new Error('fallthrough'); }}
            ];
            for (const fn of apis) {{
                try {{ const r = fn(); if (r) return r; }} catch(e) {{}}
            }}
            return [];
        }}
        """
        result = await self.cdp.execute_js(code)
        return result or []

    async def health_check(self) -> bool:
        code = """() => typeof window.tvWidget !== 'undefined' || typeof window.TradingViewApi !== 'undefined'"""
        return bool(await self.cdp.execute_js(code))


class JsIndicatorBackend(IndicatorBackend):
    """Indicator management via JS API."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def add(self, pine_code: str, name: str) -> None:
        # Fall back to DOM-based approach since JS API for Pine injection is unlikely
        from tradingview_mcp.core.services.backends.dom_backend import DomIndicatorBackend
        dom_backend = DomIndicatorBackend(self.cdp, self.dom, self.detail)
        await dom_backend.add(pine_code, name)

    async def remove(self, name: str) -> None:
        code = f"""
        () => {{
            const chart = window.tvWidget?.activeChart();
            if (!chart) return false;
            const studies = chart.getAllStudies() || [];
            for (const s of studies) {{
                if (s.name === '{name}') {{
                    chart.removeEntity(s.id);
                    return true;
                }}
            }}
            return false;
        }}
        """
        await self.cdp.execute_js(code)

    async def health_check(self) -> bool:
        return await JsChartBackend(self.cdp, self.dom, {}).health_check()


class JsBacktestBackend(BacktestBackend):
    """Backtest operations via JS API."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def run(self, strategy_name: str) -> None:
        # Backtests auto-run when strategy is added; nothing to do
        pass

    async def get_summary(self) -> dict[str, Any]:
        code = """() => {
            try {
                const chart = window.tvWidget?.activeChart();
                if (!chart) return {};
                const bt = chart.getPineScriptBacktestResults?.();
                if (!bt) return {};
                return {
                    net_profit: bt.netProfit,
                    win_rate: bt.winRate,
                    profit_factor: bt.profitFactor,
                    max_drawdown: bt.maxDrawdown,
                    total_trades: bt.totalTrades,
                };
            } catch(e) {
                return {};
            }
        }"""
        result = await self.cdp.execute_js(code)
        return result or {}

    async def get_trade_list(self) -> list[dict[str, Any]]:
        code = """() => {
            try {
                const chart = window.tvWidget?.activeChart();
                if (!chart) return [];
                const bt = chart.getPineScriptBacktestResults?.();
                if (!bt || !bt.trades) return [];
                return bt.trades;
            } catch(e) {
                return [];
            }
        }"""
        result = await self.cdp.execute_js(code)
        return result or []

    async def get_equity_curve(self) -> list[dict[str, Any]] | None:
        code = """() => {
            try {
                const chart = window.tvWidget?.activeChart();
                if (!chart) return null;
                const bt = chart.getPineScriptBacktestResults?.();
                if (!bt || !bt.equity) return null;
                return bt.equity;
            } catch(e) {
                return null;
            }
        }"""
        result = await self.cdp.execute_js(code)
        return result

    async def health_check(self) -> bool:
        return await JsChartBackend(self.cdp, self.dom, {}).health_check()
