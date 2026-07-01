"""High-level DOM automation helpers built on CDP primitives.

Provides selector resolution with fallback arrays, click/type/extract
primitives, and utilities for waiting, scrolling, and canvas-position
clicking used across all domain backends.
"""

import asyncio
import logging
from typing import Any

from core.services.errors import SelectorResolutionError

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 0.3


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
        escaped = selector.replace("'", "\\'")
        result = await self._cdp.execute_js(
            f"document.querySelectorAll('{escaped}').length",
        )
        val = result.get("result", {}).get("value", 0)
        return int(val) if val is not None else 0

    async def _get_element_bounds(self, selector: str) -> dict | None:
        """Return bounding-box info for the first element matching *selector*."""
        escaped = selector.replace("'", "\\'")
        js = f"""
        (() => {{
            const el = document.querySelector('{escaped}');
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
        escaped_sel = sel.replace("'", "\\'")
        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
        js = f"""
        (() => {{
            const el = document.querySelector('{escaped_sel}');
            if (!el) return false;
            el.focus();
            {'el.value = "";' if clear_first else ''}
            el.value = '{escaped_text}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }})()
        """
        await self._cdp.execute_js(js)

    # ── Extract text / table data ───────────────────────────────

    async def extract_text(self, selectors: list[str],
                           timeout: float = 5.0) -> str | None:
        """Extract ``textContent`` from the first matching element."""
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return None
        escaped = sel.replace("'", "\\'")
        result = await self._cdp.execute_js(
            f"document.querySelector('{escaped}')?.textContent ?? ''",
        )
        return result.get("result", {}).get("value")

    async def extract_table(self, selectors: list[str],
                            row_selectors: list[str] | None = None,
                            timeout: float = 5.0) -> list[list[str]]:
        """Scrape a table element as a list of rows.

        Each row is a list of cell text values. If *row_selectors* is given,
        rows are located via that sub-selector within the container.
        """
        sel = await self.resolve_selector(selectors, timeout=timeout)
        if sel is None:
            return []
        escaped = sel.replace("'", "\\'")
        row_sel = ""
        if row_selectors:
            rs = await self.resolve_selector(
                [f"{sel} {rs}" for rs in row_selectors] + row_selectors,
                timeout=2.0,
            )
            if rs:
                row_sel = rs.replace("'", "\\'")

        if row_sel:
            js = f"""
            Array.from(document.querySelectorAll('{row_sel}')).map(row =>
                Array.from(row.querySelectorAll('td, th')).map(cell => cell.textContent.trim())
            )
            """
        else:
            js = f"""
            Array.from(document.querySelector('{escaped}')?.querySelectorAll('tr') ?? []).map(row =>
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
        escaped = sel.replace("'", "\\'")
        await self._cdp.execute_js(
            f"document.querySelector('{escaped}')?.scrollBy(0, {delta})",
        )

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
        escaped = sel.replace("'", "\\'")
        result = await self._cdp.execute_js(
            f"""(function() {{
                const el = document.querySelector('{escaped}');
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
        escaped = sel.replace("'", "\\'")
        result = await self._cdp.execute_js(
            f"document.querySelector('{escaped}')?.getAttribute('{attr}') ?? null",
        )
        return result.get("result", {}).get("value")
