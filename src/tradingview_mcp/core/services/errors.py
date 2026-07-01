"""
Typed exception classes for the TradingView Desktop Controller.

Every module in the TV Desktop subsystem imports from this module and
raises the appropriate typed error instead of a bare ``Exception`` or
generic ``RuntimeError``.  This lets callers (including agent code)
branch cleanly on error type.
"""


class TvMcpError(Exception):
    """Base class for all errors raised by this server."""


class ConnectionSetupError(TvMcpError):
    """CDP launch/connect/target-selection failed."""


class ReconRequired(TvMcpError):
    """``recon_findings.json`` is missing, has an unsupported
    ``schema_version``, or is otherwise unusable.  Message must tell the
    operator to run ``tv_recon_run()``."""


class BackendConfigurationError(TvMcpError):
    """``recon_findings.json`` exists but a specific capability's entry
    is malformed (missing path, empty selector array, unsupported path
    value, etc.), or the capability is unverified and ``allow_unverified``
    was not set."""


class CapabilityUnavailable(TvMcpError):
    """Recon explicitly determined this capability has no working path
    (e.g. equity curve has no underlying table)."""


class ElementNotFound(TvMcpError):
    """All selectors in a fallback array failed to resolve within timeout.
    Includes the full selector list and timeout in the message."""


class SelectorVerificationFailed(TvMcpError):
    """A selector resolved to an element, but a sanity check on its
    content/structure failed (e.g. expected a table, got empty div) —
    signals the UI likely changed shape, not just class names."""


class BacktestTimeout(TvMcpError):
    """``wait_for_complete()`` exceeded its timeout."""


class NetworkCaptureError(TvMcpError):
    """``listen_network()`` failed to establish or lost the CDP Network
    domain subscription."""
