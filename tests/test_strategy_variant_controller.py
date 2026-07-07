from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.strategy_variant_controller import StrategyVariantController


def _make_controller():
    cdp = MagicMock()
    pine = MagicMock()
    backtest = MagicMock()
    chart = MagicMock()
    return StrategyVariantController(cdp, pine, backtest, chart)


def test_apply_regex_replacement_count_one():
    ctrl = _make_controller()
    source = "entry_mode = input.string(\"A\")\nentry_mode = input.string(\"B\")\n"
    result = ctrl._apply_replacements(
        source,
        [
            {
                "pattern": r"entry_mode = input\.string\(.*?\n",
                "replacement": 'entry_mode = "Fast + Medium Confluence"\n',
                "regex": True,
                "count": 1,
            }
        ],
    )
    assert result.startswith('entry_mode = "Fast + Medium Confluence"')
    assert 'entry_mode = input.string("B")' in result


def test_apply_literal_replacement():
    ctrl = _make_controller()
    result = ctrl._apply_replacements(
        "trade_direction = input.string(\"Both\")\n",
        [
            {
                "pattern": 'trade_direction = input.string("Both")',
                "replacement": 'trade_direction = "Long Only"',
                "regex": False,
            }
        ],
    )
    assert result == 'trade_direction = "Long Only"\n'


def test_missing_source_raises():
    ctrl = _make_controller()
    with pytest.raises(ValueError):
        ctrl._source_from_args(None, None)


@pytest.mark.asyncio
async def test_run_variant_restores_original_source(monkeypatch):
    ctrl = _make_controller()
    ctrl._pine.read = AsyncMock(side_effect=["// original", "// variant", "// original"])
    ctrl._backtest.get_performance_summary = AsyncMock(return_value={"profit_factor": "2.0"})
    ctrl._paste_source = AsyncMock(return_value=True)
    ctrl._update_on_chart = AsyncMock(return_value={"success": True})

    result = await ctrl.run_variant(
        script_name="Test Strategy",
        source="// variant",
        restore=True,
        wait_seconds=0,
    )

    assert result["source_match"] is True
    assert result["restore"]["source_match"] is True
    assert ctrl._paste_source.await_count == 2
    assert ctrl._update_on_chart.await_count == 2


def test_mcp_tools_registered():
    import server

    names = {tool.name for tool in server._tools_def}
    assert "tv_pine_update_chart_reliable" in names
    assert "tv_strategy_variant_run" in names
    assert "tv_strategy_sweep" in names
