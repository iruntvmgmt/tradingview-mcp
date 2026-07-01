"""
CDP (Chrome DevTools Protocol) Connection Manager for TradingView Desktop.

Launches TV Desktop with --remote-debugging-port, connects via Playwright CDP,
and provides execute_js / listen_network primitives for all backend impls.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
from typing import Any, AsyncIterator, Callable

from playwright.async_api import async_playwright

from tradingview_mcp.core.services.errors import ConnectionSetupError, NetworkCaptureError


DEFAULT_CDP_PORT = 8315
CONNECT_RETRIES = [0.25, 0.5, 1.0, 2.0, 4.0]


def _resolve_tv_app_path() -> str:
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/TradingView.app/Contents/MacOS/TradingView",
            os.path.expanduser("~/Applications/TradingView.app/Contents/MacOS/TradingView"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        raise ConnectionSetupError(
            "TradingView Desktop not found at /Applications/TradingView.app."
        )
    elif system == "Windows":
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\TradingView\TradingView.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\TradingView\TradingView.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        raise ConnectionSetupError("TradingView Desktop not found.")
    else:
        candidates = ["/usr/bin/tradingview", "/usr/local/bin/tradingview"]
        for p in candidates:
            if os.path.exists(p):
                return p
        raise ConnectionSetupError(f"Unsupported platform: {system}")


class CDPConnectionManager:
    """Manages CDP connection lifecycle to TradingView Desktop.

    Usage::

        cdp = CDPConnectionManager()
        cdp.launch()
        await cdp.connect()
        result = await cdp.execute_js("1+1")
        await cdp.disconnect_async()
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._target_id: str | None = None
        self._port: int = DEFAULT_CDP_PORT
        self._launched: bool = False
        self._connected: bool = False

    # ------------------------------------------------------------------
    def launch(self, path: str | None = None, port: int = DEFAULT_CDP_PORT) -> None:
        """Launch TV Desktop with ``--remote-debugging-port={port}``."""
        if self._launched or self._process is not None:
            raise ConnectionSetupError("Already launched — call disconnect() first.")
        app_path = path or _resolve_tv_app_path()
        self._port = port
        try:
            self._process = subprocess.Popen(
                [app_path, f"--remote-debugging-port={port}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise ConnectionSetupError(f"Binary not found: {app_path}")
        except Exception as exc:
            raise ConnectionSetupError(f"Launch failed: {exc}")
        self._launched = True

    async def connect(self, port: int | None = None, retries: int | None = None) -> None:
        """Connect to running TV Desktop via CDP with exponential backoff."""
        if self._connected:
            return
        self._port = port or self._port
        schedule = CONNECT_RETRIES[:retries] if retries else CONNECT_RETRIES
        last_exc = None
        cdp_url = f"http://127.0.0.1:{self._port}"
        for delay in schedule:
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                self._playwright = await async_playwright().__aenter__()
                self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
                self._connected = True
                return
            except Exception as exc:
                last_exc = exc
                if self._playwright:
                    try:
                        await self._playwright.__aexit__(None, None, None)
                    except Exception:
                        pass
                    self._playwright = None
        raise ConnectionSetupError(
            "TV Desktop not exposing CDP port. Run: scripts/launch_tv_desktop.sh"
        ) from last_exc

    async def _ensure_page(self):
        if self._page:
            return self._page
        if not self._browser:
            raise ConnectionSetupError("Not connected.")
        ctx = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        self._context = ctx
        pages = ctx.pages
        self._page = pages[0] if pages else await ctx.new_page()
        return self._page

    async def list_targets(self) -> list[dict[str, Any]]:
        """Enumerate CDP targets via CDP Target.getTargets."""
        page = await self._ensure_page()
        session = await self._context.new_cdp_session(page)
        try:
            result = await session.send("Target.getTargets")
            return [
                {"id": t.get("targetId", ""), "type": t.get("type", "unknown"),
                 "title": t.get("title", ""), "url": t.get("url", "")}
                for t in result.get("targetInfos", [])
            ]
        except Exception:
            return [{"id": str(id(p)), "type": "page", "title": await p.title(), "url": p.url}
                    for p in self._context.pages]

    async def select_main_renderer_target(self) -> str:
        """Pick the TradingView main window from CDP targets."""
        targets = await self.list_targets()
        filtered = [
            t for t in targets
            if t["type"] not in ("other", "background_page")
            and not t["url"].startswith("devtools://")
        ]
        if len(filtered) == 1:
            self._target_id = filtered[0]["id"]
            return self._target_id
        if len(filtered) == 0:
            raise ConnectionSetupError("No viable renderer target found.")
        for t in filtered:
            if "tradingview" in t["title"].lower() or "tradingview" in t["url"].lower():
                self._target_id = t["id"]
                return self._target_id
        raise ConnectionSetupError(
            f"Ambiguous targets ({len(filtered)}):\n" +
            "\n".join(f"  [{t['type']}] {t['title']}" for t in filtered)
        )

    async def execute_js(self, code: str) -> Any:
        """Evaluate JS in the selected renderer target."""
        page = await self._ensure_page()
        return await page.evaluate(code)

    async def listen_network(self, filter_fn: Callable | None = None) -> AsyncIterator[dict]:
        """Yield CDP Network events matching filter_fn via Playwright events."""
        page = await self._ensure_page()
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def _on_req(req):
            e = {"method": "Network.requestWillBeSent", "params": {
                "request": {"url": req.url, "method": req.method,
                            "headers": dict(req.headers), "postData": req.post_data},
                "type": req.resource_type}}
            if filter_fn is None or filter_fn(e):
                await queue.put(e)

        async def _on_res(res):
            e = {"method": "Network.responseReceived", "params": {
                "response": {"url": res.url, "status": res.status, "headers": dict(res.headers)}}}
            if filter_fn is None or filter_fn(e):
                await queue.put(e)

        page.on("request", _on_req)
        page.on("response", _on_res)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            page.remove_listener("request", _on_req)
            page.remove_listener("response", _on_res)

    async def disconnect_async(self) -> None:
        """Close CDP connection and kill TV Desktop process."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.__aexit__(None, None, None)
            except Exception:
                pass
            self._playwright = None
        self._page = self._context = self._target_id = None
        self._connected = self._launched = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def disconnect(self) -> None:
        """Sync stub — use disconnect_async() for proper cleanup."""
        self._connected = self._launched = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_launched(self) -> bool:
        return self._launched

    @property
    def port(self) -> int:
        return self._port
