"""Validate WaveTrend MAX dynamic-cross HTF filter variants.

Keeps the dynamic-cross trigger isolated and compares the new default
HTF EMA-slope permission layer against small ATR anti-chop additions.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.backtest_controller import TVBacktestController
from core.services.cdp_connection import CDPConnection
from core.services.chart_controller import TVChartController
from core.services.pinescript_controller import TVPineScriptController
from core.services.strategy_variant_controller import StrategyVariantController


ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT.parent / "TRADINGVIEW_INDICATORS" / "WAVETREND" / "WaveTrend_MAX.pine"
SCRIPT_NAME = "WaveTrend MAX"
DEBUG_PORT = 8315
WAIT_SECONDS = 8.0
OUT_PATH = ROOT / "logs" / "wt_dynamic_filter_validation.json"
SCREENSHOT_DIR = ROOT / "logs" / "wt_dynamic_filter_validation"

ENTRY_NAMES = [
    "useDynamicCross",
    "useSignalCross",
    "useFib50Cross",
    "useZeroLineCross",
    "useBBReversion",
    "useDivergence",
    "useHiddenDivergence",
    "useBreakoutDyanmicCross",
    "useBBCross",
    "useFixedCross",
]


def repl(pattern: str, replacement: str, regex: bool = True) -> dict[str, Any]:
    return {"pattern": pattern, "replacement": replacement, "regex": regex}


def bool_input(name: str, value: bool) -> dict[str, Any]:
    return repl(rf"{name} = input\.bool\((true|false),", f"{name} = input.bool({str(value).lower()},")


def float_input(name: str, value: float) -> dict[str, Any]:
    return repl(rf"{name} = input\.float\([\d.]+", f"{name} = input.float({value}")


def int_input(name: str, value: int) -> dict[str, Any]:
    return repl(rf"{name} = input\.int\(\d+,", f"{name} = input.int({value},")


def trend_filter(value: str) -> dict[str, Any]:
    return repl(
        r'trendFilterOption = input\.string\("[^"]+", "Trend Filter"',
        f'trendFilterOption = input.string("{value}", "Trend Filter"',
    )


def base_dynamic_only() -> list[dict[str, Any]]:
    changes = [bool_input(name, name == "useDynamicCross") for name in ENTRY_NAMES]
    changes.extend(
        [
            trend_filter("None"),
            bool_input("useDynamicHtfFilter", True),
            bool_input("dynamicRequireHtfSlope", True),
            int_input("dynamicHtfEmaLen", 50),
            bool_input("useAutoRiskScaling", True),
        ]
    )
    return changes


VARIANTS = [
    {
        "label": "01_HTF_Slope_Default",
        "description": "Dynamic cross + 1H EMA50 side/slope",
        "changes": [bool_input("dynamicUseAtrChopFilter", False)],
    },
    {
        "label": "02_HTF_Slope_ATR_075",
        "description": "HTF slope + loose ATR anti-chop",
        "changes": [bool_input("dynamicUseAtrChopFilter", True), float_input("dynamicAtrThreshold", 0.75)],
    },
    {
        "label": "03_HTF_Slope_ATR_085",
        "description": "HTF slope + tested ATR anti-chop",
        "changes": [bool_input("dynamicUseAtrChopFilter", True), float_input("dynamicAtrThreshold", 0.85)],
    },
    {
        "label": "04_HTF_Slope_ATR_100",
        "description": "HTF slope + stricter ATR anti-chop",
        "changes": [bool_input("dynamicUseAtrChopFilter", True), float_input("dynamicAtrThreshold", 1.0)],
    },
    {
        "label": "05_HTF_Side_NoSlope",
        "description": "HTF side only, no slope requirement",
        "changes": [bool_input("dynamicRequireHtfSlope", False), bool_input("dynamicUseAtrChopFilter", False)],
    },
]


def to_num(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, "", "N/A"):
        return 0.0
    text = str(value).replace("−", "-").replace(",", "")
    for char in "+$%\u202f\u00a0 ":
        text = text.replace(char, "")
    try:
        return float(text)
    except ValueError:
        return 0.0


async def open_strategy_tester(cdp: CDPConnection) -> bool:
    js = r"""(() => {
        const candidates = Array.from(document.querySelectorAll('button, [role="tab"], [data-name], div, span'));
        const el = candidates.find((node) => {
            const txt = (node.textContent || '').trim();
            const meta = node.getAttribute && [
                node.getAttribute('aria-label') || '',
                node.getAttribute('title') || '',
                node.getAttribute('data-name') || '',
                node.id || ''
            ].join(' ');
            return txt === 'Strategy Tester' || txt === 'Overview' || meta.includes('Strategy Tester') || meta.includes('strategy-report');
        });
        if (!el) return false;
        el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, pointerId:1, pointerType:'mouse', isPrimary:true}));
        el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, buttons:1}));
        el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
        el.dispatchEvent(new PointerEvent('pointerup', {bubbles:true, pointerId:1, pointerType:'mouse', isPrimary:true}));
        el.click();
        return true;
    })()"""
    result = await cdp.execute_js(js)
    await asyncio.sleep(1.0)
    return bool(result.get("result", {}).get("value"))


async def body_metrics(cdp: CDPConnection) -> dict[str, Any]:
    js = r"""(() => {
        const text = document.body.innerText || '';
        const pick = (re) => {
            const m = text.match(re);
            return m ? m[1].replace('−', '-').replace(/,/g, '').trim() : 'N/A';
        };
        const trades = text.match(/Profitable\s*trades\s*[\d.]+%\s*(\d+)\s*\/\s*(\d+)/i);
        return {
            total_pnl: pick(/Total\s*PnL\s*([+\-−]?[\d,.]+)/i),
            total_pnl_pct: pick(/Total\s*PnL\s*[+\-−]?[\d,.]+\s*(?:USD|USDT)?\s*([+\-−]?[\d.]+)%/i),
            max_dd_pct: pick(/Max\s*[Dd]rawdown\s*[\d,.]+\s*(?:USD|USDT|points|pts)?\s*([\d.]+)%/i),
            winners: trades ? trades[1] : 'N/A',
            total_trades: trades ? trades[2] : 'N/A',
            win_rate_pct: pick(/(?:Percent\s*Profitable|Profitable\s*trades)\s*([\d.]+)%/i),
            body_has_tester: text.includes('Total PnL') || text.includes('Strategy Tester')
        };
    })()"""
    result = await cdp.execute_js(js)
    value = result.get("result", {}).get("value", {})
    return value if isinstance(value, dict) else {}


def score(row: dict[str, Any]) -> float:
    pf = to_num(row.get("profit_factor"))
    sharpe = to_num(row.get("sharpe"))
    total_pnl = to_num(row.get("total_pnl"))
    dd_pct = max(to_num(row.get("max_dd_pct")), 0.1)
    trades = max(int(to_num(row.get("total_trades"))), 0)
    if trades < 20 or pf <= 0:
        return -999.0
    return 2.0 * math.log(max(pf, 0.01)) + 0.7 * sharpe + 0.00005 * total_pnl + 0.25 * math.log(trades) - dd_pct / 10.0


async def main() -> None:
    cdp = CDPConnection(debug_port=DEBUG_PORT)
    await cdp.connect()
    try:
        recon = json.loads((ROOT / "recon_findings.json").read_text())
        pine = TVPineScriptController(cdp, recon, allow_unverified=True)
        backtest = TVBacktestController(cdp, recon, allow_unverified=True)
        chart = TVChartController(cdp, recon, allow_unverified=True)
        ctrl = StrategyVariantController(cdp, pine, backtest, chart)

        original_source = await pine.read(SCRIPT_NAME)
        results = []
        try:
            for idx, variant in enumerate(VARIANTS, start=1):
                safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", variant["label"]).strip("_")
                screenshot_path = SCREENSHOT_DIR / f"{idx:02d}_{safe_label}.png"
                result = await ctrl.run_variant(
                    script_name=SCRIPT_NAME,
                    source_path=str(SOURCE_PATH),
                    replacements=base_dynamic_only() + variant["changes"],
                    restore=False,
                    wait_seconds=WAIT_SECONDS,
                    screenshot_path=str(screenshot_path),
                )
                await open_strategy_tester(cdp)
                body = await body_metrics(cdp)
                summary = result.get("summary", {}) or {}
                row = {
                    "label": variant["label"],
                    "description": variant["description"],
                    "summary": summary,
                    "body_metrics": body,
                    "total_pnl": body.get("total_pnl", summary.get("net_profit", "N/A")),
                    "total_pnl_pct": body.get("total_pnl_pct", "N/A"),
                    "max_dd_pct": body.get("max_dd_pct", "N/A"),
                    "win_rate_pct": body.get("win_rate_pct", "N/A"),
                    "total_trades": body.get("total_trades", "N/A"),
                    "profit_factor": summary.get("profit_factor", "N/A"),
                    "sharpe": summary.get("sharpe", "N/A"),
                    "screenshot_path": str(screenshot_path),
                }
                row["score"] = score(row)
                results.append(row)
        finally:
            await ctrl.run_variant(SCRIPT_NAME, source=original_source, restore=False, wait_seconds=3.0)

        results.sort(key=lambda item: item["score"], reverse=True)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(results, indent=2, default=str))

        print(f"Validation results: {OUT_PATH}")
        print(f"{'Rank':<5} {'Variant':<24} {'Score':>8} {'PnL':>10} {'PF':>6} {'DD%':>7} {'WR%':>7} {'Trades':>7} {'Sharpe':>8}")
        print("-" * 92)
        for idx, row in enumerate(results, start=1):
            print(
                f"{idx:<5} {row['label']:<24} {row['score']:>8.3f} {str(row['total_pnl']):>10} "
                f"{str(row['profit_factor']):>6} {str(row['max_dd_pct']):>7} {str(row['win_rate_pct']):>7} "
                f"{str(row['total_trades']):>7} {str(row['sharpe']):>8}"
            )
    finally:
        await cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
