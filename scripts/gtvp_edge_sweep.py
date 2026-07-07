#!/usr/bin/env python3
"""GT_VP v9.9.6 focused edge sweep.

Searches the current TradingView chart using strategy settings rather than
source rewrites. The goal is not max profit; it is stable, tradeable behavior:
daily-ish frequency, low drawdown, and validation survival.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.backtest_controller import TVBacktestController
from core.services.cdp_connection import CDPConnection
from core.services.dom_utils import DomUtils
from core.services.backends.dom_backend import DomPineScriptBackend
from core.services.settings_controller import TVSettingsController


STRATEGY = "GT_VP_v9.9.6_STRAT"
DEBUG_PORT = 8315
WAIT_SECONDS = 18.0
RESEARCH_INITIAL_CAPITAL = 10_000_000.0
SOURCE_PATH = Path(__file__).resolve().parents[2] / "TRADINGVIEW_INDICATORS" / "GT_VP_v9.9.6_STRAT" / "GT_VP_v9.9.6_STRAT.pine"
OVERRIDE_RE = re.compile(r'string strategy_setup_source_override = "[^"]+"')

BASE_SETTINGS: dict[str, Any] = {
    "Trade Signal Mode": "All Signals",
    "Entry Strictness": "Normal",
    "Trade Direction": "Both",
    "MA Filter Mode": "Off",
    "Fallback R:R Target": 1.5,
    "ATR Stop Multiplier": 1.0,
    "Level Buffer ATR": 0.1,
    "Timeout Bars": 30,
}


def source_with_override(base_source: str, setup_name: str) -> str:
    override = "AUTO" if setup_name == "__AUTO__" else "All Signals" if setup_name == "All Setups" else setup_name
    return OVERRIDE_RE.sub(f'string strategy_setup_source_override = "{override}"', base_source, count=1)

SETUP_TOGGLES = [
    "S1 Sweep",
    "S2 Failed Auction",
    "S3 POC Rotation",
    "S4 CHoCH",
    "S5 BOS / Value Break",
    "S6 VA Reclaim / Reject",
    "S7 Defense",
    "S8 Divergence",
    "S9 FVG / IFVG",
    "S10 LVN Break",
]


def to_num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, "", "N/A", "n/a", "NA", "na"):
        return default
    text = str(value)
    text = text.replace(",", "").replace("$", "").replace("%", "")
    text = text.replace("\u2212", "-").replace("\u00a0", " ").strip()
    try:
        return float(text)
    except ValueError:
        return default


def direction_settings(direction: str) -> dict[str, str]:
    return {"Trade Direction": direction}


async def safe_write(settings: TVSettingsController, values: dict[str, Any]) -> bool:
    for attempt in range(3):
        try:
            await settings.list_fields(STRATEGY)
            await asyncio.sleep(0.25)
            await settings.write(STRATEGY, values)
            await asyncio.sleep(0.75)
            return True
        except Exception as exc:
            if attempt == 2:
                print(f"    settings write failed: {exc}", flush=True)
                return False
            await asyncio.sleep(1.0)
    return False


async def apply_source_override(
    cdp: CDPConnection,
    dom: DomUtils,
    pine: DomPineScriptBackend,
    base_source: str,
    setup_name: str,
) -> bool:
    source = source_with_override(base_source, setup_name)
    try:
        subprocess.run(["pbcopy"], input=source, text=True, check=True)
    except Exception as exc:
        print(f"    pbcopy failed: {exc}", flush=True)
        return False

    await cdp._send_command("Page.bringToFront", {})
    subprocess.run(["open", "-a", "TradingView"], check=False)
    await asyncio.sleep(0.6)
    await cdp.execute_js(
        """
        (() => {
            const all = document.querySelectorAll('.monaco-editor textarea.inputarea');
            for (let i = 0; i < all.length; i++) {
                if (all[i].offsetWidth > 0) {
                    all[i].focus();
                    all[i].select();
                    return 'focused';
                }
            }
            return 'no-textarea';
        })()
        """
    )
    paste_ok = await dom._paste_via_cgevent()
    if not paste_ok:
        await dom._paste_via_cdp()
    result = await cdp.execute_js(
        """
        (() => {
            const btn = document.querySelector('button[title="Update on chart"]')
                || document.querySelector('button[title="Add to chart"]')
                || document.querySelector('button[title="Save script"]');
            if (btn) {
                btn.click();
                return {success: true, title: btn.getAttribute('title')};
            }
            return {success: false};
        })()
        """
    )
    update = result.get("result", {}).get("value", {})
    await asyncio.sleep(2.0)
    messages = await pine.read_compile_errors()
    errors = [msg for msg in messages if msg.get("type") == "error"]
    if errors:
        print(f"    compile errors for {setup_name}: {errors}", flush=True)
        return False
    warnings = [msg for msg in messages if msg.get("type") == "warning"]
    if warnings:
        print(f"    compile warnings for {setup_name}: {len(warnings)}", flush=True)
    if not update.get("success"):
        print(f"    update button not found for {setup_name}: {update}", flush=True)
        return False
    return True


async def set_date_preset(cdp: CDPConnection, preset: str) -> bool:
    js = f"""(() => {{
        const buttons = document.querySelectorAll('[data-name*="date-range-tab"]');
        for (const b of buttons) {{
            const name = b.getAttribute('data-name') || '';
            if (name.includes({json.dumps(preset)})) {{
                b.click();
                return true;
            }}
        }}
        return false;
    }})()"""
    result = await cdp.execute_js(js)
    return bool(result.get("result", {}).get("value"))


async def force_timeframe(cdp: CDPConnection, data_value: str = "5") -> bool:
    js = f"""(() => {{
        const clickLike = (target) => {{
            target.scrollIntoView({{block:'center', inline:'center'}});
            target.focus();
            target.dispatchEvent(new PointerEvent('pointerdown', {{bubbles:true, pointerId:1, pointerType:'mouse', isPrimary:true}}));
            target.dispatchEvent(new MouseEvent('mousedown', {{bubbles:true, buttons:1}}));
            target.dispatchEvent(new MouseEvent('mouseup', {{bubbles:true}}));
            target.dispatchEvent(new PointerEvent('pointerup', {{bubbles:true, pointerId:1, pointerType:'mouse', isPrimary:true}}));
            target.click();
        }};
        let buttons = [...document.querySelectorAll('button[role="radio"]')];
        let target = buttons.find(b => b.getAttribute('data-value') === {json.dumps(data_value)});
        if (!target) {{
            const openers = [...document.querySelectorAll('button, [role="button"], [data-name]')];
            const opener = openers.find(el => {{
                const txt = (el.textContent || '').trim();
                const aria = el.getAttribute('aria-label') || '';
                const title = el.getAttribute('title') || '';
                const data = el.getAttribute('data-name') || '';
                return txt === '1D' || txt === 'D' || txt === '5' || aria.includes('interval') || title.includes('interval') || data.includes('interval');
            }});
            if (opener) clickLike(opener);
            buttons = [...document.querySelectorAll('button[role="radio"]')];
            target = buttons.find(b => b.getAttribute('data-value') === {json.dumps(data_value)} || (b.textContent || '').trim() === '5 minutes' || (b.textContent || '').trim() === '5m');
        }}
        if (!target) return false;
        clickLike(target);
        return true;
    }})()"""
    result = await cdp.execute_js(js)
    await asyncio.sleep(2.0)
    return bool(result.get("result", {}).get("value"))


async def body_metrics(cdp: CDPConnection) -> dict[str, Any]:
    js = r"""(() => {
        const text = document.body.innerText || '';
        const pick = (re) => {
            const m = text.match(re);
            return m ? m[1].replace('−', '-').replace(/,/g, '').trim() : 'N/A';
        };
        return {
            total_trades_text: pick(/Total\s*(?:closed\s*)?trades\s*(\d+)/i),
            win_rate_pct: pick(/Percent\s*Profitable\s*([\d.]+)%/i),
            max_dd_pct: pick(/Max\s*[Dd]rawdown\s*([\d.]+)%/i),
            body_has_tester: text.includes('Strategy Tester') || text.includes('Overview')
        };
    })()"""
    result = await cdp.execute_js(js)
    value = result.get("result", {}).get("value", {})
    return value if isinstance(value, dict) else {}


async def open_strategy_tester(cdp: CDPConnection) -> bool:
    js = r"""(() => {
        const wanted = ['Strategy Tester', 'Strategy tester', 'Overview'];
        const candidates = Array.from(document.querySelectorAll('button, [role="tab"], [data-name], div, span'));
        for (const label of wanted) {
            const el = candidates.find((node) => {
                const txt = (node.textContent || '').trim();
                const aria = node.getAttribute && (node.getAttribute('aria-label') || node.getAttribute('title') || node.getAttribute('id') || node.getAttribute('data-name') || '');
                return txt === label || aria.includes(label) || aria.includes('strategy-report');
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


async def run_cycle(
    cdp: CDPConnection,
    backtest: TVBacktestController,
    window: str | None,
    label: str,
    settings_values: dict[str, Any],
) -> dict[str, Any]:
    if window:
        await set_date_preset(cdp, window)
        await asyncio.sleep(0.5)
        await force_timeframe(cdp, "5")
    await open_strategy_tester(cdp)
    await backtest.run_strategy(STRATEGY)
    await asyncio.sleep(WAIT_SECONDS)
    await open_strategy_tester(cdp)
    summary = await backtest.get_performance_summary()
    trades = await backtest.get_trade_list()
    body = await body_metrics(cdp)
    summary_trade_count = int(to_num(summary.get("total_trades"), 0))
    body_trade_count = int(to_num(body.get("total_trades_text"), 0))
    trade_count = len(trades) if isinstance(trades, list) and trades else max(summary_trade_count, body_trade_count)
    if trade_count <= 0:
        net = abs(to_num(summary.get("net_profit"), 0))
        avg = abs(to_num(summary.get("avg_pnl"), 0))
        trade_count = int(round(net / avg)) if avg > 0 else 0
    max_dd = to_num(summary.get("max_drawdown"), 0)
    max_dd_pct = body.get("max_dd_pct", "N/A")
    if max_dd_pct in (None, "", "N/A", "n/a", "NA", "na") and max_dd > 0:
        max_dd_pct = round(max_dd / RESEARCH_INITIAL_CAPITAL * 100, 4)
    return {
        "label": label,
        "settings": settings_values,
        "window": window or "current",
        "summary": summary,
        "trades": trades if isinstance(trades, list) else [],
        "trade_count": trade_count,
        "win_rate_pct": body.get("win_rate_pct", "N/A"),
        "max_dd_pct": max_dd_pct,
        "profit_factor": summary.get("profit_factor", "N/A"),
        "net_profit": summary.get("net_profit", "N/A"),
        "max_drawdown": summary.get("max_drawdown", "N/A"),
        "sharpe": summary.get("sharpe", "N/A"),
        "avg_pnl": summary.get("avg_pnl", "N/A"),
    }


def score_result(result: dict[str, Any]) -> float:
    pf = to_num(result.get("profit_factor"), 0)
    sharpe = to_num(result.get("sharpe"), 0)
    net = to_num(result.get("net_profit"), 0)
    dd_pct = max(to_num(result.get("max_dd_pct"), 99), 0.25)
    trades = max(int(result.get("trade_count") or 0), 0)

    if trades <= 0 or pf <= 0:
        return -999.0

    daily_target = 252
    freq_penalty = abs(trades - daily_target) / daily_target
    under_sample_penalty = 1.0 if trades < 30 else 0.0
    dd_penalty = dd_pct / 20.0

    return (
        2.5 * math.log(max(pf, 0.01))
        + 0.8 * max(sharpe, -2.0)
        + 0.00002 * net
        + 0.35 * math.log(trades)
        - 1.2 * freq_penalty
        - 1.4 * dd_penalty
        - 2.0 * under_sample_penalty
    )


def summarize_top(title: str, results: list[dict[str, Any]], count: int = 8) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    tradable = [r for r in results if int(r.get("trade_count") or 0) > 0 and to_num(r.get("profit_factor"), 0) > 0]
    rows = sorted(tradable, key=score_result, reverse=True)[:count]
    if not rows:
        rows = sorted(results, key=score_result, reverse=True)[:count]
    for idx, row in enumerate(rows, 1):
        print(
            f"{idx:>2}. {row['label']:<52} "
            f"PF={row.get('profit_factor')} DD%={row.get('max_dd_pct')} "
            f"T={row.get('trade_count')} WR={row.get('win_rate_pct')} "
            f"Score={score_result(row):.2f}",
            flush=True,
        )


def build_stage1() -> list[dict[str, Any]]:
    variants = []
    for setup_name in ["All Setups", *SETUP_TOGGLES]:
        for strictness in ["Loose", "Normal"]:
            for direction in ["Both", "Long Only", "Short Only"]:
                values = {
                    **BASE_SETTINGS,
                    "Trade Signal Mode": "All Signals",
                    "Entry Strictness": strictness,
                    **direction_settings(direction),
                }
                variants.append({
                    "label": f"{setup_name} | {strictness} | {direction}",
                    "settings": values,
                    "metadata": {
                        "mode": "All Signals",
                        "setup": setup_name,
                        "strictness": strictness,
                        "direction": direction,
                    },
                })
    return variants


def build_stage2(seed: dict[str, Any]) -> list[dict[str, Any]]:
    variants = []
    meta = seed.get("metadata", {})
    base = {
        **BASE_SETTINGS,
        "Trade Signal Mode": "All Signals",
        "Entry Strictness": meta.get("strictness", "Normal"),
        **direction_settings(meta.get("direction", "Both")),
    }
    for ma_filter in ["Off", "2-MA (Fast/Medium)", "3-MA (All Aligned)"]:
        for timeout in [10, 20, 30, 60]:
            values = {**base, "MA Filter Mode": ma_filter, "Timeout Bars": timeout}
            variants.append({
                "label": f"{seed['label']} | MA={ma_filter} | T={timeout}",
                "settings": values,
                "metadata": {**meta, "ma_filter": ma_filter, "timeout": timeout},
            })
    return variants


async def run_variant(
    cdp: CDPConnection,
    settings: TVSettingsController,
    backtest: TVBacktestController,
    variant: dict[str, Any],
    window: str | None,
) -> dict[str, Any]:
    ok = await safe_write(settings, variant["settings"])
    if not ok:
        return {
            "label": variant["label"],
            "settings": variant["settings"],
            "metadata": variant.get("metadata", {}),
            "window": window or "current",
            "error": "settings_write_failed",
        }
    result = await run_cycle(cdp, backtest, window, variant["label"], variant["settings"])
    result["metadata"] = variant.get("metadata", {})
    return result


async def main() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    recon_path = Path(__file__).resolve().parent.parent / "recon_findings.json"
    recon = json.loads(recon_path.read_text())
    cdp = CDPConnection(debug_port=DEBUG_PORT)
    await cdp.connect()
    try:
        base_source = SOURCE_PATH.read_text()
        dom = DomUtils(cdp)
        pine = DomPineScriptBackend(cdp, dom, recon.get("capabilities", {}))
        settings = TVSettingsController(cdp, recon, allow_unverified=True)
        backtest = TVBacktestController(cdp, recon, allow_unverified=True)
        current_setup = ""

        print("GT_VP focused edge sweep")
        print(f"Started: {started.isoformat()}")
        print("Forcing chart timeframe to 5m...")
        await force_timeframe(cdp, "5")
        print("Restoring base settings...")
        await safe_write(settings, BASE_SETTINGS)

        stage1_results: list[dict[str, Any]] = []
        stage1 = build_stage1()
        print(f"\nStage 1: setup isolation x strictness x direction ({len(stage1)} variants)")
        for idx, variant in enumerate(stage1, 1):
            setup_name = variant.get("metadata", {}).get("setup", "All Setups")
            if setup_name != current_setup:
                print(f"    compiling setup override: {setup_name}", flush=True)
                if not await apply_source_override(cdp, dom, pine, base_source, setup_name):
                    stage1_results.append({
                        "label": variant["label"],
                        "settings": variant["settings"],
                        "metadata": variant.get("metadata", {}),
                        "window": "12M",
                        "error": "compile_failed",
                    })
                    continue
                current_setup = setup_name
            print(f"[S1 {idx:02d}/{len(stage1)}] {variant['label']}", flush=True)
            result = await run_variant(cdp, settings, backtest, variant, "12M")
            stage1_results.append(result)
            print(
                f"    PF={result.get('profit_factor')} DD%={result.get('max_dd_pct')} "
                f"T={result.get('trade_count')} WR={result.get('win_rate_pct')}",
                flush=True,
            )

        summarize_top("Stage 1 top", stage1_results)

        tradable_stage1 = [
            r for r in stage1_results
            if int(r.get("trade_count") or 0) > 0 and to_num(r.get("profit_factor"), 0) > 0
        ]
        seeds = sorted(tradable_stage1, key=score_result, reverse=True)[:3]
        stage2_variants: list[dict[str, Any]] = []
        for seed in seeds:
            stage2_variants.extend(build_stage2(seed))

        stage2_results: list[dict[str, Any]] = []
        print(f"\nStage 2: MA filter x timeout around top 3 ({len(stage2_variants)} variants)")
        for idx, variant in enumerate(stage2_variants, 1):
            setup_name = variant.get("metadata", {}).get("setup", "All Setups")
            if setup_name != current_setup:
                print(f"    compiling setup override: {setup_name}", flush=True)
                if not await apply_source_override(cdp, dom, pine, base_source, setup_name):
                    stage2_results.append({
                        "label": variant["label"],
                        "settings": variant["settings"],
                        "metadata": variant.get("metadata", {}),
                        "window": "12M",
                        "error": "compile_failed",
                    })
                    continue
                current_setup = setup_name
            print(f"[S2 {idx:02d}/{len(stage2_variants)}] {variant['label']}", flush=True)
            result = await run_variant(cdp, settings, backtest, variant, "12M")
            stage2_results.append(result)
            print(
                f"    PF={result.get('profit_factor')} DD%={result.get('max_dd_pct')} "
                f"T={result.get('trade_count')} WR={result.get('win_rate_pct')}",
                flush=True,
            )

        summarize_top("Stage 2 top", stage2_results)

        validation_results: list[dict[str, Any]] = []
        finalists = sorted(stage2_results, key=score_result, reverse=True)[:5]
        print(f"\nValidation: 6M check for top {len(finalists)}")
        for idx, finalist in enumerate(finalists, 1):
            variant = {
                "label": finalist["label"],
                "settings": finalist["settings"],
                "metadata": finalist.get("metadata", {}),
            }
            setup_name = variant.get("metadata", {}).get("setup", "All Setups")
            if setup_name != current_setup:
                print(f"    compiling setup override: {setup_name}", flush=True)
                if not await apply_source_override(cdp, dom, pine, base_source, setup_name):
                    validation_results.append({
                        "label": variant["label"],
                        "settings": variant["settings"],
                        "metadata": variant.get("metadata", {}),
                        "window": "6M",
                        "error": "compile_failed",
                    })
                    continue
                current_setup = setup_name
            print(f"[VAL {idx:02d}/{len(finalists)}] {variant['label']}", flush=True)
            result = await run_variant(cdp, settings, backtest, variant, "6M")
            train_pf = to_num(finalist.get("profit_factor"), 0)
            val_pf = to_num(result.get("profit_factor"), 0)
            divergence = abs(train_pf - val_pf) / train_pf * 100 if train_pf > 0 else 100
            result["train"] = finalist
            result["pf_divergence_pct"] = round(divergence, 2)
            validation_results.append(result)
            print(
                f"    VAL PF={result.get('profit_factor')} DD%={result.get('max_dd_pct')} "
                f"T={result.get('trade_count')} Div={divergence:.1f}%",
                flush=True,
            )

        summarize_top("Validation top", validation_results)

        completed = datetime.now(timezone.utc)
        report = {
            "metadata": {
                "strategy": STRATEGY,
                "started": started.isoformat(),
                "completed": completed.isoformat(),
                "elapsed_seconds": round((completed - started).total_seconds(), 1),
                "objective": "daily-ish scalp-to-swing candidates with low drawdown",
            },
            "base_settings": BASE_SETTINGS,
            "stage1": stage1_results,
            "stage2": stage2_results,
            "validation": validation_results,
            "ranked_validation": sorted(validation_results, key=score_result, reverse=True),
        }

        out_dir = Path(__file__).resolve().parent.parent / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"gtvp_edge_sweep_{started.strftime('%Y%m%d_%H%M%S')}.json"
        out_path.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nReport: {out_path}")

        print("Restoring base settings...")
        await apply_source_override(cdp, dom, pine, base_source, "__AUTO__")
        await safe_write(settings, BASE_SETTINGS)
        return report
    finally:
        await cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
