"""TradingView Desktop Controller — MCP Server.

A standalone MCP server that provides autonomous programmatic control
over TradingView Desktop via Chrome DevTools Protocol (CDP).

Startup validates ``recon_findings.json`` (schema v2 required), constructs
all 8 domain controllers, and registers 36+ MCP tools accessible to any
MCP-compatible client.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from core.services.cdp_connection import CDPConnection
from core.services.chart_controller import TVChartController
from core.services.backtest_controller import TVBacktestController
from core.services.alert_controller import TVAlertController
from core.services.drawing_controller import TVDrawingController
from core.services.order_controller import TVOrderController
from core.services.replay_controller import TVReplayController
from core.services.settings_controller import TVSettingsController
from core.services.pinescript_controller import TVPineScriptController
from core.services.errors import (
    TvMcpError,
    OrderSubmissionBlocked,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════

CONFIG_PATH = Path(__file__).parent / "recon_findings.json"


def _load_recon() -> dict:
    """Load and validate ``recon_findings.json``."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"recon_findings.json not found at {CONFIG_PATH}. Run recon."
        )
    with open(CONFIG_PATH) as f:
        data: dict[str, Any] = json.load(f)
    if data.get("schema_version") != 2:
        raise RuntimeError(
            f"recon_findings.json has schema_version={data.get('schema_version')}. "
            f"Schema v2 required. Rerun recon."
        )
    return data


# ── Construct controllers at import time ──
# allow_unverified=True during development
_recon = _load_recon()
_cdp = CDPConnection(debug_port=8315)

_ctrl_chart = TVChartController(_cdp, _recon, allow_unverified=True)
_ctrl_backtest = TVBacktestController(_cdp, _recon, allow_unverified=True)
_ctrl_alert = TVAlertController(_cdp, _recon, allow_unverified=True)
_ctrl_drawing = TVDrawingController(_cdp, _recon, allow_unverified=True)
_ctrl_order = TVOrderController(_cdp, _recon, allow_unverified=True)
_ctrl_replay = TVReplayController(_cdp, _recon, allow_unverified=True)
_ctrl_settings = TVSettingsController(_cdp, _recon, allow_unverified=True)
_ctrl_pine = TVPineScriptController(_cdp, _recon, allow_unverified=True)

# Tool name → (handler, Tool definition)
_tools_def: list[Tool] = []
_tool_handlers: dict[str, Any] = {}


def _register(name: str, description: str, input_schema: dict, handler):
    _tools_def.append(Tool(name=name, description=description, inputSchema=input_schema))
    _tool_handlers[name] = handler


def _ok(data: Any) -> list[TextContent]:
    if isinstance(data, (dict, list)):
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]
    return [TextContent(type="text", text=str(data))]


def _err(exc: Exception) -> list[TextContent]:
    if isinstance(exc, TvMcpError):
        detail = exc.to_dict()
    else:
        detail = {"code": "INTERNAL_ERROR", "message": str(exc)}
    return [TextContent(type="text", text=json.dumps(detail, indent=2))]


# ═══════════════════════════════════════════════════════════════
# Tool Registration
# ═══════════════════════════════════════════════════════════════

_register("tv_desktop_launch", "Launch TradingView Desktop with debug port (default 8315)",
          {"type": "object", "properties": {"port": {"type": "integer", "default": 8315}}},
          lambda port=8315: asyncio.ensure_future(_cdp.launch()) or _ok({"status": "launching"}))

_register("tv_disconnect", "Disconnect from TV Desktop CDP session",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_cdp.disconnect()) or _ok({"status": "disconnected"}))

_register("tv_diagnostics", "Full diagnostics across all 9 domains",
          {"type": "object", "properties": {}},
          lambda: _ok({"cdp": asyncio.ensure_future(_cdp.health_check()),
                        "schema_version": _recon.get("schema_version"),
                        "tv_version": _recon.get("tv_desktop_version")}))

