import asyncio
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "TRADINGVIEW_INDICATORS" / "MULTI_SPEED_ZIGZAG" / "MS-ZZ-BO-V2-STRAT.pine"


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
        print("PASTE", paste_ok)
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
        result = await server._cdp.execute_js(js)
        print("UPDATE", result.get("result", {}).get("value"))
        await asyncio.sleep(2.0)
        actual = (await server._ctrl_pine.read("MS-ZZ-BO-V2-STRAT")).replace(chr(13) + chr(10), chr(10))
        expected = source.replace(chr(13) + chr(10), chr(10))
        print({"restored_source_match": actual == expected})
    finally:
        await server._cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
