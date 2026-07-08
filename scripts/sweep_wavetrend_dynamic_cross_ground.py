"""WaveTrend MAX — focused dynamic-cross permission sweep.

This intentionally keeps the entry trigger constant:
  long  = WT1 crosses up through the dynamic lower band (db)
  short = WT1 crosses down through the dynamic upper band (ub)

Variants only change the permission layer around that trigger so we can
separate useful swing/scalp locations from HTF-against-trend and chop fires.
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
WINDOW = "1M"
OUT_PATH = ROOT / "logs" / "wt_dynamic_cross_ground_results.json"
SCREENSHOT_DIR = ROOT / "logs" / "wt_dynamic_cross_ground"
RESEARCH_INITIAL_CAPITAL = 1_000_000.0

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


def bool_toggle(var_name: str, to_value: bool) -> dict[str, Any]:
    return {
        "pattern": rf"{var_name} = input\.bool\((true|false),",
        "replacement": f"{var_name} = input.bool({str(to_value).lower()},",
        "regex": True,
    }


def trend_filter_to(value: str) -> dict[str, Any]:
    return {
        "pattern": r'trendFilterOption = input\.string\("[^"]+", "Trend Filter"',
        "replacement": f'trendFilterOption = input.string("{value}", "Trend Filter"',
        "regex": True,
    }


def int_param(var_name: str, value: int) -> dict[str, Any]:
    return {
        "pattern": rf"{var_name} = input\.int\(\d+,",
        "replacement": f"{var_name} = input.int({value},",
        "regex": True,
    }


def float_param(var_name: str, value: float) -> dict[str, Any]:
    return {
        "pattern": rf"{var_name} = input\.float\([\d.]+",
        "replacement": f"{var_name} = input.float({value}",
        "regex": True,
    }


def research_filter(code: str) -> dict[str, Any]:
    insert = f"""sqzShortFilterOk = not useSqzFilter or sqzSelectedShortOk

// Research-only dynamic-cross permission layer.
{code}
"""
    return {
        "pattern": "sqzShortFilterOk = not useSqzFilter or sqzSelectedShortOk",
        "replacement": insert,
        "regex": False,
    }


def dynamic_go_conditions() -> list[dict[str, Any]]:
    return [
        {
            "pattern": r"goLong = longEntrySignals and isBullishTrend and sqzLongFilterOk and strategy\.position_size == 0",
            "replacement": "goLong = longEntrySignals and isBullishTrend and sqzLongFilterOk and researchLongOk and strategy.position_size == 0",
            "regex": True,
        },
        {
            "pattern": r"goShort = shortEntrySignals and isBearishTrend and sqzShortFilterOk and strategy\.position_size == 0",
            "replacement": "goShort = shortEntrySignals and isBearishTrend and sqzShortFilterOk and researchShortOk and strategy.position_size == 0",
            "regex": True,
        },
    ]


def base_replacements(trend: str = "None") -> list[dict[str, Any]]:
    repls = [bool_toggle(name, name == "useDynamicCross") for name in ENTRY_NAMES]
    repls.extend(
        [
            trend_filter_to(trend),
            bool_toggle("useSqzFilter", False),
            bool_toggle("useAutoRiskScaling", True),
            bool_toggle("useStopLoss", True),
            bool_toggle("useAtrStop", True),
            bool_toggle("useChandelierStop", True),
            bool_toggle("useBreakeven", True),
            bool_toggle("usePartialTakeProfit", True),
            bool_toggle("useTakeProfit", False),
            bool_toggle("useWtTrendExit", True),
            int_param("cooldownBars", 5),
            int_param("minBarsBeforeTrendExit", 1),
        ]
    )
    return repls


ALWAYS = "researchLongOk = true\nresearchShortOk = true"

HTF_EMA = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchLongOk = researchHtfClose > researchHtfEma
researchShortOk = researchHtfClose < researchHtfEma
""".strip()

HTF_EMA_SLOPE = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEmaPrev = request.security(syminfo.tickerid, "60", ta.ema(close, 50)[1], barmerge.gaps_off, barmerge.lookahead_off)
researchLongOk = researchHtfClose > researchHtfEma and researchHtfEma >= researchHtfEmaPrev
researchShortOk = researchHtfClose < researchHtfEma and researchHtfEma <= researchHtfEmaPrev
""".strip()

HTF_ATR = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchAtrOk = atrVal > ta.sma(atrVal, 50) * 0.85
researchLongOk = researchHtfClose > researchHtfEma and researchAtrOk
researchShortOk = researchHtfClose < researchHtfEma and researchAtrOk
""".strip()

HTF_SQZ_DIRECTION = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchLongOk = researchHtfClose > researchHtfEma and sqzMomentumUp
researchShortOk = researchHtfClose < researchHtfEma and sqzMomentumDown
""".strip()

HTF_RANGE_ROOM = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchLongOk = researchHtfClose > researchHtfEma and sqzLongRoomOk
researchShortOk = researchHtfClose < researchHtfEma and sqzShortRoomOk
""".strip()

