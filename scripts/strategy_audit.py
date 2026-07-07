#!/usr/bin/env python3
"""
GT_VP v9.9.6 Strategy Audit - Aggressive Intraday Configuration Search.
Uses existing controllers (backtest, settings, pinescript) with CDP fallbacks.
"""

import asyncio, json, math, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from core.services.cdp_connection import CDPConnection
from core.services.settings_controller import TVSettingsController
from core.services.pinescript_controller import TVPineScriptController
from core.services.backtest_controller import TVBacktestController

STRATEGY = "GT_VP_v9.9.6_STRAT"
DEBUG_PORT = 8315

MIN_TRADES = 20
MAX_DD_PCT = 35.0
MIN_PF = 1.10
MAX_VAL_DIVERGENCE = 40.0

COMMISSION = 0.0004
SLIPPAGE = 0.0002

AGGRESSIVE_MA_COMBOS = [
    {"Fast MA Length": 3, "Medium MA Length": 7, "Slow MA Length": 20},
    {"Fast MA Length": 5, "Medium MA Length": 10, "Slow MA Length": 30},
    {"Fast MA Length": 7, "Medium MA Length": 14, "Slow MA Length": 30},
    {"Fast MA Length": 3, "Medium MA Length": 10, "Slow MA Length": 50},
    {"Fast MA Length": 5, "Medium MA Length": 14, "Slow MA Length": 50},
    {"Fast MA Length": 7, "Medium MA Length": 21, "Slow MA Length": 50},
    {"Fast MA Length": 9, "Medium MA Length": 21, "Slow MA Length": 50},
    {"Fast MA Length": 3, "Medium MA Length": 5, "Slow MA Length": 20},
    {"Fast MA Length": 5, "Medium MA Length": 7, "Slow MA Length": 20},
]

def to_num(val):
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    s = str(val).replace(",", "").replace("\u2212", "-")
    for c in "+$\u00a0 ":
        s = s.strip(c)
    try:
        return float(s)
    except ValueError:
        return 0.0

def is_missing(val):
    return val in (None, "", "N/A", "n/a", "NA", "na")

async def set_date_preset(cdp, preset):
    code = f"""(function(){{
        var btns = document.querySelectorAll('[data-name*="date-range-tab"]');
        for (var i=0; i<btns.length; i++) {{
            if (btns[i].getAttribute('data-name').indexOf('{preset}') >= 0) {{
                btns[i].click(); return 'ok';
            }}
        }}
        return 'not_found';
    }})()"""
    r = await cdp.execute_js(code)
    val = r.get("result", {}).get("value", "")
    return "ok" in str(val)

async def get_body_metrics(cdp):
    code = """(function(){
        var t = document.body.innerText;
        var get = function(re) {
            var m = t.match(re);
            return m ? m[1].replace('\u2212','-').replace(/,/g,'').trim() : 'N/A';
        };
        return JSON.stringify({
            winRate: get(/Percent\\s*Profitable\\s*([\\d.]+)%/),
            maxDrawdownPct: get(/Max\\s*[Dd]rawdown\\s*([\\d.]+)%/),
            totalTradesText: get(/Total\\s*(?:closed\\s*)?trades\\s*(\\d+)/i),
            longWinRate: get(/Longs\\s*([\\d.]+)%/),
            shortWinRate: get(/Shorts\\s*([\\d.]+)%/),
        });
    })()"""
    r = await cdp.execute_js(code)
    val = r.get("result", {}).get("value", "")
    try:
        return json.loads(val)
    except (TypeError, json.JSONDecodeError):
        return {}

async def run_backtest_cycle(cdp, bt, window, wait=6.0):
    ok = await set_date_preset(cdp, window)
    if not ok:
        return {"error": f"date_preset_failed:{window}"}
    await bt.run_strategy(STRATEGY)
    await asyncio.sleep(wait)
    summary = await bt.get_performance_summary()
    trades = await bt.get_trade_list()
    body = await get_body_metrics(cdp)
    parsed_trade_count = int(to_num(body.get("totalTradesText", 0)))
    trade_count = len(trades) if isinstance(trades, list) and trades else parsed_trade_count
    return {
        **summary,
        "trade_count_actual": trade_count,
        "trade_count_source": "trade_list" if isinstance(trades, list) and trades else "overview_text",
        "trades": trades if isinstance(trades, list) else [],
        "win_rate_pct": body.get("winRate", "N/A"),
        "max_dd_pct": body.get("maxDrawdownPct", "N/A"),
        "total_trades_text": body.get("totalTradesText", "N/A"),
        "window": window,
    }

