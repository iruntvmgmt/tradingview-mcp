"""Tests for TVReplayController — critical: state-guard sequences."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.errors import ReplayStateError
from core.services.replay_controller import TVReplayController


@pytest.fixture
def mock_backend():
    b = MagicMock()
    b.enter = AsyncMock()
    b.step = AsyncMock()
    b.exit = AsyncMock()
    b.state = AsyncMock(return_value={"position": "bar-100"})
    b.health_check = AsyncMock(return_value=True)
    return b


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.replay_controller.build_replay_backend",
               return_value=mock_backend):
        yield TVReplayController(MagicMock(), {"capabilities": {}}, allow_unverified=True)


class TestTVReplayController:
    @pytest.mark.asyncio
    async def test_step_before_enter_raises(self, controller, mock_backend):
        with pytest.raises(ReplayStateError) as exc:
            await controller.step()
        assert "enter() first" in str(exc.value).lower()
        mock_backend.step.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exit_before_enter_raises(self, controller, mock_backend):
        with pytest.raises(ReplayStateError):
            await controller.exit()
        mock_backend.exit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enter_twice_raises(self, controller, mock_backend):
        await controller.enter("2024-01-01")
        assert controller._in_replay is True
        with pytest.raises(ReplayStateError):
            await controller.enter("2024-01-02")
        mock_backend.enter.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_happy_path_enter_step_exit(self, controller, mock_backend):
        await controller.enter("2024-01-01")
        assert controller._in_replay is True
        mock_backend.enter.assert_awaited_once_with("2024-01-01")

        await controller.step(bars=3)
        mock_backend.step.assert_awaited_once_with(3)

        await controller.exit()
        assert controller._in_replay is False
        mock_backend.exit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_state(self, controller, mock_backend):
        result = await controller.state()
        assert result["position"] == "bar-100"

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "replay" in result