HTF_ATR_SQZ_ROOM = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchAtrOk = atrVal > ta.sma(atrVal, 50) * 0.85
researchLongOk = researchHtfClose > researchHtfEma and researchAtrOk and sqzMomentumUp and sqzLongRoomOk
researchShortOk = researchHtfClose < researchHtfEma and researchAtrOk and sqzMomentumDown and sqzShortRoomOk
""".strip()

HTF_LOOSE_PULLBACK = """
researchHtfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEma = request.security(syminfo.tickerid, "60", ta.ema(close, 50), barmerge.gaps_off, barmerge.lookahead_off)
researchHtfEmaPrev = request.security(syminfo.tickerid, "60", ta.ema(close, 50)[1], barmerge.gaps_off, barmerge.lookahead_off)
researchNotHardDown = researchHtfClose > researchHtfEma or researchHtfEma >= researchHtfEmaPrev
researchNotHardUp = researchHtfClose < researchHtfEma or researchHtfEma <= researchHtfEmaPrev
researchAtrOk = atrVal > ta.sma(atrVal, 50) * 0.75
researchLongOk = researchNotHardDown and researchAtrOk and sqzLongRoomOk
researchShortOk = researchNotHardUp and researchAtrOk and sqzShortRoomOk
""".strip()


VARIANTS = [
    ("01_Dynamic_Raw", "Dynamic cross only, no permission filter", ALWAYS, "None"),
    ("02_Dynamic_WTSignal", "Dynamic cross plus chart WT1/WT2 trend", ALWAYS, "WT Signal Trend"),
    ("03_Dynamic_HTF_EMA", "Dynamic cross aligned with 1H EMA50 side", HTF_EMA, "None"),
    ("04_Dynamic_HTF_EMA_Slope", "1H EMA50 side plus EMA slope", HTF_EMA_SLOPE, "None"),
    ("05_Dynamic_HTF_ATR", "1H EMA50 side plus ATR anti-chop", HTF_ATR, "None"),
    ("06_Dynamic_HTF_SQZ_Dir", "1H EMA50 side plus squeeze momentum direction", HTF_SQZ_DIRECTION, "None"),
    ("07_Dynamic_HTF_Room", "1H EMA50 side plus range room", HTF_RANGE_ROOM, "None"),
    ("08_Dynamic_HTF_ATR_SQZ_Room", "1H EMA50 side, ATR, SQZ direction, and range room", HTF_ATR_SQZ_ROOM, "None"),
    ("09_Dynamic_Loose_Pullback", "Not hard against 1H trend, ATR loose, range room", HTF_LOOSE_PULLBACK, "None"),
]


def build_variant(label: str, description: str, filter_code: str, trend: str) -> dict[str, Any]:
    repls = base_replacements(trend)
    repls.append(research_filter(filter_code))
    repls.extend(dynamic_go_conditions())
    return {
        "label": label,
        "replacements": repls,
        "metadata": {"description": description, "filter_code": filter_code, "trend": trend},
        "wait_seconds": WAIT_SECONDS,
    }


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
        const wanted = ['Strategy Tester', 'Strategy tester', 'Overview'];
        for (const label of wanted) {
            const el = candidates.find((node) => {
                const txt = (node.textContent || '').trim();
                const meta = node.getAttribute && [
                    node.getAttribute('aria-label') || '',
                    node.getAttribute('title') || '',
                    node.getAttribute('data-name') || '',
                    node.id || ''
                ].join(' ');
                return txt === label || meta.includes(label) || meta.includes('strategy-report');
            });
            if (el) {
                el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, pointerId:1, pointerType:'mouse', isPrimary:true}));
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, buttons:1}));
                el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                el.dispatchEvent(new PointerEvent('pointerup', {bubbles:true, pointerId:1, pointerType:'mouse', isPrimary:true}));
                el.click();
                return true;
            }
        }
        return false;
    })()"""
    result = await cdp.execute_js(js)
    await asyncio.sleep(1.0)
    return bool(result.get("result", {}).get("value"))