def compute_risk_of_ruin(wr, aw, al, risk_pct, account=50000.0):
    lr = 1.0 - wr
    rr = abs(aw / al) if al != 0 else 0.0
    ev = wr * aw + lr * al
    edge = ev / abs(al) if al != 0 else 0.0
    kelly = max(0.0, (wr - (lr / rr)) if rr > 0 else 0.0)
    units = max(1.0 / risk_pct, 2.0) if risk_pct > 0 else 100.0
    ror = ((1.0 - edge) / (1.0 + edge)) ** units if edge > 0 else 1.0
    mc = int(math.ceil(math.log(0.01) / math.log(lr))) if 0 < lr < 1 else 100
    dd = 1.0 - (1.0 - risk_pct) ** mc
    eq = account * (1.0 - risk_pct) ** mc
    safe = ror < 0.01 and eq > account * 0.3
    return {
        "wr": round(wr, 4), "aw": round(aw, 2), "al": round(al, 2),
        "rr": round(rr, 3), "ev": round(ev, 2), "kelly": round(kelly, 4),
        "ror": round(ror, 6), "max_cons": mc, "dd_cons_pct": round(dd * 100, 1),
        "eq_post_cons": round(eq, 2), "safe": safe,
        "risk_pct": round(risk_pct * 100, 1),
    }

def compute_risk_table(trades):
    if not trades:
        return []
    wins = [t.get("net_pnl", 0) for t in trades if t.get("net_pnl", 0) > 0]
    losses = [t.get("net_pnl", 0) for t in trades if t.get("net_pnl", 0) < 0]
    if not wins or not losses:
        return []
    wr = len(wins) / len(trades)
    aw = sum(wins) / len(wins)
    al = sum(losses) / len(losses)
    return [compute_risk_of_ruin(wr, aw, al, r) for r in
            [0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]]


async def safe_write(settings, strategy, values, retries=3):
    """Write settings with retry and dialog-reopen on failure."""
    for attempt in range(retries):
        try:
            await settings.list_fields(strategy)
            await asyncio.sleep(0.5)
            await settings.write(strategy, values)
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            if attempt < retries - 1:
                print(f"    [retry {attempt+1}] settings write: {e}")
                await asyncio.sleep(1.0)
            else:
                print(f"    [FAILED] settings write after {retries} retries: {e}")
                return False

async def apply_candidate(settings, candidate):
    config = candidate.get("settings", {})
    if not config:
        return True
    ok = await safe_write(settings, STRATEGY, config)
    if not ok:
        candidate.setdefault("warnings", []).append("failed_to_reapply_settings")
    return ok


async def audit():
    cdp = CDPConnection(debug_port=DEBUG_PORT)
    await cdp.connect()
    try:
        return await _audit_connected(cdp)
    finally:
        await cdp.disconnect()

