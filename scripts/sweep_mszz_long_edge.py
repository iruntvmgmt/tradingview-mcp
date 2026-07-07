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
EXIT_OPPOSITE_PATTERN = re.compile(r"exit_on_opposite = input\.bool\(.*?\n")
MAX_BARS_PATTERN = re.compile(r"max_bars_in_trade = input\.int\(.*?\n")

MAX_BARS = [15, 20, 30, 45, 60]
EXIT_OPPOSITE = [True, False]


def pine_bool(value: bool) -> str:
    return "true" if value else "false"


def make_source(base_source: str, max_bars: int, exit_on_opposite: bool) -> str:
    source = ENTRY_MODE_PATTERN.sub('entry_mode = "Fast + Medium Confluence"\n', base_source, count=1)
    source = TRADE_DIRECTION_PATTERN.sub('trade_direction = "Long Only"\n', source, count=1)
    source = EXIT_OPPOSITE_PATTERN.sub(f"exit_on_opposite = {pine_bool(exit_on_opposite)}\n", source, count=1)
    source = MAX_BARS_PATTERN.sub(f"max_bars_in_trade = {max_bars}\n", source, count=1)
    return source


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
    for _ in range(60):
        result = await server._cdp.execute_js(js)
        last = result.get("result", {}).get("value") or {"success": False}
        if last.get("success"):
            return last
        await asyncio.sleep(0.25)
    return last


async def run_variant(base_source: str, max_bars: int, exit_on_opposite: bool) -> dict:
    source = make_source(base_source, max_bars, exit_on_opposite)
    paste_ok = await paste_source(source)
    actual = await server._ctrl_pine.read("MS-ZZ-BO-V2-STRAT")
    source_ok = (
        'entry_mode = "Fast + Medium Confluence"' in actual
        and 'trade_direction = "Long Only"' in actual
        and f"exit_on_opposite = {pine_bool(exit_on_opposite)}" in actual
        and f"max_bars_in_trade = {max_bars}" in actual
    )
    update = await click_update_on_chart()
    await asyncio.sleep(6.0)
    summary = await server.call_tool("tv_get_backtest_summary", {})
    return {
        "max_bars": max_bars,
        "exit_on_opposite": exit_on_opposite,
        "paste_ok": paste_ok,
        "source_ok": source_ok,
        "update": update,
        "summary": json.loads(summary[0].text),
    }


async def main() -> None:
    base_source = SOURCE_PATH.read_text()
    results = []

    await server._cdp.connect()
    try:
        for exit_on_opposite in EXIT_OPPOSITE:
            for max_bars in MAX_BARS:
                print("VARIANT_START", max_bars, exit_on_opposite, flush=True)
                result = await run_variant(base_source, max_bars, exit_on_opposite)
                print("VARIANT_RESULT", json.dumps(result), flush=True)
                results.append(result)

        print("RESTORE_BASE_SOURCE", flush=True)
        await paste_source(base_source)
        restore_update = await click_update_on_chart()
        print("RESTORE_UPDATE", restore_update, flush=True)
    finally:
        await server._cdp.disconnect()

    print("RESULTS_JSON")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
