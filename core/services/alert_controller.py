"""Alert controller — create, edit, delete, and list price alerts.

Wraps the AlertBackend behind a controller interface for MCP tools.
"""

from typing import Any

from core.services.backends import build_alert_backend
from core.services.backends.base import AlertBackend
from core.services.dom_utils import DomUtils


class TVAlertController:
    """Manage TradingView price alerts."""

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: AlertBackend = build_alert_backend(
            recon, cdp, self._dom, allow_unverified
        )

    async def create(self, symbol: str, condition: dict,
                     message: str) -> str:
        """Create a new price alert. Returns the alert ID."""
        return await self._backend.create(symbol, condition, message)

    async def edit(self, alert_id: str,
                   condition: dict | None = None,
                   message: str | None = None) -> None:
        """Modify an existing alert's condition or message."""
        await self._backend.edit(alert_id, condition, message)

    async def delete(self, alert_id: str) -> None:
        """Delete an alert by ID."""
        await self._backend.delete(alert_id)

    async def list(self) -> list[dict[str, Any]]:
        """List all active alerts (name, condition, status, symbol)."""
        return await self._backend.list()

    async def health_check(self) -> dict[str, Any]:
        return {"alert": await self._backend.health_check()}
