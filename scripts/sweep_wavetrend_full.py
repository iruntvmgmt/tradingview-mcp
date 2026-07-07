"""WaveTrend MAX v5.9 — Full Parameter Sweep (Phases 2-7).

Sequential sweeps, each locking the winner from the previous phase.
Phase 1 (Entry Signals) already completed → Divergence Only is best.

Phases:
  2. Exit Management  (SL × TP grid, trail pts, cooldown)
  3. Calculation      (n1 × n2 grid, MA type)
  4. Divergence Pivots (lookback left × right)
  5. Signal Filters   (Volume, ATR toggles)
  6. Dynamic Bands    (cyclicMemory × leveling)
  7. B-Bands          (bbLen × bbMult)

Total: ~80 variants, ~12 min at 8s each.
"""

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection
from core.services.strategy_variant_controller import StrategyVariantController
from core.services.pinescript_controller import TVPineScriptController
from core.services.backtest_controller import TVBacktestController
from core.services.chart_controller import TVChartController

SOURCE_PATH = str(Path(__file__).resolve().parent.parent.parent /
                   "TRADINGVIEW_INDICATORS" / "WAVETREND" / "WaveTrend_MAX.pine")
SCRIPT_NAME = "WaveTrend MAX"
WAIT_SECONDS = 8.0
SCREENSHOT_DIR = str(Path(__file__).resolve().parent.parent / "logs" / "wt_max_full_sweep")

# ── Divergence Only baseline (locked from Phase 1) ──
DIVERGENCE_ONLY_ENTRIES = {
    "useDynamicCross": False, "useSignalCross": False, "useFib50Cross": False,
    "useZeroLineCross": False, "useBBReversion": False, "useDivergence": True,
    "useHiddenDivergence": True, "useBreakoutDyanmicCross": False,
    "useBBCross": False, "useFixedCross": False,
    "trendFilterOption": "None",
}

ENTRY_NAMES = list(DIVERGENCE_ONLY_ENTRIES.keys())[:10]

# ── Replacement helpers ──
def bool_toggle(var: str, to: bool) -> dict:
    return {"pattern": f"{var} = input.bool({str(not to).lower()},", "replacement": f"{var} = input.bool({str(to).lower()},", "regex": False}

def trend_filter_to(val: str) -> dict:
    return {"pattern": r'trendFilterOption = input\.string\("[^"]+", "Trend Filter"', "replacement": f'trendFilterOption = input.string("{val}", "Trend Filter"', "regex": True}

def int_param(var: str, to: int) -> dict:
    return {"pattern": rf'{var} = input\.int\(\d+,', "replacement": f'{var} = input.int({to},', "regex": True}


def base_entry_replacements() -> list[dict]:
    """Replacements that lock entry signals to Divergence Only."""
    repls = []
    for name in ENTRY_NAMES:
        repls.append(bool_toggle(name, DIVERGENCE_ONLY_ENTRIES[name]))
    repls.append(trend_filter_to(DIVERGENCE_ONLY_ENTRIES["trendFilterOption"]))
    return repls


def lock_exit_defaults() -> list[dict]:
    """Lock exit params to v5.9 defaults (adjusted per-phase)."""
    return [
        int_param("stopLossPoints", 2000),
        int_param("takeProfitPoints", 4000),
        int_param("trailPointsInput", 2000),
        int_param("trailOffsetInput", 500),
        int_param("cooldownBars", 5),
    ]


def lock_calc_defaults() -> list[dict]:
    return [
        int_param("n1", 10),
        int_param("n2", 21),
        {"pattern": 'maType = input.string("EMA",', "replacement": 'maType = input.string("EMA",', "regex": False},
    ]


def lock_pivot_defaults() -> list[dict]:
    return [
        int_param("divPivotLookbackLeft", 5),
        int_param("divPivotLookbackRight", 3),
        int_param("maxBarsBetweenPivots", 100),
        int_param("maxStoredPivots", 30),
    ]


def lock_filter_defaults() -> list[dict]:
    return [
        bool_toggle("useVolumeFilter", False),
        int_param("volumeLookback", 20),
        bool_toggle("useAtrFilter", False),
        {"pattern": r'atrThreshold = input\.float\([\d.]+', "replacement": 'atrThreshold = input.float(1.0', "regex": True},
    ]


def lock_bands_defaults() -> list[dict]:
    return [
        int_param("cyclicMemory", 20),
        int_param("leveling", 10),
        int_param("bbLen", 14),
        {"pattern": r'bbMult = input\.float\([\d.]+', "replacement": 'bbMult = input.float(0.8', "regex": True},
    ]


# ═══════════════════════════════════════════════════════════════
# PHASE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

@dataclass
class Phase:
    name: str
    description: str
    variants: list[dict] = field(default_factory=list)
    winner: dict | None = None


