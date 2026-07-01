"""Backend factory functions — dispatches to the correct concrete backend
based on recon_findings.json capability path classification."""

from core.services.backends.base import (
    ChartBackend,
    IndicatorBackend,
    BacktestBackend,
    AlertBackend,
    DrawingBackend,
    OrderBackend,
    ReplayBackend,
    SettingsBackend,
    PineScriptBackend,
)

from core.services.backends.dom_backend import (
    DomChartBackend,
    DomIndicatorBackend,
    DomBacktestBackend,
    DomAlertBackend,
    DomDrawingBackend,
    DomOrderBackend,
    DomReplayBackend,
    DomSettingsBackend,
    DomPineScriptBackend,
)

from core.services.backends.js_backend import (
    JsChartBackend,
    JsIndicatorBackend,
    JsBacktestBackend,
    JsAlertBackend,
    JsDrawingBackend,
    JsOrderBackend,
    JsReplayBackend,
    JsSettingsBackend,
    JsPineScriptBackend,
)

from core.services.backends.network_backend import (
    NetworkChartBackend,
    NetworkIndicatorBackend,
    NetworkBacktestBackend,
    NetworkAlertBackend,
    NetworkDrawingBackend,
    NetworkOrderBackend,
    NetworkReplayBackend,
    NetworkSettingsBackend,
    NetworkPineScriptBackend,
)

from core.services.errors import BackendConfigurationError


def _get_capability(recon: dict, cap_name: str, allow_unverified: bool = False) -> dict:
    """Read a capability entry from recon and validate it's usable."""
    caps = recon.get("capabilities", {})
    entry = caps.get(cap_name)
    if entry is None:
        raise CapabilityUnavailable(
            code="CAPABILITY_NOT_FOUND",
            details={"capability": cap_name, "message": f"Capability '{cap_name}' not found in recon_findings.json"}
        )
    if not entry.get("verified") and not allow_unverified:
        raise CapabilityUnavailable(
            code="CAPABILITY_UNVERIFIED",
            details={"capability": cap_name, "message": f"Capability '{cap_name}' is not verified. Set allow_unverified=True or rerun recon."}
        )
    if not entry.get("path"):
        raise BackendConfigurationError(
            code="NO_PATH",
            details={"capability": cap_name, "message": f"Capability '{cap_name}' has no path set."}
        )
    return entry


def build_chart_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> ChartBackend:
    entry = _get_capability(recon, "symbol_control", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomChartBackend(cdp, dom, caps)
    elif path == "js":
        return JsChartBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkChartBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for chart")


def build_indicator_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> IndicatorBackend:
    entry = _get_capability(recon, "indicator_apply", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomIndicatorBackend(cdp, dom, caps)
    elif path == "js":
        return JsIndicatorBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkIndicatorBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for indicators")


def build_backtest_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> BacktestBackend:
    entry = _get_capability(recon, "backtest_run", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomBacktestBackend(cdp, dom, caps)
    elif path == "js":
        return JsBacktestBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkBacktestBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for backtest")


def build_alert_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> AlertBackend:
    entry = _get_capability(recon, "alert_create", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomAlertBackend(cdp, dom, caps)
    elif path == "js":
        return JsAlertBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkAlertBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for alerts")


def build_drawing_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> DrawingBackend:
    entry = _get_capability(recon, "drawing_create", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomDrawingBackend(cdp, dom, caps)
    elif path == "js":
        return JsDrawingBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkDrawingBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for drawing tools")


def build_order_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> OrderBackend:
    entry = _get_capability(recon, "order_place", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomOrderBackend(cdp, dom, caps)
    elif path == "js":
        return JsOrderBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkOrderBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for order panel")


def build_replay_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> ReplayBackend:
    entry = _get_capability(recon, "replay_enter", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomReplayBackend(cdp, dom, caps)
    elif path == "js":
        return JsReplayBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkReplayBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for replay mode")


def build_settings_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> SettingsBackend:
    entry = _get_capability(recon, "settings_list_fields", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomSettingsBackend(cdp, dom, caps)
    elif path == "js":
        return JsSettingsBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkSettingsBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for settings")


def build_pinescript_backend(recon: dict, cdp, dom, allow_unverified: bool = False) -> PineScriptBackend:
    entry = _get_capability(recon, "pine_read", allow_unverified)
    path = entry["path"]
    caps = recon["capabilities"]
    if path == "dom":
        return DomPineScriptBackend(cdp, dom, caps)
    elif path == "js":
        return JsPineScriptBackend(cdp, dom, caps)
    elif path == "network":
        return NetworkPineScriptBackend(cdp, dom, caps)
    raise BackendConfigurationError(f"Unsupported path '{path}' for pinescript")


# Import needed for CapabilityUnavailable used in _get_capability
from core.services.errors import CapabilityUnavailable
