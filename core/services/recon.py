"""Interactive reconnaissance tool for TradingView Desktop.

Launches TV Desktop via CDP, then guides a human operator through a
~4-minute interaction sequence while capturing DOM snapshots, network
traffic, and JS global probes.  Outputs a structured
``recon_findings.json`` that drives all backend strategy decisions.

Usage (after starting the server):
    tv-desktop-recon --port 8315

Or import and use interactively:
    from core.services.recon import ReconRunner
    rr = ReconRunner(cdp)
    await rr.run_full_protocol()
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

from core.services.cdp_connection import CDPConnection
from core.services.dom_utils import DomUtils

logger = logging.getLogger(__name__)

# Where recon output is saved (relative to project root)
DEFAULT_OUTPUT = "recon_findings.json"

# Known internal JS paths to probe — these are guesses, not assumptions.
# Recon will try each and record which (if any) actually resolve.
KNOWN_JS_PATHS = [
    "window.tradingView",
    "window.TradingView",
    "window.tvWidget",
    "window.tvChart",
    "window.chart",
    "window.mainChart",
    "window.activeChart",
    "window.pineJs",
    "window.PineEditor",
    "window.StrategyTester",
    "window.Backtesting",
    "window.Alerts",
    "window.DrawingManager",
    "window.OrderPanel",
    "window.ReplayManager",
]

# Mapping from capability keys to the JS paths we'd expect if Path A.
# If a JS path resolves, we can upgrade from DOM→JS for that capability.
CAP_JS_PATH_MAP: dict[str, str] = {
    "symbol_control": "window.tvWidget?.activeChart?.setSymbol",
    "timeframe_control": "window.tvWidget?.activeChart?.setResolution",
    "ohlcv_read": "window.tvWidget?.activeChart?.getChartData",
    "indicator_apply": "window.tvWidget?.activeChart?.createStudy",
    "indicator_remove": "window.tvWidget?.activeChart?.removeEntity",
}

# Capabilities whose selectors we want to capture by dumping specific panels.
DOM_SNAPSHOT_KEYS = [
    "pine_editor",
    "strategy_tester",
    "alert_modal",
    "alert_list_panel",
    "drawing_toolbar",
    "order_ticket",
    "replay_toolbar",
]


class ReconRunner:
    """Drives the interactive discovery protocol and produces structured findings."""

    def __init__(self, cdp: CDPConnection):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._findings: dict[str, Any] = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tv_desktop_version": "unknown",
            "capabilities": self._empty_capabilities(),
            "window_globals_found": [],
            "raw_dom_snapshots": {k: "" for k in DOM_SNAPSHOT_KEYS},
        }

    # ── Public entry point ───────────────────────────────────────

    async def run_full_protocol(self) -> dict[str, Any]:
        """Run the complete reconnaissance protocol.

        Steps:
        1. Detect TV Desktop version
        2. Dump window globals
        3. Probe known JS paths
        4. Tap network (with guided interaction)
        5. Dump DOM structures
        6. Produce final report
        """
        click.echo("\n=== TradingView Desktop Reconnaissance ===\n")

        # Step 1 — version
        await self._detect_version()

        # Step 2 — window globals
        await self._dump_window_globals()

        # Step 3 — probe JS paths
        await self._probe_known_paths()

        # Step 4 — guided network tap
        await self._tap_network()

        # Step 5 — DOM snapshots
        await self._dump_dom_structure()

        # Step 6 — report & save
        self._findings["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._findings

    # ── Step implementations ─────────────────────────────────────

    async def _detect_version(self) -> None:
        """Try to detect the TradingView Desktop version via CDP."""
        try:
            result = await self._cdp.execute_js(
                "navigator.userAgent",
            )
            ua = result.get("result", {}).get("value", "unknown")
            # Try TradingView-specific version global
            tv_ver = await self._cdp.execute_js(
                "window.tvDesktopVersion || window.TradingView?.version || 'unknown'",
            )
            ver = tv_ver.get("result", {}).get("value", "unknown")
            self._findings["tv_desktop_version"] = str(ver)
            click.echo(f"  TV Desktop version: {ver}")
            click.echo(f"  User-Agent: {ua[:120]}...")
        except Exception as exc:
            logger.warning("Version detection failed: %s", exc)
            self._findings["tv_desktop_version"] = "unknown"

    async def _dump_window_globals(self) -> None:
        """List top-level window keys and identify TradingView-specific ones."""
        click.echo("\n--- Dumping window globals ---")
        try:
            result = await self._cdp.execute_js("Object.keys(window)")
            keys: list[str] = result.get("result", {}).get("value", [])
            tv_related = [k for k in keys if any(
                keyword in k.lower() for keyword in
                ["trading", "tv", "chart", "pine", "widget", "backtest",
                 "alert", "drawing", "order", "replay", "strategy", "study",
                 "indicator", "symbol", "market"]
            )]
            self._findings["window_globals_found"] = tv_related
            if tv_related:
                click.echo(f"  Found {len(tv_related)} TradingView-related globals:")
                for g in sorted(tv_related):
                    click.echo(f"    - {g}")
            else:
                click.echo("  No TradingView-related globals detected.")
        except Exception as exc:
            logger.warning("Window globals dump failed: %s", exc)

    async def _probe_known_paths(self) -> None:
        """Check each known JS path and update capability paths."""
        click.echo("\n--- Probing known JS paths ---")
        for path in KNOWN_JS_PATHS:
            try:
                result = await self._cdp.execute_js(f"typeof ({path})")
                typeof_val = result.get("result", {}).get("value", "undefined")
                exists = typeof_val not in ("undefined", "null")
                click.echo(f"  {path}: {typeof_val}")
                # If a JS function exists, upgrade relevant capabilities
                if exists and path in CAP_JS_PATH_MAP:
                    cap_name = CAP_JS_PATH_MAP[path]
                    # Check that the method actually exists
                    method_result = await self._cdp.execute_js(f"typeof ({path})")
                    mtype = method_result.get("result", {}).get("value", "undefined")
                    if mtype == "function":
                        click.echo(f"    → Upgrading {cap_name} to JS path")
                        self._findings["capabilities"][cap_name]["path"] = "js"
                        self._findings["capabilities"][cap_name]["detail"]["js_path"] = path
            except Exception as exc:
                logger.debug("Probe failed for %s: %s", path, exc)

    async def _tap_network(self) -> None:
        """Enable network monitoring and guide the operator through interactions."""
        click.echo("\n--- Network tap ---")
        try:
            await self._cdp.listen_network(True)
        except Exception as exc:
            click.echo(f"  (Network domain not available: {exc})")
            return

        click.echo("\n" + "=" * 70)
        click.echo("NETWORK TAP — Follow these steps now (~4 min):")
        click.echo("=" * 70)
        steps = [
            ("[0:00-0:20]", "Change the chart symbol to any different symbol now."),
            ("[0:20-0:40]", "Change the timeframe now."),
            ("[0:40-1:00]", "Open Pine Editor, paste any indicator, click Add to Chart."),
            ("[1:00-1:30]", "Open Strategy Tester and let a backtest run to completion."),
            ("[1:30-2:00]", "Open the Trades List tab and scroll through it."),
            ("[2:00-2:30]", "Create a price alert on the current symbol, then open the alert list panel."),
            ("[2:30-3:00]", "Place a trendline and a Fibonacci retracement on the chart."),
            ("[3:00-3:30]", "Open the order panel (paper trading) and place one small paper order, then cancel it."),
            ("[3:30-4:00]", "Enter Replay mode, step forward a few bars, then exit Replay mode."),
        ]
        for ts, instruction in steps:
            click.echo(f"\n  {ts}")
            click.echo(f"  → {instruction}")
            input("    Press Enter when done with this step...")

        # Collect network events
        events = self._cdp.get_network_events()
        click.echo(f"\n  Captured {len(events)} network events")

        # Categorize network events
        ws_frames = [e for e in events if e.get("method") == "Network.webSocketFrameReceived"]
        xhr_events = [e for e in events if e.get("method") in (
            "Network.responseReceived", "Network.loadingFinished")]
        click.echo(f"  WebSocket frames: {len(ws_frames)}")
        click.echo(f"  HTTP responses:   {len(xhr_events)}")

        # Try to identify OHLCV data streams in network events
        ohlcv_patterns = []
        for ev in ws_frames:
            payload = ev.get("params", {}).get("response", {}).get("payloadData", "")
            if any(kw in payload.lower() for kw in ["ohlc", "bars", "series", "marketdata"]):
                ohlcv_patterns.append(payload[:200])
        if ohlcv_patterns:
            click.echo(f"\n  Found {len(ohlcv_patterns)} potential OHLCV data frames:")
            for p in ohlcv_patterns[:3]:
                click.echo(f"    - {p}")
            detail = self._findings["capabilities"]["ohlcv_read"]["detail"]
            detail["ws_message_shape"] = ohlcv_patterns[0] if ohlcv_patterns else ""
            detail["match_pattern"] = "ohlc|bars|series|marketdata"
            self._findings["capabilities"]["ohlcv_read"]["path"] = "network"

        await self._cdp.listen_network(False)

    async def _dump_dom_structure(self) -> None:
        """Snapshot key UI panels by dumping their outer HTML."""
        click.echo("\n--- DOM snapshots ---")

        panel_map: list[tuple[str, str, str]] = [
            ("pine_editor", "Pine Editor", "div[class*='pine-editor'], div[class*='editor']"),
            ("strategy_tester", "Strategy Tester", "div[class*='strategy-tester'], div[class*='backtest']"),
            ("alert_modal", "Alert Modal", "div[class*='alert-dialog'], div[class*='create-alert']"),
            ("alert_list_panel", "Alert List", "div[class*='alert-list'], div[class*='alerts-panel']"),
            ("drawing_toolbar", "Drawing Toolbar", "div[class*='drawing-toolbar'], div[class*='drawing-bar']"),
            ("order_ticket", "Order Ticket", "div[class*='order-ticket'], div[class*='order-panel'], div[class*='ticket']"),
            ("replay_toolbar", "Replay Toolbar", "div[class*='replay'], div[role='toolbar'][class*='replay']"),
        ]

        for key, label, selector in panel_map:
            try:
                html = await self._snapshot_outer_html(selector)
                if html and len(html) > 20:
                    self._findings["raw_dom_snapshots"][key] = html[:2000]  # trim for file size
                    click.echo(f"  {label}: captured ({len(html)} chars)")
                else:
                    click.echo(f"  {label}: not found (panel may not be open)")
            except Exception as exc:
                logger.debug("DOM snapshot failed for %s: %s", key, exc)
                click.echo(f"  {label}: error ({exc})")

    async def _snapshot_outer_html(self, css_selector: str) -> str | None:
        """Return the outerHTML of the first element matching *css_selector*."""
        escaped = css_selector.replace("'", "\\'")
        result = await self._cdp.execute_js(
            f"document.querySelector('{escaped}')?.outerHTML ?? ''",
        )
        return result.get("result", {}).get("value")

    # ── Report generation ───────────────────────────────────────

    def save(self, output_path: str = DEFAULT_OUTPUT) -> str:
        """Write the findings dict to a JSON file and return the path."""
        # Resolve relative to project root (where server.py lives)
        path = Path(output_path)
        if not path.is_absolute():
            # Walk up to find project root (look for pyproject.toml)
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / "pyproject.toml").exists():
                    path = parent / output_path
                    break
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._findings, f, indent=2, ensure_ascii=False)
        click.echo(f"\n  Findings saved to {path}")
        return str(path)

    @staticmethod
    def _empty_capabilities() -> dict[str, dict]:
        """Return the template capability dict with all 32 keys."""
        return {
            "symbol_control":        {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "timeframe_control":     {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "ohlcv_read":            {"path": "network", "verified": False, "detail": {"ws_message_shape": "", "match_pattern": ""}},
            "indicator_apply":       {"path": "dom", "verified": False, "detail": {"editor_selectors": [""], "add_to_chart_selectors": [""]}},
            "indicator_remove":      {"path": "dom", "verified": False, "detail": {"context_menu_selectors": [""]}},
            "backtest_run":          {"path": "dom", "verified": False, "detail": {"tab_selectors": [""]}},
            "backtest_summary":      {"path": "dom", "verified": False, "detail": {"tab_selectors": [""], "row_selectors": {"net_profit": [""], "win_rate": [""]}}},
            "backtest_trade_list":   {"path": "dom", "verified": False, "detail": {"table_selectors": [""], "row_selectors": [""], "pagination": "scroll|paged|none"}},
            "backtest_equity_curve": {"path": "dom", "verified": False, "detail": {"fallback": "numeric_table_if_present_else_null"}},
            "alert_create":          {"path": "dom", "verified": False, "detail": {"open_modal_selectors": [""], "field_selectors": {"condition": [""], "message": [""]}, "confirm_selectors": [""]}},
            "alert_edit":            {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "alert_delete":          {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "alert_list":            {"path": "dom", "verified": False, "detail": {"panel_selectors": [""], "row_selectors": [""]}},
            "drawing_create":        {"path": "dom", "verified": False, "detail": {"toolbar_selectors": {"trendline": [""], "fib": [""], "rectangle": [""]}, "canvas_selector": [""]}},
            "drawing_remove":        {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "drawing_list":          {"path": "dom", "verified": False, "detail": {"panel_selectors": [""]}},
            "order_place":           {"path": "dom", "verified": False, "detail": {"ticket_selectors": [""], "field_selectors": {"size": [""], "sl": [""], "tp": [""]}, "submit_selectors": [""]}},
            "order_modify":          {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "order_cancel":          {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "order_status_read":     {"path": "dom", "verified": False, "detail": {"positions_panel_selectors": [""], "row_selectors": [""]}},
            "replay_enter":          {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "replay_step":           {"path": "dom", "verified": False, "detail": {"step_selectors": [""]}},
            "replay_exit":           {"path": "dom", "verified": False, "detail": {"selectors": [""]}},
            "replay_state_read":     {"path": "dom", "verified": False, "detail": {"indicator_selectors": [""]}},
            "screenshot":            {"path": "cdp", "verified": True, "detail": {}},
            "settings_list_fields":  {"path": "dom", "verified": False, "detail": {"dialog_selectors": [""], "field_mappings": {}}},
            "settings_read":         {"path": "dom", "verified": False, "detail": {"dialog_selectors": [""]}},
            "settings_write":        {"path": "dom", "verified": False, "detail": {"dialog_selectors": [""], "apply_selectors": [""]}},
            "pine_read":             {"path": "dom", "verified": False, "detail": {"editor_selectors": [""]}},
            "pine_write":            {"path": "dom", "verified": False, "detail": {"editor_selectors": [""]}},
            "pine_compile":          {"path": "dom", "verified": False, "detail": {"compile_selectors": [""]}},
            "pine_compile_errors_read": {"path": "dom", "verified": False, "detail": {"console_selectors": [""]}},
            "pine_logs_read":        {"path": "dom", "verified": False, "detail": {"pane_selectors": [""], "entry_selectors": [""]}},
        }


# ── CLI entry point ─────────────────────────────────────────────

@click.command()
@click.option("--port", default=8315, help="CDP remote debugging port", show_default=True)
@click.option("--app-path", default=None, help="Path to TradingView Desktop executable")
@click.option("--output", default=DEFAULT_OUTPUT, help="Output JSON file path", show_default=True)
@click.option("--launch/--no-launch", default=True, help="Auto-launch TV Desktop")
def cli_main(port: int, app_path: str | None, output: str, launch: bool):
    """Run interactive reconnaissance against TradingView Desktop.

    Launches (or connects to) a TV Desktop instance, guides you through
    a ~4-minute interaction sequence, and saves capability findings to
    recon_findings.json.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _run():
        cdp = CDPConnection(debug_port=port)

        if launch:
            click.echo(f"Launching TV Desktop on port {port}...")
            await cdp.launch(app_path=app_path)
            await asyncio.sleep(2)

        click.echo(f"Connecting to CDP at ws://127.0.0.1:{port}...")
        try:
            await cdp.connect()
        except Exception as exc:
            click.echo(f"Failed to connect: {exc}", err=True)
            sys.exit(1)

        try:
            runner = ReconRunner(cdp)
            findings = await runner.run_full_protocol()
            saved_path = runner.save(output)

            click.echo("\n" + "=" * 70)
            click.echo("RECON COMPLETE")
            click.echo("=" * 70)
            click.echo(f"  Output: {saved_path}")
            click.echo(f"  Capabilities: {len(findings['capabilities'])} entries")
            verified = sum(1 for c in findings["capabilities"].values() if c.get("verified"))
            unverified = len(findings["capabilities"]) - verified
            click.echo(f"  Verified: {verified}")
            click.echo(f"  Unverified: {unverified}")
            click.echo(f"\n  IMPORTANT: Review the JSON file and update selector arrays")
            click.echo(f"  before writing any backend code. Set 'verified' to true for")
            click.echo(f"  capabilities whose selectors you've confirmed.")
        finally:
            await cdp.disconnect()

    asyncio.run(_run())


if __name__ == "__main__":
    cli_main()
