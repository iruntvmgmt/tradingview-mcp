"""Tests for TVPineScriptController — mocked backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.pinescript_controller import TVPineScriptController


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.read = AsyncMock(return_value="//@version=5\nindicator('test')")
    backend.write = AsyncMock()
    backend.compile = AsyncMock(return_value={"success": True})
    backend.read_compile_errors = AsyncMock(return_value=[{"message": "test error"}])
    backend.read_logs = AsyncMock(return_value=[{"timestamp": "t", "level": "info", "message": "hello"}])
    backend.health_check = AsyncMock(return_value=True)
    return backend


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.pinescript_controller.build_pinescript_backend",
               return_value=mock_backend):
        cdp = MagicMock()
        yield TVPineScriptController(cdp, {"capabilities": {}}, allow_unverified=True)


class TestTVPineScriptController:
    @pytest.mark.asyncio
    async def test_read(self, controller, mock_backend):
        result = await controller.read("test")
        assert "indicator('test')" in result

    @pytest.mark.asyncio
    async def test_write(self, controller, mock_backend):
        await controller.write("test", "new code")
        mock_backend.write.assert_awaited_once_with("test", "new code")

    @pytest.mark.asyncio
    async def test_compile(self, controller, mock_backend):
        result = await controller.compile("test")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_read_compile_errors(self, controller, mock_backend):
        result = await controller.read_compile_errors()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_read_logs(self, controller, mock_backend):
        result = await controller.read_logs("test")
        assert result[0]["level"] == "info"

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "pinescript" in result
