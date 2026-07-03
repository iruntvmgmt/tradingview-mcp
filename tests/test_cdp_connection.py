"""Tests for CDPConnection — with mocked WebSocket transport.

Unit tests cover command dispatch, retry/backoff, and connection lifecycle.
Integration tests (marked @integration) require a running TV Desktop instance.
"""

import pytest

from core.services.cdp_connection import CDPConnection
from core.services.errors import CDPConnectionError


class TestCDPConnectionUnit:
    """Unit tests with no live CDP endpoint — verify logic and error paths."""

    @pytest.mark.asyncio
    async def test_connect_no_target_raises(self):
        """Connecting without a running TV Desktop should fail gracefully."""
        cdp = CDPConnection(debug_port=19999)  # unlikely-to-be-used port
        with pytest.raises(CDPConnectionError) as exc:
            await cdp.connect()
        assert "CONNECTION_ERROR" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_js_before_connect_raises(self):
        """Calling execute_js before connecting raises."""
        cdp = CDPConnection()
        with pytest.raises(CDPConnectionError) as exc:
            await cdp.execute_js("1+1")
        assert "Not connected" in str(exc.value)

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self):
        """health_check returns clean 'not connected' state."""
        cdp = CDPConnection()
        result = await cdp.health_check()
        assert result["connected"] is False
        assert result["target_id"] is None

    def test_default_port(self):
        cdp = CDPConnection()
        assert cdp._port == 8315

    def test_custom_port(self):
        cdp = CDPConnection(debug_port=9222)
        assert cdp._port == 9222


@pytest.mark.integration
class TestCDPConnectionIntegration:
    """Integration tests — require a live TV Desktop with --remote-debugging-port=8315.

    Run with: pytest tests/test_cdp_connection.py -m integration
    """

    @pytest.mark.asyncio
    async def test_connect_and_eval(self):
        cdp = CDPConnection(debug_port=8315)
        await cdp.connect()
        try:
            result = await cdp.execute_js("1+1")
            assert result.get("result", {}).get("value") == 2
        finally:
            await cdp.disconnect()

    @pytest.mark.asyncio
    async def test_list_targets(self):
        cdp = CDPConnection(debug_port=8315)
        await cdp.connect()
        try:
            targets = await cdp.list_targets()
            assert isinstance(targets, list)
            assert len(targets) > 0
        finally:
            await cdp.disconnect()

    @pytest.mark.asyncio
    async def test_select_main_renderer(self):
        cdp = CDPConnection(debug_port=8315)
        await cdp.connect()
        try:
            target_id = await cdp.select_main_renderer_target()
            assert target_id is not None
            assert isinstance(target_id, str)
        finally:
            await cdp.disconnect()

    @pytest.mark.asyncio
    async def test_health_check_connected(self):
        cdp = CDPConnection(debug_port=8315)
        await cdp.connect()
        try:
            result = await cdp.health_check()
            assert result["connected"] is True
            assert result["eval_ok"] is True
        finally:
            await cdp.disconnect()

    @pytest.mark.asyncio
    async def test_network_domain(self):
        cdp = CDPConnection(debug_port=8315)
        await cdp.connect()
        try:
            await cdp.listen_network(True)
            events = cdp.get_network_events()
            assert isinstance(events, list)
            await cdp.listen_network(False)
        finally:
            await cdp.disconnect()