async def _audit_connected(cdp):
    recon = json.loads(Path(__file__).parents[1].joinpath("recon_findings.json").read_text())
    settings = TVSettingsController(cdp, recon, allow_unverified=True)
    pine = TVPineScriptController(cdp, recon, allow_unverified=True)
    bt = TVBacktestController(cdp, recon, allow_unverified=True)
    t0 = datetime.now(timezone.utc)
    print("=" * 70)
    print(f"GT_VP v9.9.6 AUDIT | ETHUSD.P 5m | {t0.isoformat()}")
    print("=" * 70)

    print("\n[PHASE 0] Enable Strategy & Baseline")
    source = await pine.read(STRATEGY)
    source = source.replace(
        'enable_strategy = input.bool(false, "Enable Strategy Orders"',
        'enable_strategy = input.bool(true, "Enable Strategy Orders"',
    )
    await pine.write(STRATEGY, source)
    cr = await pine.compile(STRATEGY)
    print(f"  Enabled: {cr.get('success')}")
    await asyncio.sleep(2.0)

    print("  Baseline 1Y...")
    b_train = await run_backtest_cycle(cdp, bt, "12M", wait=6.0)
    print(f"  Train: PF={b_train.get('profit_factor')} DD%={b_train.get('max_dd_pct')} DD$={b_train.get('max_drawdown')} T={b_train.get('trade_count_actual')} WR={b_train.get('win_rate_pct')}%")

    print("  Baseline 6M...")
    b_val = await run_backtest_cycle(cdp, bt, "6M", wait=5.0)
    print(f"  Val:   PF={b_val.get('profit_factor')} DD%={b_val.get('max_dd_pct')}")

    print("  Baseline YTD...")
    b_hld = await run_backtest_cycle(cdp, bt, "YTD", wait=5.0)
    print(f"  Hld:   PF={b_hld.get('profit_factor')} DD%={b_hld.get('max_dd_pct')}")

    all_results = []

    print("\n[PHASE 1] Parameter Sweep (1Y train)")
    print("  Signal Mode x Strictness...")
    for mode in ["All Signals", "Reversal Only", "Structure Only"]:
        for strictness in ["Loose", "Normal", "Strict"]:
            candidate_settings = {"Trade Signal Mode": mode, "Entry Strictness": strictness}
            await safe_write(settings, STRATEGY, candidate_settings)
            await asyncio.sleep(0.5)
            r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
            r["label"] = f"mode={mode},strict={strictness}"
            r["settings"] = candidate_settings
            all_results.append(r)
            print(f"    {r['label']}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')} WR={r.get('win_rate_pct')}%")

    print("  R:R sweep...")
    for rr in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        candidate_settings = {"Fallback R:R Target": rr}
        await safe_write(settings, STRATEGY, candidate_settings)
        await asyncio.sleep(0.5)
        r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
        r["label"] = f"RR={rr}"
        r["settings"] = candidate_settings
        all_results.append(r)
        print(f"    RR={rr}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')}")

    print("  ATR Stop sweep...")
    for atr in [0.5, 0.75, 1.0, 1.5, 2.0]:
        candidate_settings = {"ATR Stop Multiplier": atr}
        await safe_write(settings, STRATEGY, candidate_settings)
        await asyncio.sleep(0.5)
        r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
        r["label"] = f"ATR={atr}"
        r["settings"] = candidate_settings
        all_results.append(r)
        print(f"    ATR={atr}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')}")

    print("  Timeout sweep...")
    for tb in [10, 20, 30, 50]:
        candidate_settings = {"Timeout Bars": tb}
        await safe_write(settings, STRATEGY, candidate_settings)
        await asyncio.sleep(0.5)
        r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
        r["label"] = f"Timeout={tb}"
        r["settings"] = candidate_settings
        all_results.append(r)
        print(f"    Timeout={tb}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')}")

    print("  MA Filter sweep...")
    for mf in ["Off", "2-MA (Fast/Medium)", "3-MA (All Aligned)"]:
        candidate_settings = {"MA Filter Mode": mf}
        await safe_write(settings, STRATEGY, candidate_settings)
        await asyncio.sleep(0.5)
        r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
        r["label"] = f"MAFilter={mf}"
        r["settings"] = candidate_settings
        all_results.append(r)
        print(f"    Filter={mf}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')}")

    print("  MA Type sweep...")
    for mt in ["EMA", "WMA", "HMA", "SMA"]:
        candidate_settings = {"MA Type": mt}
        await safe_write(settings, STRATEGY, candidate_settings)
        await asyncio.sleep(0.5)
        r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
        r["label"] = f"MA={mt}"
        r["settings"] = candidate_settings
        all_results.append(r)
        print(f"    MA={mt}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')}")

    print("  MA Combo sweep...")
    for combo in AGGRESSIVE_MA_COMBOS:
        candidate_settings = dict(combo)
        await safe_write(settings, STRATEGY, candidate_settings)
        await asyncio.sleep(0.5)
        r = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
        r["label"] = f"MA({combo['Fast MA Length']},{combo['Medium MA Length']},{combo['Slow MA Length']})"
        r["settings"] = candidate_settings
        all_results.append(r)
        print(f"    {r['label']}: PF={r.get('profit_factor')} DD%={r.get('max_dd_pct')} T={r.get('trade_count_actual')}")

    total = len(all_results)
    print(f"\n  Total tested: {total}")

    print("\n[PHASE 2] Filter & Rank")
    valid, rejected = [], []
    for r in all_results:
        pf = to_num(r.get("profit_factor", 0))
        dd = to_num(r.get("max_dd_pct", 100))
        tc = r.get("trade_count_actual", 0)
        reasons = []
        if r.get("error"):
            reasons.append(r["error"])
        if is_missing(r.get("profit_factor")):
            reasons.append("missing_profit_factor")
        if is_missing(r.get("max_dd_pct")):
            reasons.append("missing_drawdown_pct")
        if pf < MIN_PF:
            reasons.append(f"PF={pf:.2f}<{MIN_PF}")
        if dd > MAX_DD_PCT:
            reasons.append(f"DD%={dd:.1f}>{MAX_DD_PCT}")
        if tc < MIN_TRADES:
            reasons.append(f"T={tc}<{MIN_TRADES}")
        if reasons:
            r["reject"] = reasons
            rejected.append(r)
        else:
            valid.append(r)
    print(f"  Valid: {len(valid)} | Rejected: {len(rejected)}")

    def score(r):
        pf = to_num(r.get("profit_factor", 0))
        dd = max(to_num(r.get("max_dd_pct", 100)), 0.1)
        tc = r.get("trade_count_actual", 1)
        wr = to_num(r.get("win_rate_pct", 0))
        return pf * math.sqrt(tc) / dd * (wr / 100 if wr > 0 else 1)

    valid.sort(key=score, reverse=True)

    print("\n[PHASE 3] Validation (6M)")
    top_n = min(6, len(valid))
    validated = []
    for i in range(top_n):
        r = valid[i]
        print(f"  Candidate {i+1}: {r['label']}")
        if not await apply_candidate(settings, r):
            r["validation"] = {"error": "failed_to_reapply_settings"}
            r["divergence"] = None
            r["val_pass"] = False
            print("    Val: skipped, failed to re-apply candidate settings")
            continue
        val_r = await run_backtest_cycle(cdp, bt, "6M", wait=5.0)
        vpf = to_num(val_r.get("profit_factor", 0))
        tpf = to_num(r.get("profit_factor", 0))
        div = abs(tpf - vpf) / tpf * 100 if tpf > 0 else 100
        passed = div <= MAX_VAL_DIVERGENCE
        print(f"    Val: PF={val_r.get('profit_factor')} DD%={val_r.get('max_dd_pct')} Div={div:.1f}% {'PASS' if passed else 'FAIL'}")
        r["validation"] = val_r
        r["divergence"] = round(div, 2)
        r["val_pass"] = passed
        if passed:
            validated.append(r)
    print(f"\n  Passed: {len(validated)}/{top_n}")

    print("\n[PHASE 4] Holdout (YTD)")
    if validated:
        best = validated[0]
        await apply_candidate(settings, best)
        hld = await run_backtest_cycle(cdp, bt, "YTD", wait=5.0)
        best["holdout"] = hld
        print(f"  Holdout: PF={hld.get('profit_factor')} DD%={hld.get('max_dd_pct')} T={hld.get('trade_count_actual')}")

    print("\n[PHASE 5] Sensitivity")
    sens = []
    if validated:
        await apply_candidate(settings, validated[0])
        fields = await settings.list_fields(STRATEGY)
        tested = 0
        for f in fields:
            if tested >= 3:
                break
            name = f.get("name", "")
            if f.get("type") != "number":
                continue
            try:
                cv = float(f.get("current_value", ""))
            except (ValueError, TypeError):
                continue
            if cv <= 0:
                continue
            tpf = to_num(validated[0].get("profit_factor", 0))
            print(f"  Testing {name} ({cv}):")
            for mult in [0.85, 1.15]:
                nv = int(round(cv * mult)) if cv == int(cv) else round(cv * mult, 2)
                await safe_write(settings, STRATEGY, {name: nv})
                await asyncio.sleep(0.5)
                d = await run_backtest_cycle(cdp, bt, "12M", wait=5.0)
                pf_d = to_num(d.get("profit_factor", 0))
                sens.append({"param": name, "perturbation": f"{int((mult-1)*100):+d}%", "pf": pf_d})
                print(f"    {name}@{(mult-1)*100:+.0f}%: PF={pf_d:.2f}")
            await safe_write(settings, STRATEGY, {name: cv})
            tested += 1

    print("\n[PHASE 6] Risk Analysis")
    risk_table = []
    for candidate in (validated[:3] if validated else valid[:3]):
        trades = candidate.get("trades", [])
        if trades:
            rt = compute_risk_table(trades)
            for e in rt:
                e["label"] = candidate.get("label", "?")
            risk_table.extend(rt)

    safe = [r for r in risk_table if r["safe"]]
    max_safe = safe[-1]["risk_pct"] / 100 if safe else 0.01

    for r in risk_table[:24]:
        flag = "SAFE" if r["safe"] else "DANGER"
        print(f"  {r['risk_pct']:5.1f}% | ROR={r['ror']:.6f} | Cons={r['max_cons']} | DD={r['dd_cons_pct']:.0f}% | Eq={r['eq_post_cons']:.0f} | {flag}")

    t1 = datetime.now(timezone.utc)
    elapsed = (t1 - t0).total_seconds()

    warnings = []
    if not validated:
        warnings.append("NO_CONFIG_PASSED_VALIDATION")
    if len(validated) < 3:
        warnings.append(f"LOW_VALIDATION_COUNT={len(validated)}")
    base_pf = to_num(b_train.get("profit_factor", 0)) if b_train else 0
    hld_pf = to_num(b_hld.get("profit_factor", 0)) if b_hld else 0
    if base_pf > 0 and hld_pf > 0 and abs(base_pf - hld_pf) / base_pf > 0.5:
        warnings.append(f"BASELINE_OVERFIT_RISK: train PF={base_pf:.2f} vs holdout PF={hld_pf:.2f}")

    report = {
        "metadata": {"strategy": STRATEGY, "symbol": "ETHUSD.P", "timeframe": "5m",
                     "started": t0.isoformat(), "completed": t1.isoformat(),
                     "elapsed_sec": round(elapsed, 1), "commission_bps": int(COMMISSION * 10000),
                     "slippage_bps": int(SLIPPAGE * 10000)},
        "baseline": {"train": {k: v for k, v in b_train.items() if k != "trades"},
                     "validation": {k: v for k, v in b_val.items() if k != "trades"},
                     "holdout": {k: v for k, v in b_hld.items() if k != "trades"}},
        "summary": {"total_tested": total, "valid_count": len(valid),
                    "rejected_count": len(rejected), "validation_passed": len(validated)},
        "rankings": [{
            "rank": i + 1, "config": r.get("label"),
            "settings": r.get("settings", {}),
            "train_pf": to_num(r.get("profit_factor", 0)),
            "train_dd_pct": to_num(r.get("max_dd_pct", 0)),
            "train_dd_dollar": r.get("max_drawdown"),
            "train_trades": r.get("trade_count_actual"),
            "train_wr_pct": to_num(r.get("win_rate_pct", 0)),
            "train_sharpe": to_num(r.get("sharpe", 0)),
            "val_pf": to_num(r.get("validation", {}).get("profit_factor", 0)),
            "val_dd_pct": to_num(r.get("validation", {}).get("max_dd_pct", 0)),
            "divergence_pct": r.get("divergence"),
            "val_pass": r.get("val_pass"),
            "holdout_pf": to_num(r.get("holdout", {}).get("profit_factor", 0)) if r.get("holdout") else None,
            "holdout_dd_pct": to_num(r.get("holdout", {}).get("max_dd_pct", 0)) if r.get("holdout") else None,
        } for i, r in enumerate(validated if validated else valid[:10])],
        "rejected_top20": [{
            "config": r.get("label"), "reasons": r.get("reject"),
            "settings": r.get("settings", {}),
            "pf": to_num(r.get("profit_factor", 0)),
            "dd_pct": to_num(r.get("max_dd_pct", 0)),
            "trades": r.get("trade_count_actual"),
        } for r in rejected[:20]],
        "sensitivity": sens,
        "risk_analysis": {"recommended_max_risk_pct": round(max_safe * 100, 1),
                          "safe_levels": [r["risk_pct"] for r in safe],
                          "all_risk_levels": risk_table[:24]},
        "warnings": warnings,
    }

    out_dir = Path(__file__).parents[1] / "docs" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gt_vp_audit_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))

    print(f"\n{'='*70}")
    print(f"AUDIT COMPLETE ({elapsed:.0f}s) | Report: {out_path}")
    print(f"{'='*70}")
    print(f"\nTested: {total} | Valid: {len(valid)} | Rejected: {len(rejected)} | Validated: {len(validated)}")

    if report["rankings"]:
        print("\nTop 3 Ranked Configurations:")
        for r in report["rankings"][:3]:
            print(f"  #{r['rank']}: {r['config']}")
            print(f"    Train PF={r['train_pf']:.2f} DD={r['train_dd_pct']:.1f}% T={r['train_trades']} WR={r['train_wr_pct']:.1f}% Sharpe={r['train_sharpe']:.2f}")
            if r["val_pf"] > 0:
                print(f"    Val   PF={r['val_pf']:.2f} DD={r['val_dd_pct']:.1f}% Div={r['divergence_pct']:.1f}% {'PASS' if r['val_pass'] else 'FAIL'}")
            if r.get("holdout_pf"):
                print(f"    Hld   PF={r['holdout_pf']:.2f} DD={r['holdout_dd_pct']:.1f}%")

    if rejected:
        print(f"\nRejected {len(rejected)} configs. Sample reasons:")
        for r in rejected[:5]:
            print(f"  {r['config']}: {', '.join(r['reject'])}")

    print(f"\nRecommended Max Risk/Trade: {report['risk_analysis']['recommended_max_risk_pct']:.0f}%")
    if warnings:
        print("\n!! WARNINGS:")
        for w in warnings:
            print(f"  * {w}")

    if sens:
        print("\nSensitivity Results:")
        for s in sens:
            print(f"  {s['param']} {s['perturbation']}: PF={s['pf']:.2f}")

    return report

if __name__ == "__main__":
    asyncio.run(audit())
