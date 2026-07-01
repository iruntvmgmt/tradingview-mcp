"""
Unit tests for backends — mocked, no live app required.
"""

import pytest

from tradingview_mcp.core.services.backends.base import ChartBackend, IndicatorBackend, BacktestBackend
from tradingview_mcp.core.services.backends.dom_backend import (
    DomChartBackend, DomIndicatorBackend, DomBacktestBackend,
)
from tradingview_mcp.core.services.backends import (
    build_chart_backend, build_indicator_backend, build_backtest_backend,
)
from tradingview_mcp.core.services.errors import BackendConfigurationError


# ── Mock classes ──────────────────────────────────────────────────────────────

class MockCDP:
    async def execute_js(self, code):
        return None


class MockDom:
    async def is_visible(self, selectors):
        return bool(selectors)

    async def click(self, selectors):
        pass

    async def type_text(self, selectors, text, clear_first=True):
        pass

    async def extract_text(self, selectors):
        return "123.45"

    async def extract_table(self, table_sels, row_sels):
        return [{"col_0": "test"}]

    async def wait_for_selector(self, selectors, timeout_s=10):
        return True

    async def wait_until(self, predicate, timeout_s=10):
        return True


@pytest.fixture
def mock_cdp():
    return MockCDP()


@pytest.fixture
def mock_dom():
    return MockDom()


@pytest.fixture
def sample_recon():
    return {
        "schema_version": 1,
        "capabilities": {
            "symbol_control": {
                "path": "dom", "verified": True,
                "detail": {"selectors": ["[data-name='symbol-search']", "[class*='symbol']"]}
            },
            "timeframe_control": {
                "path": "dom", "verified": True,
                "detail": {"selectors": ["[data-name='timeframe']"]}
            },
            "indicator_apply": {
                "path": "dom", "verified": True,
                "detail": {
                    "editor_selectors": ["[class*='pine-editor']"],
                    "add_to_chart_selectors": ["button:has-text('Add')"]
                }
            },
            "ohlcv_read": {
                "path": "network", "verified": False,
                "detail": {}
            },
            "backtest_run": {
                "path": "dom", "verified": True,
                "detail": {"tab_selectors": ["[class*='strategy-tester']"]}
            },
            "backtest_summary": {
                "path": "dom", "verified": True,
                "detail": {
                    "tab_selectors": ["button:has-text('Overview')"],
                    "row_selectors": {"net_profit": ["..."], "win_rate": ["..."]}
                }
            },
            "backtest_trade_list": {
                "path": "dom", "verified": True,
                "detail": {"table_selectors": ["table"], "row_selectors": ["tr"]}
            },
            "backtest_equity_curve": {
                "path": "dom", "verified": False,
                "detail": {"fallback": "numeric_table_if_present_else_null"}
            },
            "screenshot": {"path": "cdp", "verified": True, "detail": {}}
        }
    }


# ── Tests for backend instantiation ───────────────────────────────────────────

class TestBackendBuilders:
    def test_build_chart_backend_dom(self, sample_recon, mock_cdp, mock_dom):
        backend = build_chart_backend("symbol_control", sample_recon, mock_cdp, mock_dom)
        assert isinstance(backend, DomChartBackend)

    def test_build_indicator_backend_dom(self, sample_recon, mock_cdp, mock_dom):
        backend = build_indicator_backend(sample_recon, mock_cdp, mock_dom)
        assert isinstance(backend, DomIndicatorBackend)

    def test_build_backtest_backend_dom(self, sample_recon, mock_cdp, mock_dom):
        backend = build_backtest_backend(sample_recon, mock_cdp, mock_dom)
        assert isinstance(backend, DomBacktestBackend)

    def test_build_backend_unverified_raises(self, sample_recon, mock_cdp, mock_dom):
        with pytest.raises(BackendConfigurationError):
            build_chart_backend("ohlcv_read", sample_recon, mock_cdp, mock_dom)

    def test_build_backend_unverified_allowed(self, sample_recon, mock_cdp, mock_dom):
        # ohlcv_read has path "network", so we get NetworkChartBackend
        from tradingview_mcp.core.services.backends.network_backend import NetworkChartBackend
        backend = build_chart_backend("ohlcv_read", sample_recon, mock_cdp, mock_dom, allow_unverified=True)
        assert isinstance(backend, NetworkChartBackend)

    def test_build_backend_missing_capability(self, sample_recon, mock_cdp, mock_dom):
        with pytest.raises(BackendConfigurationError):
            build_chart_backend("nonexistent", sample_recon, mock_cdp, mock_dom)


# ── Tests for backend methods ─────────────────────────────────────────────────

class TestDomBackendMethods:
    @pytest.mark.asyncio
    async def test_dom_chart_health_check(self, mock_cdp, mock_dom):
        detail = {"selectors": ["[data-name='symbol-search']"]}
        backend = DomChartBackend(mock_cdp, mock_dom, detail)
        result = await backend.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_dom_backtest_get_summary(self, mock_cdp, mock_dom):
        detail = {
            "tab_selectors": ["button:has-text('Overview')"],
            "row_selectors": {"net_profit": ["..."], "win_rate": ["..."]}
        }
        backend = DomBacktestBackend(mock_cdp, mock_dom, detail)
        summary = await backend.get_summary()
        assert "net_profit" in summary
        assert "win_rate" in summary

    @pytest.mark.asyncio
    async def test_dom_backtest_get_trade_list(self, mock_cdp, mock_dom):
        detail = {"table_selectors": ["table"], "row_selectors": ["tr"], "tab_selectors": []}
        backend = DomBacktestBackend(mock_cdp, mock_dom, detail)
        trades = await backend.get_trade_list()
        assert isinstance(trades, list)

    @pytest.mark.asyncio
    async def test_dom_backtest_equity_curve_is_none(self, mock_cdp, mock_dom):
        detail = {"fallback": "numeric_table_if_present_else_null"}
        backend = DomBacktestBackend(mock_cdp, mock_dom, detail)
        curve = await backend.get_equity_curve()
        assert curve is None
