#!/usr/bin/env python3
"""Direct Aggressive Scalp Sweep — Simplified, robust approach.

Uses GT_VP v9.9.6 settings-based control (no Pine editor dependency).
Tests 15m timeframe only with aggressive settings, then projects compound growth.

Target: $100 → $1,000 in 5 trading days. Max DD: 50%.
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection
from core.services.backtest_controller import TVBacktestController
from core.services.chart_controller import TVChartController
from core.services.settings_controller import TVSettingsController
from core.services.dom_utils import DomUtils

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs" / "scalp_sweep"
RECON_PATH = ROOT / "recon_findings.json"
GTVP_SOURCE_PATH = ROOT.parent / "TRADINGVIEW_INDICATORS" / "GT_VP_v9.9.6_STRAT" / "GT_VP_v9.9.6_STRAT.pine"
STRATEGY = "GT_VP_v9.9.6_STRAT"
TF = "15m"
DEBUG_PORT = 8315
WAIT_SECONDS = 12.0

STARTING_CAPITAL = 100.0
TARGET_CAPITAL = 1000.0
MAX_DD_PCT = 50.0
TRADING_DAYS = 5


def to_num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, "", "N/A", "n/a", "NA", "na"):
        return default
    text = str(value).replace(",", "").replace("$", "").replace("%", "")
    text = text.replace("\u2212", "-").replace("\u00a0", " ").strip()
    try: return float(text)
    except ValueError: return default


def parse_metrics(summary: dict) -> dict:
    raw = summary.get("summary", summary)
    if not raw: return {}
    return {
        "net_profit": to_num(raw.get("net_profit", raw.get("Net Profit", 0))),
        "sharpe": to_num(raw.get("sharpe", raw.get("Sharpe Ratio", 0))),
        "profit_factor": to_num(raw.get("profit_factor", raw.get("Profit Factor", 1))),
        "max_drawdown_pct": to_num(raw.get("max_drawdown", raw.get("Max Drawdown", 0))),
        "return_pct": to_num(raw.get("return_pct", raw.get("Return", 0))),
        "total_trades": int(to_num(raw.get("total_trades", raw.get("Total Closed Trades", 0)))),
        "win_rate": to_num(raw.get("win_rate_pct", raw.get("Percent Profitable", 0))),
        "avg_pnl": to_num(raw.get("avg_pnl", raw.get("Avg Trade", 0))),
    }


def compound(balance: float, daily_pct: float, days: int) -> float:
    return balance * ((1 + daily_pct / 100) ** days)


def score(m: dict) -> dict:
    dd = abs(m.get("max_drawdown_pct", 100))
    pf = m.get("profit_factor", 1.0)
    ret = m.get("return_pct", 0)
    trades = m.get("total_trades", 0)
    
    if dd > MAX_DD_PCT: return {"score": 0, "reason": f"DD {dd:.1f}% > {MAX_DD_PCT}%", "compound_end": 0}
    if trades < 5: return {"score": 0, "reason": f"Only {trades} trades", "compound_end": 0}
    if pf < 0.8: return {"score": 0, "reason": f"PF {pf:.2f} too low", "compound_end": 0}
    
    daily = ret / TRADING_DAYS
    end = compound(STARTING_CAPITAL, daily, TRADING_DAYS) if ret > 0 else STARTING_CAPITAL
    raw = pf * (trades ** 0.5) * max(ret, 0.01) / max(dd, 1)
    
    return {
        "score": round(raw, 2),
        "daily_edge_pct": round(daily, 2),
        "compound_end": round(end, 2),
        "hits_target": end >= TARGET_CAPITAL,
    }


# Aggressive scalp variants for GT_VP on 15m
VARIANTS = [
    {
        "label": "GTVP_MaxSignals_Loose_Both",
        "desc": "All signals, loose entry, both directions, tight stops",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.3,
            "ATR Stop Multiplier": 0.4,
            "Level Buffer ATR": 0.03,
            "Timeout Bars": 8,
        },
    },
    {
        "label": "GTVP_MaxSignals_Loose_Long",
        "desc": "All signals, loose, long only, ultra-tight stops",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Long Only",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.5,
            "ATR Stop Multiplier": 0.3,
            "Level Buffer ATR": 0.02,
            "Timeout Bars": 5,
        },
    },
    {
        "label": "GTVP_MaxSignals_Loose_Short",
        "desc": "All signals, loose, short only, ultra-tight stops",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Short Only",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.5,
            "ATR Stop Multiplier": 0.3,
            "Level Buffer ATR": 0.02,
            "Timeout Bars": 5,
        },
    },
    {
        "label": "GTVP_HighFreq_Normal_Both",
        "desc": "All signals, normal entry, both, high RR",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Normal",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 2.0,
            "ATR Stop Multiplier": 0.5,
            "Level Buffer ATR": 0.05,
            "Timeout Bars": 10,
        },
    },
    {
        "label": "GTVP_ScalpOnly_Normal_Both",
        "desc": "All signals, normal, both, pure scalp RR",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Normal",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.0,
            "ATR Stop Multiplier": 0.25,
            "Level Buffer ATR": 0.01,
            "Timeout Bars": 3,
        },
    },
    {
        "label": "GTVP_ScalpOnly_Loose_Both",
        "desc": "All signals, loose, both, pure scalp RR (most aggressive)",
        "settings": {
            "Trade Signal Mode": "All Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.0,
            "ATR Stop Multiplier": 0.2,
            "Level Buffer ATR": 0.01,
            "Timeout Bars": 3,
        },
    },
    {
        "label": "GTVP_DivOnly_Loose_Both",
        "desc": "Divergence only, loose, both, tight exits",
        "settings": {
            "Trade Signal Mode": "Divergence",
            "Entry Strictness": "Loose",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.3,
            "ATR Stop Multiplier": 0.4,
            "Level Buffer ATR": 0.03,
            "Timeout Bars": 8,
        },
    },
    {
        "label": "GTVP_VPAOnly_Loose_Both",
        "desc": "VPA signals only, loose, both",
        "settings": {
            "Trade Signal Mode": "VPA Signals",
            "Entry Strictness": "Loose",
            "Trade Direction": "Both",
            "MA Filter Mode": "Off",
            "Fallback R:R Target": 1.3,
            "ATR Stop Multiplier": 0.4,
            "Level Buffer ATR": 0.03,
            "Timeout Bars": 8,
        },
    },
]


async def apply_strategy_to_chart(cdp: CDPConnection, source_path: Path) -> bool:
    """Load a Pine strategy source into the editor and apply it to the chart."""
    source = source_path.read_text()
    
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
    
    # Paste via CGEvent or CDP fallback
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
    r = await cdp.execute_js(js)
    return bool(r.get("result", {}).get("value"))


async def main():
    print("=" * 70)
    print("DIRECT AGGRESSIVE SCALP SWEEP — GT_VP v9.9.6")
    print(f"Timeframe: {TF} | Window: 5D | Variants: {len(VARIANTS)}")
    print(f"Target: ${STARTING_CAPITAL} → ${TARGET_CAPITAL} in {TRADING_DAYS} days")
    print(f"Max DD: {MAX_DD_PCT}%")
    print("=" * 70)

    # Connect
    cdp = CDPConnection(debug_port=DEBUG_PORT)
    await cdp.connect()
    print("✅ CDP connected")

    recon = json.loads(RECON_PATH.read_text()) if RECON_PATH.exists() else {}
    backtest = TVBacktestController(cdp, recon, allow_unverified=True)
    chart = TVChartController(cdp, recon, allow_unverified=True)
    settings = TVSettingsController(cdp, recon, allow_unverified=True)

    # Set timeframe
    print(f"\nSetting timeframe to {TF}...")
    await chart.set_timeframe(TF)
    await asyncio.sleep(2.0)

    # Set 5D window
    print("Setting backtest window to 5D...")
    await set_date_preset(cdp, "5D")
    await asyncio.sleep(1.5)

    # ── CRITICAL: Apply GT_VP to chart first ──
    print(f"\nLoading GT_VP strategy onto chart...")
    print(f"  Source: {GTVP_SOURCE_PATH}")
    if not GTVP_SOURCE_PATH.exists():
        print(f"  ❌ Source file not found!")
        await cdp.disconnect()
        return
    applied = await apply_strategy_to_chart(cdp, GTVP_SOURCE_PATH)
    if not applied:
        print(f"  ❌ Failed to apply GT_VP to chart!")
        await cdp.disconnect()
        return
    print(f"  ✅ GT_VP applied, waiting for chart to settle...")
    await asyncio.sleep(4.0)

    # Ensure Strategy Tester is visible
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

    results = []
    for i, v in enumerate(VARIANTS):
        label = v["label"]
        print(f"\n{'─'*60}")
        print(f"  [{i+1}/{len(VARIANTS)}] {label}")
        print(f"  {v['desc']}")

        # Write settings
        try:
            await settings.list_fields(STRATEGY)
            await asyncio.sleep(0.3)
            await settings.write(STRATEGY, v["settings"])
            await asyncio.sleep(0.5)
            print(f"  ✅ Settings applied")
        except Exception as e:
            print(f"  ❌ Settings failed: {e}")
            results.append({"label": label, "error": str(e), "metrics": {}, "scoring": {"score": 0, "reason": str(e)}})
            continue

        # Run backtest
        try:
            await backtest.run_strategy(STRATEGY)
            await asyncio.sleep(WAIT_SECONDS)
            summary = await backtest.get_performance_summary()
            print(f"  ✅ Backtest complete")
        except Exception as e:
            print(f"  ❌ Backtest failed: {e}")
            results.append({"label": label, "error": str(e), "metrics": {}, "scoring": {"score": 0, "reason": str(e)}})
            continue

        # Parse & score
        m = parse_metrics(summary)
        s = score(m)
        
        print(f"  PF={m.get('profit_factor','?'):.2f} "
              f"Return={m.get('return_pct','?'):.2f}% "
              f"DD={m.get('max_drawdown_pct','?'):.1f}% "
              f"Trades={m.get('total_trades','?')} "
              f"WR={m.get('win_rate','?'):.1f}%")
        print(f"  Score={s['score']} | Daily Edge={s.get('daily_edge_pct',0):.2f}% | "
              f"${STARTING_CAPITAL:.0f}→${s.get('compound_end',0):.0f}")
        
        if s.get("reason"):
            print(f"  ⚠️ {s['reason']}")

        results.append({"label": label, "desc": v["desc"], "settings": v["settings"],
                        "metrics": m, "scoring": s, "summary_raw": summary})

    # ── Results ──
    print("\n" + "=" * 70)
    print("RESULTS — Sorted by Score")
    print("=" * 70)

    scored = sorted(results, key=lambda x: x.get("scoring", {}).get("score", 0), reverse=True)
    
    print(f"{'Rank':<5} {'Config':<35} {'PF':>6} {'Ret%':>7} {'DD%':>7} {'Trades':>7} {'WR%':>6} {'Score':>7} {'$ End':>7}")
    print("-" * 97)
    
    for i, r in enumerate(scored):
        m = r.get("metrics", {})
        s = r.get("scoring", {})
        marker = "⭐" if s.get("hits_target") else "  "
        print(f"{marker}{i+1:<4} {r['label'][:33]:<35} "
              f"{m.get('profit_factor',0):>6.2f} {m.get('return_pct',0):>7.2f} "
              f"{m.get('max_drawdown_pct',0):>7.1f} {m.get('total_trades',0):>7} "
              f"{m.get('win_rate',0):>6.1f} {s.get('score',0):>7.2f} "
              f"${s.get('compound_end',0):>7.0f}")
        if s.get("reason"):
            print(f"     ⚠️ {s['reason']}")

    # ── Recommendation ──
    valid = [r for r in scored if r.get("scoring", {}).get("score", 0) > 0]
    
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    
    if valid:
        best = valid[0]
        m = best["metrics"]
        s = best["scoring"]
        print(f"\n  Best Config: {best['label']}")
        print(f"  Description: {best['desc']}")
        print(f"  Settings: {json.dumps(best['settings'], indent=4)}")
        print(f"\n  Backtest Metrics (5D, {TF}):")
        print(f"    Profit Factor:  {m.get('profit_factor', 'N/A')}")
        print(f"    Net Profit:     {m.get('net_profit', 'N/A')}")
        print(f"    Return:         {m.get('return_pct', 'N/A')}%")
        print(f"    Max Drawdown:   {m.get('max_drawdown_pct', 'N/A')}%")
        print(f"    Total Trades:   {m.get('total_trades', 'N/A')}")
        print(f"    Win Rate:       {m.get('win_rate', 'N/A')}%")
        print(f"    Avg PnL/Trade:  {m.get('avg_pnl', 'N/A')}")
        print(f"    Sharpe:         {m.get('sharpe', 'N/A')}")
        
        print(f"\n  Compound Projection ({TRADING_DAYS} trading days @ {s.get('daily_edge_pct',0):.2f}%/day):")
        bal = STARTING_CAPITAL
        print(f"    Day 0: ${bal:.2f}")
        for d in range(1, TRADING_DAYS + 1):
            bal = compound(STARTING_CAPITAL, s.get("daily_edge_pct", 0), d)
            print(f"    Day {d}: ${bal:.2f}")
        
        if s.get("hits_target"):
            print(f"\n  ✅ TARGET ACHIEVABLE — Reaches ${TARGET_CAPITAL}+")
        else:
            print(f"\n  ⚠️ Shortfall: ${TARGET_CAPITAL - s.get('compound_end', 0):.0f}")
            print(f"  Target ${TARGET_CAPITAL} requires ~{((TARGET_CAPITAL/STARTING_CAPITAL)**(1/TRADING_DAYS)-1)*100:.1f}% daily return.")
    else:
        print("\n  ❌ No valid configs found. This is expected for a 900% weekly target.")
    
    # Save
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = LOG_DIR / f"scalp_direct_{ts}.json"
    out.write_text(json.dumps({
        "metadata": {"target": f"${STARTING_CAPITAL}→${TARGET_CAPITAL}", "timeframe": TF, "window": "5D", "days": TRADING_DAYS, "timestamp": ts},
        "results": scored,
        "best": valid[0] if valid else None,
    }, indent=2, default=str))
    print(f"\n📁 Saved: {out}")

    await cdp.disconnect()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())
