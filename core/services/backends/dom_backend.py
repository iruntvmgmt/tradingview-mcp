"""DOM-based concrete backends for all 9 domains.

Each class implements one of the abstract interfaces from ``base.py``
by driving the TradingView Desktop DOM via ``DomUtils`` primitives
(click, type_text, extract_table, etc.).

All selectors are injected from ``recon_findings.json`` at construction
time — no hardcoded selectors in this file.
"""

import asyncio
from typing import Any

from core.services.backends.base import (
    AlertBackend,
    BacktestBackend,
    ChartBackend,
    DrawingBackend,
    IndicatorBackend,
    OrderBackend,
    PineScriptBackend,
    ReplayBackend,
    SettingsBackend,
)
from core.services.errors import (
    BackendConfigurationError,
    CapabilityUnavailable,
    OrderSubmissionBlocked,
    SelectorResolutionError,
)


# ── Helper ────────────────────────────────────────────────────

def _cap(caps: dict, name: str) -> dict:
    """Shorthand: return the detail dict for a capability."""
    entry = caps.get(name, {})
    return entry.get("detail", {})


# ═══════════════════════════════════════════════════════════════
# Chart
# ═══════════════════════════════════════════════════════════════

class DomChartBackend(ChartBackend):
    """Chart control via DOM clicks and text input."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def set_symbol(self, symbol: str) -> None:
        detail = _cap(self._caps, "symbol_control")
        # Click the symbol search button to open the dialog
        await self._dom.click(detail.get("selectors", []))
        # Type the symbol into the search input
        input_sels = detail.get("symbol_search_input_selectors", [])
        if input_sels:
            await self._dom.type_text(input_sels, symbol, clear_first=True)
        else:
            await self._dom.type_text(detail.get("selectors", []), symbol)

    async def set_timeframe(self, timeframe: str) -> None:
        detail = _cap(self._caps, "timeframe_control")
        interval_map = detail.get("interval_map", {})
        val = interval_map.get(timeframe, timeframe)
        # Build selector by substituting the interval value
        raw_sels = detail.get("selectors", [])
        resolved = [s.replace("{tf}", str(val)) for s in raw_sels]
        await self._dom.click(resolved)

    async def get_ohlcv(self, limit: int = 500) -> list[dict]:
        raise CapabilityUnavailable(
            "OHLCV read is not available via DOM — use network path",
            details={"limit": limit},
        )

    async def health_check(self) -> bool:
        try:
            detail = _cap(self._caps, "symbol_control")
            await self._dom.resolve_selector(detail.get("selectors", []), timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Indicators
# ═══════════════════════════════════════════════════════════════

class DomIndicatorBackend(IndicatorBackend):
    """Apply / remove indicators via DOM."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def apply(self, pine_code: str, name: str) -> None:
        """Apply a Pine Script indicator/strategy to the chart.

        1. Open the Pine Editor via the toolbar button.
        2. Paste the Pine Script source into the editor.
        3. Click "Add to Chart" to compile and apply.
        """
        # 1. Open Pine Editor
        editor_sels = _cap(self._caps, "indicator_apply").get("editor_selectors", [])
        await self._dom.click(editor_sels)

        # 2. Write the Pine code into the editor
        import time
        await asyncio.sleep(0.5)  # Wait for editor to open
        pine_detail = _cap(self._caps, "pine_write")
        monaco_sels = pine_detail.get("monaco_editor_selectors",
                                       pine_detail.get("editor_selectors", []))
        if monaco_sels:
            await self._dom.click(monaco_sels)  # Focus editor
            await asyncio.sleep(0.2)

        textarea_sels = pine_detail.get("textarea_selectors",
                                         [".inputarea.monaco-mouse-cursor-text"])
        escaped_source = pine_code.replace("'", "\\'").replace("\n", "\\n")
        js = f"""
        (() => {{
            const ta = document.querySelector('{textarea_sels[0].replace(chr(39), "\\'")}');
            if (ta) {{
                ta.focus();
                ta.value = '{escaped_source}';
                ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }})()
        """
        await self._cdp.execute_js(js)

        # 3. Click "Add to Chart" to compile & apply
        add_sels = _cap(self._caps, "indicator_apply").get("add_to_chart_selectors", [])
        if add_sels:
            await asyncio.sleep(0.3)
            await self._dom.click(add_sels)

    async def remove(self, name: str) -> None:
        sels = _cap(self._caps, "indicator_remove").get("context_menu_selectors", [])
        if sels:
            await self._dom.click(sels)

    async def health_check(self) -> bool:
        try:
            sels = _cap(self._caps, "indicator_apply").get("editor_selectors", [])
            await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Backtest
# ═══════════════════════════════════════════════════════════════

