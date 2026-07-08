#!/usr/bin/env python3
"""Aggressive Scalp Strategy Sweep — $100 → $1,000 in one week.

Tests WaveTrend MAX and GT_VP on 1m/5m/15m timeframes with ultra-aggressive
settings: all entry signals ON, no trend filter, tight stops, zero cooldown.

The goal is to find the config with the highest return rate while keeping
max drawdown ≤ 50%, suitable for compounding a small account aggressively.

Strategy:
  1. WaveTrend MAX — All entries ON, no filter, tight SL/TP
  2. GT_VP — All Signals, Loose strictness, Both directions
  3. Test on 1m, 5m, 15m (scalp territory)
  4. Backtest window: 5D (most recent price action for realistic scalp)
  5. Compound projection: if daily return > 0, compound over 5 trading days
"""

import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection
from core.services.strategy_variant_controller import StrategyVariantController
from core.services.pinescript_controller import TVPineScriptController
from core.services.backtest_controller import TVBacktestController
from core.services.chart_controller import TVChartController
from core.services.settings_controller import TVSettingsController
from core.services.dom_utils import DomUtils

# ── Paths ──
ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs" / "scalp_sweep"
WT_SOURCE = ROOT.parent / "TRADINGVIEW_INDICATORS" / "WAVETREND" / "WaveTrend_MAX.pine"
GTVP_SOURCE = ROOT.parent / "TRADINGVIEW_INDICATORS" / "GT_VP_v9.9.6_STRAT" / "GT_VP_v9.9.6_STRAT.pine"
RECON_PATH = ROOT / "recon_findings.json"

DEBUG_PORT = 8315
WAIT_SECONDS = 10.0  # generous wait for backtest on lower TFs

# ── Scalp timeframes ──
TIMEFRAMES = ["1m", "5m", "15m"]
TF_VALUES = {"1m": "1", "5m": "5", "15m": "15"}

# ── Account parameters ──
STARTING_CAPITAL = 100.0
TARGET_CAPITAL = 1000.0
MAX_DRAWDOWN_PCT = 50.0
TRADING_DAYS = 5  # one week


# ═══════════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════════

def to_num(value: Any, default: float = 0.0) -> float:
    """Parse a string/number to float, handling commas, $, %, unicode minus."""
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, "", "N/A", "n/a", "NA", "na"):
        return default
    text = str(value).replace(",", "").replace("$", "").replace("%", "")
    text = text.replace("\u2212", "-").replace("\u00a0", " ").strip()
    try:
        return float(text)
    except ValueError:
        return default


def parse_backtest_metrics(summary: dict) -> dict:
    """Extract and normalize backtest metrics into a flat dict."""
    raw = summary.get("summary", summary)
    if not raw:
        return {}
    
    return {
        "net_profit": to_num(raw.get("net_profit", raw.get("Net Profit", 0))),
        "sharpe": to_num(raw.get("sharpe", raw.get("Sharpe Ratio", 0))),
        "profit_factor": to_num(raw.get("profit_factor", raw.get("Profit Factor", 1))),
        "max_drawdown": to_num(raw.get("max_drawdown", raw.get("Max Drawdown", 0))),
        "return_pct": to_num(raw.get("return_pct", raw.get("Return", 0))),
        "total_trades": int(to_num(raw.get("total_trades", raw.get("Total Closed Trades", 0)))),
        "win_rate": to_num(raw.get("win_rate_pct", raw.get("Percent Profitable", 0))),
        "avg_pnl": to_num(raw.get("avg_pnl", raw.get("Avg Trade", 0))),
    }


def compound_projection(daily_return_pct: float, days: int, start: float) -> float:
    """Project compounded balance over N days at given daily return %."""
    return start * ((1 + daily_return_pct / 100) ** days)


