"""Backend factory functions — dispatches to the correct concrete backend
based on recon_findings.json capability path classification.

Note: Concrete backend classes (Dom*, Js*, Network*) are implemented in
Sprint 2.  Until then, all factory calls with a recognised path will raise
BackendConfigurationError indicating the backend is not yet built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.errors import BackendConfigurationError, CapabilityUnavailable

if TYPE_CHECKING:
    from core.services.backends.base import (
        AlertBackend,
        BacktestBackend,
        ChartBackend,
        DrawingBackend,
        IndicatorBackend,
        OrderBackend,
        PineScriptBackend,
        ReplayBackend,
        SettingsBackend,
    )


def _get_capability(recon: dict, cap_name: str, allow_unverified: bool = False) -> dict:
    """Read a capability entry from recon and validate it's usable."""
    caps = recon.get("capabilities", {})
    entry = caps.get(cap_name)
    if entry is None:
        raise CapabilityUnavailable(
            code="CAPABILITY_NOT_FOUND",
            details={"capability": cap_name,
                     "message": f"Capability '{cap_name}' not found in recon_findings.json"}
        )
    if not entry.get("verified") and not allow_unverified:
        raise CapabilityUnavailable(
            code="CAPABILITY_UNVERIFIED",
            details={"capability": cap_name,
                     "message": f"Capability '{cap_name}' is not verified. "
                                f"Set allow_unverified=True or rerun recon."}
        )
    if not entry.get("path"):
        raise BackendConfigurationError(
            code="NO_PATH",
            details={"capability": cap_name,
                     "message": f"Capability '{cap_name}' has no path set."}
        )
    return entry


def _build_not_implemented(path: str, domain: str):
    """Raise a clear error when a concrete backend has not been built yet."""
    raise BackendConfigurationError(
        f"No concrete backend for path '{path}' in domain '{domain}' — "
        f"implement in Sprint 2.",
        details={"path": path, "domain": domain},
    )


def build_chart_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "ChartBackend":
    entry = _get_capability(recon, "symbol_control", allow_unverified)
    _build_not_implemented(entry["path"], "chart")


def build_indicator_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "IndicatorBackend":
    entry = _get_capability(recon, "indicator_apply", allow_unverified)
    _build_not_implemented(entry["path"], "indicators")


def build_backtest_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "BacktestBackend":
    entry = _get_capability(recon, "backtest_run", allow_unverified)
    _build_not_implemented(entry["path"], "backtest")


def build_alert_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "AlertBackend":
    entry = _get_capability(recon, "alert_create", allow_unverified)
    _build_not_implemented(entry["path"], "alerts")


def build_drawing_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "DrawingBackend":
    entry = _get_capability(recon, "drawing_create", allow_unverified)
    _build_not_implemented(entry["path"], "drawing tools")


def build_order_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "OrderBackend":
    entry = _get_capability(recon, "order_place", allow_unverified)
    _build_not_implemented(entry["path"], "order panel")


def build_replay_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "ReplayBackend":
    entry = _get_capability(recon, "replay_enter", allow_unverified)
    _build_not_implemented(entry["path"], "replay mode")


def build_settings_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "SettingsBackend":
    entry = _get_capability(recon, "settings_list_fields", allow_unverified)
    _build_not_implemented(entry["path"], "settings")


def build_pinescript_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "PineScriptBackend":
    entry = _get_capability(recon, "pine_read", allow_unverified)
    _build_not_implemented(entry["path"], "pinescript")
