"""DOM-based concrete backends for all 9 domains.

Each class implements one of the abstract interfaces from ``base.py``
by driving the TradingView Desktop DOM via ``DomUtils`` primitives
(click, type_text, extract_table, etc.).

All selectors are injected from ``recon_findings.json`` at construction
time — no hardcoded selectors in this file.
"""

import asyncio
import json
import logging
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

logger = logging.getLogger(__name__)


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

    async def set_visible_range(self, start: str, end: str) -> None:
        """Set the chart visible range via TradingView chart API.

        Converts ISO date strings to Unix timestamps (seconds) and calls
        ``chartWidget.setVisibleRange()`` through CDP.
        """
        from datetime import datetime, timezone

        def _to_timestamp(date_str: str) -> int:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return int(dt.timestamp())

        start_ts = _to_timestamp(start)
        end_ts = _to_timestamp(end)

        js = f"""
        (() => {{
            const iframe = document.querySelector('iframe');
            const win = iframe ? iframe.contentWindow : window;
            const widget = win.TradingView || win.tvWidget || win.widget;
            if (!widget) return 'no_widget';
            const chart = widget.chart ? widget.chart() : (widget.activeChart ? widget.activeChart() : null);
            if (!chart) return 'no_chart';
            chart.setVisibleRange({{ from: {start_ts}, to: {end_ts} }}, {{ applyDefaultRightMargin: false }});
            return 'ok';
        }})()
        """
        result = await self._cdp.execute_js(js, await_promise=True)
        value = result.get("result", {}).get("value", "")
        if value == "no_widget":
            logger.warning("set_visible_range: TradingView widget not found in DOM")
        elif value == "no_chart":
            logger.warning("set_visible_range: chart instance not found on widget")

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
    """Apply / remove indicators via DOM.

    Per ADR-0002, the **write step delegates to DomPineScriptBackend**
    which uses the proven clipboard-based + trusted-keystroke approach.
    The old naive ``textarea.value =`` write is removed — it is
    documented as broken in ``docs/monaco-editor-integration.md``.
    """

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def apply(self, pine_code: str, name: str) -> None:
        """Apply a Pine Script indicator/strategy to the chart.

        1. Open the Pine Editor tab (per recon pine_read selectors).
        2. Write the source via DomPineScriptBackend.write (clipboard).
        3. Compile & apply via DomPineScriptBackend.compile.
        """
        # 1. Open the Pine Editor
        pine_detail = _cap(self._caps, "pine_read")
        tab_sels = pine_detail.get("open_tab_selectors", [])
        if tab_sels:
            await self._dom.click(tab_sels)
        await asyncio.sleep(0.5)

        # 2. Write using the proven clipboard-based approach (ADR-0002)
        pine = DomPineScriptBackend(self._cdp, self._dom, self._caps)
        await pine.write(name, pine_code)
        await asyncio.sleep(0.3)

        # 3. Compile & add to chart
        await pine.compile(name)

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
        """Return structured trade records from the Strategy Tester.

        The trade list is rendered as ``innerText`` within the DOM.
        Each trade block follows this line layout::

            N<direction>
            <tab><tab>Exit<tab>Entry<tab>
            <exit_date><tab><entry_date><tab>
            <exit_price> USD <entry_price> USD <tab>
            <size> <value>KUSD <tab>
            <pnl> USD <tab>
            <return_pct>%
        """
        import re

        js = """
        (() => {
            const body = document.body.innerText;
            const idx = body.indexOf('List of trades');
            if (idx < 0) return '';
            return body.slice(idx, idx + 8000);
        })()
        """
        result = await self._cdp.execute_js(js)
        text = result.get("result", {}).get("value", "") or ""
        if not isinstance(text, str) or "List of trades" not in text:
            return []

        lines = text.strip().split('\n')
        trades: list[dict[str, Any]] = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Detect trade header: "<num><direction>" e.g. "1long"
            m = re.match(r'^(\d+)(long|short)$', line)
            if not m:
                i += 1
                continue

            trade: dict[str, Any] = {
                "trade_number": int(m.group(1)),
                "direction": m.group(2),
            }

            # Skip to the Exit/Entry line and past it
            while i < len(lines) and lines[i].strip() not in ('Exit', 'Entry'):
                i += 1
            # Consume the Exit/Entry lines (usually 2 lines: "Exit" then "Entry")
            while i < len(lines) and lines[i].strip() in ('Exit', 'Entry'):
                i += 1

            # Next non-empty lines after Exit/Entry are dates
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                trade["exit_datetime"] = lines[i].strip()
                i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                trade["entry_datetime"] = lines[i].strip()
                i += 1

            # Skip to prices (after dates, skip tabs/blanks)
            while i < len(lines) and not re.match(r'^[\d,]+\.\d{2}$', lines[i].strip()):
                i += 1
            if i < len(lines):
                trade["exit_price"] = float(lines[i].strip().replace(',', ''))
                i += 1
            i += 1  # Skip USD
            if i < len(lines) and re.match(r'^[\d,]+\.\d{2}$', lines[i].strip()):
                trade["entry_price"] = float(lines[i].strip().replace(',', ''))
                i += 1
            i += 1  # Skip USD

            # Skip to size line
            while i < len(lines) and not re.match(r'^\d+$', lines[i].strip()):
                i += 1
            if i < len(lines):
                trade["size"] = int(lines[i].strip())
                i += 1
            i += 1  # Skip value (KUSD)

            # Next is PnL
            while i < len(lines) and not re.match(r'^[+\u2212-]?[\d,]+$', lines[i].strip()):
                i += 1
            if i < len(lines):
                pnl_str = lines[i].strip().replace('\u2212', '-').replace(',', '')
                trade["net_pnl"] = float(pnl_str)
                i += 1
            i += 1  # Skip USD

            # Next is return pct
            while i < len(lines) and not re.match(r'^[+\u2212-]?[\d]+\.[\d]{2}%$', lines[i].strip()):
                i += 1
            if i < len(lines):
                ret_str = lines[i].strip().replace('\u2212', '-').replace('%', '')
                trade["return_pct"] = float(ret_str)
                i += 1

            trades.append(trade)

        return trades

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
        # Fill stop loss field if provided
        sl_sels = field_sels.get("sl", [])
        if sl is not None and sl_sels:
            await self._dom.type_text(sl_sels, str(sl))
        # Fill take profit field if provided
        tp_sels = field_sels.get("tp", [])
        if tp is not None and tp_sels:
            await self._dom.type_text(tp_sels, str(tp))
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
    """Study / indicator Inputs tab via DOM.

    Selectors were discovered from a live TradingView Desktop 3.2.0
    Settings dialog dump on 2026-07-03.  The dialog uses a table-row
    layout where each field has a label cell (``cell-RLntasnw first-RLntasnw``)
    followed by a value cell containing one of:
      - ``input[data-qa-id=\"ui-lib-Input-input\"]`` (number fields)
      - ``button[role=\"combobox\"]`` (dropdowns — displayed value is
        the button's text)
      - ``input[type=\"checkbox\"][data-qa-id=\"ui-lib-checkbox-input-input\"]``
        (checkboxes)
    """

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
        """Open the Settings dialog and enumerate all fields.

        Opens the dialog via CDP mouse hover+click on the indicator's
        gear icon (legend-settings-action), then reads structured fields
        from the Inputs/Style tab.

        Returns a list of dicts with keys: name, type (number/checkbox/
        dropdown/string), current_value.
        """
        detail = _cap(self._caps, "settings_list_fields")
        dialog_sel = detail.get("dialog_selector")
        if not dialog_sel:
            return []

        # ── 1. Ensure the dialog is open ──────────────────────────
        await self._open_settings_dialog(study_name)

        # ── 2. Read fields ────────────────────────────────────────
        row_label_sel = detail.get("row_label_selector", "div.cell-RLntasnw.first-RLntasnw")
        input_sel = detail.get("input_selector_within_row", "input, select, button[role='combobox']")

        js = """
        (() => {
            const dialog = document.querySelector(%s);
            if (!dialog) return [];
            const labels = dialog.querySelectorAll(%s);
            const results = [];
            labels.forEach(labelDiv => {
                const name = labelDiv.textContent.trim();
                if (!name) return;
                // The value cell is the next sibling in the row
                const row = labelDiv.parentElement;
                if (!row) return;
                const cells = Array.from(row.children);
                const labelIdx = cells.indexOf(labelDiv);
                const valueCell = cells[labelIdx + 1];
                // Check BOTH the value cell and the label cell itself for inputs
                // (checkboxes are nested inside the label cell's inner-RLntasnw subtree)
                let input = null;
                if (valueCell) input = valueCell.querySelector(%s);
                if (!input) input = labelDiv.querySelector(%s);
                if (!input) return;
                let fieldType = 'string';
                let currentValue = null;
                if (input.tagName === 'INPUT' && input.type === 'checkbox') {
                    fieldType = 'checkbox';
                    currentValue = input.checked;
                } else if (input.getAttribute('role') === 'combobox' || input.tagName === 'BUTTON') {
                    fieldType = 'dropdown';
                    currentValue = input.textContent.trim();
                } else if (input.tagName === 'INPUT' && input.getAttribute('inputmode') === 'numeric') {
                    fieldType = 'number';
                    currentValue = input.value;
                } else if (input.tagName === 'INPUT') {
                    fieldType = 'string';
                    currentValue = input.value;
                } else if (input.tagName === 'SELECT') {
                    fieldType = 'dropdown';
                    currentValue = input.value;
                }
                results.push({name, type: fieldType, current_value: currentValue});
            });
            return results;
        })()
        """ % (json.dumps(dialog_sel), json.dumps(row_label_sel), json.dumps(input_sel), json.dumps(input_sel))

        result = await self._cdp.execute_js(js)
        return result.get("result", {}).get("value", []) or []

    async def _open_settings_dialog(self, study_name: str) -> None:
        """Open the indicator-properties-dialog via CDP mouse hover+click.

        Uses CDP ``Input.dispatchMouseEvent`` to hover over the
        indicator's legend row (revealing the gear icon via CSS :hover),
        then clicks the gear at ``[data-qa-id=\"legend-settings-action\"]``.

        This is the ONLY mechanism confirmed to open the indicator
        settings dialog programmatically — CGEventPostToPid and
        JS ``.click()`` do not trigger CSS :hover or React's event
        delegation for this button.
        """
        import asyncio

        # Check if dialog is already open
        check_js = """
        (() => {
            const d = document.querySelector(%s);
            return !!(d && d.getBoundingClientRect().width > 0);
        })()
        """ % json.dumps(_cap(self._caps, "settings_list_fields").get("dialog_selector", ""))
        result = await self._cdp.execute_js(check_js)
        if result.get("result", {}).get("value"):
            return  # Already open

        # Find the indicator's legend row and gear icon coordinates
        find_js = """
        (() => {
            const titles = document.querySelectorAll('.title-YTFIJ62h');
            for (let i = 0; i < titles.length; i++) {
                if (titles[i].textContent.trim() === %s) {
                    const tr = titles[i].getBoundingClientRect();
                    // Find the gear icon closest in Y-position to this title
                    // (multiple studies share a parent row; querySelector alone
                    //  picks the wrong gear)
                    const gears = document.querySelectorAll('[data-qa-id="legend-settings-action"]');
                    let bestGear = null, bestDist = Infinity;
                    gears.forEach(g => {
                        const gr = g.getBoundingClientRect();
                        const dist = Math.abs(gr.y - tr.y);
                        if (dist < bestDist) { bestDist = dist; bestGear = g; }
                    });
                    if (bestGear) {
                        const gr = bestGear.getBoundingClientRect();
                        return {
                            titleX: tr.x + tr.width / 2,
                            titleY: tr.y + tr.height / 2,
                            gearX: gr.x + gr.width / 2,
                            gearY: gr.y + gr.height / 2,
                        };
                    }
                }
            }
            return null;
        })()
        """ % json.dumps(study_name)
        result = await self._cdp.execute_js(find_js)
        coords = result.get("result", {}).get("value")
        if not coords:
            return  # Indicator not found in legend

        # Step 1: Click indicator title to select it (so dialog opens for THIS indicator)
        await self._cdp._send_command("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": coords["titleX"], "y": coords["titleY"],
            "modifiers": 0,
        })
        await asyncio.sleep(0.2)
        await self._cdp._send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": coords["titleX"], "y": coords["titleY"],
            "button": "left", "clickCount": 1,
        })
        await self._cdp._send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": coords["titleX"], "y": coords["titleY"],
            "button": "left", "clickCount": 1,
        })
        await asyncio.sleep(0.3)

        # Step 2: Hover over legend row (triggers CSS :hover → gear visible)
        await self._cdp._send_command("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": coords["titleX"], "y": coords["titleY"],
            "modifiers": 0,
        })
        await asyncio.sleep(0.4)

        # Step 3: Click on gear icon
        await self._cdp._send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": coords["gearX"], "y": coords["gearY"],
            "button": "left", "clickCount": 1,
        })
        await self._cdp._send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": coords["gearX"], "y": coords["gearY"],
            "button": "left", "clickCount": 1,
        })
        await asyncio.sleep(0.5)

    async def read(self, study_name: str) -> dict[str, Any]:
        """Read current input values from the Settings dialog.

        Returns a flat dict of {field_name: current_value}.
        """
        fields = await self.list_fields(study_name)
        return {f["name"]: f["current_value"] for f in fields}

    async def write(self, study_name: str, values: dict[str, Any]) -> None:
        """Set one or more input values and click OK.

        For number/string fields: native setter + input/change events.
        For checkboxes: click the checkbox element.
        For dropdowns: click combo to open, await, then click target option.
        """
        detail = _cap(self._caps, "settings_write")
        dialog_sel = detail.get("dialog_selector", "div[data-name=\"indicator-properties-dialog\"]")
        row_label_sel = detail.get("row_label_selector", "div.cell-RLntasnw.first-RLntasnw")
        submit_sel = detail.get("submit_selector", "button[data-name=\"submit-button\"]")

        for field, value in values.items():
            escaped_field = json.dumps(field)
            str_val = json.dumps(str(value))

            # Step 1: Find the input element and determine its type
            find_js = """
            (() => {
                const dialog = document.querySelector(%s);
                if (!dialog) return {error: 'no dialog'};
                const labels = dialog.querySelectorAll(%s);
                for (const labelDiv of labels) {
                    if (labelDiv.textContent.trim() !== %s) continue;
                    const row = labelDiv.parentElement;
                    const cells = Array.from(row.children);
                    const idx = cells.indexOf(labelDiv);
                    const valueCell = cells[idx + 1];

                    // Checkbox — may be in value cell OR inside label cell's inner-RLntasnw
                    let cb = valueCell ? valueCell.querySelector('input[type=\"checkbox\"]') : null;
                    if (!cb) cb = labelDiv.querySelector('input[type=\"checkbox\"]');
                    if (cb) return {type: 'checkbox', checked: cb.checked, id: cb.id};

                    if (!valueCell) return {error: 'no value cell'};

                    // Combobox dropdown
                    const combo = valueCell.querySelector('button[role=\"combobox\"]');
                    if (combo) {
                        combo.click();
                        return {type: 'dropdown', currentText: combo.textContent.trim()};
                    }

                    // Number/string input
                    const input = valueCell.querySelector('input');
                    if (input && !input.disabled) {
                        return {type: 'number', currentValue: input.value};
                    }
                    return {error: 'no editable input found'};
                }
                return {error: 'field not found: ' + %s};
            })()
            """ % (json.dumps(dialog_sel), json.dumps(row_label_sel), escaped_field, escaped_field)

            r = await self._cdp.execute_js(find_js)
            found = r.get("result", {}).get("value", {})

            if isinstance(found, dict) and "error" in found:
                raise SelectorResolutionError(
                    f"Settings write failed for field '{field}': {found['error']}",
                    details={"field": field, "study": study_name},
                )

            ftype = found.get("type", "")

            # Step 2: Set the value based on field type
            if ftype == "checkbox":
                want = bool(value)
                if found.get("checked") != want:
                    # Click the checkbox
                    click_js = """
                    (() => {
                        const dialog = document.querySelector(%s);
                        const labels = dialog.querySelectorAll(%s);
                        for (const labelDiv of labels) {
                            if (labelDiv.textContent.trim() !== %s) continue;
                            const row = labelDiv.parentElement;
                            const cells = Array.from(row.children);
                            const idx = cells.indexOf(labelDiv);
                            const valueCell = cells[idx + 1];
                            let cb = valueCell ? valueCell.querySelector('input[type=\"checkbox\"]') : null;
                            if (!cb) cb = labelDiv.querySelector('input[type=\"checkbox\"]');
                            if (cb) { cb.click(); return {toggled: true}; }
                            return {error: 'checkbox disappeared'};
                        }
                        return {error: 'field disappeared'};
                    })()
                    """ % (json.dumps(dialog_sel), json.dumps(row_label_sel), escaped_field)
                    await self._cdp.execute_js(click_js)

            elif ftype == "dropdown":
                # Dropdown was already opened by the find_js call above
                await asyncio.sleep(0.3)
                # Click the target option
                option_js = """
                (() => {
                    const opts = document.querySelectorAll('[role=\"option\"]');
                    for (const o of opts) {
                        if (o.textContent.trim() === %s) { o.click(); return {clicked: %s}; }
                    }
                    return {error: 'option not found: ' + %s};
                })()
                """ % (str_val, str_val, str_val)
                await self._cdp.execute_js(option_js)

            elif ftype == "number":
                # Use native value setter for React-controlled inputs
                set_js = """
                (() => {
                    const dialog = document.querySelector(%s);
                    const labels = dialog.querySelectorAll(%s);
                    for (const labelDiv of labels) {
                        if (labelDiv.textContent.trim() !== %s) continue;
                        const row = labelDiv.parentElement;
                        const cells = Array.from(row.children);
                        const idx = cells.indexOf(labelDiv);
                        const valueCell = cells[idx + 1];
                        const input = valueCell.querySelector('input');
                        if (input && !input.disabled) {
                            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                            setter.call(input, %s);
                            input.dispatchEvent(new Event('input', {bubbles: true}));
                            input.dispatchEvent(new Event('change', {bubbles: true}));
                            return {set: true, value: input.value};
                        }
                        return {error: 'input disappeared'};
                    }
                    return {error: 'field disappeared'};
                })()
                """ % (json.dumps(dialog_sel), json.dumps(row_label_sel), escaped_field, str_val)
                await self._cdp.execute_js(set_js)

            else:
                raise SelectorResolutionError(
                    f"Unknown field type '{ftype}' for '{field}'",
                    details={"field": field, "type": ftype},
                )

        # Click OK to apply
        await self._dom.click([submit_sel])

    async def health_check(self) -> bool:
        try:
            detail = _cap(self._caps, "settings_list_fields")
            dialog_sel = detail.get("dialog_selector")
            if dialog_sel:
                await self._dom.resolve_selector([dialog_sel], timeout=3.0)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# Pine Script