def score_config(metrics: dict) -> dict:
    """Score a config for aggressive scalp suitability.
    
    Returns a dict with scores and a compound projection.
    Higher score = better for aggressive compounding.
    """
    pf = metrics.get("profit_factor", 1.0)
    return_pct = metrics.get("return_pct", 0)
    dd_pct = abs(metrics.get("max_drawdown", 100))
    trades = metrics.get("total_trades", 0)
    win_rate = metrics.get("win_rate", 0)
    
    # Penalize if DD exceeds 50%
    if dd_pct > MAX_DRAWDOWN_PCT:
        return {"score": 0, "reason": f"DD {dd_pct:.1f}% > {MAX_DRAWDOWN_PCT}% limit", "compound_end": 0}
    
    if trades < 5:
        return {"score": 0, "reason": f"Only {trades} trades — not enough data", "compound_end": 0}
    
    if pf < 0.8:
        return {"score": 0, "reason": f"PF {pf:.2f} too low", "compound_end": 0}
    
    # Daily return from backtest window (5D window → daily = return / 5 roughly)
    # But we'll use the per-trade edge for projection
    daily_edge = return_pct / TRADING_DAYS if return_pct > 0 else return_pct
    
    # Compound projection
    compound_end = compound_projection(return_pct / TRADING_DAYS, TRADING_DAYS, STARTING_CAPITAL) if return_pct > 0 else STARTING_CAPITAL
    
    # Score formula: PF * sqrt(trades) * return / DD
    # This favors: high PF, high trade count (frequency), high return, low DD
    raw_score = pf * (trades ** 0.5) * max(return_pct, 0.01) / max(dd_pct, 1)
    
    return {
        "score": round(raw_score, 2),
        "daily_edge_pct": round(daily_edge, 2),
        "compound_end": round(compound_end, 2),
        "hits_target": compound_end >= TARGET_CAPITAL,
        "reason": "",
    }


async def set_timeframe_via_click(cdp: CDPConnection, tf: str) -> bool:
    """Click the timeframe button. Works with 1m/5m/15m."""
    data_value = TF_VALUES.get(tf, "5")
    # Try direct click on the radio button
    js = f"""(function() {{
        var buttons = document.querySelectorAll('button[role="radio"]');
        for (var i=0; i<buttons.length; i++) {{
            if (buttons[i].getAttribute('data-value') === '{data_value}') {{
                buttons[i].click();
                return 'clicked ' + '{data_value}';
            }}
        }}
        return 'not_found';
    }})()"""
    result = await cdp.execute_js(js)
    val = str(result.get("result", {}).get("value", ""))
    return "clicked" in val


async def load_source_into_editor(
    cdp: CDPConnection, source: str, script_name: str
) -> bool:
    """Paste source into Pine editor and click Add/Update to chart.
    
    Returns True if source was loaded and applied successfully.
    """
    import subprocess
    
    # Copy to clipboard
    try:
        subprocess.run(["pbcopy"], input=source, text=True, check=True)
    except Exception:
        return False
    
    # Bring TV to front
    await cdp._send_command("Page.bringToFront", {})
    subprocess.run(["open", "-a", "TradingView"], check=False)
    await asyncio.sleep(0.8)
    
    # Focus Monaco textarea
    await cdp.execute_js("""
        (function() {
            var all = document.querySelectorAll('.monaco-editor textarea.inputarea');
            for (var i = 0; i < all.length; i++) {
                if (all[i].offsetWidth > 0) {
                    all[i].focus();
                    all[i].select();
                    return 'focused';
                }
            }
            return 'no-textarea';
        })()
    """)
    
    # Try CGEvent paste first (macOS accessibility), then CDP fallback
    dom = DomUtils(cdp)
    pasted = await dom._paste_via_cgevent()
    if not pasted:
        await dom._paste_via_cdp()
    
    await asyncio.sleep(0.5)
    
    # Click Add to chart / Update on chart
    update_js = """
        (function() {
            var btn = document.querySelector('button[title="Update on chart"]')
                || document.querySelector('button[title="Add to chart"]')
                || document.querySelector('button[title="Save script"]');
            if (btn) {
                btn.click();
                return { success: true, title: btn.getAttribute('title') };
            }
            return { success: false };
        })()
    """
    for _ in range(30):
        result = await cdp.execute_js(update_js)
        last = result.get("result", {}).get("value") or {"success": False}
        if last.get("success"):
            return True
        await asyncio.sleep(0.3)
    
    return False


