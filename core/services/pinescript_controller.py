"""Pine Script controller — read/write source, compile, debug, logs.

Wraps the PineScriptBackend to provide code editing, compilation,
error reading, and Pine Logs access.
"""

from typing import Any

from core.services.backends import build_pinescript_backend
from core.services.backends.base import PineScriptBackend
from core.services.dom_utils import DomUtils
from core.services.errors import CapabilityUnavailable


class TVPineScriptController:
    """Pine Script development: editor, compiler, debug output."""

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: PineScriptBackend = build_pinescript_backend(
            recon, cdp, self._dom, allow_unverified
        )

    async def read(self, script_name: str) -> str:
        """Read the current Pine Script source from the editor."""
        return await self._backend.read(script_name)

    async def write(self, script_name: str, source: str) -> None:
        """Replace the Pine Script source in the editor."""
        await self._backend.write(script_name, source)

    async def compile(self, script_name: str) -> dict[str, Any]:
        """Trigger compile and return the result.

        Returns ``{"success": True}`` on success, or
        ``{"success": False, "errors": [...]}`` on failure.
        """
        return await self._backend.compile(script_name)

    async def read_compile_errors(self) -> list[dict[str, Any]]:
        """Read compiler errors / warnings from the console panel."""
        return await self._backend.read_compile_errors()

    async def read_logs(self, script_name: str) -> list[dict[str, Any]]:
        """Read Pine Logs output for the given script.

        Raises ``CapabilityUnavailable`` if the script is published/
        protected (TradingView restricts Pine Logs to unpublished scripts).
        """
        return await self._backend.read_logs(script_name)

    async def health_check(self) -> dict[str, Any]:
        """Health check for the Pine Script domain."""
        return {
            "pinescript": await self._backend.health_check(),
        }