# ═══════════════════════════════════════════════════════════════

class DomPineScriptBackend(PineScriptBackend):
    """Pine Script editor interaction via DOM.

    IMPORTANT: Monaco Editor virtualizes its hidden textarea — direct DOM
    reads/writes are silently truncated.  See ``docs/monaco-editor-integration.md``
    for the full investigation and rationale.

    **Write** uses system clipboard write + CDP Cmd+V (real keystrokes).
    **Read** uses CDP Cmd+A + Cmd+C + clipboard read.
    **Compile** uses CDP Cmd+Enter (trusted keystroke).
    """

    def __init__(self, cdp, dom, capabilities: dict):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities

    async def read(self, script_name: str) -> str:
        """Read the full Pine Script source via a copy-event intercept.

        1. Focus the Monaco textarea.
        2. Select all text via ``execCommand('selectAll')``.
        3. Dispatch a synthetic ``ClipboardEvent('copy')`` with a
           one-shot event listener that captures the full source from
           Monaco's internal model.
        """
        detail = _cap(self._caps, "pine_read")
        textarea_sels = detail.get("textarea_selectors", [])

        # 1. Open the Pine Editor tab if needed
        tab_sels = detail.get("open_tab_selectors", [])
        if tab_sels:
            await self._dom.click(tab_sels)

        # 2. Read via Monaco copy-event intercept (full source)
        if textarea_sels:
            text = await self._dom.read_text_monaco(textarea_sels, timeout=3.0)
            if text and len(text) > 50:
                return text

        # Fallback: read view-lines from current viewport
        view_sels = detail.get("view_line_selectors", [])
        text = await self._dom.extract_text(view_sels, timeout=3.0)
        return text or ""

    async def write(self, script_name: str, source: str) -> None:
        """Write new source into the Pine Editor via system clipboard + Cmd+V.

        ``type_text_monaco`` handles: clipboard write, editor focus,
        Cmd+A (select all), and Cmd+V (paste via real keystrokes).
        """
        detail = _cap(self._caps, "pine_write")
        textarea_sels = detail.get("textarea_selectors", [])
        editor_sels = detail.get("editor_selectors", [])

        await self._dom.type_text_monaco(
            textarea_sels or editor_sels, source
        )

    async def compile(self, script_name: str) -> dict[str, Any]:
        """Compile and add the script to the chart.

        Clicks the Pine Editor toolbar button via JS ``element.click()``.
        The button title changes state: "Add to chart" (first add) →
        "Update on chart" (subsequent updates).
        """
        detail = _cap(self._caps, "pine_compile")
        import asyncio, logging
        logger = logging.getLogger(__name__)

        # ── Primary: JS click on Add/Update button ───────────────
        click_js = """
        (() => {
            for (const title of ['Add to chart', 'Update on chart', 'Save script']) {
                const btn = document.querySelector('button[title="' + title + '"]');
                if (btn) { btn.click(); return title.replace(/ /g,'_') + '_clicked'; }
            }
            return 'compile_button_not_found';
        })()
        """
        result = await self._cdp.execute_js(click_js)
        status = result.get("result", {}).get("value", "")

        if "clicked" in str(status):
            logger.debug("Compile button clicked via JS: %s", status)
            await asyncio.sleep(1.5)
            return {"success": True, "method": status}

        logger.warning("Could not find Add/Update/Save button in Pine Editor")
        return {"success": False, "error": "compile_button_not_found", "method": status}

    async def read_compile_errors(self) -> list[dict[str, Any]]:
        """Read compile errors from the Pine Editor console panel.

        Returns a list of dicts with keys: type (error/warning), line,
        column, message, timestamp.  Only returns errors from the most
        recent compilation (entries after the last "Compiling..." line).

        Uses the structural classes discovered in the Pine Editor console:
        - ``.selectable-v4HmQr2o.error-v4HmQr2o`` → error entries
        - ``.selectable-v4HmQr2o.warning-v4HmQr2o`` → warning entries
        - ``.time-v4HmQr2o`` → timestamp child element
        """
        js = """
        (() => {
            const d = document.getElementById('pine-editor-dialog');
            if (!d) return [];

            // Find all console entries
            const entries = d.querySelectorAll('.selectable-v4HmQr2o');
            const results = [];

            // Find the index of the last "Compiling..." entry
            let lastCompileIdx = -1;
            entries.forEach((e, i) => {
                if (e.textContent.includes('Compiling...')) lastCompileIdx = i;
            });

            entries.forEach((e, i) => {
                // Only process entries after the last compile
                if (i <= lastCompileIdx) return;

                const cls = e.className;
                const isError = cls.includes('error-v4HmQr2o');
                const isWarning = cls.includes('warning-v4HmQr2o');
                if (!isError && !isWarning) return;

                const text = e.textContent.trim();
                if (!text) return;

                // Parse: "HH:MM:SS AMError at LINE:COL MESSAGE" or
                //        "HH:MM:SS AMWarning at LINE:COL MESSAGE"
                const match = text.match(/(?:\\d{1,2}:\\d{2}:\\d{2}\\s*(?:AM|PM))?(Error|Warning)\\s+at\\s+(\\d+):(\\d+)\\s+(.+)/);
                if (match) {
                    results.push({
                        type: match[1].toLowerCase(),
                        line: parseInt(match[2]),
                        column: parseInt(match[3]),
                        message: match[4].trim()
                    });
                } else {
                    // Fallback: return raw text if parse fails
                    results.push({type: isError ? 'error' : 'warning', message: text});
                }
            });

            return results;
        })()
        """
        result = await self._cdp.execute_js(js)
        return result.get("result", {}).get("value", []) or []

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
