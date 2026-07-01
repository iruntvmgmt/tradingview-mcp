"""
Backend factory functions.

Select the correct backend implementation at construction time based on
``recon_findings.json``.  Controllers never branch on path — that
decision happens here, once.
"""

from __future__ import annotations

from typing import Any

from tradingview_mcp.core.services.backends.base import (
    ChartBackend,
    IndicatorBackend,
    BacktestBackend,
)
from tradingview_mcp.core.services.backends.dom_backend import (
    DomChartBackend,
    DomIndicatorBackend,
    DomBacktestBackend,
)
from tradingview_mcp.core.services.backends.js_backend import (
    JsChartBackend,
    JsIndicatorBackend,
    JsBacktestBackend,
)
from tradingview_mcp.core.services.backends.network_backend import NetworkChartBackend
from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager
from tradingview_mcp.core.services.dom_utils import DomUtils
from tradingview_mcp.core.services.errors import BackendConfigurationError


def _get_capability(recon: dict, capability: str, allow_unverified: bool = False) -> dict:
    """Fetch a capability entry from recon_findings.json, with validation."""
    entry = recon.get("capabilities", {}).get(capability)
    if entry is None:
        raise BackendConfigurationError(
            f"'{capability}' missing from recon_findings.json — run tv_recon_run()"
        )
    if not entry.get("verified", False) and not allow_unverified:
        raise BackendConfigurationError(
            f"'{capability}' is unverified — run tv_recon_run() or pass allow_unverified=True"
        )
    return entry


def build_chart_backend(
    capability: str,
    recon: dict,
    cdp: CDPConnectionManager,
    dom: DomUtils,
    allow_unverified: bool = False,
) -> ChartBackend:
    """Select and construct the correct ChartBackend for *capability*."""
    entry = _get_capability(recon, capability, allow_unverified)
    path = entry.get("path", "dom")
    detail = entry.get("detail", {})

    if path == "js":
        return JsChartBackend(cdp, dom, detail)
    elif path == "network":
        return NetworkChartBackend(cdp, dom, detail)
    elif path == "dom":
        return DomChartBackend(cdp, dom, detail)
    elif path == "cdp":
        # CDP-only capabilities (screenshot) don't need a backend
        return DomChartBackend(cdp, dom, detail)
    else:
        raise BackendConfigurationError(
            f"Unsupported path '{path}' for capability '{capability}'"
        )


def build_indicator_backend(
    recon: dict,
    cdp: CDPConnectionManager,
    dom: DomUtils,
    allow_unverified: bool = False,
) -> IndicatorBackend:
    """Select and construct the correct IndicatorBackend."""
    entry = _get_capability(recon, "indicator_apply", allow_unverified)
    path = entry.get("path", "dom")
    detail = entry.get("detail", {})

    if path == "js":
        return JsIndicatorBackend(cdp, dom, detail)
    elif path == "dom":
        return DomIndicatorBackend(cdp, dom, detail)
    else:
        raise BackendConfigurationError(
            f"Unsupported path '{path}' for indicator_apply"
        )


def build_backtest_backend(
    recon: dict,
    cdp: CDPConnectionManager,
    dom: DomUtils,
    allow_unverified: bool = False,
) -> BacktestBackend:
    """Select and construct the correct BacktestBackend."""
    entry = _get_capability(recon, "backtest_summary", allow_unverified)
    path = entry.get("path", "dom")
    detail = entry.get("detail", {})

    if path == "js":
        return JsBacktestBackend(cdp, dom, detail)
    elif path == "dom":
        return DomBacktestBackend(cdp, dom, detail)
    else:
        raise BackendConfigurationError(
            f"Unsupported path '{path}' for backtest capabilities"
        )
