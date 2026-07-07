#!/usr/bin/env python3
"""Paste the local GT_VP strategy source into TradingView and compile it."""

import asyncio
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "TRADINGVIEW_INDICATORS" / "GT_VP_v9.9.6_STRAT" / "GT_VP_v9.9.6_STRAT.pine"
SCRIPT_NAME = "GT_VP_v9.9.6_STRAT"


async def main() -> None:
    source = SOURCE_PATH.read_text()
    subprocess.run(["pbcopy"], input=source, text=True, check=True)

    await server._cdp.connect()
    try:
        await server._cdp._send_command("Page.bringToFront", {})
        subprocess.run(["open", "-a", "TradingView"], check=False)
        await asyncio.sleep(1.0)

        await server._cdp.execute_js(
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

        paste_ok = await server._ctrl_pine._dom._paste_via_cgevent()
        print({"paste_ok": paste_ok})

        result = await server._cdp.execute_js(
            """
            (() => {
                const btn = document.querySelector('button[title="Update on chart"]')
                    || document.querySelector('button[title="Add to chart"]')
                    || document.querySelector('button[title="Save script"]');
                if (btn) {
                    btn.click();
                    return {success: true, title: btn.getAttribute('title')};
                }
                return {success: false};
            })()
            """
        )
        print({"update": result.get("result", {}).get("value")})

        await asyncio.sleep(2.0)
        errors = await server._ctrl_pine.read_compile_errors()
        print({"errors": errors})

        actual = (await server._ctrl_pine.read(SCRIPT_NAME)).replace("\r\n", "\n")
        expected = source.replace("\r\n", "\n")
        print({
            "source_match": actual == expected,
            "has_strategy_toggle": "strategy_enable_s10_lvn" in actual,
            "chars": len(actual),
        })
    finally:
        await server._cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
