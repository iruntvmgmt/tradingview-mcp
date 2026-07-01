"""Domain-specific error types for TradingView Desktop MCP controller.

Every error carries a machine-readable `code` and structured `details` dict
so MCP tool handlers can surface them cleanly to the calling agent.
"""

from typing import Any


class TvMcpError(Exception):
    """Base error for all TV Desktop MCP operations."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        full = f"[{code}] {message}"
        if details:
            full += f" | {details}"
        super().__init__(full)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.args[0], "details": self.details}


class CDPConnectionError(TvMcpError):
    """CDP WebSocket connection or launch failure."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("CONNECTION_ERROR", message, details)


class CapabilityUnavailable(TvMcpError):
    """Capability not found in recon, unverified, or explicitly unavailable."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("CAPABILITY_UNAVAILABLE", message, details)


class BackendConfigurationError(TvMcpError):
    """Unknown / unsupported path type in recon (not A/B/C)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("BACKEND_CONFIG_ERROR", message, details)


class SelectorResolutionError(TvMcpError):
    """None of the fallback selectors matched in the DOM."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("SELECTOR_RESOLUTION_ERROR", message, details)


class OrderSubmissionBlocked(TvMcpError):
    """order_place / order_modify called without explicit confirmation,
    or against a non-paper session."""

    def __init__(self, message: str = "Order submission requires explicit confirmed=True",
                 details: dict[str, Any] | None = None):
        super().__init__("ORDER_SUBMISSION_BLOCKED", message, details)


class ReplayStateError(TvMcpError):
    """Invalid replay mode transition (step/exit while not in replay,
    enter while already in replay)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("REPLAY_STATE_ERROR", message, details)
