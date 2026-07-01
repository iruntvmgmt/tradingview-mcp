"""Tests for TVOrderController — critical: confirmed gate at controller level."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.errors import OrderSubmissionBlocked
from core.services.order_controller import TVOrderController


@pytest.fixture
def mock_backend():
    b = MagicMock()
    b.place = AsyncMock(return_value="order-1")
    b.modify = AsyncMock()
    b.cancel = AsyncMock()
    b.status = AsyncMock(return_value=[{"type": "limit", "size": "1"}])
    b.health_check = AsyncMock(return_value=True)
    return b


@pytest.fixture
def controller(mock_backend):
    with patch("core.services.order_controller.build_order_backend",
               return_value=mock_backend):
        yield TVOrderController(MagicMock(), {"capabilities": {}}, allow_unverified=True)


class TestTVOrderController:
    @pytest.mark.asyncio
    async def test_place_without_confirmation_raises_at_controller(self, controller, mock_backend):
        """confirmed=False should raise at the controller level,
        never reaching the backend."""
        with pytest.raises(OrderSubmissionBlocked) as exc:
            await controller.place("AAPL", "buy", 1.0, confirmed=False)
        assert "ORDER_SUBMISSION_BLOCKED" in str(exc.value)
        mock_backend.place.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_place_with_confirmation_passes_through(self, controller, mock_backend):
        """confirmed=True should reach the backend and return the order id."""
        result = await controller.place("AAPL", "buy", 10, confirmed=True)
        assert result == "order-1"
        mock_backend.place.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_modify(self, controller, mock_backend):
        await controller.modify("order-1", size=5.0)
        mock_backend.modify.assert_awaited_once_with("order-1", 5.0, None, None)

    @pytest.mark.asyncio
    async def test_cancel(self, controller, mock_backend):
        await controller.cancel("order-1")
        mock_backend.cancel.assert_awaited_once_with("order-1")

    @pytest.mark.asyncio
    async def test_status(self, controller, mock_backend):
        result = await controller.status()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_health_check(self, controller, mock_backend):
        result = await controller.health_check()
        assert "order" in result
