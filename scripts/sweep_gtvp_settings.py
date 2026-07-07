"""GT_VP v9.9.6 — Settings-Based Sweep (no source replacement).

Uses tv_settings_write + tv_run_backtest. Much faster than source replacement
since GT_VP has 11 cloud library imports that are slow to compile.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection
from core.services.settings_controller import TVSettingsController
from core.services.backtest_controller import TVBacktestController
from core.services.chart_controller import TVChartController

SCRIPT_NAME = "GT_VP_v9.9.6_STRAT"
WAIT_SECONDS = 8.0

# ── Helpers ──
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
        return 0.4*max(0,net/50000) + 0.35*max(0,sharpe/0.5) + 0.25*max(0,(pf-0.5)/2.0)
    return sorted(results, key=score, reverse=True)

def print_phase(name: str, results: list[dict], top_n: int = 5):
    print(f"\n{'='*80}")
    print(f"📊 {name}")
    print(f"{'='*80}")
    sr = sort_by_score(results)
    hdr = f"{'Rank':<5} {'Label':<35} {'Net Profit':>13} {'Sharpe':>8} {'PF':>7} {'DD':>12} {'Return%':>8}"
    print(hdr); print("-"*len(hdr))
    for i, r in enumerate(sr[:top_n]):
        s = r.get("summary", {}); m = r.get("metadata", {})
        mark = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else f"{i+1:>2}."
        print(f"{mark:<5} {r['label']:<35} {str(s.get('net_profit','?')):>13} {str(s.get('sharpe','?')):>8} {str(s.get('profit_factor','?')):>7} {str(s.get('max_drawdown','?')):>12} {str(s.get('return_pct','?')):>8}")
    if sr:
        best = sr[0]; ws = best.get("summary",{})
        print(f"\n🏆 {best['label']} | Net: {ws.get('net_profit')} | Sharpe: {ws.get('sharpe')} | PF: {ws.get('profit_factor')} | DD: {ws.get('max_drawdown')}")
    return sr[0] if sr else None

async def run_variant(settings: TVSettingsController, backtest: TVBacktestController,
                      chart: TVChartController, values: dict, label: str, metadata: dict) -> dict:
    """Write settings, run backtest, return summary."""
    await settings.write(SCRIPT_NAME, values)
    await asyncio.sleep(2.0)
    await backtest.run_strategy(SCRIPT_NAME)
    await asyncio.sleep(WAIT_SECONDS)
    summary = await backtest.get_performance_summary()
    return {"label": label, "summary": summary, "metadata": metadata}

# ═══════════════════════════════════════════════════════════════
# PHASE BUILDERS
# ═══════════════════════════════════════════════════════════════

BASE_SETTINGS = {
    "Trade Signal Mode": "All Signals",
    "Entry Strictness": "Normal",
    "MA Filter Mode": "Off",
    "Fallback R:R Target": "1.5",
    "ATR Stop Multiplier": "1",
    "Level Buffer ATR": "0.1",
    "Timeout Bars": "30",
    "Value Area %": "70",
}

async def phase1(settings, backtest, chart) -> list[dict]:
    modes = ["All Signals", "Conservative", "Aggressive", "Structure Only"]
    results = []
    for mode in modes:
        vals = {**BASE_SETTINGS, "Trade Signal Mode": mode}
        r = await run_variant(settings, backtest, chart, vals, f"P1_{mode.replace(' ','_')}", {"phase":1,"mode":mode})
        results.append(r)
    return results

async def phase2(settings, backtest, chart) -> list[dict]:
    filters = ["Off", "Filter Only", "Filter + Direction"]
    results = []
    for f in filters:
        vals = {**BASE_SETTINGS, "MA Filter Mode": f}
        r = await run_variant(settings, backtest, chart, vals, f"P2_{f.replace(' ','_').replace('+','p')}", {"phase":2,"ma_filter":f})
        results.append(r)
    return results

async def phase3(settings, backtest, chart) -> list[dict]:
    levels = ["Loose", "Normal", "Strict"]
    results = []
    for lvl in levels:
        vals = {**BASE_SETTINGS, "Entry Strictness": lvl}
        r = await run_variant(settings, backtest, chart, vals, f"P3_{lvl}", {"phase":3,"strictness":lvl})
        results.append(r)
    return results

async def phase4(settings, backtest, chart) -> list[dict]:
    rr_vals = [1.0, 1.5, 2.0, 2.5]
    atr_vals = [0.5, 1.0, 1.5, 2.0]
    results = []
    for rr in rr_vals:
        for atr in atr_vals:
            vals = {**BASE_SETTINGS, "Fallback R:R Target": str(rr), "ATR Stop Multiplier": str(atr)}
            r = await run_variant(settings, backtest, chart, vals, f"P4_RR{rr}_ATR{atr}", {"phase":4,"rr":rr,"atr_stop":atr})
            results.append(r)
    return results

async def phase5(settings, backtest, chart) -> list[dict]:
    va_vals = [60, 70, 80]
    results = []
    for va in va_vals:
        vals = {**BASE_SETTINGS, "Value Area %": str(va)}
        r = await run_variant(settings, backtest, chart, vals, f"P5_VA{va}", {"phase":5,"va_pct":va})
        results.append(r)
    return results

async def phase6(settings, backtest, chart) -> list[dict]:
    timeouts = [15, 30, 60]
    results = []
    for t in timeouts:
        vals = {**BASE_SETTINGS, "Timeout Bars": str(t)}
        r = await run_variant(settings, backtest, chart, vals, f"P6_T{t}", {"phase":6,"timeout":t})
        results.append(r)
    return results

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    print("="*80)
    print("GT_VP v9.9.6 — Settings-Based Parameter Sweep")
    print("="*80)
    print(f"Wait per variant: {WAIT_SECONDS}s")
    print()

    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()
    print("✅ CDP connected")

    recon_path = Path(__file__).resolve().parent.parent / "recon_findings.json"
    recon = json.loads(recon_path.read_text()) if recon_path.exists() else {}
    settings = TVSettingsController(cdp, recon, allow_unverified=True)
    backtest = TVBacktestController(cdp, recon, allow_unverified=True)
    chart = TVChartController(cdp, recon, allow_unverified=True)

    phases = [
        ("Phase 1: Strategy Mode", phase1),
        ("Phase 2: MA Filter Mode", phase2),
        ("Phase 3: Entry Strictness", phase3),
        ("Phase 4: Exit Grid (RR × ATR Stop)", phase4),
        ("Phase 5: VA Percentage", phase5),
        ("Phase 6: Timeout Bars", phase6),
    ]

    all_results = []
    for name, phase_fn in phases:
        print(f"\n{'─'*80}")
        print(f"🔬 {name}")
        print(f"{'─'*80}")
        results = await phase_fn(settings, backtest, chart)
        print_phase(name, results)
        all_results.extend(results)

    # Grand summary
    print(f"\n\n{'═'*80}")
    print(f"🏁  TOP 10 — ALL PHASES")
    print(f"{'═'*80}")
    top10 = sort_by_score(all_results)[:10]
    hdr = f"{'Rank':<5} {'Label':<35} {'Net Profit':>13} {'Sharpe':>8} {'PF':>7} {'DD':>12} {'Return%':>8}"
    print(hdr); print("-"*len(hdr))
    for i, r in enumerate(top10):
        s = r.get("summary",{}); m = r.get("metadata",{})
        mark = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else f"{i+1:>2}."
        print(f"{mark:<5} {r['label']:<35} {str(s.get('net_profit','?')):>13} {str(s.get('sharpe','?')):>8} {str(s.get('profit_factor','?')):>7} {str(s.get('max_drawdown','?')):>12} {str(s.get('return_pct','?')):>8}")

    out = Path(__file__).resolve().parent.parent / "logs" / "gtvp_settings_sweep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n📁 {out}")

    # Restore defaults
    await settings.write(SCRIPT_NAME, BASE_SETTINGS)
    await cdp.disconnect()
    print("✅ Done — defaults restored")

if __name__ == "__main__":
    asyncio.run(main())
