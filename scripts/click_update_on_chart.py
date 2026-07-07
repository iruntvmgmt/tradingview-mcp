import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


async def main() -> None:
    await server._cdp.connect()
    try:
        js = """
        (() => {
            const btn = document.querySelector('button[title="Update on chart"]');
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        })()
        """
        result = await server._cdp.execute_js(js)
        print(result.get("result", {}).get("value"))
        await asyncio.sleep(2)
    finally:
        await server._cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
