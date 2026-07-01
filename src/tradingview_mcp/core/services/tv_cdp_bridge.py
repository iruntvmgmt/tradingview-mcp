"""
Direct CDP bridge to TradingView Desktop — works without the MCP server restart.

Connects via raw WebSocket to the CDP endpoint and executes JS commands
directly on the chart page. All methods return structured Python dicts.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any

import websockets


# Current chart page ID (changes on each TV Desktop restart)
CHART_PAGE_IDS: dict[str, str] = {}


def _get_chart_page_id(pages: list[dict]) -> str | None:
    """Find the chart page from a CDP /json target list."""
    for p in pages:
        url = p.get("url", "")
        if "tradingview.com/chart" in url:
            return p["id"]
    return None


async def fetch_page_ids() -> list[dict]:
    """Fetch current CDP page list from the HTTP endpoint."""
    import urllib.request
    req = urllib.request.urlopen("http://127.0.0.1:8315/json", timeout=5)
    return json.loads(req.read().decode())


async def get_chart_page_id() -> str:
    """Get or refresh the chart page ID."""
    global CHART_PAGE_IDS
    pages = await fetch_page_ids()
    pid = _get_chart_page_id(pages)
    if not pid:
        raise ConnectionError("No chart page found. Is TradingView Desktop open?")
    CHART_PAGE_IDS["chart"] = pid
    return pid


class TVCDPBridge:
    """Direct CDP WebSocket bridge to the TradingView chart page.

    Usage::

        tv = TVCDPBridge()
        await tv.connect()
        info = await tv.get_chart_info()
        await tv.screenshot("chart.png")
        await tv.disconnect()
    """

    def __init__(self) -> None:
        self._ws: Any = None
        self._msg_id: int = 0

    async def connect(self) -> None:
        """Connect to the chart page via CDP WebSocket."""
        pid = await get_chart_page_id()
        ws_url = f"ws://127.0.0.1:8315/devtools/page/{pid}"
        self._ws = await websockets.connect(ws_url, max_size=2**24, ping_interval=None)
        # Enable Runtime domain
        await self._send("Runtime.enable")
        # Consume the executionContextCreated event
        await self._recv()

    async def _send(self, method: str, params: dict | None = None) -> int:
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        return self._msg_id

    async def _recv(self) -> dict:
        return json.loads(await self._ws.recv())

    async def _wait_response(self, expected_id: int) -> dict:
        while True:
            msg = await self._recv()
            if msg.get("id") == expected_id:
                return msg

    async def eval(self, js: str) -> Any:
        """Execute JavaScript on the chart page and return the result value."""
        mid = await self._send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
        })
        resp = await self._wait_response(mid)
        if "exceptionDetails" in resp.get("result", {}):
            exc = resp["result"]["exceptionDetails"]
            raise RuntimeError(f"JS error: {exc.get('text', '')} — {exc.get('exception', {}).get('description', '')}")
        result = resp.get("result", {}).get("result", {})
        return result.get("value")

    async def get_chart_info(self) -> dict[str, Any]:
        """Get chart symbol, timeframe, and active indicators."""
        info = await self.eval("""
        (() => {
            const text = document.body ? document.body.innerText || '' : '';
            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
            
            // Extract symbol (usually first non-empty meaningful line)
            const symbol = lines.find(l => /^[A-Z]{2,6}\/?[A-Z]{0,6}$/.test(l) && l !== 'SELL' && l !== 'BUY') || '?';
            
            // Find timeframes in the line list
            const timeframes = lines.filter(l => /^(1m|5m|15m|30m|1h|2h|4h|1D|1W|1M)$/.test(l));
            
            // Find indicator names
            const known = ['LuxAlgo','SMC','Strategy','Engine','Strategy Engine',
                'Trendlines','Breaks','Sessions','PatternForge','SOLO LEVELING',
                'SQZ','PVTG','TEIR','GT_VP','MS-ZZ','BO-V2','IRUNTV'];
            const indicators = lines.filter(l =>
                known.some(k => l.includes(k)) && l.length < 60
            );
            
            // Get the Pine Editor content snippet if visible
            const pineText = [...document.querySelectorAll('[class*=\"monaco\"], [class*=\"view-line\"]')]
                .map(el => el.textContent || '').filter(Boolean).slice(0, 5);
            
            return {
                symbol: symbol,
                timeframes: [...new Set(timeframes)],
                indicators: [...new Set(indicators)],
                pine_editor_lines: pineText.slice(0, 3),
                url: window.location.href,
            };
        })()
        """)
        return info or {}

    async def get_backtest_results(self) -> dict[str, Any]:
        """Try to extract backtest results from the Strategy Tester panel."""
        result = await self.eval("""
        (() => {
            const text = document.body ? document.body.innerText || '' : '';
            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
            
            // Find numeric values near known labels
            const extract = (label) => {
                const idx = lines.findIndex(l => l.includes(label));
                if (idx >= 0 && idx + 1 < lines.length) return lines[idx + 1];
                return null;
            };
            
            return {
                net_profit: extract('Net Profit'),
                win_rate: extract('Win Rate'),
                profit_factor: extract('Profit Factor'),
                max_drawdown: extract('Max Drawdown'),
                total_trades: extract('Total Trades'),
                all_lines_snippet: lines.slice(0, 100),
            };
        })()
        """)
        return result or {}

    async def get_strategy_tester_text(self) -> list[str]:
        """Get raw text from the Strategy Tester panel."""
        result = await self.eval("""
        (() => {
            const panels = document.querySelectorAll(
                '[class*=\"strategy-tester\"], [class*=\"backtest\"], [class*=\"tester\"]'
            );
            const texts = [];
            panels.forEach(p => {
                const t = p.innerText || p.textContent || '';
                if (t.trim()) texts.push(t.trim());
            });
            return texts;
        })()
        """)
        return result or []

    async def screenshot(self, path: str = "/tmp/tv_chart.png") -> str:
        """Take a screenshot of the chart page and save to path."""
        mid = await self._send("Page.captureScreenshot", {"format": "png"})
        resp = await self._wait_response(mid)
        data = resp.get("result", {}).get("data", "")
        if data:
            png = base64.b64decode(data)
            with open(path, "wb") as f:
                f.write(png)
            return f"Saved {len(png)} bytes to {path}"
        return "Screenshot failed"

    async def eval_and_screenshot(self, js: str, screenshot_path: str = "/tmp/tv_chart.png") -> dict:
        """Execute JS and then take a screenshot. Returns both."""
        result = await self.eval(js)
        ss = await self.screenshot(screenshot_path)
        return {"result": result, "screenshot": ss}

    async def disconnect(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None


async def quick_look() -> dict[str, Any]:
    """Quick one-shot: connect, get chart info + screenshot, disconnect."""
    tv = TVCDPBridge()
    try:
        await tv.connect()
        info = await tv.get_chart_info()
        ss = await tv.screenshot()
        info["screenshot"] = ss
        return info
    finally:
        await tv.disconnect()
