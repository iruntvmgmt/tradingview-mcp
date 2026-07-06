"""Network-intercept backends — Path B.

Captures OHLCV and other data from WebSocket frames and XHR responses
intercepted via CDP ``Network`` domain.  Currently a stub — the network
path is expected only for ``ohlcv_read``; all other network backends
raise ``CapabilityUnavailable``.
"""

from typing import Any

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
from core.services.errors import CapabilityUnavailable


class _NetworkStubMixin:
    """Mixin that raises CapabilityUnavailable on any method call."""

    def __init__(self, cdp=None, dom=None, capabilities: dict | None = None):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities or {}

    def _unavailable(self, method: str) -> None:
        raise CapabilityUnavailable(
            f"Network path not implemented for {method} — "
            f"CDP Network domain requires event buffering",
            details={"method": method, "domain": type(self).__name__},
        )


class NetworkChartBackend(_NetworkStubMixin, ChartBackend):
    async def set_symbol(self, symbol: str) -> None:
        self._unavailable("set_symbol")
    async def set_timeframe(self, timeframe: str) -> None:
        self._unavailable("set_timeframe")
    async def set_visible_range(self, start: str, end: str) -> None:
        self._unavailable("set_visible_range")
    async def get_ohlcv(self, limit: int = 500) -> list[dict]:
        self._unavailable("get_ohlcv")
    def supports_absolute_visible_range(self) -> bool:
        return False
    async def health_check(self) -> bool:
        return False


class NetworkIndicatorBackend(_NetworkStubMixin, IndicatorBackend):
    async def apply(self, pine_code: str, name: str) -> None:
        self._unavailable("apply")
    async def remove(self, name: str) -> None:
        self._unavailable("remove")
    async def health_check(self) -> bool:
        return False


class NetworkBacktestBackend(_NetworkStubMixin, BacktestBackend):
    async def run(self, strategy_name: str) -> None:
        self._unavailable("run")
    async def get_summary(self) -> dict[str, Any]:
        self._unavailable("get_summary")
    async def get_trade_list(self) -> list[dict[str, Any]]:
        self._unavailable("get_trade_list")
    async def get_equity_curve(self) -> list[dict[str, Any]]:
        self._unavailable("get_equity_curve")
    async def health_check(self) -> bool:
        return False


class NetworkAlertBackend(_NetworkStubMixin, AlertBackend):
    async def create(self, symbol: str, condition: dict, message: str) -> str:
        self._unavailable("create")
    async def edit(self, alert_id: str, condition: dict | None = None, message: str | None = None) -> None:
        self._unavailable("edit")
    async def delete(self, alert_id: str) -> None:
        self._unavailable("delete")
    async def list(self) -> list[dict[str, Any]]:
        self._unavailable("list")
    async def health_check(self) -> bool:
        return False


class NetworkDrawingBackend(_NetworkStubMixin, DrawingBackend):
    async def create(self, drawing_type: str, points: list[dict]) -> str:
        self._unavailable("create")
    async def remove(self, drawing_id: str) -> None:
        self._unavailable("remove")
    async def list(self) -> list[dict[str, Any]]:
        self._unavailable("list")
    async def health_check(self) -> bool:
        return False


class NetworkOrderBackend(_NetworkStubMixin, OrderBackend):
    async def place(self, symbol: str, side: str, size: float, order_type: str, sl: float | None, tp: float | None, confirmed: bool) -> str:
        self._unavailable("place")
    async def modify(self, order_id: str, size: float | None = None, sl: float | None = None, tp: float | None = None) -> None:
        self._unavailable("modify")
    async def cancel(self, order_id: str) -> None:
        self._unavailable("cancel")
    async def status(self) -> list[dict[str, Any]]:
        self._unavailable("status")
    async def health_check(self) -> bool:
        return False


class NetworkReplayBackend(_NetworkStubMixin, ReplayBackend):
    async def enter(self, start_bar: str | int) -> None:
        self._unavailable("enter")
    async def step(self, bars: int = 1) -> None:
        self._unavailable("step")
    async def exit(self) -> None:
        self._unavailable("exit")
    async def state(self) -> dict[str, Any]:
        self._unavailable("state")
    async def health_check(self) -> bool:
        return False


class NetworkSettingsBackend(_NetworkStubMixin, SettingsBackend):
    async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
        self._unavailable("list_fields")
    async def read(self, study_name: str) -> dict[str, Any]:
        self._unavailable("read")
    async def write(self, study_name: str, values: dict[str, Any]) -> None:
        self._unavailable("write")
    async def health_check(self) -> bool:
        return False


class NetworkPineScriptBackend(_NetworkStubMixin, PineScriptBackend):
    async def read(self, script_name: str) -> str:
        self._unavailable("read")
    async def write(self, script_name: str, source: str) -> None:
        self._unavailable("write")
    async def compile(self, script_name: str) -> dict[str, Any]:
        self._unavailable("compile")
    async def read_compile_errors(self) -> list[dict[str, Any]]:
        self._unavailable("read_compile_errors")
    async def read_logs(self, script_name: str) -> list[dict[str, Any]]:
        self._unavailable("read_logs")
    async def health_check(self) -> bool:
        return False
