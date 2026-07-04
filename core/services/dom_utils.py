"""High-level DOM automation helpers built on CDP primitives.

Provides selector resolution with fallback arrays, click/type/extract
primitives, and utilities for waiting, scrolling, and canvas-position
clicking used across all domain backends.
"""

import asyncio
import json
import logging
import re
from typing import Any

from core.services.errors import SelectorResolutionError

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 0.3

# macOS keycodes: a=0, c=8, v=9
_KCD_A = 0
_KCD_C = 8
_KCD_V = 9


def _get_tv_pid() -> int | None:
    """Return TradingView Desktop's PID, or None if not running."""
    try:
        from Cocoa import NSWorkspace
        ws = NSWorkspace.sharedWorkspace()
        for app in ws.runningApplications():
            if app.bundleIdentifier() == 'com.tradingview.tradingviewapp.desktop':
                return app.processIdentifier()
        return None
    except Exception:
        return None


def _has_accessibility_permission() -> bool:
    """Check if this process has macOS Accessibility permission."""
    try:
        from HIServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except ImportError:
        return False


def _send_cmd_key(pid: int, keycode: int) -> None:
    """Send Cmd+<key> to *pid* via Quartz CGEventPostToPid.

    This is the ONLY mechanism confirmed to trigger Monaco's paste/copy
    handlers on macOS.  CDP ``Input.dispatchKeyEvent`` with Meta modifier
    does NOT generate ClipboardEvents on macOS.  See ADR-0006.
    """
    from Quartz import (
        CGEventCreateKeyboardEvent, CGEventPostToPid, CGEventSetFlags,
    )
    CMD_FLAG = 0x100000  # kCGEventFlagMaskCommand = 1 << 20

    down = CGEventCreateKeyboardEvent(None, keycode, True)
    CGEventSetFlags(down, CMD_FLAG)
    CGEventPostToPid(pid, down)

    up = CGEventCreateKeyboardEvent(None, keycode, False)
    CGEventSetFlags(up, CMD_FLAG)
    CGEventPostToPid(pid, up)


