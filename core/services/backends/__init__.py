"""Backend factory functions — dispatches to the correct concrete backend
based on recon_findings.json capability path classification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.backends.dom_backend import (
    DomAlertBackend,
    DomBacktestBackend,
    DomChartBackend,
    DomDrawingBackend,
    DomIndicatorBackend,
    DomOrderBackend,
    DomPineScriptBackend,
    DomReplayBackend,
    DomSettingsBackend,
)
from core.services.backends.js_backend import (
    JsAlertBackend,
    JsBacktestBackend,
    JsChartBackend,
    JsDrawingBackend,
    JsIndicatorBackend,
    JsOrderBackend,
    JsPineScriptBackend,
    JsReplayBackend,
    JsSettingsBackend,
)
from core.services.backends.network_backend import (
    NetworkAlertBackend,
    NetworkBacktestBackend,
    NetworkChartBackend,
    NetworkDrawingBackend,
    NetworkIndicatorBackend,
    NetworkOrderBackend,
    NetworkPineScriptBackend,
    NetworkReplayBackend,
    NetworkSettingsBackend,
)
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
            f"Capability '{cap_name}' not found in recon_findings.json",
            details={"capability": cap_name},
        )
    if not entry.get("verified") and not allow_unverified:
        raise CapabilityUnavailable(
            f"Capability '{cap_name}' is not verified. "
            f"Set allow_unverified=True or rerun recon.",
            details={"capability": cap_name},
        )
    if not entry.get("path"):
        raise BackendConfigurationError(
            f"Capability '{cap_name}' has no path set.",
            details={"capability": cap_name},
        )
    return entry


def _dispatch(path: str, domain: str, dom_cls, js_cls, net_cls, cdp, dom, caps):
    """Select the correct concrete backend based on the path."""
    if path == "dom":
        return dom_cls(cdp, dom, caps)
    elif path == "js":
        return js_cls(cdp, dom, caps)
    elif path == "network":
        return net_cls(cdp, dom, caps)
    raise BackendConfigurationError(
        f"Unsupported path '{path}' for {domain}",
        details={"path": path, "domain": domain},
    )


def build_chart_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "ChartBackend":
    entry = _get_capability(recon, "symbol_control", allow_unverified)
    return _dispatch(entry["path"], "chart",
                     DomChartBackend, JsChartBackend, NetworkChartBackend,
                     cdp, dom, recon["capabilities"])


def build_indicator_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "IndicatorBackend":
    entry = _get_capability(recon, "indicator_apply", allow_unverified)
    return _dispatch(entry["path"], "indicators",
                     DomIndicatorBackend, JsIndicatorBackend, NetworkIndicatorBackend,
                     cdp, dom, recon["capabilities"])


def build_backtest_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "BacktestBackend":
    entry = _get_capability(recon, "backtest_run", allow_unverified)
    return _dispatch(entry["path"], "backtest",
                     DomBacktestBackend, JsBacktestBackend, NetworkBacktestBackend,
                     cdp, dom, recon["capabilities"])


def build_alert_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "AlertBackend":
    entry = _get_capability(recon, "alert_create", allow_unverified)
    return _dispatch(entry["path"], "alerts",
                     DomAlertBackend, JsAlertBackend, NetworkAlertBackend,
                     cdp, dom, recon["capabilities"])


def build_drawing_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "DrawingBackend":
    entry = _get_capability(recon, "drawing_create", allow_unverified)
    return _dispatch(entry["path"], "drawing tools",
                     DomDrawingBackend, JsDrawingBackend, NetworkDrawingBackend,
                     cdp, dom, recon["capabilities"])


def build_order_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "OrderBackend":
    entry = _get_capability(recon, "order_place", allow_unverified)
    return _dispatch(entry["path"], "order panel",
                     DomOrderBackend, JsOrderBackend, NetworkOrderBackend,
                     cdp, dom, recon["capabilities"])


def build_replay_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "ReplayBackend":
    entry = _get_capability(recon, "replay_enter", allow_unverified)
    return _dispatch(entry["path"], "replay mode",
                     DomReplayBackend, JsReplayBackend, NetworkReplayBackend,
                     cdp, dom, recon["capabilities"])


def build_settings_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "SettingsBackend":
    entry = _get_capability(recon, "settings_list_fields", allow_unverified)
    return _dispatch(entry["path"], "settings",
                     DomSettingsBackend, JsSettingsBackend, NetworkSettingsBackend,
                     cdp, dom, recon["capabilities"])


def build_pinescript_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> "PineScriptBackend":
    entry = _get_capability(recon, "pine_read", allow_unverified)
    return _dispatch(entry["path"], "pinescript",
                     DomPineScriptBackend, JsPineScriptBackend, NetworkPineScriptBackend,
                     cdp, dom, recon["capabilities"])
