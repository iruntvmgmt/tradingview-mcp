#!/usr/bin/env python3
"""End-to-end verification of Phase 3-4 fixes against live TV Desktop.

Tests:
  1. scroll_and_collect_text — reads Pine Editor source (should get >72 lines)
  2. extract_innertext_map — extracts Strategy Tester metrics
  3. click_at_text — navigates Strategy Tester sub-tabs
  4. screenshot — captures via CDP Page.captureScreenshot
"""

import asyncio
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.services.cdp_connection import CDPConnection
from core.services.dom_utils import DomUtils


async def main():
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()
    dom = DomUtils(cdp)
    results = {}

    # ── Test 1: scroll_and_collect_text ──────────────────────
    print("=" * 60)
    print("TEST 1: scroll_and_collect_text (Pine Editor full source)")
    print("=" * 60)

    # Ensure Pine Editor is open
    js_open = """(function() {
        var ed = document.querySelector('#pine-editor-dialog');
        if (ed && ed.offsetParent !== null) return 'already_open';
        // Try clicking Pine Editor tab
        var tab = document.querySelector('[class*="tab"][class*="isActive"]');
        return tab ? 'tab_found' : 'no_tab';
    })()"""
    r = await cdp.execute_js(js_open)
    print(f"  Editor state: {r.get('result', {}).get('value')}")

    scrollable_sels = [".monaco-scrollable-element.editor-scrollable"]
    textarea_sels = [".inputarea.monaco-mouse-cursor-text"]

    # Focus the editor first
    monaco_sels = [".monaco-editor.pine-editor-monaco"]
    editor_found = await dom.resolve_selector(monaco_sels, timeout=3.0)
    if editor_found:
        await dom.click(monaco_sels)
        await asyncio.sleep(0.3)

    source = await dom.scroll_and_collect_text(
        scrollable_sels, textarea_sels, pages=8, delay=0.35
    )
    lines = source.count("\n") + 1 if source else 0
    print(f"  Lines captured: {lines}")
    print(f"  Chars captured: {len(source)}")
    print(f"  First 120 chars: {source[:120] if source else 'EMPTY'}")

    results["scroll_and_collect"] = {
        "lines": lines,
        "chars": len(source),
        "status": "PASS" if lines > 72 else "PARTIAL" if lines > 0 else "FAIL",
        "note": "Expected >72 lines (previous viewport-only limit was 72)"
    }

    # ── Test 2: extract_innertext_map ────────────────────────
    print("\n" + "=" * 60)
    print("TEST 2: extract_innertext_map (Strategy Tester metrics)")
    print("=" * 60)

    labels = {
        "sharpe": ["Sharpe ratio", "Sharpe"],
        "total_trades": ["Total trades", "Total closed trades"],
        "win_rate": ["Percent Profitable", "Win Rate"],
        "net_profit": ["Net Profit", "Strategy outperformance"],
        "max_drawdown": ["Max drawdown"],
        "cagr": ["CAGR"],
        "avg_pnl": ["Average PnL", "Avg Trade"],
        "return_pct": ["Return on initial capital"],
        "profit_factor": ["Profit Factor", "Profit factor"],
    }

    metrics = await dom.extract_innertext_map(labels, timeout=5.0)
    found_keys = list(metrics.keys())
    print(f"  Metrics extracted: {len(found_keys)}")
    for k, v in metrics.items():
        print(f"    {k}: {v}")

    results["extract_innertext_map"] = {
        "keys_found": len(found_keys),
        "keys": found_keys,
        "status": "PASS" if len(found_keys) >= 3 else "PARTIAL" if len(found_keys) >= 1 else "FAIL",
        "note": "Expected at least 3 metrics from Strategy Tester panel"
    }

    # ── Test 3: click_at_text (sub-tab navigation) ───────────
    print("\n" + "=" * 60)
    print("TEST 3: click_at_text (Strategy Tester sub-tab navigation)")
    print("=" * 60)

    # Try clicking "Overview" sub-tab
    clicked = await dom.click_at_text("Overview", exact=True, timeout=3.0)
    print(f"  Click 'Overview': {'✅' if clicked else '❌ not found'}")

    # Read text around the Overview area to see if it changed
    js = """(function() {
        var body = document.body.innerText || '';
        var idx = body.indexOf('Trades analysis');
        if (idx === -1) return 'Trades analysis not found';
        return body.substring(idx, idx + 200);
    })()"""
    r = await cdp.execute_js(js)
    section = r.get("result", {}).get("value", "")
    print(f"  Trades analysis section: {section[:150]}...")

    results["click_at_text"] = {
        "clicked": clicked,
        "status": "PASS" if clicked else "PARTIAL",
        "note": "Expected to find and click 'Overview' sub-tab in Strategy Tester"
    }

    # ── Test 4: screenshot ────────────────────────────────────
    print("\n" + "=" * 60)
    print("TEST 4: Screenshot (CDP Page.captureScreenshot)")
    print("=" * 60)

    try:
        img_result = await cdp._send_command("Page.captureScreenshot", {
            "format": "png",
            "fromSurface": True,
        })
        data = img_result.get("data", "")
        img_bytes = len(data) if data else 0
        print(f"  Screenshot data length: {img_bytes} chars (base64)")
        import base64
        raw = base64.b64decode(data) if data else b""
        print(f"  Decoded PNG size: {len(raw)} bytes")
        results["screenshot"] = {
            "status": "PASS" if len(raw) > 1000 else "FAIL",
            "size_bytes": len(raw),
            "note": "Expected >1KB PNG image data"
        }
    except Exception as e:
        print(f"  ❌ Screenshot failed: {e}")
        results["screenshot"] = {
            "status": "FAIL",
            "error": str(e)
        }

    # ── Summary ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    for name, r in results.items():
        icon = "✅" if r["status"] == "PASS" else "⚠️" if r["status"] == "PARTIAL" else "❌"
        print(f"  {icon} {name}: {r['status']} — {r.get('note', '')}")

    await cdp.disconnect()

    # Write results to file
    results_path = Path(__file__).resolve().parent.parent / "docs" / "qa" / "verification-results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