# ── Chart ──
_register("tv_set_symbol", "Change the chart symbol (e.g. 'AAPL', 'BTCUSD')",
          {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
          lambda symbol: asyncio.ensure_future(_ctrl_chart.set_symbol(symbol)) or _ok({"symbol": symbol}))

_register("tv_set_timeframe", "Change the chart timeframe (e.g. '1h', '4h', '1D')",
          {"type": "object", "properties": {"timeframe": {"type": "string"}}, "required": ["timeframe"]},
          lambda timeframe: asyncio.ensure_future(_ctrl_chart.set_timeframe(timeframe)) or _ok({"timeframe": timeframe}))

_register("tv_apply_script", "Apply a Pine Script indicator/strategy to the chart",
          {"type": "object", "properties": {"pine_code": {"type": "string"}, "name": {"type": "string"}}, "required": ["pine_code", "name"]},
          lambda pine_code, name: asyncio.ensure_future(_ctrl_chart.add_indicator(pine_code, name)) or _ok({"name": name}))

_register("tv_remove_indicator", "Remove an indicator from the chart",
          {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
          lambda name: asyncio.ensure_future(_ctrl_chart.remove_indicator(name)) or _ok({"name": name}))

_register("tv_get_chart_data", "Get OHLCV data from the chart",
          {"type": "object", "properties": {"limit": {"type": "integer", "default": 500}}},
          lambda limit=500: asyncio.ensure_future(_ctrl_chart.get_ohlcv(limit)))

_register("tv_screenshot", "Capture a screenshot of the current chart view",
          {"type": "object", "properties": {}},
          lambda: _ok({"status": "screenshot not yet implemented"}))

# ── Backtest ──
_register("tv_run_backtest", "Run a strategy backtest",
          {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
          lambda name: asyncio.ensure_future(_ctrl_backtest.run_strategy(name)) or _ok({"strategy": name}))

_register("tv_get_backtest_summary", "Get backtest performance summary",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_backtest.get_performance_summary()))

_register("tv_get_backtest_trades", "Get list of backtest trades",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_backtest.get_trade_list()))

_register("tv_get_backtest_equity_curve", "Get equity curve data",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_backtest.get_equity_curve()))

# ── Alerts ──
_register("tv_alert_create", "Create a price alert",
          {"type": "object", "properties": {"symbol": {"type": "string"}, "condition": {"type": "string"}, "message": {"type": "string"}}, "required": ["symbol", "condition", "message"]},
          lambda symbol, condition, message: asyncio.ensure_future(_ctrl_alert.create(symbol, {"condition": condition}, message)))

_register("tv_alert_edit", "Edit an existing alert",
          {"type": "object", "properties": {"alert_id": {"type": "string"}, "condition": {"type": "string"}, "message": {"type": "string"}}, "required": ["alert_id"]},
          lambda alert_id, condition=None, message=None: asyncio.ensure_future(_ctrl_alert.edit(alert_id, {"condition": condition} if condition else None, message)) or _ok({"alert_id": alert_id}))

_register("tv_alert_delete", "Delete an alert",
          {"type": "object", "properties": {"alert_id": {"type": "string"}}, "required": ["alert_id"]},
          lambda alert_id: asyncio.ensure_future(_ctrl_alert.delete(alert_id)) or _ok({"alert_id": alert_id}))

_register("tv_alert_list", "List all active alerts",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_alert.list()))

# ── Drawings ──
_register("tv_drawing_create", "Place a drawing on the chart",
          {"type": "object", "properties": {"drawing_type": {"type": "string"}, "points": {"type": "array"}}, "required": ["drawing_type", "points"]},
          lambda drawing_type, points: asyncio.ensure_future(_ctrl_drawing.create(drawing_type, points)))

_register("tv_drawing_remove", "Remove a drawing by ID",
          {"type": "object", "properties": {"drawing_id": {"type": "string"}}, "required": ["drawing_id"]},
          lambda drawing_id: asyncio.ensure_future(_ctrl_drawing.remove(drawing_id)) or _ok({"drawing_id": drawing_id}))

_register("tv_drawing_list", "List all drawings on the chart",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_drawing.list()))

# ── Orders ──
_register("tv_order_place", "Place a paper order. **confirm must be True**",
          {"type": "object", "properties": {"symbol": {"type": "string"}, "side": {"type": "string"}, "size": {"type": "number"}, "order_type": {"type": "string", "default": "market"}, "sl": {"type": "number"}, "tp": {"type": "number"}, "confirm": {"type": "boolean", "default": False}}, "required": ["symbol", "side", "size"]},
          lambda symbol, side, size, order_type="market", sl=None, tp=None, confirm=False: asyncio.ensure_future(_ctrl_order.place(symbol, side, size, order_type, sl, tp, bool(confirm))))

