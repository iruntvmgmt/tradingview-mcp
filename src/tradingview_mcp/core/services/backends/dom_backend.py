"""
DOM-based backend implementations.

Each backend reads its selectors from the ``detail`` dict provided by
``recon_findings.json`` at construction time — no hardcoded selectors.
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


class DomChartBackend(ChartBackend):
    """Chart control via DOM automation (click symbol search, type, etc.)."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def set_symbol(self, symbol: str) -> None:
        selectors = self.detail.get("selectors", [])
        if not selectors:
            raise ValueError("No symbol_control selectors configured in recon_findings.json")
        await self.dom.click(selectors)
        # Type the new symbol and press Enter
        await self.dom.type_text(selectors, symbol)
        await self.cdp.execute_js(
            """() => {
                const el = document.activeElement;
                if (el) {
                    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter'}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter'}));
                }
            }"""
        )

    async def set_timeframe(self, tf: str) -> None:
        selectors = self.detail.get("selectors", [])
        if not selectors:
            raise ValueError("No timeframe_control selectors configured")
        await self.dom.click(selectors)
        # Try to find and click the specific timeframe button
        tf_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
                  "1h": "60", "2h": "120", "4h": "240",
                  "1D": "D", "1W": "W", "1M": "M"}
        mapped = tf_map.get(tf, tf)
        await self.cdp.execute_js(
            f"""() => {{
                const items = document.querySelectorAll('[data-value="{mapped}"], [class*="item"], button');
                for (const el of items) {{
                    if (el.textContent.trim() === "{mapped}" || el.textContent.trim() === "{tf}") {{
                        el.click();
                        return;
                    }}
                }}
            }}"""
        )

    async def get_ohlcv(self, limit: int = 500) -> list[dict[str, Any]]:
        # DOM-based OHLCV is impractical — we'd need to parse rendered candles.
        # This will be overridden by NetworkChartBackend when network path works.
        raise NotImplementedError(
            "DOM-based OHLCV reading is not feasible. "
            "Run tv_recon_run() to discover a network path."
        )

    async def health_check(self) -> bool:
        selectors = self.detail.get("selectors", [])
        if not selectors:
            return False
        return await self.dom.is_visible(selectors)


class DomIndicatorBackend(IndicatorBackend):
    """Indicator management via DOM automation (Pine Editor, Add to Chart)."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def add(self, pine_code: str, name: str) -> None:
        editor_sel = self.detail.get("editor_selectors", [])
        add_sel = self.detail.get("add_to_chart_selectors", [])

        # Try to open Pine Editor first via keyboard shortcut or menu
        # If editor is not already open, try Cmd+E / Ctrl+E
        editor_open = await self.dom.is_visible(editor_sel)
        if not editor_open:
            # Try opening via keyboard shortcut
            await self.cdp.execute_js(
                """() => {
                    document.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'e', code: 'KeyE', metaKey: true, ctrlKey: true,
                        bubbles: true
                    }));
                }"""
            )
            await self.dom.wait_for_selector(editor_sel, timeout_s=3.0)

        # Paste the Pine code into the editor
        await self.dom.type_text(editor_sel, pine_code, clear_first=True)

        # Click "Add to Chart"
        if add_sel:
            await self.dom.click(add_sel)

    async def remove(self, name: str) -> None:
        # Click on the indicator name in the legend to select it
        await self.cdp.execute_js(
            f"""() => {{
                const indicators = document.querySelectorAll('[class*="legend"], [class*="study"]');
                for (const el of indicators) {{
                    if (el.textContent.includes({name!r})) {{
                        el.click();
                        return;
                    }}
                }}
            }}"""
        )
        # Right-click and select "Remove"
        context_sel = self.detail.get("context_menu_selectors", [])
        if context_sel:
            await self.dom.click(context_sel)

    async def health_check(self) -> bool:
        editor_sel = self.detail.get("editor_selectors", [])
        return await self.dom.is_visible(editor_sel)


class DomBacktestBackend(BacktestBackend):
    """Backtest operations via DOM automation (Strategy Tester tabs/panels)."""

    def __init__(
        self, cdp: CDPConnectionManager, dom: DomUtils, detail: dict[str, Any]
    ) -> None:
        self.cdp = cdp
        self.dom = dom
        self.detail = detail

    async def run(self, strategy_name: str) -> None:
        # Switch to Strategy Tester tab
        bt_sel = self.detail.get("tab_selectors", [])
        if bt_sel:
            await self.dom.click(bt_sel)
        # The backtest runs automatically when a strategy is added to the chart

    async def get_summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        row_sel = self.detail.get("row_selectors", {})
        for key, selectors in row_sel.items():
            try:
                text = await self.dom.extract_text(selectors)
                # Parse numeric value
                text = text.replace(",", "").replace("$", "").replace("%", "")
                try:
                    result[key] = float(text)
                except ValueError:
                    result[key] = text
            except Exception:
                result[key] = None
        return result

    async def get_trade_list(self) -> list[dict[str, Any]]:
        # Click on "Trades" tab first
        try:
            await self.dom.click(['button:has-text("Trades")', '[data-tab="trades"]'])
        except Exception:
            pass
        table_sel = self.detail.get("table_selectors", [])
        row_sel = self.detail.get("row_selectors", [])
        return await self.dom.extract_table(table_sel, row_sel)

    async def get_equity_curve(self) -> list[dict[str, Any]] | None:
        # Equity curve is typically rendered as a canvas — not viable.
        # Return None and let the caller know.
        return None

    async def health_check(self) -> bool:
        bt_sel = self.detail.get("tab_selectors", [])
        return await self.dom.is_visible(bt_sel)