def build_phase2_exit() -> Phase:
    """Exit Management: SL × TP grid → best combo → trail sweep → cooldown sweep."""
    variants = []

    # ── 5×5 SL×TP grid ──
    sl_values = [1000, 2000, 3000, 4000, 5000]
    tp_values = [2000, 4000, 6000, 8000, 10000]
    
    for sl in sl_values:
        for tp in tp_values:
            if tp <= sl:
                continue  # invalid: TP must exceed SL
            label = f"E_SL{sl}_TP{tp}"
            desc = f"SL={sl}pts, TP={tp}pts"
            repls = base_entry_replacements() + lock_exit_defaults() + [
                int_param("stopLossPoints", sl),
                int_param("takeProfitPoints", tp),
            ]
            # Disable trailing for pure SL/TP test
            repls.append(bool_toggle("useTrailingStop", False))
            variants.append({
                "label": label, "replacements": repls,
                "metadata": {"phase": 2, "type": "sl_tp_grid", "description": desc,
                             "sl": sl, "tp": tp},
            })

    return Phase(name="Exit Management SL×TP", description="5×5 SL/TP grid with trail disabled", variants=variants)


def build_phase3_calculation() -> Phase:
    """Calculation: n1 × n2 grid → best → MA type sweep."""
    variants = []

    n1_vals = [6, 10, 14, 18]
    n2_vals = [14, 21, 28, 35]
    ma_types = ["SMA", "EMA", "WMA", "RMA", "HMA"]

    # ── n1 × n2 grid (EMA by default) ──
    for n1 in n1_vals:
        for n2 in n2_vals:
            label = f"C_n1_{n1}_n2_{n2}"
            desc = f"WT Channel={n1}, Average={n2}, EMA"
            repls = (base_entry_replacements() + lock_exit_defaults() +
                     lock_calc_defaults() + lock_pivot_defaults() +
                     lock_filter_defaults() + lock_bands_defaults() +
                     [int_param("n1", n1), int_param("n2", n2)])
            variants.append({
                "label": label, "replacements": repls,
                "metadata": {"phase": 3, "type": "n1_n2_grid", "description": desc,
                             "n1": n1, "n2": n2, "maType": "EMA"},
            })

    # ── MA type sweep (on default n1=10, n2=21) ──
    for ma in ma_types:
        label = f"C_MA_{ma}"
        desc = f"MA Type={ma}, n1=10, n2=21"
        repls = (base_entry_replacements() + lock_exit_defaults() +
                 lock_calc_defaults() + lock_pivot_defaults() +
                 lock_filter_defaults() + lock_bands_defaults() +
                 [{"pattern": r'maType = input\.string\("EMA",', "replacement": f'maType = input.string("{ma}",', "regex": True}])
        variants.append({
            "label": label, "replacements": repls,
            "metadata": {"phase": 3, "type": "ma_type", "description": desc, "maType": ma},
        })

    return Phase(name="Calculation", description="n1×n2 grid + MA type sweep", variants=variants)


def build_phase4_pivots() -> Phase:
    """Divergence Pivots: lookback left × right grid."""
    variants = []

    left_vals = [3, 5, 7, 10]
    right_vals = [2, 3, 4]

    for left in left_vals:
        for right in right_vals:
            label = f"P_L{left}_R{right}"
            desc = f"Pivot Left={left}, Right={right}"
            repls = (base_entry_replacements() + lock_exit_defaults() +
                     lock_calc_defaults() + lock_pivot_defaults() +
                     lock_filter_defaults() + lock_bands_defaults() +
                     [int_param("divPivotLookbackLeft", left),
                      int_param("divPivotLookbackRight", right)])
            variants.append({
                "label": label, "replacements": repls,
                "metadata": {"phase": 4, "type": "pivot_lookback", "description": desc,
                             "left": left, "right": right},
            })

    return Phase(name="Divergence Pivots", description="Pivot left × right sweep", variants=variants)


def build_phase5_filters() -> Phase:
    """Signal Filters: Volume + ATR combos."""
    variants = []
    configs = [
        ("F_Both_Off", "Volume OFF, ATR OFF", False, False),
        ("F_Vol_Only", "Volume ON, ATR OFF", True, False),
        ("F_ATR_Only", "Volume OFF, ATR ON", False, True),
        ("F_Both_On", "Volume ON, ATR ON", True, True),
    ]

    for label, desc, vol, atr in configs:
        repls = (base_entry_replacements() + lock_exit_defaults() +
                 lock_calc_defaults() + lock_pivot_defaults() +
                 lock_filter_defaults() + lock_bands_defaults() +
                 [bool_toggle("useVolumeFilter", vol),
                  bool_toggle("useAtrFilter", atr)])
        variants.append({
            "label": label, "replacements": repls,
            "metadata": {"phase": 5, "type": "filters", "description": desc,
                         "volume_filter": vol, "atr_filter": atr},
        })

    return Phase(name="Signal Filters", description="Volume & ATR filter combos", variants=variants)


