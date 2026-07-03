"""Tests for TVDrawingController — mocked backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.drawing_controller import TVDrawingController


@pytest.fixture
def mock_backend():
    b = MagicMock()
    b.create = AsyncMock(return_value="drawing-1")
    b.remove = AsyncMock()
    b.list = AsyncMock(return_value=[{"type": "trendline", "points": []}])
    b.health_check = AsyncMock(return_value=True)
    return b


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.drawing_controller.build_drawing_backend",
               return_value=mock_backend):
        yield TVDrawingController(MagicMock(), {"capabilities": {}}, allow_unverified=True)


class TestTVDrawingController:
    @pytest.mark.asyncio
    async def test_create(self, controller, mock_backend):
        pts = [{"time": "2024-01-01", "price": 100}]
        result = await controller.create("trendline", pts)
        assert result == "drawing-1"
        mock_backend.create.assert_awaited_once_with("trendline", pts)

    @pytest.mark.asyncio
    async def test_remove(self, controller, mock_backend):
        await controller.remove("drawing-1")
        mock_backend.remove.assert_awaited_once_with("drawing-1")

    @pytest.mark.asyncio
    async def test_list(self, controller, mock_backend):
        result = await controller.list()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "drawing" in result