class DomUtils:
    """Stateless DOM helper — all methods operate via the injected CDP connection."""

    def __init__(self, cdp):
        self._cdp = cdp

    # ── Selector Resolution ──────────────────────────────────────

    async def resolve_selector(self, selectors: list[str],
                               timeout: float = 5.0) -> str | None:
        """Try each CSS selector in *selectors* until one matches the DOM.

        Returns the first matching selector string, or ``None`` if none
        matched within *timeout* seconds.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            for sel in selectors:
                if not sel:
                    continue
                count = await self._count_selector(sel)
                if count and count > 0:
                    return sel
            await asyncio.sleep(POLL_INTERVAL_SEC)
        return None

    async def _count_selector(self, selector: str) -> int:
        """Return the number of DOM nodes matching *selector*."""
        result = await self._cdp.execute_js(
            f"document.querySelectorAll({json.dumps(selector)}).length",
        )
        val = result.get("result", {}).get("value", 0)
        return int(val) if val is not None else 0

    async def _get_element_bounds(self, selector: str) -> dict | None:
        """Return bounding-box info for the first element matching *selector*."""
        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{ x: rect.x, y: rect.y, w: rect.width, h: rect.height }};
        }})()
        """
        result = await self._cdp.execute_js(js)
        return result.get("result", {}).get("value")

    # ── Click ────────────────────────────────────────────────────

    async def click(self, selectors: list[str],
                    timeout: float = 5.0) -> None:
        """Resolve *selectors* (fallback list) and click the first match."""
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            raise SelectorResolutionError(
                f"No selector matched (tried {len(selectors)} selectors)",
                details={"selectors": selectors, "timeout": timeout},
            )
        await self._click_selector(sel)

    async def _click_selector(self, selector: str) -> None:
        """Click the center of the first element matching *selector*.

        Uses the already-computed bounding box to dispatch a native CDP
        ``Input.dispatchMouseEvent`` — no redundant DOM queries, no
        synthetic JS MouseEvent objects.
        """
        bounds = await self._get_element_bounds(selector)
        if bounds is None:
            raise SelectorResolutionError(
                f"Element matched but has no bounds: {selector}",
                details={"selector": selector},
            )
        x = bounds["x"] + bounds["w"] / 2
        y = bounds["y"] + bounds["h"] / 2
        await self._cdp.click_at(x, y)

    # ── Type text ────────────────────────────────────────────────

    async def type_text(self, selectors: list[str], text: str,
                        clear_first: bool = True,
                        timeout: float = 5.0) -> None:
        """Resolve *selectors*, optionally clear, then type *text*."""
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            raise SelectorResolutionError(
                f"No selector matched for typing (tried {len(selectors)})",
                details={"selectors": selectors, "timeout": timeout},
            )
        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(sel)});
            if (!el) return false;
            el.focus();
            {'el.value = "";' if clear_first else ''}
            el.value = {json.dumps(text)};
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }})()
        """
        await self._cdp.execute_js(js)

    async def type_text_monaco(self, selectors: list[str], text: str,
                               timeout: float = 5.0) -> None:
        """Write *text* into a Monaco editor via system clipboard + CGEventPostToPid.

        Pipeline:
            1. ``Page.bringToFront`` — fix clipboard focus
            2. ``navigator.clipboard.writeText`` — write to system clipboard
            3. Focus Monaco textarea via JS
            4. ``CGEventPostToPid`` Cmd+A + Cmd+V — real OS keystrokes

        Falls back to CDP ``Input.dispatchKeyEvent`` if CGEvent is unavailable
        (non-macOS or missing Accessibility permission).
        """
        import asyncio

        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            raise SelectorResolutionError(
                f"No textarea selector matched (tried {len(selectors)})",
                details={"selectors": selectors, "timeout": timeout},
            )

        # ── Step 1: Ensure page has focus ────────────────────────
        await self._cdp._send_command("Page.bringToFront", {})
        await asyncio.sleep(0.6)

        # ── Step 2: Write to system clipboard ────────────────────
        import base64
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        clip_js = f"""
        (async () => {{
            const binary = atob("{b64}");
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            const decoded = new TextDecoder().decode(bytes);
            try {{
                await navigator.clipboard.writeText(decoded);
                return 'clipboard_ok';
            }} catch(e) {{
                return 'clipboard_fail: ' + e.message;
            }}
        }})()
        """
        clip_result = await self._cdp.execute_js(clip_js, await_promise=True)
        ret_val = clip_result.get("result", {}).get("value", "")
        if "clipboard_fail" in str(ret_val):
            logger.warning("Clipboard write failed: %s", ret_val)

        # ── Step 3: Focus the Monaco textarea ────────────────────
        await self._cdp.execute_js("""
        (() => {
            const ta = document.querySelector('#pine-editor-dialog textarea.inputarea');
            if (ta) { ta.focus(); ta.select(); return 'focused'; }
            const all = document.querySelectorAll('.monaco-editor textarea.inputarea');
            for (let i = 0; i < all.length; i++) {
                if (all[i].offsetWidth > 0) { all[i].focus(); all[i].select(); return 'focused-fallback'; }
            }
            return 'no-textarea';
        })()
        """)
        await asyncio.sleep(0.2)

        # ── Step 4: OS-level Cmd+A → Cmd+V ──────────────────────
        if not await self._paste_via_cgevent():
            await self._paste_via_cdp()

        await asyncio.sleep(0.3)

    async def _paste_via_cgevent(self) -> bool:
        """Send Cmd+A then Cmd+V via CGEventPostToPid.

        Returns True if TradingView PID was found, Accessibility permission
        is granted, and keystrokes were dispatched.
        """
        if not _has_accessibility_permission():
            logger.debug("No Accessibility permission — using CDP fallback")
            return False

        tv_pid = _get_tv_pid()
        if not tv_pid:
            logger.debug("TradingView PID not found")
            return False

        try:
            _send_cmd_key(tv_pid, _KCD_A)
            await asyncio.sleep(0.25)
            _send_cmd_key(tv_pid, _KCD_V)
            await asyncio.sleep(0.25)
            logger.debug("Dispatched Cmd+A/V via CGEventPostToPid")
            return True
        except Exception:
            logger.debug("CGEventPostToPid failed", exc_info=True)
            return False

    async def _paste_via_cdp(self) -> None:
        """Fallback: Cmd+A → Cmd+V via CDP Input.dispatchKeyEvent.

        NOTE: On macOS, Meta-modified CDP keystrokes are intercepted by the OS
        and do NOT trigger ``paste`` ClipboardEvents.  This fallback only
        works reliably on Windows/Linux where Ctrl (modifier=2) is used
        instead of Meta/Cmd.
        """
        import asyncio

        # Cmd+A
        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "modifiers": 4, "key": "a",
            "code": "KeyA", "windowsVirtualKeyCode": 65,
        })
        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "keyUp", "modifiers": 4, "key": "a",
            "code": "KeyA", "windowsVirtualKeyCode": 65,
        })
        await asyncio.sleep(0.3)

        # Cmd+V
        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "modifiers": 4, "key": "v",
            "code": "KeyV", "windowsVirtualKeyCode": 86,
        })
        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "keyUp", "modifiers": 4, "key": "v",
            "code": "KeyV", "windowsVirtualKeyCode": 86,
        })
        await asyncio.sleep(0.3)

    async def read_text_monaco(self, selectors: list[str],
                                timeout: float = 5.0) -> str | None:
        """Read full source from a Monaco editor via system clipboard + CGEventPostToPid Cmd+C.

        Pipeline: bringToFront → clear clipboard → focus textarea → CGEventPostToPid Cmd+A+C → clipboard readText
        """
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return None

        import asyncio

        # Step 0: Ensure page focus
        await self._cdp._send_command("Page.bringToFront", {})
        await asyncio.sleep(0.3)

        # Step 1: Clear stale clipboard from previous writes
        await self._cdp.execute_js(
            "(async () => { try { await navigator.clipboard.writeText(''); } catch(e) {} })()",
            await_promise=True,
        )

        # Step 2: Focus the textarea via JS
        await self._cdp.execute_js("""
        (() => {
            const ta = document.querySelector('#pine-editor-dialog textarea.inputarea');
            if (ta) { ta.focus(); return 'focused'; }
            const all = document.querySelectorAll('.monaco-editor textarea.inputarea');
            for (let i = 0; i < all.length; i++) {
                if (all[i].offsetWidth > 0) { all[i].focus(); return 'focused-fallback'; }
            }
            return 'no-textarea';
        })()
        """)
        await asyncio.sleep(0.2)

        # Step 3: Cmd+A → Cmd+C (via CGEventPostToPid or CDP fallback)
        if not await self._copy_via_cgevent():
            await self._copy_via_cdp()

        # Step 4: Read from system clipboard
        await self._cdp._send_command("Page.bringToFront", {})
        await asyncio.sleep(0.2)

        read_js = """
        (async () => {
            try {
                return await navigator.clipboard.readText();
            } catch(e) {
                return 'read_fail: ' + e.message;
            }
        })()
        """
        result = await self._cdp.execute_js(read_js, await_promise=True)
        text = result.get("result", {}).get("value", "")
        if not text or "read_fail" in str(text):
            return None
        return text

    async def _copy_via_cgevent(self) -> bool:
        """Send Cmd+A then Cmd+C via CGEventPostToPid."""
        if not _has_accessibility_permission():
            logger.debug("No Accessibility permission — using CDP fallback")
            return False

        tv_pid = _get_tv_pid()
        if not tv_pid:
            logger.debug("TradingView PID not found")
            return False

        try:
            _send_cmd_key(tv_pid, _KCD_A)
            await asyncio.sleep(0.25)
            _send_cmd_key(tv_pid, _KCD_C)
            await asyncio.sleep(0.25)
            logger.debug("Dispatched Cmd+A/C via CGEventPostToPid")
            return True
        except Exception:
            logger.debug("CGEventPostToPid failed", exc_info=True)
            return False

    async def _copy_via_cdp(self) -> None:
        """Fallback: Cmd+A → Cmd+C via CDP (may not work on macOS)."""
        import asyncio

        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "modifiers": 4, "key": "a",
            "code": "KeyA", "windowsVirtualKeyCode": 65,
        })
        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "keyUp", "modifiers": 4, "key": "a",
            "code": "KeyA", "windowsVirtualKeyCode": 65,
        })
        await asyncio.sleep(0.2)

        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "modifiers": 4, "key": "c",
            "code": "KeyC", "windowsVirtualKeyCode": 67,
        })
        await self._cdp._send_command("Input.dispatchKeyEvent", {
            "type": "keyUp", "modifiers": 4, "key": "c",
            "code": "KeyC", "windowsVirtualKeyCode": 67,
        })
        await asyncio.sleep(0.3)

    # ── Extract text / table data ───────────────────────────────

    async def extract_text(self, selectors: list[str],
                           timeout: float = 5.0) -> str | None:
        """Extract text from the first matching element.

        For ``<input>`` and ``<textarea>`` elements, returns ``.value`` instead
        of ``.textContent`` so user-typed values are captured correctly.
        """
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return None
        js = f"""(function() {{
            const el = document.querySelector({json.dumps(sel)});
            if (!el) return '';
            return (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
                ? (el.value ?? '')
                : (el.textContent ?? '');
        }})()"""
        result = await self._cdp.execute_js(js)
        return result.get("result", {}).get("value")

    async def extract_table(self, selectors: list[str],
                            row_selectors: list[str] | None = None,
                            timeout: float = 5.0) -> list[list[str]]:
        """Scrape a table element as a list of rows.

        Each row is a list of cell text values. If *row_selectors* is given,
        rows are located via that sub-selector scoped within the container.
        """
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return []

        if row_selectors:
            # Resolve row selector within the container context only
            js = f"""
            (() => {{
                const container = document.querySelector({json.dumps(sel)});
                if (!container) return [];
                const selectors = {json.dumps(row_selectors)};
                let rows = [];
                for (const rs of selectors) {{
                    const found = container.querySelectorAll(rs);
                    if (found.length > 0) {{
                        rows = Array.from(found);
                        break;
                    }}
                }}
                return rows.map(row =>
                    Array.from(row.querySelectorAll('td, th')).map(cell => cell.textContent.trim())
                );
            }})()
            """
        else:
            js = f"""
            Array.from(document.querySelector({json.dumps(sel)})?.querySelectorAll('tr') ?? []).map(row =>
                Array.from(row.querySelectorAll('td, th')).map(cell => cell.textContent.trim())
            )
            """
        result = await self._cdp.execute_js(js)
        return result.get("result", {}).get("value", [])

    # ── Wait ──────────────────────────────────────────────────────

    async def wait_until(self, selectors: list[str],
                         timeout: float = 10.0) -> str | None:
        """Block until a matching selector appears, then return it."""
        return await self.resolve_selector(selectors, timeout=timeout)

    # ── Scrolling ────────────────────────────────────────────────

    async def scroll_paginated_list(self, container_selectors: list[str],
                                    direction: str = "down",
                                    amount: int = 300) -> None:
        """Scroll a container element by *amount* pixels."""
        sel = await self.resolve_selector(container_selectors, timeout=5.0)
        if sel is None:
            raise SelectorResolutionError(
                "Container not found for scroll",
                details={"selectors": container_selectors},
            )
        delta = amount if direction == "down" else -amount
        await self._cdp.execute_js(
            f"document.querySelector({json.dumps(sel)})?.scrollBy(0, {delta})",
        )

    # ── Scroll-and-stitch for virtual scrollers ─────────────────

    async def scroll_and_collect_text(self, scrollable_selectors: list[str],
                                       textarea_selectors: list[str],
                                       pages: int = 6,
                                       delay: float = 0.3) -> str:
        """Scroll through a virtual-scroller editor and collect text snapshots.

        Designed for Monaco Editor's virtual viewport.  Scrolls to evenly-
        spaced positions, reads ``textarea.value`` at each (which preserves
        real newlines), and stitches snippets together.

        Returns the longest collected snippet (best-effort full source).
        """
        sel = await self.resolve_selector(scrollable_selectors, timeout=5.0)
        if sel is None:
            return ""

        collected: list[str] = []
        seen = set()

        for i in range(pages + 1):
            pct = i / max(pages, 1)

            # Scroll to position
            await self._cdp.execute_js(
                f"var s = document.querySelector({json.dumps(sel)}); "
                f"if(s) s.scrollTop = s.scrollHeight * {pct};"
            )

            # Wait for virtual scroller to re-render
            await asyncio.sleep(delay)

            # Read textarea.value (not textContent — textarea stores in .value)
            text = None
            if textarea_selectors:
                ta_sel = await self.resolve_selector(textarea_selectors, timeout=2.0)
                if ta_sel:
                    r = await self._cdp.execute_js(
                        f"document.querySelector({json.dumps(ta_sel)})?.value ?? ''"
                    )
                    text = r.get("result", {}).get("value", "")

            if text and text not in seen:
                seen.add(text)
                if len(text) > 50:
                    collected.append(text)

        if not collected:
            return ""

        # Return the longest snippet (usually covers the most of the file)
        collected.sort(key=len, reverse=True)
        return collected[0]

    # ── Strategy Tester innerText parsing ───────────────────────

    async def extract_innertext_map(self, labels: dict[str, list[str]],
                                     timeout: float = 5.0) -> dict[str, str]:
        """Scan ``document.body.innerText`` for known Strategy Tester labels
        and extract the associated numeric values.

        *labels* is a ``{key: [label_variants]}`` mapping where each value
        is a list of possible text labels (e.g. ``"sharpe": ["Sharpe ratio", "Sharpe"]``).

        Returns a dict of ``{key: value_string}`` for each key where a
        matching label was found.  Values are extracted as the text
        immediately following the label in the innerText block.
        """
        js = """
        (() => {
            const body = document.body.innerText || '';
            return body;
        })()
        """
        deadline = asyncio.get_running_loop().time() + timeout
        body = ""
        while asyncio.get_running_loop().time() < deadline:
            result = await self._cdp.execute_js(js)
            body = result.get("result", {}).get("value", "")
            if body:
                break
            await asyncio.sleep(POLL_INTERVAL_SEC)

        if not body:
            return {}

        out: dict[str, str] = {}
        for key, variants in labels.items():
            for variant in variants:
                idx = body.find(variant)
                if idx == -1:
                    continue
                # Extract the text chunk after the label (up to ~80 chars)
                chunk = body[idx + len(variant):idx + len(variant) + 120]
                # Try to find a numeric value: <number> possibly followed by %, USD, etc.
                m = re.search(
                    r'[\n\s]*(-?[\d,.]+(?:e[+-]?\d+)?)\s*(?:%|USD|trades)?',
                    chunk.split('\n')[0] if '\n' in chunk else chunk
                )
                if m:
                    out[key] = m.group(1).strip()
                    break
                # Fallback: just take the first non-empty line
                lines = [l.strip() for l in chunk.split('\n') if l.strip()]
                if lines:
                    out[key] = lines[0]
                break
        return out

    # ── Text-based element click ────────────────────────────────

    async def click_at_text(self, text: str, exact: bool = True,
                            timeout: float = 5.0) -> bool:
        """Find an element containing *text* and click it.

        Searches the DOM for a visible leaf element whose textContent
        matches *text*.  If *exact* is False, a substring match is used.

        Returns True if an element was found and clicked, False otherwise.
        """
        txt_json = json.dumps(text)
        compare = f"txt === {txt_json}" if exact else f"txt.indexOf({txt_json}) !== -1"
        js = f"""
        (() => {{
            const all = document.querySelectorAll('*');
            for (const el of all) {{
                if (el.children.length !== 0) continue;
                if (el.offsetParent === null) continue;
                const txt = el.textContent?.trim() || '';
                if ({compare}) {{
                    const r = el.getBoundingClientRect();
                    return {{ x: r.x + r.width / 2, y: r.y + r.height / 2, text: txt.substring(0, 50) }};
                }}
            }}
            return null;
        }})()
        """
        result = await self._cdp.execute_js(js)
        pos = result.get("result", {}).get("value")
        if pos and pos.get("x") is not None:
            await self._cdp.click_at(pos["x"], pos["y"])
            return True
        return False

    # ── Canvas coordinate click ──────────────────────────────────

    async def click_at_coordinates(self, container_selectors: list[str],
                                   x_ratio: float, y_ratio: float,
                                   timeout: float = 5.0) -> None:
        """Click at a relative position within a container element.

        *x_ratio* and *y_ratio* are 0.0-1.0 fractions of the container's
        bounding box.  Used for placing drawing objects on the chart canvas
        by position rather than by CSS selector.
        """
        sel = await self.resolve_selector(container_selectors, timeout=timeout)
        if sel is None:
            raise SelectorResolutionError(
                "Container not found for coordinate click",
                details={"selectors": container_selectors, "x_ratio": x_ratio, "y_ratio": y_ratio},
            )
        bounds = await self._get_element_bounds(sel)
        if bounds is None:
            raise SelectorResolutionError(
                f"Cannot get bounds for container: {sel}",
                details={"selector": sel},
            )
        px = bounds["x"] + bounds["w"] * x_ratio
        py = bounds["y"] + bounds["h"] * y_ratio
        # Dispatch native CDP mouse click instead of synthetic JS events
        await self._cdp.click_at(px, py)

    # ── Visibility / attribute helpers ──────────────────────────

    async def is_visible(self, selectors: list[str],
                         timeout: float = 3.0) -> bool:
        """Check whether a matching element is currently visible."""
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return False
        result = await self._cdp.execute_js(
            f"""(function() {{
                const el = document.querySelector({json.dumps(sel)});
                if (!el) return false;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0;
            }})()"""
        )
        return bool(result.get("result", {}).get("value", False))

    async def get_attribute(self, selectors: list[str], attr: str,
                            timeout: float = 5.0) -> str | None:
        """Read a DOM attribute from the first matching element."""
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return None
        result = await self._cdp.execute_js(
            f"document.querySelector({json.dumps(sel)})?.getAttribute({json.dumps(attr)}) ?? null",
        )
        return result.get("result", {}).get("value")