async def set_date_preset(cdp: CDPConnection, preset: str) -> bool:
    js = f"""(() => {{
        const tabs = Array.from(document.querySelectorAll('[data-name*="date-range-tab"]'));
        const target = tabs.find((el) => (el.getAttribute('data-name') || '').includes({json.dumps(preset)}));
        if (target) {{
            target.click();
            return true;
        }}
        return false;
    }})()"""
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
            total_trades_text: pick(/Total\s*(?:closed\s*)?trades\s*(\d+)/i),
            profitable_winners: trades ? trades[1] : 'N/A',
            profitable_total: trades ? trades[2] : 'N/A',
            win_rate_pct: pick(/(?:Percent\s*Profitable|Profitable\s*trades)\s*([\d.]+)%/i),
            max_dd_pct: pick(/Max\s*[Dd]rawdown\s*[\d.,]+\s*(?:USD|USDT|points|pts)?\s*([\d.]+)%/i),
            body_has_tester: text.includes('Strategy Tester') || text.includes('Total PnL')
        };
    })()"""
    result = await cdp.execute_js(js)
    value = result.get("result", {}).get("value", {})
    return value if isinstance(value, dict) else {}


def score(result: dict[str, Any]) -> float:
    pf = to_num(result.get("profit_factor"))
    sharpe = to_num(result.get("sharpe"))
    net = to_num(result.get("net_profit"))
    dd_pct = to_num(result.get("max_dd_pct"))
    trades = int(to_num(result.get("trade_count")))
    if trades < 20 or pf <= 0:
        return -999.0
    dd_penalty = max(dd_pct, 0.1) / 10.0
    return (
        2.0 * math.log(max(pf, 0.01))
        + 0.7 * sharpe
        + 0.00005 * net
        + 0.25 * math.log(trades)
        - dd_penalty
    )


async def enrich_result(cdp: CDPConnection, result: dict[str, Any]) -> dict[str, Any]:
    await open_strategy_tester(cdp)
    body = await body_metrics(cdp)
    summary = result.get("summary", {}) or {}
    total_from_body = int(to_num(body.get("profitable_total") or body.get("total_trades_text")))
    if total_from_body <= 0:
        net = abs(to_num(summary.get("net_profit")))
        avg = abs(to_num(summary.get("avg_pnl")))
        total_from_body = int(round(net / avg)) if avg > 0 else 0
    dd_pct = body.get("max_dd_pct", "N/A")
    if dd_pct == "N/A":
        dd_value = to_num(summary.get("max_drawdown"))
        dd_pct = round(dd_value / RESEARCH_INITIAL_CAPITAL * 100, 4) if dd_value > 0 else "N/A"
    result.update(
        {
            "body_metrics": body,
            "trade_count": total_from_body,
            "win_rate_pct": body.get("win_rate_pct", "N/A"),
            "max_dd_pct": dd_pct,
            "net_profit": summary.get("net_profit", "N/A"),
            "profit_factor": summary.get("profit_factor", "N/A"),
            "sharpe": summary.get("sharpe", "N/A"),
            "max_drawdown": summary.get("max_drawdown", "N/A"),
            "score": score(
                {
                    "profit_factor": summary.get("profit_factor", "N/A"),
                    "sharpe": summary.get("sharpe", "N/A"),
                    "net_profit": summary.get("net_profit", "N/A"),
                    "max_dd_pct": dd_pct,
                    "trade_count": total_from_body,
                }
            ),
        }
    )
    return result


async def main() -> None:
    cdp = CDPConnection(debug_port=DEBUG_PORT)
    await cdp.connect()
    try:
        recon_path = ROOT / "recon_findings.json"
        recon = json.loads(recon_path.read_text()) if recon_path.exists() else {}
        pine = TVPineScriptController(cdp, recon, allow_unverified=True)
        backtest = TVBacktestController(cdp, recon, allow_unverified=True)
        chart = TVChartController(cdp, recon, allow_unverified=True)
        variants = [build_variant(*variant) for variant in VARIANTS]
        ctrl = StrategyVariantController(cdp, pine, backtest, chart)

        await open_strategy_tester(cdp)
        await set_date_preset(cdp, WINDOW)

        original_source = await pine.read(SCRIPT_NAME)
        enriched = []
        try:
            for index, variant in enumerate(variants, start=1):
                safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", variant["label"]).strip("_")
                screenshot_path = SCREENSHOT_DIR / f"{index:02d}_{safe_label}.png"
                result = await ctrl.run_variant(
                    script_name=SCRIPT_NAME,
                    source_path=str(SOURCE_PATH),
                    replacements=variant["replacements"],
                    restore=False,
                    wait_seconds=WAIT_SECONDS,
                    screenshot_path=str(screenshot_path),
                )
                result["label"] = variant["label"]
                result["metadata"] = variant["metadata"]
                enriched.append(await enrich_result(cdp, result))
        finally:
            await ctrl.run_variant(
                script_name=SCRIPT_NAME,
                source=original_source,
                restore=False,
                wait_seconds=3.0,
            )

        enriched.sort(key=lambda item: item.get("score", -999.0), reverse=True)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(enriched, indent=2, default=str))

        print("\nDynamic-cross permission sweep")
        print(f"Window: {WINDOW} | Results: {OUT_PATH}")
        print(f"{'Rank':<5} {'Variant':<32} {'Score':>8} {'PF':>7} {'Net':>12} {'DD%':>8} {'WR%':>7} {'Trades':>7} {'Sharpe':>8}")
        print("-" * 105)
        for idx, result in enumerate(enriched, start=1):
            print(
                f"{idx:<5} {result['label']:<32} {result.get('score', 0):>8.3f} "
                f"{str(result.get('profit_factor')):>7} {str(result.get('net_profit')):>12} "
                f"{str(result.get('max_dd_pct')):>8} {str(result.get('win_rate_pct')):>7} "
                f"{str(result.get('trade_count')):>7} {str(result.get('sharpe')):>8}"
            )
    finally:
        await cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
