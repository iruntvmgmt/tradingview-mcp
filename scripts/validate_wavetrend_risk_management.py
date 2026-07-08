"""WaveTrend MAX risk-management validation.

Compares exit personalities for the current entry/filter stack:
close sooner for drawdown control, balanced protection, and runner-style
settings for longer holds.
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

from core.services.cdp_connection import CDPConnection
from core.services.chart_controller import TVChartController
from core.services.pinescript_controller import TVPineScriptController
from core.services.backtest_controller import TVBacktestController
from core.services.strategy_variant_controller import StrategyVariantController


ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT.parent / "TRADINGVIEW_INDICATORS" / "WAVETREND" / "WaveTrend_MAX.pine"
SCRIPT_NAME = "WaveTrend MAX"
DEBUG_PORT = 8315
WAIT_SECONDS = 8.0
OUT_PATH = ROOT / "logs" / "wt_risk_management_validation.json"
SCREENSHOT_DIR = ROOT / "logs" / "wt_risk_management_validation"


def repl(pattern: str, replacement: str, regex: bool = True) -> dict[str, Any]:
    return {"pattern": pattern, "replacement": replacement, "regex": regex}


def bool_input(name: str, value: bool) -> dict[str, Any]:
    return repl(rf"{name} = input\.bool\((true|false),", f"{name} = input.bool({str(value).lower()},")


def int_input(name: str, value: int) -> dict[str, Any]:
    return repl(rf"{name} = input\.int\(\d+,", f"{name} = input.int({value},")


def float_input(name: str, value: float) -> dict[str, Any]:
    return repl(rf"{name} = input\.float\([\d.]+", f"{name} = input.float({value}")


def string_input(name: str, value: str, title: str) -> dict[str, Any]:
    return repl(rf'{name} = input\.string\("[^"]+", "{re.escape(title)}"', f'{name} = input.string("{value}", "{title}"')


def risk_changes(
    *,
    label: str,
    description: str,
    stop: int,
    atr_mult: float,
    chand_len: int,
    chand_mult: float,
    be_trigger: int,
    be_offset: int,
    tp1: int,
    tp1_qty: float,
    final_tp: int,
    use_final_tp: bool,
    trend_exit: bool,
    trend_mode: str,
    min_bars_exit: int,
    cooldown: int,
) -> dict[str, Any]:
    return {
        "label": label,
        "description": description,
        "changes": [
            bool_input("useAutoRiskScaling", False),
            bool_input("useStopLoss", True),
            int_input("stopLossPoints", stop),
            bool_input("useAtrStop", True),
            float_input("atrStopMult", atr_mult),
            bool_input("useChandelierStop", True),
            int_input("chandelierLength", chand_len),
            float_input("chandelierMult", chand_mult),
            bool_input("useBreakeven", True),
            int_input("breakevenTriggerPoints", be_trigger),
            int_input("breakevenOffsetPoints", be_offset),
            bool_input("useTradeCooldown", True),
            int_input("cooldownBars", cooldown),
            bool_input("usePartialTakeProfit", True),
            int_input("partialTakeProfitPoints", tp1),
            float_input("partialTakeProfitQty", tp1_qty),
            bool_input("useTakeProfit", use_final_tp),
            int_input("takeProfitPoints", final_tp),
            bool_input("useWtTrendExit", trend_exit),
            repl(
                r'wtTrendExitMode = input\.string\("[^"]+", "", options=',
                f'wtTrendExitMode = input.string("{trend_mode}", "", options=',
            ),
            int_input("minBarsBeforeTrendExit", min_bars_exit),
        ],
    }


VARIANTS = [
    risk_changes(
        label="01_Current_Default",
        description="Current manual risk defaults",
        stop=2500,
        atr_mult=2.5,
        chand_len=22,
        chand_mult=3.0,
        be_trigger=1500,
        be_offset=100,
        tp1=2000,
        tp1_qty=50.0,
        final_tp=6000,
        use_final_tp=False,
        trend_exit=True,
        trend_mode="WT1/WT2 Cross",
        min_bars_exit=1,
        cooldown=5,
    ),
    risk_changes(
        label="02_Faster_Protection",
        description="Close sooner: tighter stop/trail, faster breakeven, larger TP1",
        stop=1500,
        atr_mult=1.6,
        chand_len=14,
        chand_mult=2.0,
        be_trigger=800,
        be_offset=50,
        tp1=1200,
        tp1_qty=65.0,
        final_tp=3000,
        use_final_tp=True,
        trend_exit=True,
        trend_mode="WT1/WT2 Cross",
        min_bars_exit=0,
        cooldown=7,
    ),
    risk_changes(
        label="03_Balanced_DD",
        description="Balanced drawdown control with moderate room",
        stop=1800,
        atr_mult=2.0,
        chand_len=18,
        chand_mult=2.4,
        be_trigger=1000,
        be_offset=50,
        tp1=1500,
        tp1_qty=55.0,
        final_tp=4000,
        use_final_tp=True,
        trend_exit=True,
        trend_mode="BB Basis Cross",
        min_bars_exit=2,
        cooldown=6,
    ),
    risk_changes(
        label="04_Runner_Loose",
        description="Stay open longer: wider stops/trail, smaller TP1, delayed trend exit",
        stop=3200,
        atr_mult=3.0,
        chand_len=30,
        chand_mult=3.6,
        be_trigger=1800,
        be_offset=100,
        tp1=2500,
        tp1_qty=35.0,
        final_tp=8000,
        use_final_tp=False,
        trend_exit=True,
        trend_mode="WT1/WT2 Cross",
        min_bars_exit=4,
        cooldown=5,
    ),
    risk_changes(
        label="05_Range_Exit",
        description="Close when WT loses BB basis, medium stop and TP",
        stop=2000,
        atr_mult=2.0,
        chand_len=20,
        chand_mult=2.5,
        be_trigger=1200,
        be_offset=50,
        tp1=1800,
        tp1_qty=50.0,
        final_tp=4500,
        use_final_tp=True,
        trend_exit=True,
        trend_mode="BB Basis Cross",
        min_bars_exit=1,
        cooldown=5,
    ),
    risk_changes(
        label="06_DynamicBand_Reversal",
        description="Let winners breathe until dynamic band reversal",
        stop=2200,
        atr_mult=2.4,
        chand_len=24,
        chand_mult=3.0,
        be_trigger=1400,
        be_offset=75,
        tp1=2000,
        tp1_qty=45.0,
        final_tp=6000,
        use_final_tp=False,
        trend_exit=True,
        trend_mode="Dynamic Band Reversal",
        min_bars_exit=2,
        cooldown=5,
    ),
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
    await asyncio.sleep(0.8)
    return bool(result.get("result", {}).get("value"))


async def body_metrics(cdp: CDPConnection) -> dict[str, Any]:
    js = r"""(() => {
        const text = document.body.innerText || '';
        const pick = (re) => {
            const m = text.match(re);
            return m ? m[1].replace('−', '-').replace(/,/g, '').trim() : 'N/A';
        };
        const trades = text.match(/Profitable\s*trades\s*[\d.]+%\s*(\d+)\s*\/\s*(\d+)/i);
        const range = text.match(/([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+—\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})/);
        return {
            range: range ? range[1] : 'N/A',
            total_pnl: pick(/Total\s*PnL\s*([+\-−]?[\d,.]+)/i),
            total_pnl_pct: pick(/Total\s*PnL\s*[+\-−]?[\d,.]+\s*(?:USD|USDT)?\s*([+\-−]?[\d.]+)%/i),
            max_dd: pick(/Max\s*[Dd]rawdown\s*([\d,.]+)/i),
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
    dd_drag = dd_pct * 0.9
    return 2.2 * math.log(max(pf, 0.01)) + 0.7 * sharpe + 0.00004 * total_pnl + 0.2 * math.log(trades) - dd_drag


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
        rows = []
        try:
            for idx, variant in enumerate(VARIANTS, start=1):
                safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", variant["label"]).strip("_")
                screenshot_path = SCREENSHOT_DIR / f"{idx:02d}_{safe_label}.png"
                result = await ctrl.run_variant(
                    script_name=SCRIPT_NAME,
                    source_path=str(SOURCE_PATH),
                    replacements=variant["changes"],
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
                    "range": body.get("range", "N/A"),
                    "total_pnl": body.get("total_pnl", summary.get("net_profit", "N/A")),
                    "total_pnl_pct": body.get("total_pnl_pct", "N/A"),
                    "max_dd": body.get("max_dd", summary.get("max_drawdown", "N/A")),
                    "max_dd_pct": body.get("max_dd_pct", "N/A"),
                    "win_rate_pct": body.get("win_rate_pct", "N/A"),
                    "total_trades": body.get("total_trades", "N/A"),
                    "profit_factor": summary.get("profit_factor", "N/A"),
                    "sharpe": summary.get("sharpe", "N/A"),
                    "screenshot_path": str(screenshot_path),
                }
                row["score"] = score(row)
                rows.append(row)
        finally:
            await ctrl.run_variant(SCRIPT_NAME, source=original_source, restore=False, wait_seconds=3.0)

        rows.sort(key=lambda item: item["score"], reverse=True)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(rows, indent=2, default=str))

        print(f"Risk validation: {OUT_PATH}")
        print(f"{'Rank':<5} {'Variant':<26} {'Score':>8} {'PnL':>10} {'PF':>6} {'DD%':>7} {'WR%':>7} {'Trades':>7} {'Sharpe':>8}")
        print("-" * 96)
        for idx, row in enumerate(rows, start=1):
            print(
                f"{idx:<5} {row['label']:<26} {row['score']:>8.3f} {str(row['total_pnl']):>10} "
                f"{str(row['profit_factor']):>6} {str(row['max_dd_pct']):>7} {str(row['win_rate_pct']):>7} "
                f"{str(row['total_trades']):>7} {str(row['sharpe']):>8}"
            )
    finally:
        await cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