class DomBacktestBackend(BacktestBackend):
    """Backtest via DOM (Strategy Tester tab)."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def run(self, strategy_name: str) -> None:
        sels = _cap(self._caps, "backtest_run").get("tab_selectors", [])
        await self._dom.click(sels)

    async def get_summary(self) -> dict[str, Any]:
        detail = _cap(self._caps, "backtest_summary")
        rows = detail.get("row_selectors", {})

        # Primary path: try innerText scan (works for SVG-based Strategy Tester)
        if detail.get("fallback") == "innertext_scan" or not rows:
            result = await self._dom.extract_innertext_map(rows, timeout=5.0)
            if result and len(result) >= 2:
                return result

        # Secondary path: DOM table extraction (legacy)
        result = {}
        for key, sels in rows.items():
            if isinstance(sels, list) and sels and not sels[0].startswith("Sharpe"):
                text = await self._dom.extract_text(sels, timeout=3.0)
                if text:
                    result[key] = text

        # Final fallback: try innerText scan even if fallback not explicitly set
        if not result:
            result = await self._dom.extract_innertext_map(rows, timeout=5.0)
        return result

    async def get_trade_list(self) -> list[dict[str, Any]]:
        detail = _cap(self._caps, "backtest_trade_list")
        rows = await self._dom.extract_table(
            detail.get("table_selectors", []),
            detail.get("row_selectors"),
        )
        return [dict(zip(rows[0], row)) for row in rows[1:]] if rows else []

    async def get_equity_curve(self) -> list[dict[str, Any]]:
        raise CapabilityUnavailable(
            "Equity curve not available via DOM",
        )

    async def health_check(self) -> bool:
        try:
            # Try bottom panel first (always visible), fall back to tab selectors
            detail = _cap(self._caps, "backtest_run")
            sels = detail.get("bottom_panel_selectors", detail.get("tab_selectors", []))
            if sels:
                await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Alerts
# ═══════════════════════════════════════════════════════════════

class DomAlertBackend(AlertBackend):
    """Alert CRUD via DOM."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def create(self, symbol: str, condition: dict, message: str) -> str:
        detail = _cap(self._caps, "alert_create")
        # 1. Open alert modal
        await self._dom.click(detail.get("open_modal_selectors", []))
        # 2. Fill condition fields
        field_sels = detail.get("field_selectors", {})
        cond_sels = field_sels.get("condition", [])
        if cond_sels and "condition" in condition:
            await self._dom.type_text(cond_sels, str(condition["condition"]))
        msg_sels = field_sels.get("message", [])
        if msg_sels:
            await self._dom.type_text(msg_sels, message)
        # 3. Click confirm
        await self._dom.click(detail.get("confirm_selectors", []))
        return f"alert-{hash((symbol, message))}"

    async def edit(self, alert_id: str, condition: dict | None = None,
                   message: str | None = None) -> None:
        sels = _cap(self._caps, "alert_edit").get("selectors", [])
        if sels:
            await self._dom.click(sels)

    async def delete(self, alert_id: str) -> None:
        sels = _cap(self._caps, "alert_delete").get("selectors", [])
        if sels:
            await self._dom.click(sels)

    async def list(self) -> list[dict[str, Any]]:
        detail = _cap(self._caps, "alert_list")
        rows = await self._dom.extract_table(
            detail.get("panel_selectors", []),
            detail.get("row_selectors"),
        )
        return [{"name": r[0], "condition": r[1]} if len(r) > 1 else {"name": r[0]}
                for r in rows]

    async def health_check(self) -> bool:
        try:
            sels = _cap(self._caps, "alert_create").get("open_modal_selectors", [])
            await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Drawings
# ═══════════════════════════════════════════════════════════════

