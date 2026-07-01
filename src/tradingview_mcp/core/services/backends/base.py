"""
Abstract backend interfaces for the TradingView Desktop Controller.

Each backend family (Chart, Indicator, Backtest) has a dedicated ABC.
Controllers call ``self.backend.<method>()`` and never branch on path.
"""

from abc import ABC, abstractmethod
from typing import Any


class ChartBackend(ABC):
    """Controls chart-level operations (symbol, timeframe, OHLCV data)."""

    @abstractmethod
    async def set_symbol(self, symbol: str) -> None: ...

    @abstractmethod
    async def set_timeframe(self, tf: str) -> None: ...

    @abstractmethod
    async def get_ohlcv(self, limit: int = 500) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap check that selectors/JS paths still resolve, without
        performing the actual action."""


class IndicatorBackend(ABC):
    """Manages Pine Script indicators on the chart."""

    @abstractmethod
    async def add(self, pine_code: str, name: str) -> None: ...

    @abstractmethod
    async def remove(self, name: str) -> None: ...

    @abstractmethod
    async def health_check(self) -> bool: ...


class BacktestBackend(ABC):
    """Runs and reads backtest results from the Strategy Tester."""

    @abstractmethod
    async def run(self, strategy_name: str) -> None: ...

    @abstractmethod
    async def get_summary(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_trade_list(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_equity_curve(self) -> list[dict[str, Any]] | None: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
