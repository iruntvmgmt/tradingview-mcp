"""Drawing controller — create, remove, and list drawing objects on the chart.

Wraps the DrawingBackend.  Drawing creation places objects at given
chart coordinates via canvas position clicks.
"""

from typing import Any

from core.services.backends import build_drawing_backend
from core.services.backends.base import DrawingBackend
from core.services.dom_utils import DomUtils


class TVDrawingController:
    """Manage drawing objects (trendlines, Fibonacci, rectangles, etc.)."""

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: DrawingBackend = build_drawing_backend(
            recon, cdp, self._dom, allow_unverified
        )

    async def create(self, drawing_type: str,
                     points: list[dict]) -> str:
        """Place a drawing object at the given chart coordinates.

        *drawing_type*: ``"trendline"``, ``"fib"``, ``"rectangle"``, etc.
        *points*: list of ``{"time": ..., "price": ...}`` or
                  ``{"bar_index": ..., "price": ...}`` dicts.
        Returns the drawing ID.
        """
        return await self._backend.create(drawing_type, points)

    async def remove(self, drawing_id: str) -> None:
        """Delete a drawing by ID."""
        await self._backend.remove(drawing_id)

    async def list(self) -> list[dict[str, Any]]:
        """Enumerate drawings on the chart with type and coordinates."""
        return await self._backend.list()

    async def health_check(self) -> dict[str, Any]:
        return {"drawing": await self._backend.health_check()}
