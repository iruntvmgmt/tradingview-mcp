"""Tests for TVAlertController — mocked backend, verify method dispatch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.alert_controller import TVAlertController


@pytest.fixture
def mock_backend():
    b = MagicMock()
    b.create = AsyncMock(return_value="alert-1")
    b.edit = AsyncMock()
    b.delete = AsyncMock()
    b.list = AsyncMock(return_value=[{"name": "test", "condition": ">100"}])
    b.health_check = AsyncMock(return_value=True)
    return b


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.alert_controller.build_alert_backend",
               return_value=mock_backend):
        yield TVAlertController(MagicMock(), {"capabilities": {}}, allow_unverified=True)


class TestTVAlertController:
    @pytest.mark.asyncio
    async def test_create(self, controller, mock_backend):
        result = await controller.create("AAPL", {"condition": ">150"}, "alert msg")
        assert result == "alert-1"
        mock_backend.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_edit(self, controller, mock_backend):
        await controller.edit("alert-1", message="new msg")
        mock_backend.edit.assert_awaited_once_with("alert-1", None, "new msg")

    @pytest.mark.asyncio
    async def test_delete(self, controller, mock_backend):
        await controller.delete("alert-1")
        mock_backend.delete.assert_awaited_once_with("alert-1")

    @pytest.mark.asyncio
    async def test_list(self, controller, mock_backend):
        result = await controller.list()
        assert len(result) == 1
        assert result[0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "alert" in result
