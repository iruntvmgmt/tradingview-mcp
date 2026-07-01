"""Chrome DevTools Protocol transport for TradingView Desktop control.

Launches TV Desktop with a remote debugging port, connects via WebSocket,
and provides low-level CDP primitives (Runtime.evaluate, Network domain,
Input automation) that all backends and controllers build on.
"""

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from httpx import ConnectError as HttpxConnectError, HTTPError as HttpxHTTPError
import websockets

from core.services.errors import ConnectionError

logger = logging.getLogger(__name__)

# Map of TV Desktop versions to known launch paths
# Users can override via TV_DESKTOP_PATH env var or the launch() argument.
DEFAULT_TV_PATHS: dict[str, str] = {
    "darwin": "/Applications/TradingView.app/Contents/MacOS/TradingView",
    "linux": "tradingview",
    "win32": r"C:\Program Files\TradingView\TradingView.exe",
}

CDP_WS_URL = "ws://127.0.0.1:{port}"
CDP_HTTP_URL = "http://127.0.0.1:{port}/json"
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2.0
DEFAULT_DEBUG_PORT = 8315


class CDPConnection:
    """Manages the WebSocket connection to TradingView Desktop's CDP endpoint."""

    def __init__(self, debug_port: int = DEFAULT_DEBUG_PORT):
        self._port = debug_port
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._target_id: str | None = None
        self._proc: subprocess.Popen | None = None
        self._network_enabled = False
        self._message_id = 0
        self._pending_responses: dict[int, asyncio.Future] = {}
        self._network_events: list[dict] = []
        self._reader_task: asyncio.Task | None = None

    # ── Lifecycle ────────────────────────────────────────────────

    async def launch(self, app_path: str | None = None) -> None:
        """Launch TradingView Desktop with --remote-debugging-port.

        If *app_path* is ``None``, attempts to auto-detect based on the
        current OS.  Raises ``ConnectionError`` if the app can't be found
        or fails to start.
        """
        if app_path is None:
            import sys
            platform_key = sys.platform
            if platform_key == "darwin":
                # Common macOS locations
                candidates = [
                    "/Applications/TradingView.app/Contents/MacOS/TradingView",
                    str(Path.home() / "Applications/TradingView.app/Contents/MacOS/TradingView"),
                ]
            elif platform_key == "linux":
                candidates = ["tradingview"]
            elif platform_key == "win32":
                candidates = [
                    r"C:\Program Files\TradingView\TradingView.exe",
                    r"C:\Program Files (x86)\TradingView\TradingView.exe",
                ]
            else:
                candidates = []

            for c in candidates:
                if Path(c).exists() or platform_key == "linux":
                    app_path = c
                    break

        if not app_path:
            raise ConnectionError(
                "TradingView Desktop not found. Provide app_path or set TV_DESKTOP_PATH.",
                details={"port": self._port},
            )

        try:
            self._proc = subprocess.Popen(
                [app_path, f"--remote-debugging-port={self._port}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Launched TV Desktop (pid=%s) on port %s", self._proc.pid, self._port)
        except FileNotFoundError:
            raise ConnectionError(
                f"Executable not found at {app_path}",
                details={"path": app_path, "port": self._port},
            )

    async def connect(self) -> None:
        """Open a WebSocket to the CDP endpoint of the main renderer target.

        Retries up to ``MAX_RETRIES`` times with ``RETRY_DELAY_SEC`` backoff
        to give TV Desktop time to finish starting up.
        """
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                target = await self._find_main_target()
                if target is None:
                    raise ConnectionError(
                        "No main renderer target found",
                        details={"port": self._port, "attempt": attempt},
                    )
                self._target_id = target["id"]
                ws_url = target.get("webSocketDebuggerUrl")
                if not ws_url:
                    ws_url = f"{CDP_WS_URL.format(port=self._port)}/devtools/page/{target['id']}"
                self._ws = await websockets.connect(ws_url, max_size=2**24)
                self._reader_task = asyncio.create_task(self._read_loop())
                logger.info("Connected to CDP target %s", self._target_id)
                return
            except (OSError, ConnectionError, websockets.WebSocketException, HttpxConnectError, HttpxHTTPError) as exc:
                last_exc = exc
                logger.warning("CDP connect attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY_SEC)
        raise ConnectionError(
            f"Could not connect to CDP after {MAX_RETRIES} attempts",
            details={"port": self._port, "last_error": str(last_exc)},
        )

    async def disconnect(self) -> None:
        """Close the WebSocket and kill the browser process if we launched it."""
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._target_id = None
        self._network_enabled = False
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
            logger.info("TV Desktop process terminated")

    # ── CDP Commands ─────────────────────────────────────────────

    async def execute_js(self, expression: str,
                         return_by_value: bool = True) -> dict[str, Any]:
        """Evaluate *expression* in the renderer context via ``Runtime.evaluate``.

        Returns the CDP result dict.  Raises ``ConnectionError`` on transport
        failure.
        """
        result = await self._send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value,
        })
        if "exceptionDetails" in result:
            logger.warning("JS exception in %r: %s",
                           expression[:80], result["exceptionDetails"])
        return result

    async def list_targets(self) -> list[dict]:
        """Enumerate all available CDP targets via ``Target.getTargets``."""
        result = await self._send_command("Target.getTargets", {})
        return result.get("targetInfos", [])

    async def select_main_renderer_target(self) -> str | None:
        """Auto-select the main page-level renderer target.

        Prefers targets whose title/url suggests the main TradingView window
        (not an extension popup, DevTools window, or service worker).
        Returns the target ID or ``None``.
        """
        targets = await self.list_targets()
        # Score targets: the main page is typically 'page' type with tradingview url
        candidates = []
        for t in targets:
            url = (t.get("url") or "").lower()
            title = (t.get("title") or "").lower()
            ttype = t.get("type", "")
            if ttype != "page":
                continue
            score = 0
            if "tradingview" in url or "tradingview" in title:
                score += 3
            if url.startswith("http"):
                score += 1
            if "about:blank" in url:
                score -= 1
            candidates.append((score, t.get("targetId", t.get("id"))))
        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[0])
        best_id = candidates[0][1]
        if self._target_id != best_id:
            self._target_id = best_id
            logger.info("Selected main renderer target %s", best_id)
        return best_id

    async def listen_network(self, enable: bool = True) -> None:
        """Enable or disable the CDP ``Network`` domain."""
        if enable:
            await self._send_command("Network.enable", {})
            self._network_enabled = True
            logger.info("Network domain enabled")
        else:
            await self._send_command("Network.disable", {})
            self._network_enabled = False
            logger.info("Network domain disabled")

    def get_network_events(self) -> list[dict]:
        """Return buffered network events collected since the last call."""
        events = list(self._network_events)
        self._network_events.clear()
        return events

    # ── Health ──────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """Ping the CDP connection and return status."""
        if not self._ws:
            return {"connected": False, "target_id": None}
        try:
            result = await self.execute_js("1+1")
            return {
                "connected": True,
                "target_id": self._target_id,
                "eval_ok": result.get("result", {}).get("value") == 2,
            }
        except Exception as exc:
            return {"connected": True, "target_id": self._target_id, "eval_ok": False, "error": str(exc)}

    # ── Internals ────────────────────────────────────────────────

    async def _find_main_target(self) -> dict | None:
        """Query the HTTP discovery endpoint for available page targets."""
        url = CDP_HTTP_URL.format(port=self._port)
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            resp.raise_for_status()
            targets: list[dict] = resp.json()
        # Prefer a real page target over about:blank / extensions
        for t in targets:
            ttype = t.get("type", "")
            url_val = (t.get("url") or "").lower()
            title = (t.get("title") or "").lower()
            if ttype == "page" and ("tradingview" in url_val or "tradingview" in title or url_val.startswith("http")):
                return t
        # Fallback: first page target
        for t in targets:
            if t.get("type") == "page":
                return t
        return None

    async def _send_command(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a CDP command and wait for its response."""
        if not self._ws:
            raise ConnectionError("Not connected to CDP", details={"method": method})
        self._message_id += 1
        msg_id = self._message_id
        payload = json.dumps({"id": msg_id, "method": method, "params": params})
        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending_responses[msg_id] = future
        await self._ws.send(payload)
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending_responses.pop(msg_id, None)
            raise ConnectionError(
                f"CDP command timed out: {method}",
                details={"method": method, "timeout": 30},
            )
        if "error" in result:
            err = result["error"]
            raise ConnectionError(
                f"CDP error in {method}: {err.get('message', 'unknown')}",
                details={"method": method, "code": err.get("code"), "message": err.get("message")},
            )
        return result.get("result", {})

    async def _read_loop(self) -> None:
        """Continuously read WebSocket messages and route them."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending_responses:
                    fut = self._pending_responses.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
                elif msg.get("method", "").startswith("Network."):
                    self._network_events.append(msg)
        except websockets.WebSocketException:
            pass
        except asyncio.CancelledError:
            pass