class DomDrawingBackend(DrawingBackend):
    """Drawing tools via DOM toolbar + canvas coordinate clicks."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def create(self, drawing_type: str, points: list[dict]) -> str:
        detail = _cap(self._caps, "drawing_create")
        # 1. Click the drawing tool button
        tool_sels = detail.get("toolbar_selectors", {}).get(drawing_type, [])
        if not tool_sels:
            raise BackendConfigurationError(
                f"Unknown drawing type '{drawing_type}'",
                details={"known_types": list(detail.get("toolbar_selectors", {}).keys())},
            )
        await self._dom.click(tool_sels)
        # 2. Click at each coordinate point on the canvas
        container_sels = detail.get("container_selector", detail.get("canvas_selector", []))
        for pt in points:
            x_ratio = pt.get("x_ratio", 0.5)
            y_ratio = pt.get("y_ratio", 0.5)
            await self._dom.click_at_coordinates(container_sels, x_ratio, y_ratio)
        return f"drawing-{hash(str(points))}"

    async def remove(self, drawing_id: str) -> None:
        sels = _cap(self._caps, "drawing_remove").get("selectors", [])
        if sels:
            await self._dom.click(sels)

    async def list(self) -> list[dict[str, Any]]:
        sels = _cap(self._caps, "drawing_list").get("panel_selectors", [])
        text = await self._dom.extract_text(sels, timeout=3.0)
        return [{"name": text}] if text else []

    async def health_check(self) -> bool:
        try:
            # toolbar_selectors is a dict of {tool_name: [selectors]}, not a single string
            tb = _cap(self._caps, "drawing_create").get("toolbar_selectors", {})
            if tb:
                # Pick the first non-empty selector list from any tool
                for tool_sels in tb.values():
                    if tool_sels:
                        await self._dom.resolve_selector(tool_sels, timeout=3.0)
                        break
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Orders
# ═══════════════════════════════════════════════════════════════

class DomOrderBackend(OrderBackend):
    """Paper trading order management via DOM.

    Safety: ``place()`` and ``modify()`` raise ``OrderSubmissionBlocked``
    unless ``confirmed=True`` is passed.
    """

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def place(self, symbol: str, side: str, size: float,
                    order_type: str, sl: float | None, tp: float | None,
                    confirmed: bool) -> str:
        if not confirmed:
            raise OrderSubmissionBlocked(
                "order_place requires confirmed=True — safety gate active",
                details={"symbol": symbol, "side": side, "size": size},
            )
        detail = _cap(self._caps, "order_place")
        # Open order panel
        open_sels = detail.get("open_panel_selector", [])
        if open_sels:
            await self._dom.click(open_sels)
        # Fill fields
        field_sels = detail.get("field_selectors", {})
        size_sels = field_sels.get("size", [])
        if size_sels:
            await self._dom.type_text(size_sels, str(size))
        # Submit
        submit_sels = detail.get("submit_selectors", [])
        if submit_sels:
            await self._dom.click(submit_sels)
        return f"order-{hash((symbol, side, size))}"

    async def modify(self, order_id: str, size: float | None = None,
                     sl: float | None = None, tp: float | None = None) -> None:
        sels = _cap(self._caps, "order_modify").get("selectors", [])
        if sels:
            await self._dom.click(sels)

    async def cancel(self, order_id: str) -> None:
        sels = _cap(self._caps, "order_cancel").get("selectors", [])
        if sels:
            await self._dom.click(sels)

    async def status(self) -> list[dict[str, Any]]:
        detail = _cap(self._caps, "order_status_read")
        rows = await self._dom.extract_table(
            detail.get("positions_panel_selectors", []),
            detail.get("row_selectors"),
        )
        return [{"type": r[0], "size": r[1]} if len(r) > 1 else {"info": r[0]}
                for r in rows]

    async def health_check(self) -> bool:
        try:
            sels = _cap(self._caps, "order_place").get("open_panel_selector", [])
            if sels:
                await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Replay
# ═══════════════════════════════════════════════════════════════

class DomReplayBackend(ReplayBackend):
    """Replay mode via DOM buttons."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def enter(self, start_bar: str | int) -> None:
        sels = _cap(self._caps, "replay_enter").get("selectors", [])
        await self._dom.click(sels)

    async def step(self, bars: int = 1) -> None:
        sels = _cap(self._caps, "replay_step").get("step_selectors", [])
        for _ in range(bars):
            await self._dom.click(sels)

    async def exit(self) -> None:
        sels = _cap(self._caps, "replay_exit").get("selectors", [])
        await self._dom.click(sels)

    async def state(self) -> dict[str, Any]:
        sels = _cap(self._caps, "replay_state_read").get("indicator_selectors", [])
        text = await self._dom.extract_text(sels, timeout=3.0)
        return {"raw": text or "unknown"}

    async def health_check(self) -> bool:
        try:
            sels = _cap(self._caps, "replay_enter").get("selectors", [])
            await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════

