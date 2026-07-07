import asyncio
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "TRADINGVIEW_INDICATORS" / "MULTI_SPEED_ZIGZAG" / "MS-ZZ-BO-V2-STRAT.pine"
ENTRY_MODE_PATTERN = re.compile(r"entry_mode = input\.string\(.*?\n")
TRADE_DIRECTION_PATTERN = re.compile(r"trade_direction = input\.string\(.*?\n")
MAX_BARS_PATTERN = re.compile(r"max_bars_in_trade = input\.int\(.*?\n")


async def paste_source(source: str) -> bool:
    subprocess.run(["pbcopy"], input=source, text=True, check=True)
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
    return await server._ctrl_pine._dom._paste_via_cgevent()


async def click_update_on_chart() -> dict:
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
    for _ in range(40):
        result = await server._cdp.execute_js(js)
        last = result.get("result", {}).get("value") or {"success": False}
        if last.get("success"):
            return last
        await asyncio.sleep(0.25)
    return last


async def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "Medium Breakout"
    direction = sys.argv[2] if len(sys.argv) > 2 else None
    max_bars = int(sys.argv[3]) if len(sys.argv) > 3 else None
    source = SOURCE_PATH.read_text()
    mode_source = ENTRY_MODE_PATTERN.sub(f'entry_mode = "{mode}"\n', source, count=1)
    if direction:
        mode_source = TRADE_DIRECTION_PATTERN.sub(f'trade_direction = "{direction}"\n', mode_source, count=1)
    if max_bars:
        mode_source = MAX_BARS_PATTERN.sub(f"max_bars_in_trade = {max_bars}\n", mode_source, count=1)

    await server._cdp.connect()
    try:
        paste_ok = await paste_source(mode_source)
        print("PASTE", paste_ok, flush=True)

        actual = await server._ctrl_pine.read("MS-ZZ-BO-V2-STRAT")
        mode_present = f'entry_mode = "{mode}"' in actual
        direction_present = True if not direction else f'trade_direction = "{direction}"' in actual
        max_bars_present = True if not max_bars else f"max_bars_in_trade = {max_bars}" in actual
        print("MODE_PRESENT", mode_present, flush=True)
        print("DIRECTION_PRESENT", direction_present, flush=True)
        print("MAX_BARS_PRESENT", max_bars_present, flush=True)

        update_result = await click_update_on_chart()
        print("UPDATE", update_result, flush=True)

        await asyncio.sleep(5.0)
        summary = await server.call_tool("tv_get_backtest_summary", {})
        print("SUMMARY", summary[0].text, flush=True)

        data = await server._ctrl_chart.screenshot()
        out = pathlib.Path("/private/tmp/mszz-mode-test.png")
        out.write_bytes(data)
        print("SCREENSHOT", str(out), flush=True)

        print(
            "RESULTS_JSON",
            json.dumps(
                {
                    "mode": mode,
                    "direction": direction,
                    "max_bars": max_bars,
                    "paste_ok": paste_ok,
                    "mode_present": mode_present,
                    "direction_present": direction_present,
                    "max_bars_present": max_bars_present,
                    "update": update_result,
                    "summary": json.loads(summary[0].text),
                    "screenshot": str(out),
                },
                indent=2,
            ),
            flush=True,
        )
    finally:
        await server._cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