async def set_date_preset(cdp: CDPConnection, preset: str = "5D") -> bool:
    """Click a date range preset button."""
    js = f"""(function() {{
        var buttons = document.querySelectorAll('[data-name*="date-range-tab"]');
        for (var i=0; i<buttons.length; i++) {{
            if ((buttons[i].getAttribute('data-name')||'').indexOf('{preset}') >= 0) {{
                buttons[i].click();
                return true;
            }}
        }}
        return false;
    }})()"""
    result = await cdp.execute_js(js)
    return bool(result.get("result", {}).get("value"))


# ═══════════════════════════════════════════════════════════════
# WaveTrend MAX — aggressive scalp variants
# ═══════════════════════════════════════════════════════════════

WT_ENTRY_NAMES = [
    "useDynamicCross", "useSignalCross", "useFib50Cross",
    "useZeroLineCross", "useBBReversion", "useDivergence",
    "useHiddenDivergence", "useBreakoutDyanmicCross",
    "useBBCross", "useFixedCross",
]

# Aggressive variants for scalping
WT_AGGRESSIVE_VARIANTS = [
    {
        "label": "WT_AllOn_NoFilter_TightSL",
        "description": "All 10 entries ON, no trend filter, SL=500 TP=1500, zero cooldown",
        "enabled": WT_ENTRY_NAMES,  # ALL ON
        "trend": "None",
        "stopLossPoints": 500,
        "takeProfitPoints": 1500,
        "trailPointsInput": 500,
        "trailOffsetInput": 200,
        "cooldownBars": 0,
    },
    {
        "label": "WT_AllOn_NoFilter_UltraTight",
        "description": "All entries ON, no filter, SL=300 TP=900, trail=300",
        "enabled": WT_ENTRY_NAMES,
        "trend": "None",
        "stopLossPoints": 300,
        "takeProfitPoints": 900,
        "trailPointsInput": 300,
        "trailOffsetInput": 100,
        "cooldownBars": 0,
    },
    {
        "label": "WT_AllOn_NoFilter_Moderate",
        "description": "All entries ON, no filter, SL=800 TP=2400, trail=800",
        "enabled": WT_ENTRY_NAMES,
        "trend": "None",
        "stopLossPoints": 800,
        "takeProfitPoints": 2400,
        "trailPointsInput": 800,
        "trailOffsetInput": 300,
        "cooldownBars": 0,
    },
    {
        "label": "WT_DivOnly_NoFilter_TightSL",
        "description": "Divergence only (best PF from daily), SL=300 TP=1200",
        "enabled": ["useDivergence", "useHiddenDivergence"],
        "trend": "None",
        "stopLossPoints": 300,
        "takeProfitPoints": 1200,
        "trailPointsInput": 300,
        "trailOffsetInput": 100,
        "cooldownBars": 0,
    },
    {
        "label": "WT_CrossOnly_NoFilter_TightSL",
        "description": "Cross entries only (dynamic+signal+fib50+zero), SL=400 TP=1200",
        "enabled": ["useDynamicCross", "useSignalCross", "useFib50Cross", "useZeroLineCross"],
        "trend": "None",
        "stopLossPoints": 400,
        "takeProfitPoints": 1200,
        "trailPointsInput": 400,
        "trailOffsetInput": 150,
        "cooldownBars": 0,
    },
    {
        "label": "WT_AllOn_WTSignal_TightSL",
        "description": "All entries ON, WT Signal Trend filter, SL=500 TP=1500",
        "enabled": WT_ENTRY_NAMES,
        "trend": "WT Signal Trend",
        "stopLossPoints": 500,
        "takeProfitPoints": 1500,
        "trailPointsInput": 500,
        "trailOffsetInput": 200,
        "cooldownBars": 0,
    },
    {
        "label": "WT_DivCross_NoFilter_Scalp",
        "description": "Divergence + Dynamic/Signal cross, no filter, SL=200 TP=600 (pure scalp)",
        "enabled": ["useDivergence", "useHiddenDivergence", "useDynamicCross", "useSignalCross"],
        "trend": "None",
        "stopLossPoints": 200,
        "takeProfitPoints": 600,
        "trailPointsInput": 200,
        "trailOffsetInput": 80,
        "cooldownBars": 0,
    },
    {
        "label": "WT_BBandMeanRev_Scalp",
        "description": "BB Reversion + Dynamic cross only, SL=250 TP=750",
        "enabled": ["useBBReversion", "useDynamicCross"],
        "trend": "None",
        "stopLossPoints": 250,
        "takeProfitPoints": 750,
        "trailPointsInput": 250,
        "trailOffsetInput": 100,
        "cooldownBars": 0,
    },
]


