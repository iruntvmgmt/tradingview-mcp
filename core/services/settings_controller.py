"""Settings controller — read/write study/indicator Inputs tab values.

Wraps the SettingsBackend to expose field listing, reading, and writing
of a study's parameter values on the Inputs tab.
"""

from typing import Any

from core.services.backends import build_settings_backend
from core.services.backends.base import SettingsBackend
from core.services.dom_utils import DomUtils


class TVSettingsController:
    """Read and write strategy / indicator settings (Inputs tab)."""

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: SettingsBackend = build_settings_backend(
            recon, cdp, self._dom, allow_unverified
        )

    async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
        """Open the Settings dialog and enumerate all input fields.

        Returns a list of dicts with keys: name, type, current_value,
        and optionally min/max/step.
        """
        return await self._backend.list_fields(study_name)

    async def read(self, study_name: str) -> dict[str, Any]:
        """Read current input values for a study (lighter than full schema dump)."""
        return await self._backend.read(study_name)

    async def write(self, study_name: str, values: dict[str, Any]) -> None:
        """Set one or more input values and click OK/Apply."""
        await self._backend.write(study_name, values)

    async def health_check(self) -> dict[str, Any]:
        """Health check for the settings domain."""
        return {
            "settings": await self._backend.health_check(),
        }
