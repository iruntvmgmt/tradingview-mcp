"""Abstract base classes for all backend implementations.

Each domain gets an abstract interface that defines the contract between
controllers and backends.  Concrete implementations in ``dom_backend.py``,
``js_backend.py``, and ``network_backend.py`` inherit from these.
"""

from abc import ABC, abstractmethod
from typing import Any


class ChartBackend(ABC):
    """Symbol / timeframe / OHLCV data."""

    @abstractmethod
    async def set_symbol(self, symbol: str) -> None:
        ...

    @abstractmethod
    async def set_timeframe(self, timeframe: str) -> None:
        ...

    @abstractmethod
    async def get_ohlcv(self, limit: int = 500) -> list[dict]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class IndicatorBackend(ABC):
    """Apply / remove indicators and strategies."""

    @abstractmethod
    async def apply(self, pine_code: str, name: str) -> None:
        ...

    @abstractmethod
    async def remove(self, name: str) -> None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class BacktestBackend(ABC):
    """Run and read backtest results."""

    @abstractmethod
    async def run(self, strategy_name: str) -> None:
        ...

    @abstractmethod
    async def get_summary(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_trade_list(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def get_equity_curve(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class AlertBackend(ABC):
    """Create / edit / delete / list alerts."""

    @abstractmethod
    async def create(self, symbol: str, condition: dict, message: str) -> str:
        """Returns the alert id."""
        ...

    @abstractmethod
    async def edit(self, alert_id: str, condition: dict | None = None,
                   message: str | None = None) -> None:
        ...

    @abstractmethod
    async def delete(self, alert_id: str) -> None:
        ...

    @abstractmethod
    async def list(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class DrawingBackend(ABC):
    """Create / remove / list drawing objects."""

    @abstractmethod
    async def create(self, drawing_type: str, points: list[dict]) -> str:
        """Returns the drawing id."""
        ...

    @abstractmethod
    async def remove(self, drawing_id: str) -> None:
        ...

    @abstractmethod
    async def list(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class OrderBackend(ABC):
    """Paper trading order management.

    All implementations **must** check the ``confirmed`` flag before
    submitting orders.  Raise ``OrderSubmissionBlocked`` when unconfirmed.
    """

    @abstractmethod
    async def place(self, symbol: str, side: str, size: float,
                    order_type: str, sl: float | None, tp: float | None,
                    confirmed: bool) -> str:
        """Returns the order id.  Requires ``confirmed=True``."""
        ...

    @abstractmethod
    async def modify(self, order_id: str, size: float | None = None,
                     sl: float | None = None, tp: float | None = None) -> None:
        ...

    @abstractmethod
    async def cancel(self, order_id: str) -> None:
        ...

    @abstractmethod
    async def status(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class ReplayBackend(ABC):
    """Replay mode lifecycle."""

    @abstractmethod
    async def enter(self, start_bar: str | int) -> None:
        ...

    @abstractmethod
    async def step(self, bars: int = 1) -> None:
        ...

    @abstractmethod
    async def exit(self) -> None:
        ...

    @abstractmethod
    async def state(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class SettingsBackend(ABC):
    """Study / indicator settings (Inputs tab)."""

    @abstractmethod
    async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def read(self, study_name: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def write(self, study_name: str, values: dict[str, Any]) -> None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class PineScriptBackend(ABC):
    """Pine Script source code read/write/compile/debug."""

    @abstractmethod
    async def read(self, script_name: str) -> str:
        ...

    @abstractmethod
    async def write(self, script_name: str, source: str) -> None:
        ...

    @abstractmethod
    async def compile(self, script_name: str) -> dict[str, Any]:
        """Returns compile result (success flag + optional errors)."""
        ...

    @abstractmethod
    async def read_compile_errors(self) -> list[dict[str, Any]]:
        """Read compiler errors / warnings from the console panel."""
        ...

    @abstractmethod
    async def read_logs(self, script_name: str) -> list[dict[str, Any]]:
        """Read Pine Logs (log.info/warning/error output).
        Raises ``CapabilityUnavailable`` for published/protected scripts."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...
