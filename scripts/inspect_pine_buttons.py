import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


async def main() -> None:
    await server._cdp.connect()
    try:
        await server._cdp._send_command("Page.bringToFront", {})
        js = """
        (() => Array.from(document.querySelectorAll('button')).map((b, i) => {
            const r = b.getBoundingClientRect();
            return {
                i,
                title: b.getAttribute('title'),
                aria: b.getAttribute('aria-label'),
                text: b.innerText,
                visible: !!(b.offsetWidth || b.offsetHeight),
                rect: { x: r.x, y: r.y, w: r.width, h: r.height }
            };
        }).filter(x => x.visible && (String(x.title) + String(x.aria) + String(x.text)).match(/chart|save|update|add|publish/i)))()
        """
        result = await server._cdp.execute_js(js)
        print(json.dumps(result.get("result", {}).get("value"), indent=2))
    finally:
        await server._cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
