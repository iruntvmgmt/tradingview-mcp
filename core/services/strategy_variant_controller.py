"""Generic strategy variant runner for TradingView Desktop.

This controller promotes the ad-hoc Pine variant workflow into reusable MCP
tools.  It intentionally stays above the existing controllers: it edits the
Pine editor, clicks Update/Add on chart, reads Strategy Tester summary, and
optionally restores the original source.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import subprocess
from pathlib import Path
from typing import Any


class StrategyVariantController:
    """Run one-off Pine source variants and parameter sweeps."""

    def __init__(self, cdp, pine_controller, backtest_controller, chart_controller):
        self._cdp = cdp
        self._pine = pine_controller
        self._backtest = backtest_controller
        self._chart = chart_controller

    async def run_variant(
        self,
        script_name: str,
        source: str | None = None,
        source_path: str | None = None,
        replacements: list[dict[str, Any]] | None = None,
        restore: bool = True,
        wait_seconds: float = 5.0,
        screenshot_path: str | None = None,
    ) -> dict[str, Any]:
        """Compile/test a single Pine variant.

        ``replacements`` entries support:
        - ``pattern``: text or regex pattern to replace
        - ``replacement``: replacement string
        - ``regex``: defaults to true
        - ``count``: defaults to 1
        """
        base_source = self._source_from_args(source, source_path)
        original_editor_source = await self._pine.read(script_name) if restore else None
        variant_source = self._apply_replacements(base_source, replacements or [])

        paste_ok = await self._paste_source(variant_source)
        actual = await self._pine.read(script_name)
        source_match = self._normalize(actual) == self._normalize(variant_source)

        update = await self._update_on_chart()
        await asyncio.sleep(wait_seconds)
        summary = await self._backtest.get_performance_summary()

        screenshot_written = None
        if screenshot_path:
            data = await self._chart.screenshot()
            out = Path(screenshot_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            screenshot_written = str(out)

        restore_result = None
        if restore and original_editor_source is not None:
            restore_paste_ok = await self._paste_source(original_editor_source)
            restore_update = await self._update_on_chart()
            restored = await self._pine.read(script_name)
            restore_result = {
                "paste_ok": restore_paste_ok,
                "update": restore_update,
                "source_match": self._normalize(restored) == self._normalize(original_editor_source),
            }

        return {
            "script_name": script_name,
            "paste_ok": paste_ok,
            "source_match": source_match,
            "update": update,
            "summary": summary,
            "screenshot_path": screenshot_written,
            "restore": restore_result,
        }

    async def sweep(
        self,
        script_name: str,
        variants: list[dict[str, Any]],
        source: str | None = None,
        source_path: str | None = None,
        restore: bool = True,
        wait_seconds: float = 5.0,
        screenshot_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run multiple variants, restoring once at the end by default."""
        base_source = self._source_from_args(source, source_path)
        original_editor_source = await self._pine.read(script_name) if restore else None
        results: list[dict[str, Any]] = []

        try:
            for index, variant in enumerate(variants):
                replacements = variant.get("replacements", [])
                label = variant.get("label", f"variant_{index + 1}")
                screenshot_path = None
                if screenshot_dir:
                    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_")
                    screenshot_path = str(Path(screenshot_dir) / f"{index + 1:02d}_{safe_label}.png")

                variant_source = self._apply_replacements(base_source, replacements)
                paste_ok = await self._paste_source(variant_source)
                actual = await self._pine.read(script_name)
                source_match = self._normalize(actual) == self._normalize(variant_source)
                update = await self._update_on_chart()
                await asyncio.sleep(float(variant.get("wait_seconds", wait_seconds)))
                summary = await self._backtest.get_performance_summary()

                screenshot_written = None
                if screenshot_path:
                    data = await self._chart.screenshot()
                    out = Path(screenshot_path)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
                    screenshot_written = str(out)

                results.append(
                    {
                        "label": label,
                        "paste_ok": paste_ok,
                        "source_match": source_match,
                        "update": update,
                        "summary": summary,
                        "screenshot_path": screenshot_written,
                        "metadata": variant.get("metadata", {}),
                    }
                )
        finally:
            if restore and original_editor_source is not None:
                restore_paste_ok = await self._paste_source(original_editor_source)
                restore_update = await self._update_on_chart()
                restored = await self._pine.read(script_name)
                restore_result = {
                    "paste_ok": restore_paste_ok,
                    "update": restore_update,
                    "source_match": self._normalize(restored) == self._normalize(original_editor_source),
                }
                for result in results:
                    result["restore"] = restore_result

        return results

    async def update_chart_reliable(self) -> dict[str, Any]:
        """Wait for and click TradingView's Update/Add on chart button."""
        return await self._update_on_chart()

    def _source_from_args(self, source: str | None, source_path: str | None) -> str:
        if source is not None:
            return source
        if source_path:
            return Path(source_path).read_text()
        raise ValueError("Either source or source_path is required")

    def _apply_replacements(self, source: str, replacements: list[dict[str, Any]]) -> str:
        result = source
        for item in replacements:
            pattern = item.get("pattern")
            replacement = item.get("replacement")
            if pattern is None or replacement is None:
                raise ValueError("Each replacement requires pattern and replacement")
            count = int(item.get("count", 1))
            if item.get("regex", True):
                result = re.sub(str(pattern), str(replacement), result, count=count)
            else:
                result = result.replace(str(pattern), str(replacement), count)
        return result

    async def _paste_source(self, source: str) -> bool:
        """Paste source into the focused Pine editor using the robust path."""
        try:
            subprocess.run(["pbcopy"], input=source, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Non-macOS fallback through page Clipboard API.
            b64 = base64.b64encode(source.encode("utf-8")).decode("ascii")
            await self._cdp.execute_js(
                f"""
                (async () => {{
                    const decoded = new TextDecoder().decode(Uint8Array.from(atob("{b64}"), c => c.charCodeAt(0)));
                    await navigator.clipboard.writeText(decoded);
                    return true;
                }})()
                """,
                await_promise=True,
            )

        await self._cdp._send_command("Page.bringToFront", {})
        try:
            subprocess.run(["open", "-a", "TradingView"], check=False)
        except FileNotFoundError:
            pass
        await asyncio.sleep(1.0)
        await self._focus_monaco_textarea()

        # Reuse the controller's proven accessibility-backed paste helper when present.
        dom = getattr(self._pine, "_dom", None)
        if dom and hasattr(dom, "_paste_via_cgevent"):
            pasted = await dom._paste_via_cgevent()
            if pasted:
                return True
        if dom and hasattr(dom, "_paste_via_cdp"):
            await dom._paste_via_cdp()
            return True
        return False

    async def _focus_monaco_textarea(self) -> None:
        await self._cdp.execute_js(
            """
            (() => {
                const all = document.querySelectorAll('.monaco-editor textarea.inputarea');
                for (let i = 0; i < all.length; i++) {
                    if (all[i].offsetWidth > 0) {
                        all[i].focus();
                        all[i].select();
                        return 'focused';
                    }
                }
                return 'no-textarea';
            })()
            """
        )

    async def _update_on_chart(self) -> dict[str, Any]:
        js = """
        (() => {
            const btn = document.querySelector('button[title="Update on chart"]')
                || document.querySelector('button[title="Add to chart"]')
                || document.querySelector('button[title="Save script"]');
            if (btn) {
                btn.click();
                return { success: true, title: btn.getAttribute('title') };
            }
            return { success: false };
        })()
        """
        last = {"success": False}
        for _ in range(60):
            result = await self._cdp.execute_js(js)
            last = result.get("result", {}).get("value") or {"success": False}
            if last.get("success"):
                return last
            await asyncio.sleep(0.25)
        return last

    def _normalize(self, value: str) -> str:
        return value.replace("\r\n", "\n")
