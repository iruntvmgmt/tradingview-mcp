"""
Phase 0 — Recon Runner.

Determines, empirically, which implementation path (JS / Network / DOM)
applies to each TradingView Desktop capability.  Produces
``recon_findings.json`` which every controller reads at construction time.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager


RECON_FINDINGS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "recon_findings.json"
)


# Known JS global patterns to probe (Path A candidates)
KNOWN_JS_PATHS = [
    "window.TradingViewApi",
    "window.__INITIAL_STATE__",
    "window.tvWidget",
    "window.widget",
    "window.chart",
    "window.tradingview",
    "window.TradingView",
    "window.__TradingView__",
    "window.__tradingview__",
    "document.querySelector('#root')._reactRootContainer",
    "document.querySelector('#js-custom-root')._reactRootContainer",
    "__NEXT_DATA__",
]

# DOM selectors to try for each capability (probed during recon)
CAPABILITY_SELECTOR_CANDIDATES: dict[str, list[str]] = {
    "symbol_control": [
        '[data-name="symbol-search"]',
        '[class*="symbol"]',
        '[class*="search"] input',
        'input[placeholder*="symbol"]',
        'input[placeholder*="Symbol"]',
        '[data-name="header"] [class*="search"]',
        '[class*="header"] [class*="symbol"]',
    ],
    "timeframe_control": [
        '[data-name="timeframe"]',
        '[class*="timeframe"]',
        '[class*="resolution"]',
        '[data-name="header"] [class*="interval"]',
        '[class*="chart-toolbar"] [class*="interval"]',
    ],
    "indicator_apply": {
        "editor_selectors": [
            '[class*="pine-editor"]',
            '[class*="editor"]',
            '[data-name="pine-editor"]',
            '[class*="source-editor"]',
            'textarea',
            '[class*="monaco"]',
            '[class*="code"]',
        ],
        "add_to_chart_selectors": [
            'button:has-text("Add to Chart")',
            'button:has-text("Add")',
            '[class*="apply"] button',
            '[class*="add"] button',
        ],
    },
    "indicator_remove": [
        '[class*="study"] [class*="close"]',
        '[class*="indicator"] [class*="remove"]',
        '[class*="legend"] [class*="close"]',
        '[data-name="legend"] [class*="close"]',
    ],
    "strategy_tester": [
        '[class*="strategy-tester"]',
        '[class*="backtest"]',
        '[data-name="strategy-tester"]',
        '[class*="tester"]',
    ],
    "backtest_summary_overview": {
        "tab_selectors": [
            'button:has-text("Overview")',
            '[class*="overview"]',
            '[data-tab="overview"]',
        ],
        "row_selectors": {
            "net_profit": [
                '[class*="net-profit"]',
                'td:has-text("Net Profit")',
                'tr:has-text("Net Profit") td:last-child',
            ],
            "win_rate": [
                '[class*="win-rate"]',
                'td:has-text("Win Rate")',
                'tr:has-text("Win Rate") td:last-child',
            ],
            "profit_factor": [
                '[class*="profit-factor"]',
                'td:has-text("Profit Factor")',
                'tr:has-text("Profit Factor") td:last-child',
            ],
            "max_drawdown": [
                '[class*="max-drawdown"]',
                'td:has-text("Max Drawdown")',
                'tr:has-text("Max Drawdown") td:last-child',
            ],
        },
    },
    "backtest_trade_list": {
        "table_selectors": [
            'button:has-text("Trades")',
            '[class*="trades"] table',
            '[class*="list"] table',
            '[data-name="trades"]',
        ],
        "row_selectors": [
            '[class*="trades"] tbody tr',
            '[class*="list"] tbody tr',
            'table tbody tr',
        ],
    },
}


class ReconRunner:
    """Probes a running TradingView Desktop instance and writes
    ``recon_findings.json`` with the results."""

    def __init__(self, cdp: CDPConnectionManager) -> None:
        self.cdp = cdp
        self.findings: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tv_desktop_version": "unknown",
            "capabilities": {},
            "window_globals_found": [],
            "raw_dom_snapshots": {},
        }

    # ------------------------------------------------------------------
    # JS global probing (Path A)
    # ------------------------------------------------------------------

    async def dump_window_globals(self) -> list[str]:
        """Return window keys matching /trading|chart|study|widget|store|data/i."""
        code = """
        () => {
            const keys = Object.keys(window);
            const pattern = /trading|chart|study|widget|store|data/i;
            return keys.filter(k => pattern.test(k)).sort();
        }
        """
        result = await self.cdp.execute_js(code)
        self.findings["window_globals_found"] = result or []
        return result or []

    async def probe_known_paths(self) -> dict[str, Any]:
        """Try each known JS global path and record whether it exists + a sample repr."""
        results: dict[str, Any] = {}
        for path in KNOWN_JS_PATHS:
            try:
                code = f"""
                () => {{
                    try {{
                        const val = {path};
                        if (val === null || val === undefined) return {{found: false, sample: null}};
                        const sample = typeof val === 'object'
                            ? JSON.stringify(val).slice(0, 200)
                            : String(val).slice(0, 200);
                        return {{found: true, sample}};
                    }} catch(e) {{
                        return {{found: false, sample: null}};
                    }}
                }}
                """
                val = await self.cdp.execute_js(code)
                results[path] = val
            except Exception as exc:
                results[path] = {"found": False, "error": str(exc)}
        return results

    # ------------------------------------------------------------------
    # Network tap (Path B)
    # ------------------------------------------------------------------

    async def tap_network(self, duration_s: int = 120) -> list[dict[str, Any]]:
        """Log network events while the human interacts with the app.

        Prints sequenced instructions for the human to follow.
        Returns captured events grouped by time bucket.
        """
        instructions = [
            (0, 20, "Change the chart symbol to any different symbol now."),
            (20, 40, "Change the timeframe now (e.g. 1h → 4h → 1D)."),
            (40, 60, "Open Pine Editor, paste any indicator, click Add to Chart."),
            (60, 90, "Open Strategy Tester tab and let a backtest run to completion."),
            (90, 120, "Open the Trades List tab and scroll through it."),
        ]

        print("\n=== Network Tap — Follow the instructions below ===")
        print(f"Capturing for {duration_s} seconds...\n")

        captured: list[dict[str, Any]] = []

        async def _capture():
            async for event in self.cdp.listen_network():
                ts = event.get("params", {}).get("timestamp", 0)
                captured.append({"timestamp": ts, "event": event})

        # Start capture in background
        task = asyncio.create_task(_capture())

        # Print sequenced instructions
        for start_s, end_s, msg in instructions:
            print(f"[{start_s}s - {end_s}s] {msg}")
            print(f"  (waiting {end_s - start_s}s...)")
            await asyncio.sleep(end_s - start_s)

        # Stop capture
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        print(f"\nCaptured {len(captured)} network events.")
        return captured

    # ------------------------------------------------------------------
    # DOM structure probing (Path C)
    # ------------------------------------------------------------------

    async def dump_dom_structure(self, selectors: list[str], label: str) -> str:
        """Try each selector and return the outerHTML snippet of the first match."""
        for sel in selectors:
            try:
                code = f"""
                () => {{
                    const el = document.querySelector('{sel.replace("'", "\\'")}');
                    if (!el) return null;
                    let html = el.outerHTML;
                    if (html.length > 2000) html = html.slice(0, 2000) + '\\n...(truncated)';
                    return html;
                }}
                """
                result = await self.cdp.execute_js(code)
                if result:
                    snapshot = f"--- {sel} ---\n{result}"
                    self.findings.setdefault("raw_dom_snapshots", {})[label] = snapshot
                    return snapshot
            except Exception:
                continue

        self.findings.setdefault("raw_dom_snapshots", {})[label] = "(none found)"
        return "(none found)"

    async def probe_dom_capabilities(self) -> None:
        """Probe DOM structure for each capability and record working selectors."""
        caps = self.findings["capabilities"]

        # --- symbol_control ---
        working_symbol_selectors = []
        for sel in CAPABILITY_SELECTOR_CANDIDATES["symbol_control"]:
            try:
                code = f"document.querySelector('{sel.replace(chr(39), '\\\\' + chr(39))}') !== null"
                if await self.cdp.execute_js(code):
                    working_symbol_selectors.append(sel)
            except Exception:
                pass
        caps["symbol_control"] = {
            "path": "dom",
            "verified": len(working_symbol_selectors) > 0,
            "detail": {"selectors": working_symbol_selectors},
        }

        # --- timeframe_control ---
        working_tf_selectors = []
        for sel in CAPABILITY_SELECTOR_CANDIDATES["timeframe_control"]:
            try:
                code = f"document.querySelector('{sel.replace(chr(39), '\\\\' + chr(39))}') !== null"
                if await self.cdp.execute_js(code):
                    working_tf_selectors.append(sel)
            except Exception:
                pass
        caps["timeframe_control"] = {
            "path": "dom",
            "verified": len(working_tf_selectors) > 0,
            "detail": {"selectors": working_tf_selectors},
        }

        # --- indicator_apply ---
        indicator_detail = {"editor_selectors": [], "add_to_chart_selectors": []}
        for sel in CAPABILITY_SELECTOR_CANDIDATES["indicator_apply"]["editor_selectors"]:
            try:
                code = f"document.querySelector('{sel.replace(chr(39), '\\\\' + chr(39))}') !== null"
                if await self.cdp.execute_js(code):
                    indicator_detail["editor_selectors"].append(sel)
            except Exception:
                pass
        for sel in CAPABILITY_SELECTOR_CANDIDATES["indicator_apply"]["add_to_chart_selectors"]:
            try:
                code = f"document.querySelector('{sel.replace(chr(39), '\\\\' + chr(39))}') !== null"
                if await self.cdp.execute_js(code):
                    indicator_detail["add_to_chart_selectors"].append(sel)
            except Exception:
                pass
        caps["indicator_apply"] = {
            "path": "dom",
            "verified": False,  # verified by interactive test
            "detail": indicator_detail,
        }

        # --- indicator_remove ---
        working_remove_selectors = []
        for sel in CAPABILITY_SELECTOR_CANDIDATES["indicator_remove"]:
            try:
                code = f"document.querySelector('{sel.replace(chr(39), '\\\\' + chr(39))}') !== null"
                if await self.cdp.execute_js(code):
                    working_remove_selectors.append(sel)
            except Exception:
                pass
        caps["indicator_remove"] = {
            "path": "dom",
            "verified": False,
            "detail": {"context_menu_selectors": working_remove_selectors},
        }

        # --- ohlcv_read (assume network) ---
        caps["ohlcv_read"] = {
            "path": "network",
            "verified": False,
            "detail": {"ws_message_shape": "unknown", "match_pattern": "unknown"},
        }

        # --- backtest_run ---
        working_bt_selectors = []
        for sel in CAPABILITY_SELECTOR_CANDIDATES["strategy_tester"]:
            try:
                code = f"document.querySelector('{sel.replace(chr(39), '\\\\' + chr(39))}') !== null"
                if await self.cdp.execute_js(code):
                    working_bt_selectors.append(sel)
            except Exception:
                pass
        caps["backtest_run"] = {
            "path": "dom",
            "verified": False,
            "detail": {"tab_selectors": working_bt_selectors},
        }

        # --- backtest_summary ---
        bt_summary_detail = {
            "tab_selectors": CAPABILITY_SELECTOR_CANDIDATES["backtest_summary_overview"]["tab_selectors"],
            "row_selectors": CAPABILITY_SELECTOR_CANDIDATES["backtest_summary_overview"]["row_selectors"],
        }
        caps["backtest_summary"] = {
            "path": "dom",
            "verified": False,
            "detail": bt_summary_detail,
        }

        # --- backtest_trade_list ---
        caps["backtest_trade_list"] = {
            "path": "dom",
            "verified": False,
            "detail": CAPABILITY_SELECTOR_CANDIDATES["backtest_trade_list"],
        }

        # --- backtest_equity_curve ---
        caps["backtest_equity_curve"] = {
            "path": "dom",
            "verified": False,
            "detail": {"fallback": "numeric_table_if_present_else_null"},
        }

        # --- screenshot (always CDP) ---
        caps["screenshot"] = {
            "path": "cdp",
            "verified": True,
            "detail": {},
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self) -> dict[str, Any]:
        """Assemble all findings and write ``recon_findings.json``."""
        self.findings["generated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_findings()
        return self.findings

    def _write_findings(self) -> None:
        path = RECON_FINDINGS_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.findings, f, indent=2, default=str)
        print(f"\n✅ recon_findings.json written to: {path}")

    @staticmethod
    def diff_findings(old: dict, new: dict) -> str:
        """Compare two recon findings dicts and return a summary of changes."""
        lines: list[str] = []
        old_caps = old.get("capabilities", {})
        new_caps = new.get("capabilities", {})

        all_keys = set(old_caps) | set(new_caps)
        for key in sorted(all_keys):
            old_entry = old_caps.get(key, {})
            new_entry = new_caps.get(key, {})
            changes: list[str] = []

            old_path = old_entry.get("path")
            new_path = new_entry.get("path")
            if old_path != new_path:
                changes.append(f"path: {old_path} → {new_path}")

            old_ver = old_entry.get("verified")
            new_ver = new_entry.get("verified")
            if old_ver != new_ver:
                changes.append(f"verified: {old_ver} → {new_ver}")

            old_detail = old_entry.get("detail", {})
            new_detail = new_entry.get("detail", {})

            # Compare selector arrays
            for field in ("selectors", "editor_selectors", "add_to_chart_selectors",
                          "tab_selectors", "table_selectors", "row_selectors",
                          "context_menu_selectors"):
                old_sel = old_detail.get(field, [])
                new_sel = new_detail.get(field, [])
                if old_sel != new_sel:
                    changes.append(f"{field}: {len(old_sel)} → {len(new_sel)} entries")

            if changes:
                lines.append(f"  {key}: {'; '.join(changes)}")

        old_version = old.get("tv_desktop_version")
        new_version = new.get("tv_desktop_version")
        if old_version != new_version:
            lines.append(f"  tv_desktop_version: {old_version} → {new_version}")

        if not lines:
            return "  No changes detected."

        return "\n".join(lines)


async def run_recon(port: int = 8315) -> dict[str, Any]:
    """Convenience: launch, connect, run full recon, return findings."""
    cdp = CDPConnectionManager()
    cdp.launch(port=port)
    await cdp.connect(port=port)

    runner = ReconRunner(cdp)

    print("Dumping window globals...")
    globals_found = await runner.dump_window_globals()
    print(f"  Found {len(globals_found)} matching window keys.")

    print("Probing known JS paths...")
    js_results = await runner.probe_known_paths()
    js_found = [k for k, v in js_results.items() if isinstance(v, dict) and v.get("found")]
    print(f"  Found {len(js_found)} accessible JS paths: {js_found}")

    print("Probing DOM capabilities...")
    await runner.probe_dom_capabilities()

    print("Dumping DOM structure (Pine Editor)...")
    await runner.dump_dom_structure(
        ['.pine-editor', '[class*="pine"]', '[class*="editor"]', '[class*="source"]'],
        "pine_editor"
    )

    print("Dumping DOM structure (Strategy Tester)...")
    await runner.dump_dom_structure(
        ['[class*="strategy-tester"]', '[class*="backtest"]', '[class*="tester"]'],
        "strategy_tester"
    )

    findings = runner.report()
    await cdp.disconnect_async()
    return findings