def build_wt_replacements(variant: dict) -> list[dict]:
    """Build source replacements for a WaveTrend MAX variant."""
    enabled = set(variant["enabled"])
    repls = []

    # 1. Entry booleans
    for name in WT_ENTRY_NAMES:
        current_val = "true" if name in enabled else "false"
        repls.append({
            "pattern": f"{name} = input.bool({str(not (name in enabled)).lower()},",
            "replacement": f"{name} = input.bool({str(name in enabled).lower()},",
            "regex": False,
        })

    # 2. Trend filter
    repls.append({
        "pattern": r'trendFilterOption = input\.string\("[^"]+", "Trend Filter"',
        "replacement": f'trendFilterOption = input.string("{variant["trend"]}", "Trend Filter"',
        "regex": True,
    })

    # 3. Exit parameters
    exit_params = {
        "stopLossPoints": variant["stopLossPoints"],
        "takeProfitPoints": variant["takeProfitPoints"],
        "trailPointsInput": variant["trailPointsInput"],
        "trailOffsetInput": variant["trailOffsetInput"],
        "cooldownBars": variant["cooldownBars"],
    }
    for param, value in exit_params.items():
        repls.append({
            "pattern": rf'{param} = input\.int\(\d+,',
            "replacement": f'{param} = input.int({value},',
            "regex": True,
        })

    return repls


# ═══════════════════════════════════════════════════════════════
# GT_VP — aggressive settings-based variants
# ═══════════════════════════════════════════════════════════════

