"""
Smoke test for CDP Connection — requires a live TradingView Desktop instance.

This is an integration test (not a unit test).  It will:
  1. Launch TradingView Desktop with remote debugging
  2. Connect via CDP
  3. Enumerate targets and select the main renderer
  4. Execute a simple JS expression
  5. Disconnect

Usage:
    uv run pytest tests/desktop/test_cdp_connection.py -v -s

    Or (skipping the app launch if already running on port 8315):
    SKIP_LAUNCH=1 uv run pytest tests/desktop/test_cdp_connection.py -v -s
"""

import asyncio
import os
import pytest

from tradingview_mcp.core.services.cdp_connection import CDPConnectionManager, ConnectionSetupError


@pytest.mark.asyncio
async def test_cdp_launch_connect_js():
    """Launch TV Desktop, connect, execute JS, disconnect."""
    skip_launch = os.environ.get("SKIP_LAUNCH") == "1"
    cdp = CDPConnectionManager()

    try:
        if not skip_launch:
            cdp.launch()

        await cdp.connect()

        # List targets
        targets = await cdp.list_targets()
        print(f"\nCDP targets found: {len(targets)}")
        for t in targets:
            print(f"  [{t['type']}] {t.get('title', '')[:60]}")

        # Select main renderer
        target_id = await cdp.select_main_renderer_target()
        print(f"Selected target: {target_id}")
        assert target_id, "No target selected"

        # Execute JS
        result = await cdp.execute_js("1 + 1")
        assert result == 2, f"Expected 2, got {result}"
        print("✅ JS execution: 1 + 1 = 2")

        # Execute another expression
        result2 = await cdp.execute_js("Object.keys(window).length")
        print(f"Window keys count: {result2}")
        assert isinstance(result2, int) and result2 > 0

        print("\n✅ CDP smoke test passed!")

    finally:
        await cdp.disconnect_async()


@pytest.mark.asyncio
async def test_cdp_connection_error():
    """Verify ConnectionSetupError is raised when connecting to a closed port."""
    cdp = CDPConnectionManager()

    # Try connecting to a port that's not open (port 1 is reserved)
    with pytest.raises(ConnectionSetupError):
        await cdp.connect(port=1, retries=1)


@pytest.mark.asyncio
async def test_select_main_renderer_no_targets():
    """Verify select_main_renderer_target raises when no viable targets."""
    # We'd need to mock list_targets for this — placeholder
    pass
