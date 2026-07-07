"""WaveTrend MAX v5.9 — Entry Signal Combination Sweep.

Tests 8 strategic variants to identify optimal entry signal + trend filter combos.
Uses the StrategyVariantController for source-level replacements + restore.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection
from core.services.strategy_variant_controller import StrategyVariantController
from core.services.pinescript_controller import TVPineScriptController
from core.services.backtest_controller import TVBacktestController
from core.services.chart_controller import TVChartController

SOURCE_PATH = str(Path(__file__).resolve().parent.parent.parent /
                   "TRADINGVIEW_INDICATORS" / "WAVETREND" / "WaveTrend_MAX.pine")
SCRIPT_NAME = "WaveTrend MAX"
WAIT_SECONDS = 8.0  # generous wait for backtest computation
SCREENSHOT_DIR = str(Path(__file__).resolve().parent.parent / "logs" / "wt_max_sweep")

# ── Boolean toggle helpers ──
def bool_toggle(var_name: str, to_value: bool) -> dict:
    """Return a literal replacement that flips an input.bool line."""
    return {
        "pattern": f"{var_name} = input.bool({str(not to_value).lower()},",
        "replacement": f"{var_name} = input.bool({str(to_value).lower()},",
        "regex": False,
    }

def trend_filter_to(value: str) -> dict:
    """Replace the trend filter dropdown value."""
    return {
        "pattern": r'trendFilterOption = input\.string\("[^"]+", "Trend Filter"',
        "replacement": f'trendFilterOption = input.string("{value}", "Trend Filter"',
        "regex": True,
    }

def int_param(var_name: str, to_value: int) -> dict:
    """Replace an input.int value."""
    return {
        "pattern": rf'{var_name} = input\.int\(\d+,',
        "replacement": f'{var_name} = input.int({to_value},',
        "regex": True,
    }

# ── Variant definitions ──
# Each variant lists which entry signals to ENABLE (all others disabled)
# plus optional trend filter and exit param overrides.

ENTRY_NAMES = [
    "useDynamicCross", "useSignalCross", "useFib50Cross",
    "useZeroLineCross", "useBBReversion", "useDivergence",
    "useHiddenDivergence", "useBreakoutDyanmicCross",
    "useBBCross", "useFixedCross",
]

VARIANTS = [
    {
        "label": "01_Baseline_Default",
        "metadata": {"description": "Default v5.9 config: Dynamic + Signal + Divergence, WT Signal Trend"},
        "enabled": ["useDynamicCross", "useSignalCross", "useDivergence"],
        "trend": "WT Signal Trend",
        "exit_overrides": {},
    },
    {
        "label": "02_All_Entries_No_Filter",
        "metadata": {"description": "Every entry signal ON, trend filter OFF — max trade frequency"},
        "enabled": ENTRY_NAMES,
        "trend": "None",
        "exit_overrides": {},
    },
    {
        "label": "03_All_Entries_WT_Signal",
        "metadata": {"description": "Every entry signal ON with WT Signal Trend filter"},
        "enabled": ENTRY_NAMES,
        "trend": "WT Signal Trend",
        "exit_overrides": {},
    },
    {
        "label": "04_Divergence_Only",
        "metadata": {"description": "Pure divergence entries (Regular + Hidden), no trend filter"},
        "enabled": ["useDivergence", "useHiddenDivergence"],
        "trend": "None",
        "exit_overrides": {},
    },
    {
        "label": "05_Cross_Only_Tight",
        "metadata": {"description": "Only cross-based entries (Dynamic+Signal+Fib50+Zero), WT Signal Trend"},
        "enabled": ["useDynamicCross", "useSignalCross", "useFib50Cross", "useZeroLineCross"],
        "trend": "WT Signal Trend",
        "exit_overrides": {"stopLossPoints": 1500, "takeProfitPoints": 3000},
    },
    {
        "label": "06_BB_Mean_Reversion",
        "metadata": {"description": "BB Reversion + Dynamic Cross, WT vs BB Basis trend"},
        "enabled": ["useDynamicCross", "useBBReversion"],
        "trend": "WT vs BB Basis",
        "exit_overrides": {},
    },
    {
        "label": "07_Breakout_Mode",
        "metadata": {"description": "Breakout crosses + BB crosses, WT Zero Line trend"},
        "enabled": ["useBreakoutDyanmicCross", "useBBCross"],
        "trend": "WT Zero Line Trend",
        "exit_overrides": {},
    },
    {
        "label": "08_Conservative_Best",
        "metadata": {"description": "Signal Cross + Divergence only, WT Fib Trend, tight exits"},
        "enabled": ["useSignalCross", "useDivergence"],
        "trend": "WT Fib Trend",
        "exit_overrides": {"stopLossPoints": 1500, "takeProfitPoints": 2500},
    },
]


def build_replacements(variant: dict) -> list[dict]:
    """Build the full replacement list for a variant starting from baseline defaults."""
    enabled = set(variant["enabled"])
    repls = []

    # 1. Set all entry booleans: ON if in enabled set, OFF otherwise
    for name in ENTRY_NAMES:
        repls.append(bool_toggle(name, name in enabled))

    # 2. Set trend filter
    repls.append(trend_filter_to(variant["trend"]))

    # 3. Override exit params if specified
    for param, value in variant.get("exit_overrides", {}).items():
        repls.append(int_param(param, value))

    # 4. Keep restore-friendly defaults for params we're not testing
    #    (ensure stop loss, TP, trail are at baseline if not overridden)
    baseline_exits = {"stopLossPoints": 2000, "takeProfitPoints": 4000,
                       "trailPointsInput": 2000, "trailOffsetInput": 500,
                       "cooldownBars": 5}
    for param, value in baseline_exits.items():
        if param not in variant.get("exit_overrides", {}):
            repls.append(int_param(param, value))

    return repls


async def main():
    print("=" * 70)
    print("WaveTrend MAX v5.9 — Entry Signal Combination Sweep")
    print("=" * 70)
    print(f"Source: {SOURCE_PATH}")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print(f"Variants: {len(VARIANTS)}")
    print(f"Wait per variant: {WAIT_SECONDS}s")
    print()

    # Connect
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()
    print("✅ CDP connected")

    # Load recon findings
    recon_path = Path(__file__).resolve().parent.parent / "recon_findings.json"
    recon = json.loads(recon_path.read_text()) if recon_path.exists() else {}

    # Build controllers
    pine = TVPineScriptController(cdp, recon, allow_unverified=True)
    backtest = TVBacktestController(cdp, recon, allow_unverified=True)
    chart = TVChartController(cdp, recon, allow_unverified=True)
    variant_ctrl = StrategyVariantController(cdp, pine, backtest, chart)

    # Build sweep variants with replacements
    sweep_variants = []
    for v in VARIANTS:
        sweep_variants.append({
            "label": v["label"],
            "replacements": build_replacements(v),
            "metadata": v["metadata"],
            "wait_seconds": WAIT_SECONDS,
        })

    print("Variants configured:")
    for v in sweep_variants:
        enabled_count = len([r for r in v["replacements"]
                             if "input.bool(true," in r["replacement"]])
        print(f"  {v['label']}: {v['metadata']['description']} "
              f"({len(v['replacements'])} replacements)")

    print("\n🚀 Running sweep...")
    results = await variant_ctrl.sweep(
        script_name=SCRIPT_NAME,
        source_path=SOURCE_PATH,
        variants=sweep_variants,
        restore=True,
        wait_seconds=WAIT_SECONDS,
        screenshot_dir=SCREENSHOT_DIR,
    )

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    # Build a comparison table
    rows = []
    for r in results:
        summary = r.get("summary", {}) or {}
        rows.append({
            "label": r["label"],
            "paste_ok": r["paste_ok"],
            "source_match": r["source_match"],
            "update_ok": r.get("update", {}).get("success", False),
            "net_profit": summary.get("Net Profit", "N/A"),
            "sharpe": summary.get("Sharpe Ratio", "N/A"),
            "win_rate": summary.get("Percent Profitable", "N/A"),
            "trades": summary.get("Total Closed Trades", "N/A"),
            "dd_pct": summary.get("Max Drawdown", "N/A"),
            "pf": summary.get("Profit Factor", "N/A"),
            "screenshot": r.get("screenshot_path", "N/A"),
        })

    # Print formatted
    header = f"{'Variant':<30} {'Net Profit':>12} {'Sharpe':>8} {'WR%':>7} {'Trades':>7} {'DD%':>9} {'PF':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        net = row["net_profit"]
        sharpe = row["sharpe"]
        wr = row["win_rate"]
        trades = row["trades"]
        dd = row["dd_pct"]
        pf = row["pf"]

        # Parse numeric from strings
        try: net_f = float(str(net).replace("$","").replace(",","").replace("%","").strip())
        except: net_f = net
        try: sharpe_f = float(str(sharpe).replace(",","").strip())
        except: sharpe_f = sharpe
        try: wr_f = float(str(wr).replace("%","").replace(",","").strip())
        except: wr_f = wr

        print(f"{row['label']:<30} {str(net_f):>12} {str(sharpe_f):>8} {str(wr_f):>7} {str(trades):>7} {str(dd):>9} {str(pf):>7}")

    print()
    print("Restore:", results[0].get("restore", {}).get("source_match", "?"))

    # Save full results
    out_path = Path(__file__).resolve().parent.parent / "logs" / "wt_max_sweep_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nFull results saved to: {out_path}")

    await cdp.disconnect()
    print("✅ CDP disconnected — source restored")


if __name__ == "__main__":
    asyncio.run(main())
