"""Tests for TVChartController — mocked backend, verify method dispatch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.chart_controller import TVChartController


@pytest.fixture
def mock_backend():
    """Return a mock that stands in for the chart + indicator backends."""
    backend = MagicMock()
    backend.set_symbol = AsyncMock()
    backend.set_timeframe = AsyncMock()
    backend.get_ohlcv = AsyncMock(return_value=[{"time": "2024-01-01", "open": 100}])
    backend.apply = AsyncMock()
    backend.remove = AsyncMock()
    backend.health_check = AsyncMock(return_value=True)
    return backend


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.chart_controller.build_chart_backend",
               return_value=mock_backend), \
         patch("core.services.chart_controller.build_indicator_backend",
               return_value=mock_backend):
        cdp = MagicMock()
        cdp.execute_js = AsyncMock()
        yield TVChartController(cdp, {"capabilities": {}}, allow_unverified=True)


class TestTVChartController:
    @pytest.mark.asyncio
    async def test_set_symbol(self, controller, mock_backend):
        await controller.set_symbol("AAPL")
        mock_backend.set_symbol.assert_awaited_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_set_timeframe(self, controller, mock_backend):
        await controller.set_timeframe("1h")
        mock_backend.set_timeframe.assert_awaited_once_with("1h")

    @pytest.mark.asyncio
    async def test_get_ohlcv(self, controller, mock_backend):
        result = await controller.get_ohlcv(limit=100)
        mock_backend.get_ohlcv.assert_awaited_once_with(100)
        assert result == [{"time": "2024-01-01", "open": 100}]

    @pytest.mark.asyncio
    async def test_add_indicator(self, controller, mock_backend):
        await controller.add_indicator("//@version=5\nindicator('test')", "Test")
        mock_backend.apply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_indicator(self, controller, mock_backend):
        await controller.remove_indicator("Test")
        mock_backend.remove.assert_awaited_once_with("Test")

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "chart" in result
        assert "indicator" in result
        assert result["chart"] is True
        assert result["indicator"] is True
