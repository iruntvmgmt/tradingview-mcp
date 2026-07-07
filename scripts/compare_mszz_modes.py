import asyncio
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


MODES = [
    "Fast Breakout",
    "Fast + Medium Confluence",
    "Medium Breakout",
    "Medium + Slow Context",
    "Slow Breakout",
]

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "TRADINGVIEW_INDICATORS" / "MULTI_SPEED_ZIGZAG" / "MS-ZZ-BO-V2-STRAT.pine"
ENTRY_MODE_PATTERN = re.compile(r"entry_mode = input\.string\(.*?\n")


async def paste_source(source: str) -> bool:
    subprocess.run(["pbcopy"], input=source, text=True, check=True)
    await server._cdp._send_command("Page.bringToFront", {})
    subprocess.run(["open", "-a", "TradingView"], check=False)
    await asyncio.sleep(0.8)
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
        const titles = ['Update on chart', 'Add to chart', 'Save script'];
        for (const title of titles) {
            const btn = document.querySelector('button[title="' + title + '"]');
            if (btn) {
                btn.click();
                return { success: true, method: title };
            }
        }
        return { success: false, method: 'button_not_found' };
    })()
    """
    for _ in range(20):
        result = await server._cdp.execute_js(js)
        value = result.get("result", {}).get("value")
        if value and value.get("success"):
            return value
        await asyncio.sleep(0.25)
    return {"success": False, "method": "button_not_found"}


async def main() -> None:
    base_source = SOURCE_PATH.read_text()
    results = []

    await server._cdp.connect()
    try:
        for mode in MODES:
            print("MODE_START", mode, flush=True)
            mode_source = ENTRY_MODE_PATTERN.sub(f'entry_mode = "{mode}"\n', base_source, count=1)
            paste_ok = await paste_source(mode_source)
            print("PASTE", paste_ok, flush=True)
            compile_result = await click_update_on_chart()
            print("UPDATE", compile_result, flush=True)
            await asyncio.sleep(3.0)
            summary = await server.call_tool("tv_get_backtest_summary", {})
            summary_text = summary[0].text
            print("SUMMARY", summary_text, flush=True)
            results.append(
                {
                    "mode": mode,
                    "compile": compile_result,
                    "summary": json.loads(summary_text),
                }
            )
    finally:
        print("RESTORE_BASE_SOURCE", flush=True)
        paste_ok = await paste_source(base_source)
        print("RESTORE_PASTE", paste_ok, flush=True)
        restore_result = await click_update_on_chart()
        print("RESTORE_UPDATE", restore_result, flush=True)
        await server._cdp.disconnect()

    print("RESULTS_JSON")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
