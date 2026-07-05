"""Tests for backend factory functions, DOM backends, and error paths.

Uses mocked CDP and DomUtils to verify correct dispatch without a live
TradingView Desktop instance.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.backends import (
    build_alert_backend,
    build_backtest_backend,
    build_chart_backend,
    build_drawing_backend,
    build_indicator_backend,
    build_order_backend,
    build_pinescript_backend,
    build_replay_backend,
    build_settings_backend,
)
from core.services.backends.dom_backend import (
    DomAlertBackend,
    DomBacktestBackend,
    DomChartBackend,
    DomDrawingBackend,
    DomIndicatorBackend,
    DomOrderBackend,
    DomPineScriptBackend,
    DomReplayBackend,
    DomSettingsBackend,
)
from core.services.backends.js_backend import (
    JsChartBackend,
    JsIndicatorBackend,
    JsBacktestBackend,
    JsAlertBackend,
    JsDrawingBackend,
    JsOrderBackend,
    JsReplayBackend,
    JsSettingsBackend,
    JsPineScriptBackend,
)
from core.services.errors import (
    BackendConfigurationError,
    CapabilityUnavailable,
    OrderSubmissionBlocked,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_cdp():
    cdp = MagicMock()
    cdp.execute_js = AsyncMock(return_value={"result": {"value": 1}})
    cdp.click_at = AsyncMock()
    return cdp


@pytest.fixture
def mock_dom():
    dom = MagicMock()
    dom.resolve_selector = AsyncMock(return_value="button.found")
    dom.click = AsyncMock()
    dom.type_text = AsyncMock()
    dom.extract_text = AsyncMock(return_value="test value")
    dom.extract_table = AsyncMock(return_value=[["col1", "col2"], ["val1", "val2"]])
    dom.click_at_coordinates = AsyncMock()
    return dom


@pytest.fixture
def recon_all_dom():
    """A recon dict where all capabilities are set to 'dom' path and verified."""
    caps = {}
    cap_names = [
        "symbol_control", "timeframe_control", "ohlcv_read",
        "indicator_apply", "indicator_remove",
        "backtest_run", "backtest_summary", "backtest_trade_list", "backtest_equity_curve",
        "alert_create", "alert_edit", "alert_delete", "alert_list",
        "drawing_create", "drawing_remove", "drawing_list",
        "order_place", "order_modify", "order_cancel", "order_status_read",
        "replay_enter", "replay_step", "replay_exit", "replay_state_read",
        "screenshot",
        "settings_list_fields", "settings_read", "settings_write",
        "pine_read", "pine_write", "pine_compile", "pine_compile_errors_read",
        "pine_logs_read",
    ]
    for name in cap_names:
        caps[name] = {"path": "dom", "verified": True, "detail": {}}
    return {"capabilities": caps}


# ═══════════════════════════════════════════════════════════════
# Factory Dispatch Tests
# ═══════════════════════════════════════════════════════════════

class TestFactoryDispatch:
    """Each factory should return the correct backend class based on path."""

    def test_chart_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_chart_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomChartBackend)

    def test_indicator_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_indicator_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomIndicatorBackend)

    def test_backtest_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_backtest_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomBacktestBackend)

    def test_alert_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_alert_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomAlertBackend)

    def test_drawing_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_drawing_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomDrawingBackend)

    def test_order_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_order_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomOrderBackend)

    def test_replay_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_replay_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomReplayBackend)

    def test_settings_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_settings_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomSettingsBackend)

    def test_pinescript_dom(self, mock_cdp, mock_dom, recon_all_dom):
        backend = build_pinescript_backend(recon_all_dom, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, DomPineScriptBackend)

    def test_unverified_raises(self, mock_cdp, mock_dom, recon_all_dom):
        """Without allow_unverified, unverified capabilities raise."""
        for cap_name in list(recon_all_dom["capabilities"].keys()):
            recon_all_dom["capabilities"][cap_name]["verified"] = False
        with pytest.raises(CapabilityUnavailable):
            build_chart_backend(recon_all_dom, mock_cdp, mock_dom)
        # Reset
        for cap_name in list(recon_all_dom["capabilities"].keys()):
            recon_all_dom["capabilities"][cap_name]["verified"] = True


# ═══════════════════════════════════════════════════════════════
# DOM Backend Method Tests
# ═══════════════════════════════════════════════════════════════

class TestDomChartBackend:
    @pytest.mark.asyncio
    async def test_set_symbol(self, mock_cdp, mock_dom):
        caps = {
            "symbol_control": {
                "verified": True, "path": "dom",
                "detail": {"selectors": ["#sym-btn"], "symbol_search_input_selectors": ["#sym-input"]}
            }
        }
        backend = DomChartBackend(mock_cdp, mock_dom, caps)
        await backend.set_symbol("AAPL")
        mock_dom.click.assert_awaited_once_with(["#sym-btn"])
        mock_dom.type_text.assert_awaited_once_with(["#sym-input"], "AAPL", clear_first=True)

    @pytest.mark.asyncio
    async def test_health_check_ok(self, mock_cdp, mock_dom):
        caps = {"symbol_control": {"detail": {"selectors": ["#sym-btn"]}}}
        backend = DomChartBackend(mock_cdp, mock_dom, caps)
        result = await backend.health_check()
        assert result is True


class TestDomOrderBackend:
    @pytest.mark.asyncio
    async def test_place_without_confirmation_raises(self, mock_cdp, mock_dom):
        caps = {"order_place": {"detail": {"field_selectors": {}, "submit_selectors": [], "open_panel_selector": []}}}
        backend = DomOrderBackend(mock_cdp, mock_dom, caps)
        with pytest.raises(OrderSubmissionBlocked) as exc:
            await backend.place("AAPL", "buy", 1.0, "market", None, None, confirmed=False)
        assert "ORDER_SUBMISSION_BLOCKED" in str(exc.value)

    @pytest.mark.asyncio
    async def test_place_with_confirmation(self, mock_cdp, mock_dom):
        caps = {
            "order_place": {
                "detail": {
                    "open_panel_selector": ["#trade-btn"],
                    "field_selectors": {"size": ["#size-input"]},
                    "submit_selectors": ["#submit-btn"],
                }
            }
        }
        backend = DomOrderBackend(mock_cdp, mock_dom, caps)
        result = await backend.place("AAPL", "buy", 10, "market", None, None, confirmed=True)
        assert result.startswith("order-")
        mock_dom.click.assert_any_await(["#trade-btn"])
        mock_dom.click.assert_any_await(["#submit-btn"])


class TestDomBacktestBackend:
    @pytest.mark.asyncio
    async def test_get_trade_list(self, mock_cdp, mock_dom):
        caps = {"backtest_trade_list": {"detail": {}}}
        # Mock innerText to return a trade list
        mock_cdp.execute_js.return_value = {
            "result": {"value": "List of trades\n\nTrade number\n\n1long\n\nExit\nEntry\n\nJun 08, 2026, 00:15\nJun 07, 2026, 22:40\n\n29,180.00\nUSD\n29,198.75\nUSD\n\n1\n583.98 KUSD\n\n-375\nUSD\n\n-0.06%"}
        }
        backend = DomBacktestBackend(mock_cdp, mock_dom, caps)
        result = await backend.get_trade_list()
        assert len(result) == 1
        assert result[0]["trade_number"] == 1
        assert result[0]["direction"] == "long"
        assert result[0]["net_pnl"] == -375.0


class TestDomReplayBackend:
    @pytest.mark.asyncio
    async def test_enter(self, mock_cdp, mock_dom):
        caps = {"replay_enter": {"detail": {"selectors": ["#replay-btn"]}}}
        backend = DomReplayBackend(mock_cdp, mock_dom, caps)
        await backend.enter("2024-01-01")
        mock_dom.click.assert_awaited_once_with(["#replay-btn"])

    @pytest.mark.asyncio
    async def test_step(self, mock_cdp, mock_dom):
        caps = {"replay_step": {"detail": {"step_selectors": ["#step-btn"]}}}
        backend = DomReplayBackend(mock_cdp, mock_dom, caps)
        await backend.step(bars=3)
        assert mock_dom.click.await_count == 3


# ═══════════════════════════════════════════════════════════════
# JS Backend Tests — all should raise CapabilityUnavailable
# ═══════════════════════════════════════════════════════════════

class TestJsBackends:
    @pytest.mark.asyncio
    async def test_js_chart_unavailable(self, mock_cdp, mock_dom):
        backend = JsChartBackend(mock_cdp, mock_dom, {})
        with pytest.raises(CapabilityUnavailable):
            await backend.set_symbol("AAPL")

    @pytest.mark.asyncio
    async def test_js_order_unavailable(self, mock_cdp, mock_dom):
        backend = JsOrderBackend(mock_cdp, mock_dom, {})
        with pytest.raises(CapabilityUnavailable):
            await backend.place("AAPL", "buy", 1, "market", None, None, True)


# ═══════════════════════════════════════════════════════════════
# BackendConfigurationError Tests
# ═══════════════════════════════════════════════════════════════

class TestBackendConfigurationErrors:
    def test_unknown_path_raises(self, mock_cdp, mock_dom):
        recon = {
            "capabilities": {
                "symbol_control": {"path": "invalid", "verified": True, "detail": {}}
            }
        }
        with pytest.raises(BackendConfigurationError):
            build_chart_backend(recon, mock_cdp, mock_dom, allow_unverified=True)
