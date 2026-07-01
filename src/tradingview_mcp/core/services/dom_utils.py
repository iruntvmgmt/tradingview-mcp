"""
DOM Utilities — selector-resolution with fallback arrays.

Extracted and generalized from existing Pine editor DOM-scrolling patterns.
Every method accepts ``selectors: list[str]`` and tries each entry in order,
using the first one that resolves — this is the core of the fallback-array
design that makes recon_findings.json selector arrays actually work end to end.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager
from tradingview_mcp.core.services.errors import ElementNotFound


class DomUtils:
    """DOM manipulation utilities backed by CDP JavaScript execution.

    All methods that take ``selectors: list[str]`` try each entry in order
    and use the first one that resolves to a visible element.
    """

    # How long to poll for an element to appear before giving up (per selector)
    DEFAULT_POLL_INTERVAL = 0.1
    DEFAULT_TIMEOUT = 10.0

    def __init__(self, cdp: CDPConnectionManager) -> None:
        self.cdp = cdp

    # ------------------------------------------------------------------
    # Selector resolution
    # ------------------------------------------------------------------

    async def resolve_selector(
        self, selectors: list[str], timeout_s: float = DEFAULT_TIMEOUT
    ) -> str:
        """Try each selector in ``selectors`` in order; return the first
        that resolves to a visible element within ``timeout_s``.

        Raises ``ElementNotFound`` (with the full list attached) if none
        resolve.
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        for sel in selectors:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    visible = await self.cdp.execute_js(
                        f"""() => {{
                            const el = document.querySelector({sel!r});
                            if (!el) return false;
                            const style = window.getComputedStyle(el);
                            return el.offsetParent !== null
                                && style.display !== 'none'
                                && style.visibility !== 'hidden';
                        }}"""
                    )
                    if visible:
                        return sel
                except Exception:
                    pass
                await asyncio.sleep(self.DEFAULT_POLL_INTERVAL)
        raise ElementNotFound(
            f"None of {len(selectors)} selectors resolved within {timeout_s}s: "
            + ", ".join(selectors)
        )

    async def wait_for_selector(
        self, selectors: list[str], timeout_s: float = DEFAULT_TIMEOUT
    ) -> bool:
        """Return ``True`` if any selector resolves within timeout."""
        try:
            await self.resolve_selector(selectors, timeout_s)
            return True
        except ElementNotFound:
            return False

    # ------------------------------------------------------------------
    # Visibility & state
    # ------------------------------------------------------------------

    async def is_visible(self, selectors: list[str]) -> bool:
        """Check if any matching selector resolves to a visible element."""
        try:
            await self.resolve_selector(selectors, timeout_s=1.0)
            return True
        except ElementNotFound:
            return False

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def click(self, selectors: list[str]) -> None:
        """Click the first visible element matching any selector."""
        sel = await self.resolve_selector(selectors)
        await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (el) el.click();
            }}"""
        )

    async def type_text(
        self, selectors: list[str], text: str, clear_first: bool = True
    ) -> None:
        """Type text into the first visible input matching any selector."""
        sel = await self.resolve_selector(selectors)
        escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        clear = "el.value = '';" if clear_first else ""
        await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (!el) return;
                {clear}
                el.focus();
                el.value = '{escaped}';
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}"""
        )

    async def hover(self, selectors: list[str]) -> None:
        """Hover over the first visible element matching any selector."""
        sel = await self.resolve_selector(selectors)
        await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (el) {{
                    el.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                }}
            }}"""
        )

    async def focus(self, selectors: list[str]) -> None:
        """Focus the first visible element matching any selector."""
        sel = await self.resolve_selector(selectors)
        await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (el) el.focus();
            }}"""
        )

    async def scroll_into_view(self, selectors: list[str]) -> None:
        """Scroll the first matching element into view."""
        sel = await self.resolve_selector(selectors)
        await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (el) el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            }}"""
        )

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    async def extract_text(self, selectors: list[str]) -> str:
        """Extract and normalize text content from the first visible element."""
        sel = await self.resolve_selector(selectors)
        result = await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (!el) return '';
                return el.textContent || el.innerText || '';
            }}"""
        )
        if result is None:
            return ""
        return re.sub(r"\\s+", " ", str(result)).strip()

    async def extract_table(
        self,
        table_selectors: list[str],
        row_selectors: list[str],
    ) -> list[dict[str, str]]:
        """Extract a table as a list of dicts (header → cell)."""
        table_sel = await self.resolve_selector(table_selectors)
        row_sel = await self.resolve_selector(row_selectors) if row_selectors else "tr"
        result = await self.cdp.execute_js(
            f"""() => {{
                const table = document.querySelector({table_sel!r});
                if (!table) return [];
                const headers = [];
                const thead = table.querySelector('thead');
                if (thead) {{
                    thead.querySelectorAll('th, td').forEach(th => headers.push(th.textContent.trim()));
                }}
                const rows = table.querySelectorAll({row_sel!r});
                const data = [];
                rows.forEach(row => {{
                    const cells = row.querySelectorAll('td, th');
                    const rowData = {{}};
                    if (headers.length > 0) {{
                        cells.forEach((cell, i) => {{
                            if (i < headers.length) rowData[headers[i]] = cell.textContent.trim();
                        }});
                    }} else {{
                        cells.forEach((cell, i) => {{ rowData[`col_${{i}}`] = cell.textContent.trim(); }});
                    }}
                    data.push(rowData);
                }});
                return data;
            }}"""
        )
        return result or []

    async def get_attribute(self, selectors: list[str], attribute: str) -> str | None:
        """Get an attribute value from the first matching element."""
        sel = await self.resolve_selector(selectors)
        result = await self.cdp.execute_js(
            f"""() => {{
                const el = document.querySelector({sel!r});
                if (!el) return null;
                return el.getAttribute({attribute!r});
            }}"""
        )
        return str(result) if result is not None else None

    # ------------------------------------------------------------------
    # Wait utilities
    # ------------------------------------------------------------------

    async def wait_until(
        self, predicate_js: str, timeout_s: float = DEFAULT_TIMEOUT
    ) -> bool:
        """Poll a JS boolean expression until true or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                result = await self.cdp.execute_js(f"() => {{ return {predicate_js}; }}")
                if result:
                    return True
            except Exception:
                pass
            await asyncio.sleep(self.DEFAULT_POLL_INTERVAL)
        return False

    async def scroll_paginated_list(
        self,
        container_selectors: list[str],
        row_selectors: list[str],
        max_scrolls: int = 50,
    ) -> list[str]:
        """Scroll a paginated/list container to load all items.

        Returns a list of row text contents.  Reuses the same DOM-scroll
        fallback pattern from the existing Pine editor code.
        """
        container_sel = await self.resolve_selector(container_selectors)
        row_sel = await self.resolve_selector(row_selectors) if row_selectors else "*"

        result = await self.cdp.execute_js(
            f"""() => {{
                const container = document.querySelector({container_sel!r});
                if (!container) return [];
                const items = new Set();
                let prevCount = -1;
                for (let i = 0; i < {max_scrolls}; i++) {{
                    const rows = container.querySelectorAll({row_sel!r});
                    rows.forEach(r => items.add(r.textContent.trim()));
                    if (items.size === prevCount) break;
                    prevCount = items.size;
                    container.scrollTop = container.scrollHeight;
                    // Small delay to let new rows render
                }}
                return Array.from(items);
            }}"""
        )
        return result or []
