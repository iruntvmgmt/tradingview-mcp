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
QUALITY_PATTERN = re.compile(r"min_quality_score = input\.int\(.*?\n")
WICK_BUFFER_PATTERN = re.compile(r"wick_buffer_atr = input\.float\(.*?\n")

QUALITY_VALUES = [3, 5, 7]
WICK_VALUES = [0.2, 0.3, 0.5]


def make_source(base_source: str, quality: int, wick_buffer: float) -> str:
    source = ENTRY_MODE_PATTERN.sub('entry_mode = "Fast + Medium Confluence"\n', base_source, count=1)
    source = TRADE_DIRECTION_PATTERN.sub('trade_direction = "Long Only"\n', source, count=1)
    source = EXIT_OPPOSITE_PATTERN.sub("exit_on_opposite = true\n", source, count=1)
    source = MAX_BARS_PATTERN.sub("max_bars_in_trade = 30\n", source, count=1)
    source = QUALITY_PATTERN.sub(f"min_quality_score = {quality}\n", source, count=1)
    source = WICK_BUFFER_PATTERN.sub(f"wick_buffer_atr = {wick_buffer}\n", source, count=1)
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


async def run_variant(base_source: str, quality: int, wick_buffer: float) -> dict:
    source = make_source(base_source, quality, wick_buffer)
    paste_ok = await paste_source(source)
    actual = await server._ctrl_pine.read("MS-ZZ-BO-V2-STRAT")
    source_ok = (
        'entry_mode = "Fast + Medium Confluence"' in actual
        and 'trade_direction = "Long Only"' in actual
        and "exit_on_opposite = true" in actual
        and "max_bars_in_trade = 30" in actual
        and f"min_quality_score = {quality}" in actual
        and f"wick_buffer_atr = {wick_buffer}" in actual
    )
    update = await click_update_on_chart()
    await asyncio.sleep(6.0)
    summary = await server.call_tool("tv_get_backtest_summary", {})
    return {
        "quality": quality,
        "wick_buffer": wick_buffer,
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
        for quality in QUALITY_VALUES:
            for wick_buffer in WICK_VALUES:
                print("VARIANT_START", quality, wick_buffer, flush=True)
                result = await run_variant(base_source, quality, wick_buffer)
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
