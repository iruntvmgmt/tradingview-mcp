"""JS-injection backends — Path A.

TradingView Desktop does not expose a public JS API (window.tvWidget,
activeChart, etc. are all undefined).  All JS backends raise
``CapabilityUnavailable``.  If a future TV Desktop version adds JS
APIs, recon will detect them and these classes become the active path.
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


class _JsStubMixin:
    """Mixin that raises CapabilityUnavailable on any method call."""

    def __init__(self, cdp=None, dom=None, capabilities: dict | None = None):
        self._cdp = cdp
        self._dom = dom
        self._caps = capabilities or {}

    def _unavailable(self, method: str) -> None:
        raise CapabilityUnavailable(
            f"JS API not available for {method} — no window.tvWidget found",
            details={"method": method, "domain": type(self).__name__},
        )


class JsChartBackend(_JsStubMixin, ChartBackend):
    async def set_symbol(self, symbol: str) -> None:
        self._unavailable("set_symbol")
    async def set_timeframe(self, timeframe: str) -> None:
        self._unavailable("set_timeframe")
    async def set_visible_range(self, start: str, end: str) -> None:
        self._unavailable("set_visible_range")
    async def get_ohlcv(self, limit: int = 500) -> list[dict]:
        self._unavailable("get_ohlcv")
    async def health_check(self) -> bool:
        return False


class JsIndicatorBackend(_JsStubMixin, IndicatorBackend):
    async def apply(self, pine_code: str, name: str) -> None:
        self._unavailable("apply")
    async def remove(self, name: str) -> None:
        self._unavailable("remove")
    async def health_check(self) -> bool:
        return False


class JsBacktestBackend(_JsStubMixin, BacktestBackend):
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


class JsAlertBackend(_JsStubMixin, AlertBackend):
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


class JsDrawingBackend(_JsStubMixin, DrawingBackend):
    async def create(self, drawing_type: str, points: list[dict]) -> str:
        self._unavailable("create")
    async def remove(self, drawing_id: str) -> None:
        self._unavailable("remove")
    async def list(self) -> list[dict[str, Any]]:
        self._unavailable("list")
    async def health_check(self) -> bool:
        return False


class JsOrderBackend(_JsStubMixin, OrderBackend):
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


class JsReplayBackend(_JsStubMixin, ReplayBackend):
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


class JsSettingsBackend(_JsStubMixin, SettingsBackend):
    async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
        self._unavailable("list_fields")
    async def read(self, study_name: str) -> dict[str, Any]:
        self._unavailable("read")
    async def write(self, study_name: str, values: dict[str, Any]) -> None:
        self._unavailable("write")
    async def health_check(self) -> bool:
        return False


class JsPineScriptBackend(_JsStubMixin, PineScriptBackend):
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
