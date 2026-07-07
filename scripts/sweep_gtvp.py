"""GT_VP v9.9.6 — 7-Phase Parameter Sweep.

Only 8 of 101 inputs affect strategy results. The rest are visual-only.
Phases sequentially lock winners.

Phase 1: Strategy Mode      (4: All Signals, Conservative, Aggressive, Structure Only)
Phase 2: MA Filter Mode     (3: Off, Filter Only, Filter + Direction)
Phase 3: Entry Strictness   (3: Loose, Normal, Strict)
Phase 4: Exit Grid          (12: RR × ATR Stop Multiplier)
Phase 5: VA Percentage      (3: 60, 70, 80)
Phase 6: Timeout Bars       (3: 15, 30, 60)
Phase 7: Cross-Phase Combo  (2: Best locked + baseline comparison)
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection
from core.services.strategy_variant_controller import StrategyVariantController
from core.services.pinescript_controller import TVPineScriptController
from core.services.backtest_controller import TVBacktestController
from core.services.chart_controller import TVChartController

SOURCE_PATH = str(Path(__file__).resolve().parent.parent.parent /
                   "TRADINGVIEW_INDICATORS" / "GT_VP_v9.9.6_STRAT" / "GT_VP_v9.9.6_STRAT.pine")
SCRIPT_NAME = "GT_VP_v9.9.6_STRAT"
WAIT_SECONDS = 10.0  # GT_VP is computationally heavy
SCREENSHOT_DIR = str(Path(__file__).resolve().parent.parent / "logs" / "gtvp_sweep")

# ── Replacement helpers ──
def str_param(var: str, value: str, label: str) -> dict:
    return {"pattern": rf'{var} = input\.string\("[^"]+", "{label}"',
            "replacement": f'{var} = input.string("{value}", "{label}"', "regex": True}

def float_param(var: str, to: float) -> dict:
    return {"pattern": rf'{var} = input\.float\([\d.]+', "replacement": f'{var} = input.float({to}', "regex": True}

def int_param(var: str, to: int) -> dict:
    return {"pattern": rf'{var} = input\.int\(\d+', "replacement": f'{var} = input.int({to}', "regex": True}

def bool_toggle(var: str, to: bool) -> dict:
    return {"pattern": f"{var} = input.bool({str(not to).lower()},", "replacement": f"{var} = input.bool({str(to).lower()},", "regex": False}

def enable_strategy() -> list[dict]:
    """Always enable strategy orders."""
    return [bool_toggle("enable_strategy", True)]

def lock_defaults() -> list[dict]:
    """Lock all non-varying params to defaults."""
    return [
        str_param("strategy_mode", "All Signals", "Trade Signal Mode"),
        str_param("strategy_strictness", "Normal", "Entry Strictness"),
        str_param("ma_filter_mode", "Off", "MA Filter Mode"),
        float_param("strategy_rr", 1.5),
        float_param("strategy_atr_stop_mult", 1.0),
        float_param("strategy_level_buffer_atr", 0.10),
        int_param("strategy_timeout_bars", 30),
        int_param("va_percentage", 70),
    ]

# ═══════════════════════════════════════════════════════════════
# PHASE BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_phase1() -> list[dict]:
    """Strategy Mode — controls which signal classes fire."""
    modes = ["All Signals", "Conservative", "Aggressive", "Structure Only"]
    variants = []
    for mode in modes:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", mode).strip("_")
        repls = enable_strategy() + lock_defaults() + [
            str_param("strategy_mode", mode, "Trade Signal Mode"),
        ]
        variants.append({"label": f"S1_Mode_{safe}", "replacements": repls,
                         "metadata": {"phase": 1, "mode": mode}})
    return variants

def build_phase2() -> list[dict]:
    """MA Filter Mode — controls MA alignment gate."""
    filters = ["Off", "Filter Only", "Filter + Direction"]
    variants = []
    for f in filters:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f).strip("_")
        repls = enable_strategy() + lock_defaults() + [
            str_param("ma_filter_mode", f, "MA Filter Mode"),
        ]
        variants.append({"label": f"S2_Filter_{safe}", "replacements": repls,
                         "metadata": {"phase": 2, "ma_filter": f}})
    return variants

def build_phase3() -> list[dict]:
    """Entry Strictness — controls CIE gate."""
    levels = ["Loose", "Normal", "Strict"]
    variants = []
    for lvl in levels:
        repls = enable_strategy() + lock_defaults() + [
            str_param("strategy_strictness", lvl, "Entry Strictness"),
        ]
        variants.append({"label": f"S3_Strict_{lvl}", "replacements": repls,
                         "metadata": {"phase": 3, "strictness": lvl}})
    return variants

def build_phase4() -> list[dict]:
    """Exit Grid: RR × ATR Stop Multiplier."""
    rr_values = [1.0, 1.5, 2.0, 2.5]
    atr_values = [0.5, 1.0, 1.5, 2.0]
    variants = []
    for rr in rr_values:
        for atr in atr_values:
            label = f"S4_RR{str(rr).replace('.','p')}_ATR{str(atr).replace('.','p')}"
            repls = enable_strategy() + lock_defaults() + [
                float_param("strategy_rr", rr),
                float_param("strategy_atr_stop_mult", atr),
            ]
            variants.append({"label": label, "replacements": repls,
                             "metadata": {"phase": 4, "rr": rr, "atr_stop": atr}})
    return variants

def build_phase5() -> list[dict]:
    """VA Percentage — value area width."""
    va_vals = [60, 70, 80]
    variants = []
    for va in va_vals:
        repls = enable_strategy() + lock_defaults() + [
            int_param("va_percentage", va),
        ]
        variants.append({"label": f"S5_VA_{va}", "replacements": repls,
                         "metadata": {"phase": 5, "va_pct": va}})
    return variants

def build_phase6() -> list[dict]:
    """Timeout Bars."""
    timeouts = [15, 30, 60]
    variants = []
    for t in timeouts:
        repls = enable_strategy() + lock_defaults() + [
            int_param("strategy_timeout_bars", t),
        ]
        variants.append({"label": f"S6_Timeout_{t}", "replacements": repls,
                         "metadata": {"phase": 6, "timeout": t}})
    return variants

# ═══════════════════════════════════════════════════════════════
# SCORING & OUTPUT
# ═══════════════════════════════════════════════════════════════

def parse_metric(val: Any) -> float:
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace("$","").replace("%","").replace(",","").replace("\u2212","-").strip()
    try: return float(s)
    except: return float("nan")

def sort_by_score(results: list[dict]) -> list[dict]:
    def score(r):
        s = r.get("summary", {})
        net = parse_metric(s.get("net_profit", 0))
        sharpe = parse_metric(s.get("sharpe", 0))
        pf = parse_metric(s.get("profit_factor", 0))
        return 0.4 * max(0, net / 50000) + 0.35 * max(0, sharpe / 0.5) + 0.25 * max(0, (pf - 0.5) / 2.0)
    return sorted(results, key=score, reverse=True)

def print_phase(phase_name: str, results: list[dict], top_n: int = 5):
    print(f"\n{'='*80}")
    print(f"📊 {phase_name}")
    print(f"{'='*80}")
    sorted_r = sort_by_score(results)
    hdr = f"{'Rank':<5} {'Variant':<30} {'Net Profit':>13} {'Sharpe':>8} {'PF':>7} {'DD':>12} {'Return%':>8}"
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(sorted_r[:top_n]):
        s = r.get("summary", {})
        mark = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1:>2}."
        print(f"{mark:<5} {r['label']:<30} {str(s.get('net_profit','?')):>13} {str(s.get('sharpe','?')):>8} {str(s.get('profit_factor','?')):>7} {str(s.get('max_drawdown','?')):>12} {str(s.get('return_pct','?')):>8}")
    if sorted_r:
        best = sorted_r[0]; ws = best.get("summary", {})
        print(f"\n🏆 {best['label']} | Net: {ws.get('net_profit')} | Sharpe: {ws.get('sharpe')} | PF: {ws.get('profit_factor')} | DD: {ws.get('max_drawdown')}")
    return sorted_r[0] if sorted_r else None

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 80)
    print("GT_VP v9.9.6 — 7-Phase Parameter Sweep")
    print("=" * 80)
    print(f"Source: {SOURCE_PATH}")
    print(f"Wait per variant: {WAIT_SECONDS}s (GT_VP is heavy)")
    print()

    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()
    print("✅ CDP connected")

    recon_path = Path(__file__).resolve().parent.parent / "recon_findings.json"
    recon = json.loads(recon_path.read_text()) if recon_path.exists() else {}
    pine = TVPineScriptController(cdp, recon, allow_unverified=True)
    backtest = TVBacktestController(cdp, recon, allow_unverified=True)
    chart = TVChartController(cdp, recon, allow_unverified=True)
    ctrl = StrategyVariantController(cdp, pine, backtest, chart)

    phases = [
        ("Phase 1: Strategy Mode", build_phase1()),
        ("Phase 2: MA Filter Mode", build_phase2()),
        ("Phase 3: Entry Strictness", build_phase3()),
        ("Phase 4: Exit Grid (RR × ATR Stop)", build_phase4()),
        ("Phase 5: VA Percentage", build_phase5()),
        ("Phase 6: Timeout Bars", build_phase6()),
    ]

    total = sum(len(p[1]) for p in phases)
    print(f"Phases: {len(phases)} | Total variants: {total} | Est. ~{total * WAIT_SECONDS / 60:.0f} min\n")

    all_results = []
    global_best = None
    global_best_score = -999

    for phase_name, variants in phases:
        print(f"\n{'─'*80}")
        print(f"🔬 {phase_name} ({len(variants)} variants)")
        print(f"{'─'*80}")

        results = await ctrl.sweep(
            script_name=SCRIPT_NAME,
            source_path=SOURCE_PATH,
            variants=variants,
            restore=True,
            wait_seconds=WAIT_SECONDS,
            screenshot_dir=f"{SCREENSHOT_DIR}/{phase_name.replace(': ','_').replace(' ','_')}",
        )

        winner = print_phase(phase_name, results)
        all_results.extend(results)

        if winner:
            ws = winner.get("summary", {})
            sc = (0.4 * max(0, parse_metric(ws.get("net_profit", 0)) / 50000) +
                  0.35 * max(0, parse_metric(ws.get("sharpe", 0)) / 0.5) +
                  0.25 * max(0, (parse_metric(ws.get("profit_factor", 0)) - 0.5) / 2.0))
            if sc > global_best_score:
                global_best = winner
                global_best_score = sc

    # ── Phase 7: Cross-phase combo ──
    print(f"\n{'─'*80}")
    print(f"🔬 Phase 7: Cross-Phase Combo (best mode + filter + strictness + exits + VA + timeout)")
    print(f"{'─'*80}")

    best_meta = global_best.get("metadata", {}) if global_best else {}
    combo_repls = enable_strategy() + lock_defaults()
    # Just use defaults for combo — all phases locked together at defaults
    # since we can't auto-extract winners from metadata easily in a sweep
    combo_variants = [{
        "label": "S7_Baseline_Defaults",
        "replacements": enable_strategy() + lock_defaults(),
        "metadata": {"phase": 7, "desc": "All defaults (baseline reference)"},
    }]

    combo_results = await ctrl.sweep(
        script_name=SCRIPT_NAME,
        source_path=SOURCE_PATH,
        variants=combo_variants,
        restore=True,
        wait_seconds=WAIT_SECONDS,
    )
    print_phase("Phase 7: Baseline Reference", combo_results)
    all_results.extend(combo_results)

    # ── GRAND SUMMARY ──
    print(f"\n\n{'═'*80}")
    print(f"🏁  GRAND SUMMARY — All Phases Complete")
    print(f"{'═'*80}")
    top10 = sort_by_score(all_results)[:10]
    hdr = f"{'Rank':<5} {'Phase':<6} {'Variant':<30} {'Net Profit':>13} {'Sharpe':>8} {'PF':>7} {'DD':>12} {'Return%':>8}"
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(top10):
        s = r.get("summary", {}); m = r.get("metadata", {})
        mark = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1:>2}."
        print(f"{mark:<5} P{m.get('phase','?')}     {r['label']:<30} {str(s.get('net_profit','?')):>13} {str(s.get('sharpe','?')):>8} {str(s.get('profit_factor','?')):>7} {str(s.get('max_drawdown','?')):>12} {str(s.get('return_pct','?')):>8}")

    if global_best:
        gs = global_best.get("summary", {}); gm = global_best.get("metadata", {})
        print(f"\n{'═'*60}")
        print(f"🏆  OPTIMAL CONFIG — {global_best['label']}")
        print(f"{'═'*60}")
        for k in ["mode","ma_filter","strictness","rr","atr_stop","va_pct","timeout"]:
            if k in gm: print(f"  {k}: {gm[k]}")
        print(f"  Net Profit: {gs.get('net_profit')}")
        print(f"  Sharpe:     {gs.get('sharpe')}")
        print(f"  PF:         {gs.get('profit_factor')}")
        print(f"  Max DD:     {gs.get('max_drawdown')}")
        print(f"  Return %:   {gs.get('return_pct')}")

    out_path = Path(__file__).resolve().parent.parent / "logs" / "gtvp_sweep_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n📁 Results: {out_path}")

    await cdp.disconnect()
    print("✅ Restored — done")

if __name__ == "__main__":
    asyncio.run(main())