_register("tv_order_modify", "Modify a working order",
          {"type": "object", "properties": {"order_id": {"type": "string"}, "size": {"type": "number"}, "sl": {"type": "number"}, "tp": {"type": "number"}}, "required": ["order_id"]},
          lambda order_id, size=None, sl=None, tp=None: asyncio.ensure_future(_ctrl_order.modify(order_id, size, sl, tp)) or _ok({"order_id": order_id}))

_register("tv_order_cancel", "Cancel a working order",
          {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
          lambda order_id: asyncio.ensure_future(_ctrl_order.cancel(order_id)) or _ok({"order_id": order_id}))

_register("tv_order_status", "Read open positions and working orders",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_order.status()))

# ── Replay ──
_register("tv_replay_enter", "Enter Replay mode",
          {"type": "object", "properties": {"start_bar": {"type": "string"}}, "required": ["start_bar"]},
          lambda start_bar: asyncio.ensure_future(_ctrl_replay.enter(start_bar)) or _ok({"start_bar": start_bar}))

_register("tv_replay_step", "Advance Replay by N bars",
          {"type": "object", "properties": {"bars": {"type": "integer", "default": 1}}},
          lambda bars=1: asyncio.ensure_future(_ctrl_replay.step(bars)) or _ok({"bars": bars}))

_register("tv_replay_exit", "Exit Replay mode",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_replay.exit()) or _ok({"status": "exited"}))

_register("tv_replay_state", "Read current Replay state",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_replay.state()))

# ── Settings ──
_register("tv_settings_list_fields", "List input fields for a study",
          {"type": "object", "properties": {"study_name": {"type": "string"}}, "required": ["study_name"]},
          lambda study_name: asyncio.ensure_future(_ctrl_settings.list_fields(study_name)))

_register("tv_settings_read", "Read input values for a study",
          {"type": "object", "properties": {"study_name": {"type": "string"}}, "required": ["study_name"]},
          lambda study_name: asyncio.ensure_future(_ctrl_settings.read(study_name)))

_register("tv_settings_write", "Write input values for a study",
          {"type": "object", "properties": {"study_name": {"type": "string"}, "values": {"type": "object"}}, "required": ["study_name", "values"]},
          lambda study_name, values: asyncio.ensure_future(_ctrl_settings.write(study_name, values)) or _ok({"study": study_name}))

# ── Pine Script ──
_register("tv_pine_read", "Read Pine Script source",
          {"type": "object", "properties": {"script_name": {"type": "string"}}, "required": ["script_name"]},
          lambda script_name: asyncio.ensure_future(_ctrl_pine.read(script_name)))

_register("tv_pine_write", "Write Pine Script source",
          {"type": "object", "properties": {"script_name": {"type": "string"}, "source": {"type": "string"}}, "required": ["script_name", "source"]},
          lambda script_name, source: asyncio.ensure_future(_ctrl_pine.write(script_name, source)) or _ok({"script": script_name}))

_register("tv_pine_compile", "Compile a Pine Script",
          {"type": "object", "properties": {"script_name": {"type": "string"}}, "required": ["script_name"]},
          lambda script_name: asyncio.ensure_future(_ctrl_pine.compile(script_name)))

_register("tv_pine_compile_errors", "Read Pine Script compile errors",
          {"type": "object", "properties": {}},
          lambda: asyncio.ensure_future(_ctrl_pine.read_compile_errors()))

_register("tv_pine_logs", "Read Pine Logs output",
          {"type": "object", "properties": {"script_name": {"type": "string"}}, "required": ["script_name"]},
          lambda script_name: asyncio.ensure_future(_ctrl_pine.read_logs(script_name)))


# ═══════════════════════════════════════════════════════════════
# MCP Server
# ═══════════════════════════════════════════════════════════════

app = Server("tv-desktop-controller")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all registered tools."""
    return list(_tools_def)


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    handler = _tool_handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    try:
        result = handler(**arguments)
        if isinstance(result, list) and all(isinstance(r, TextContent) for r in result):
            return result
        # If result is a coroutine, await it
        if asyncio.iscoroutine(result):
            result = await result
        if isinstance(result, list) and all(isinstance(r, TextContent) for r in result):
            return result
        return _ok(result)
    except Exception as exc:
        logger.exception("Tool '%s' failed", name)
        return _err(exc)


def main():
    """Run the MCP server via stdio transport."""

    async def _run():
        logger.info("Starting TV Desktop MCP Controller — %d tools registered", len(_tools_def))
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