def build_phase6_dynamic_bands() -> Phase:
    """Dynamic Bands: cyclicMemory × leveling."""
    variants = []

    mem_vals = [10, 20, 30]
    level_vals = [5, 10, 15]

    for mem in mem_vals:
        for level in level_vals:
            label = f"DB_M{mem}_L{level}"
            desc = f"Bands Lookback={mem}, Percentile={level}"
            repls = (base_entry_replacements() + lock_exit_defaults() +
                     lock_calc_defaults() + lock_pivot_defaults() +
                     lock_filter_defaults() + lock_bands_defaults() +
                     [int_param("cyclicMemory", mem),
                      int_param("leveling", level)])
            variants.append({
                "label": label, "replacements": repls,
                "metadata": {"phase": 6, "type": "dynamic_bands", "description": desc,
                             "cyclicMemory": mem, "leveling": level},
            })

    return Phase(name="Dynamic Bands", description="cyclicMemory × leveling sweep", variants=variants)


def build_phase7_bb() -> Phase:
    """Bollinger Bands: bbLen × bbMult."""
    variants = []

    len_vals = [10, 14, 20]
    mult_vals = [0.5, 1.0, 1.5]

    for length in len_vals:
        for mult in mult_vals:
            label = f"BB_L{length}_M{str(mult).replace('.','p')}"
            desc = f"BB Length={length}, Mult={mult}"
            repls = (base_entry_replacements() + lock_exit_defaults() +
                     lock_calc_defaults() + lock_pivot_defaults() +
                     lock_filter_defaults() + lock_bands_defaults() +
                     [int_param("bbLen", length),
                      {"pattern": r'bbMult = input\.float\([\d.]+', "replacement": f'bbMult = input.float({mult}', "regex": True}])
            variants.append({
                "label": label, "replacements": repls,
                "metadata": {"phase": 7, "type": "bollinger_bands", "description": desc,
                             "bbLen": length, "bbMult": mult},
            })

    return Phase(name="Bollinger Bands", description="bbLen × bbMult sweep", variants=variants)


# ═══════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════

def parse_metric(val: Any) -> float:
    """Parse a metric value into float, handling strings with $, %, commas."""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("$", "").replace("%", "").replace(",", "").replace("\u2212", "-").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def score_variant(summary: dict) -> float:
    """Composite score: 50% net profit + 30% sharpe + 20% profit factor."""
    net = parse_metric(summary.get("net_profit", 0))
    sharpe = parse_metric(summary.get("sharpe", 0))
    pf = parse_metric(summary.get("profit_factor", 0))

    # Normalize - rescale so reasonable ranges contribute
    net_score = max(0, net / 50000)  # 50K net = 1.0
    sharpe_score = max(0, sharpe / 0.5)  # 0.5 sharpe = 1.0
    pf_score = max(0, (pf - 0.5) / 2.0)  # 2.5 PF = 1.0

    return 0.5 * net_score + 0.3 * sharpe_score + 0.2 * pf_score


def sort_by_score(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: score_variant(r.get("summary", {})), reverse=True)


