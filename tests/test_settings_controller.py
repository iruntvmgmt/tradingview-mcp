"""Tests for TVSettingsController — mocked backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.settings_controller import TVSettingsController


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.list_fields = AsyncMock(return_value=[
        {"name": "length", "type": "int", "current_value": 14}
    ])
    backend.read = AsyncMock(return_value={"length": 14})
    backend.write = AsyncMock()
    backend.health_check = AsyncMock(return_value=True)
    return backend


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.settings_controller.build_settings_backend",
               return_value=mock_backend):
        cdp = MagicMock()
        yield TVSettingsController(cdp, {"capabilities": {}}, allow_unverified=True)


class TestTVSettingsController:
    @pytest.mark.asyncio
    async def test_list_fields(self, controller, mock_backend):
        result = await controller.list_fields("SMA")
        assert len(result) == 1
        assert result[0]["name"] == "length"

    @pytest.mark.asyncio
    async def test_read(self, controller, mock_backend):
        result = await controller.read("SMA")
        assert result["length"] == 14

    @pytest.mark.asyncio
    async def test_write(self, controller, mock_backend):
        await controller.write("SMA", {"length": 21})
        mock_backend.write.assert_awaited_once_with("SMA", {"length": 21})

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "settings" in result
