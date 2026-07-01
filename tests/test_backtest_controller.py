"""Tests for TVBacktestController — mocked backend, verify polling logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.backtest_controller import TVBacktestController


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.run = AsyncMock()
    backend.get_summary = AsyncMock(return_value={"net_profit": "1000", "win_rate": "60%"})
    backend.get_trade_list = AsyncMock(return_value=[{"entry": "1", "exit": "2"}])
    backend.get_equity_curve = AsyncMock(return_value=[{"time": "t", "value": 100}])
    backend.health_check = AsyncMock(return_value=True)
    return backend


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.backtest_controller.build_backtest_backend",
               return_value=mock_backend):
        cdp = MagicMock()
        yield TVBacktestController(cdp, {"capabilities": {}}, allow_unverified=True)


class TestTVBacktestController:
    @pytest.mark.asyncio
    async def test_run_strategy(self, controller, mock_backend):
        await controller.run_strategy("Test Strategy")
        mock_backend.run.assert_awaited_once_with("Test Strategy")

    @pytest.mark.asyncio
    async def test_wait_for_complete_returns_true(self, controller, mock_backend):
        result = await controller.wait_for_complete(timeout=5.0)
        assert result is True
        mock_backend.health_check.assert_awaited()

    @pytest.mark.asyncio
    async def test_wait_for_complete_timeout(self, controller, mock_backend):
        mock_backend.health_check = AsyncMock(return_value=False)
        result = await controller.wait_for_complete(timeout=0.5)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_performance_summary(self, controller, mock_backend):
        result = await controller.get_performance_summary()
        assert result["net_profit"] == "1000"

    @pytest.mark.asyncio
    async def test_get_trade_list(self, controller, mock_backend):
        result = await controller.get_trade_list()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_equity_curve(self, controller, mock_backend):
        result = await controller.get_equity_curve()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "backtest" in result