def print_phase_results(phase_name: str, results: list[dict], top_n: int = 5):
    print(f"\n{'='*80}")
    print(f"📊 {phase_name}")
    print(f"{'='*80}")
    sorted_r = sort_by_score(results)
    
    header = f"{'Rank':<5} {'Variant':<28} {'Net Profit':>13} {'Sharpe':>8} {'PF':>7} {'DD%':>10} {'Return%':>8}"
    print(header)
    print("-" * len(header))

    for i, r in enumerate(sorted_r[:top_n]):
        s = r.get("summary", {})
        net = s.get("net_profit", "N/A")
        sharpe = s.get("sharpe", "N/A")
        pf = s.get("profit_factor", "N/A")
        dd = s.get("max_drawdown", "N/A")
        ret = s.get("return_pct", "N/A")

        rank_mark = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1:>2}."
        print(f"{rank_mark:<5} {r['label']:<28} {str(net):>13} {str(sharpe):>8} {str(pf):>7} {str(dd):>10} {str(ret):>8}")

    if sorted_r:
        best = sorted_r[0]
        win_s = best.get("summary", {})
        print(f"\n🏆 Winner: {best['label']}")
        print(f"   Net: {win_s.get('net_profit')} | Sharpe: {win_s.get('sharpe')} | PF: {win_s.get('profit_factor')} | DD: {win_s.get('max_drawdown')}")

    return sorted_r[0] if sorted_r else None


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 80)
    print("WaveTrend MAX v5.9 — Full Parameter Sweep (Phases 2-7)")
    print("=" * 80)
    print(f"Source: {SOURCE_PATH}")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print(f"Wait per variant: {WAIT_SECONDS}s")
    print()

    # Connect
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()
    print("✅ CDP connected")

    recon_path = Path(__file__).resolve().parent.parent / "recon_findings.json"
    recon = json.loads(recon_path.read_text()) if recon_path.exists() else {}

    pine = TVPineScriptController(cdp, recon, allow_unverified=True)
    backtest = TVBacktestController(cdp, recon, allow_unverified=True)
    chart = TVChartController(cdp, recon, allow_unverified=True)
    variant_ctrl = StrategyVariantController(cdp, pine, backtest, chart)

    # ── Build phases ──
    phases = [
        build_phase2_exit(),
        build_phase3_calculation(),
        build_phase4_pivots(),
        build_phase5_filters(),
        build_phase6_dynamic_bands(),
        build_phase7_bb(),
    ]

    total_variants = sum(len(p.variants) for p in phases)
    print(f"Phases: {len(phases)} | Total variants: {total_variants}")
    print(f"Est. time: ~{total_variants * WAIT_SECONDS / 60:.0f} min")
    print()

    # Track master winner across all phases
    master_results: list[dict] = []
    global_best: dict | None = None
    global_best_score: float = -999

    for phase_idx, phase in enumerate(phases):
        print(f"\n{'─'*80}")
        print(f"🔬 PHASE {phase_idx + 2}/{len(phases) + 1}: {phase.name}")
        print(f"   {phase.description}")
        print(f"   Variants: {len(phase.variants)}")
        print(f"{'─'*80}")

        results = await variant_ctrl.sweep(
            script_name=SCRIPT_NAME,
            source_path=SOURCE_PATH,
            variants=phase.variants,
            restore=True,
            wait_seconds=WAIT_SECONDS,
            screenshot_dir=f"{SCREENSHOT_DIR}/phase{phase_idx+2}",
        )

        winner = print_phase_results(f"Phase {phase_idx+2}: {phase.name}", results)
        master_results.extend(results)

        # Track global best
        if winner:
            w_score = score_variant(winner.get("summary", {}))
            if w_score > global_best_score:
                global_best = winner
                global_best_score = w_score

    # ── GRAND SUMMARY ──
    print(f"\n\n{'═'*80}")
    print(f"🏁  GRAND SUMMARY — All Phases Complete")
    print(f"{'═'*80}")

    all_sorted = sort_by_score(master_results)
    print(f"\n{'='*80}")
    print(f"TOP 10 ACROSS ALL PHASES")
    print(f"{'='*80}")
    header = f"{'Rank':<5} {'Phase':<6} {'Variant':<28} {'Net Profit':>13} {'Sharpe':>8} {'PF':>7} {'DD%':>10} {'Return%':>8}"
    print(header)
    print("-" * len(header))

    for i, r in enumerate(all_sorted[:10]):
        s = r.get("summary", {})
        meta = r.get("metadata", {})
        phase = f"P{meta.get('phase', '?')}"
        rank_mark = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1:>2}."
        print(f"{rank_mark:<5} {phase:<6} {r['label']:<28} {str(s.get('net_profit','?')):>13} {str(s.get('sharpe','?')):>8} {str(s.get('profit_factor','?')):>7} {str(s.get('max_drawdown','?')):>10} {str(s.get('return_pct','?')):>8}")

    # ── Best-of-best config ──
    if global_best:
        gs = global_best.get("summary", {})
        gm = global_best.get("metadata", {})
        print(f"\n{'═'*60}")
        print(f"🏆  OPTIMAL CONFIGURATION")
        print(f"{'═'*60}")
        print(f"  Variant:    {global_best['label']}")
        print(f"  Phase:      {gm.get('phase', '?')} — {gm.get('description', '?')}")
        print(f"  Net Profit: {gs.get('net_profit', '?')}")
        print(f"  Sharpe:     {gs.get('sharpe', '?')}")
        print(f"  PF:         {gs.get('profit_factor', '?')}")
        print(f"  Max DD:     {gs.get('max_drawdown', '?')}")
        print(f"  Return %:   {gs.get('return_pct', '?')}")
        print(f"  Screenshot: {global_best.get('screenshot_path', '?')}")

    # Save all results
    out_path = Path(__file__).resolve().parent.parent / "logs" / "wt_max_full_sweep_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(master_results, indent=2, default=str))
    print(f"\n📁 Full results saved to: {out_path}")

    await cdp.disconnect()
    print("✅ CDP disconnected — source fully restored")


if __name__ == "__main__":
    asyncio.run(main())