GTVP_AGGRESSIVE_VARIANTS = [
    {
        "label": "GTVP_AllSignals_Loose_Both",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.5,
            "ATR Stop Multiplier": 0.5,
            "Level Buffer ATR": 0.05,
            "Timeout Bars": 15,
        },
    },
    {
        "label": "GTVP_AllSignals_Loose_LongOnly",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Long Only",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 2.0,
            "ATR Stop Multiplier": 0.5,
            "Level Buffer ATR": 0.05,
            "Timeout Bars": 10,
        },
    },
    {
        "label": "GTVP_AllSignals_Loose_ShortOnly",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Short Only",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 2.0,
            "ATR Stop Multiplier": 0.5,
            "Level Buffer ATR": 0.05,
            "Timeout Bars": 10,
        },
    },
    {
        "label": "GTVP_AllSignals_Aggressive_Both",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.2,
            "ATR Stop Multiplier": 0.3,
            "Level Buffer ATR": 0.02,
            "Timeout Bars": 5,
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# Main sweep orchestration
# ═══════════════════════════════════════════════════════════════

async def run_wt_sweep(
    cdp: CDPConnection,
    variant_ctrl: StrategyVariantController,
    backtest: TVBacktestController,
    chart: TVChartController,
    tf: str,
) -> list[dict]:
    """Run WaveTrend MAX aggressive sweep on a given timeframe."""
    print(f"\n{'='*70}")
    print(f"  WaveTrend MAX — Timeframe: {tf}")
    print(f"{'='*70}")
    
    # Set timeframe
    print(f"  Setting timeframe to {tf}...")
    try:
        await chart.set_timeframe(tf)
    except Exception as e:
        print(f"  ⚠️ set_timeframe failed: {e}, trying click-based fallback...")
        ok = await set_timeframe_via_click(cdp, tf)
        print(f"  Click-based: {'OK' if ok else 'FAILED'}")
    await asyncio.sleep(1.5)
    
    # Set 5D backtest window
    await set_date_preset(cdp, "5D")
    await asyncio.sleep(1.0)
    
    # CRITICAL: Pre-load the base source into the Pine editor
    print(f"  Loading WaveTrend MAX source into editor...")
    base_source = WT_SOURCE.read_text()
    loaded = await load_source_into_editor(cdp, base_source, "WaveTrend MAX")
    if not loaded:
        print(f"  ❌ Failed to load source — skipping {tf}")
        return []
    print(f"  ✅ Source loaded, waiting for chart update...")
    await asyncio.sleep(3.0)
    
    # Build sweep variants
    sweep_variants = []
    for v in WT_AGGRESSIVE_VARIANTS:
        sweep_variants.append({
            "label": f"{v['label']}_{tf}",
            "replacements": build_wt_replacements(v),
            "metadata": {"description": v["description"], "timeframe": tf},
            "wait_seconds": WAIT_SECONDS,
        })
    
    print(f"  Running {len(sweep_variants)} variants...")
    
    try:
        results = await variant_ctrl.sweep(
            script_name="WaveTrend MAX",
            source_path=str(WT_SOURCE),
            variants=sweep_variants,
            restore=True,
            wait_seconds=WAIT_SECONDS,
            screenshot_dir=str(LOG_DIR),
        )
    except Exception as exc:
        print(f"  ❌ Sweep crashed: {exc}")
        return []
    
    # Parse and score
    parsed = []
    for r in results:
        metrics = parse_backtest_metrics(r.get("summary", {}))
        scoring = score_config(metrics)
        parsed.append({
            "label": r["label"],
            "tf": tf,
            "description": r.get("metadata", {}).get("description", ""),
            "metrics": metrics,
            "scoring": scoring,
            "paste_ok": r.get("paste_ok", False),
            "source_match": r.get("source_match", False),
            "update_ok": r.get("update", {}).get("success", False),
        })
    
    return parsed


async def run_gtvp_sweep(
    cdp: CDPConnection,
    settings: TVSettingsController,
    backtest: TVBacktestController,
    chart: TVChartController,
    tf: str,
) -> list[dict]:
    """Run GT_VP aggressive settings sweep on a given timeframe."""
    print(f"\n{'='*70}")
    print(f"  GT_VP v9.9.6 — Timeframe: {tf}")
    print(f"{'='*70}")
    
    strategy_name = "GT_VP_v9.9.6_STRAT"
    
    # Set timeframe
    print(f"  Setting timeframe to {tf}...")
    try:
        await chart.set_timeframe(tf)
    except Exception as e:
        print(f"  ⚠️ set_timeframe failed: {e}, trying click-based fallback...")
        ok = await set_timeframe_via_click(cdp, tf)
        print(f"  Click-based: {'OK' if ok else 'FAILED'}")
    await asyncio.sleep(1.5)
    
    # Set 5D backtest window
    await set_date_preset(cdp, "5D")
    await asyncio.sleep(1.0)
    
    parsed = []
    for v in GTVP_AGGRESSIVE_VARIANTS:
        print(f"\n  ▶ {v['label']}")
        
        # Write settings
        try:
            await settings.list_fields(strategy_name)
            await asyncio.sleep(0.3)
            await settings.write(strategy_name, v["settings"])
            await asyncio.sleep(1.0)
        except Exception as exc:
            print(f"    ⚠️ Settings write failed: {exc}")
            parsed.append({
                "label": f"{v['label']}_{tf}",
                "tf": tf,
                "description": v.get("label", ""),
                "metrics": {},
                "scoring": {"score": 0, "reason": f"Settings error: {exc}", "compound_end": 0},
                "error": str(exc),
            })
            continue
        
        # Run backtest
        try:
            await backtest.run_strategy(strategy_name)
            await asyncio.sleep(WAIT_SECONDS)
            summary = await backtest.get_performance_summary()
        except Exception as exc:
            print(f"    ⚠️ Backtest failed: {exc}")
            summary = {}
        
        metrics = parse_backtest_metrics(summary)
        scoring = score_config(metrics)
        
        parsed.append({
            "label": f"{v['label']}_{tf}",
            "tf": tf,
            "description": str(v["settings"]),
            "metrics": metrics,
            "scoring": scoring,
        })
        
        print(f"    PF={metrics.get('profit_factor','?')} "
              f"Return={metrics.get('return_pct','?')}% "
              f"DD={metrics.get('max_drawdown','?')}% "
              f"Trades={metrics.get('total_trades','?')} "
              f"Score={scoring['score']} "
              f"→ ${scoring['compound_end']}")
    
    return parsed


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 70)
    print("AGGRESSIVE SCALP STRATEGY SWEEP")
    print(f"Target: ${STARTING_CAPITAL} → ${TARGET_CAPITAL} in {TRADING_DAYS} days")
    print(f"Max Drawdown: {MAX_DRAWDOWN_PCT}%")
    print(f"Timeframes: {TIMEFRAMES}")
    print(f"Date Window: 5D (preset)")
    print("=" * 70)
    
    # Connect
    cdp = CDPConnection(debug_port=DEBUG_PORT)
    await cdp.connect()
    print("✅ CDP connected")
    
    # Load recon
    recon = json.loads(RECON_PATH.read_text()) if RECON_PATH.exists() else {}
    
    # Build controllers
    pine = TVPineScriptController(cdp, recon, allow_unverified=True)
    backtest = TVBacktestController(cdp, recon, allow_unverified=True)
    chart = TVChartController(cdp, recon, allow_unverified=True)
    settings = TVSettingsController(cdp, recon, allow_unverified=True)
    variant_ctrl = StrategyVariantController(cdp, pine, backtest, chart)
    
    # Ensure Strategy Tester is open
    print("Opening Strategy Tester...")
    await cdp.execute_js("""
        (function(){
            var tabs = document.querySelectorAll('[role="tab"]');
            for (var i=0; i<tabs.length; i++) {
                if ((tabs[i].textContent||'').indexOf('Strategy Tester') >= 0) {
                    tabs[i].click();
                    return 'clicked';
                }
            }
            return 'not found';
        })()
    """)
    await asyncio.sleep(2.0)
    
    all_results = []
    
    # ── WaveTrend MAX sweep ──
    print("\n🔹 PHASE 1: WaveTrend MAX Aggressive Scalp Sweep")
    for tf in TIMEFRAMES:
        try:
            results = await run_wt_sweep(cdp, variant_ctrl, backtest, chart, tf)
            all_results.extend(results)
        except Exception as exc:
            print(f"  ❌ WT sweep failed for {tf}: {exc}")
    
    # ── GT_VP sweep ──
    print("\n🔹 PHASE 2: GT_VP Aggressive Settings Sweep")
    for tf in TIMEFRAMES:
        try:
            results = await run_gtvp_sweep(cdp, settings, backtest, chart, tf)
            all_results.extend(results)
        except Exception as exc:
            print(f"  ❌ GTVP sweep failed for {tf}: {exc}")
    
    # ── Results ──
    print("\n" + "=" * 70)
    print("RESULTS — Sorted by Score")
    print("=" * 70)
    
    # Sort by score descending
    scored = sorted(all_results, key=lambda x: x.get("scoring", {}).get("score", 0), reverse=True)
    
    print(f"{'Rank':<5} {'Config':<40} {'TF':<5} {'PF':>6} {'Return%':>8} {'DD%':>8} {'Trades':>7} {'Score':>8} {'$ End':>8}")
    print("-" * 105)
    
    for i, r in enumerate(scored):
        m = r.get("metrics", {})
        s = r.get("scoring", {})
        rank = i + 1
        label = r["label"][:38]
        tf = r["tf"]
        pf = m.get("profit_factor", 0)
        ret = m.get("return_pct", 0)
        dd = m.get("max_drawdown", 0)
        trades = m.get("total_trades", 0)
        score = s.get("score", 0)
        end = s.get("compound_end", 0)
        
        marker = "⭐" if s.get("hits_target") else "  "
        print(f"{marker}{rank:<4} {label:<40} {tf:<5} {pf:>6.2f} {ret:>8.2f} {dd:>8.1f} {trades:>7} {score:>8.2f} ${end:>7.0f}")
        
        if s.get("reason"):
            print(f"     ⚠️ {s['reason']}")
    
    # ── Best config recommendation ──
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    
    valid = [r for r in scored if r.get("scoring", {}).get("score", 0) > 0]
    
    if valid:
        best = valid[0]
        m = best.get("metrics", {})
        s = best.get("scoring", {})
        print(f"\n  Best Config: {best['label']}")
        print(f"  Timeframe: {best['tf']}")
        print(f"  Profit Factor: {m.get('profit_factor', 'N/A')}")
        print(f"  Return (5D window): {m.get('return_pct', 'N/A')}%")
        print(f"  Max Drawdown: {m.get('max_drawdown', 'N/A')}%")
        print(f"  Total Trades: {m.get('total_trades', 'N/A')}")
        print(f"  Win Rate: {m.get('win_rate', 'N/A')}%")
        print(f"  Score: {s.get('score', 'N/A')}")
        print(f"\n  Compound Projection ({TRADING_DAYS} trading days):")
        print(f"    Day 0: ${STARTING_CAPITAL:.2f}")
        daily_r = s.get("daily_edge_pct", 0)
        for day in range(1, TRADING_DAYS + 1):
            bal = compound_projection(daily_r, day, STARTING_CAPITAL)
            print(f"    Day {day}: ${bal:.2f}")
        
        if s.get("hits_target"):
            print(f"\n  ✅ TARGET ACHIEVABLE — Reaches ${TARGET_CAPITAL}+ in projection")
        else:
            shortfall = TARGET_CAPITAL - s.get("compound_end", 0)
            print(f"\n  ⚠️ Shortfall: ${shortfall:.0f} — Target ${TARGET_CAPITAL} not reached in projection")
            print(f"  Consider: higher leverage, more aggressive position sizing, or longer timeframe")
    else:
        print("\n  ❌ No valid configurations found that pass DD ≤ 50% and PF ≥ 0.8")
        print("  This is expected — 900% weekly return from scalping is extremely aggressive.")
        print("\n  Realistic alternatives:")
        print("  1. Extend timeframe to 2-4 weeks (compound over more days)")
        print("  2. Use higher starting capital ($500+ instead of $100)")
        print("  3. Accept higher drawdown risk (>50%)")
        print("  4. Focus on 1-2 high-probability setups per day instead of scalping")
    
    # ── Save results ──
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = LOG_DIR / f"scalp_sweep_{timestamp}.json"
    
    output_data = {
        "metadata": {
            "target": f"${STARTING_CAPITAL} → ${TARGET_CAPITAL}",
            "trading_days": TRADING_DAYS,
            "max_dd_pct": MAX_DRAWDOWN_PCT,
            "timeframes": TIMEFRAMES,
            "date_window": "5D",
            "timestamp": timestamp,
        },
        "results": scored,
        "best": valid[0] if valid else None,
    }
    
    output_path.write_text(json.dumps(output_data, indent=2, default=str))
    print(f"\n📁 Results saved to: {output_path}")
    
    await cdp.disconnect()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())