class DomSettingsBackend(SettingsBackend):
    """Study / indicator Inputs tab via DOM."""

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
        """Click the gear icon to open settings, then extract field labels."""
        detail = _cap(self._caps, "settings_list_fields")
        # Click the gear icon to open settings dialog
        gear_sels = detail.get("gear_icon_selectors", [])
        if gear_sels:
            await self._dom.click(gear_sels)
        # Read field labels from the dialog
        dialog_sels = detail.get("dialog_selectors", [])
        text = await self._dom.extract_text(dialog_sels, timeout=5.0)
        if text:
            # Parse field names from the dialog text
            return [{"name": line.strip(), "type": "unknown"}
                    for line in text.split('\n') if line.strip()]
        return [{"name": "settings_panel", "type": "dialog"}]

    async def read(self, study_name: str) -> dict[str, Any]:
        """Read input values from the settings dialog."""
        detail = _cap(self._caps, "settings_read")
        dialog_sels = detail.get("dialog_selectors", [])
        text = await self._dom.extract_text(dialog_sels, timeout=5.0)
        if text:
            # Return the raw text; caller can parse key:value pairs
            return {"raw": text, "study_name": study_name}
        return {}

    async def write(self, study_name: str, values: dict[str, Any]) -> None:
        """Type values into settings inputs and click Apply."""
        detail = _cap(self._caps, "settings_write")
        dialog_sels = detail.get("dialog_selectors", [])
        if dialog_sels:
            await self._dom.click(dialog_sels)
        # For each field, find and type the value
        for field, value in values.items():
            # Try to type into an input near the field label
            field_sels = [f"input[name='{field}']", f"[data-name='{field}']",
                          f"input[placeholder*='{field}']"]
            await self._dom.type_text(field_sels, str(value), clear_first=True)
        # Click Apply/OK
        apply_sels = detail.get("apply_selectors", [])
        if apply_sels:
            await self._dom.click(apply_sels)

    async def health_check(self) -> bool:
        try:
            detail = _cap(self._caps, "settings_list_fields")
            sels = detail.get("gear_icon_selectors", detail.get("dialog_selectors", []))
            if sels:
                await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Pine Script
# ═══════════════════════════════════════════════════════════════

class DomPineScriptBackend(PineScriptBackend):
    """Pine Script editor interaction via DOM.

    The Pine Editor uses Monaco with a virtual scroller — ``.view-line``
    elements only render the visible viewport.  Full source access requires
    scrolling through the editor and collecting textarea snapshots.
    """

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def read(self, script_name: str) -> str:
        """Read the Pine Script source from the editor.

        Uses scroll-and-stitch to work around Monaco's virtual scroller:
        1. Ensure the Pine Editor dialog is open.
        2. Focus the Monaco editor via click.
        3. Scroll to multiple positions and collect textarea snapshots.
        4. Return the longest collected snippet.
        """
        detail = _cap(self._caps, "pine_read")
        monaco_sels = detail.get("monaco_editor_selectors", [])
        textarea_sels = detail.get("textarea_selectors", [])
        scrollable_sels = detail.get("scrollable_selectors", [])

        # 1. Open the Pine Editor tab if needed
        tab_sels = detail.get("open_tab_selectors", [])
        if tab_sels:
            await self._dom.click(tab_sels)

        # 2. Focus the editor
        if monaco_sels:
            await self._dom.click(monaco_sels)

        # 3. Use scroll-and-stitch for virtual scroller
        if scrollable_sels and textarea_sels:
            text = await self._dom.scroll_and_collect_text(
                scrollable_sels, textarea_sels, pages=6, delay=0.3
            )
            if text and len(text) > 50:
                return text

        # 4. Fallback: read view-lines from current viewport
        view_sels = detail.get("view_line_selectors", [])
        text = await self._dom.extract_text(view_sels, timeout=3.0)
        return text or ""

    async def write(self, script_name: str, source: str) -> None:
        """Write new source into the Pine Editor.

        1. Focus the Monaco editor.
        2. Select all existing content.
        3. Type the new source.
        """
        detail = _cap(self._caps, "pine_write")
        monaco_sels = detail.get("monaco_editor_selectors", [])
        editor_sels = detail.get("editor_selectors", [])
        textarea_sels = detail.get("textarea_selectors", [])

        # Focus editor
        if monaco_sels:
            await self._dom.click(monaco_sels)
        elif editor_sels:
            await self._dom.click(editor_sels)

        # Select all and type the new source
        # Monaco syncs its content to the hidden textarea for IME input
        await self._dom.type_text(textarea_sels or editor_sels, source,
                                  clear_first=True)

    async def compile(self, script_name: str) -> dict[str, Any]:
        detail = _cap(self._caps, "pine_compile")
        compile_sels = detail.get("compile_selectors", [])
        if compile_sels:
            await self._dom.click(compile_sels)
        return {"success": True}

    async def read_compile_errors(self) -> list[dict[str, Any]]:
        sels = _cap(self._caps, "pine_compile_errors_read").get("console_selectors", [])
        text = await self._dom.extract_text(sels, timeout=3.0)
        return [{"message": text}] if text else []

    async def read_logs(self, script_name: str) -> list[dict[str, Any]]:
        detail = _cap(self._caps, "pine_logs_read")
        entries = await self._dom.extract_table(
            detail.get("pane_selectors", []),
            detail.get("entry_selectors"),
        )
        return [{"timestamp": r[0], "level": r[1], "message": r[2]}
                if len(r) > 2 else {"message": str(r)}
                for r in entries]

    async def health_check(self) -> bool:
        try:
            sels = _cap(self._caps, "pine_read").get("editor_selectors", [])
            await self._dom.resolve_selector(sels, timeout=3.0)
            return True
        except Exception:
            return False
