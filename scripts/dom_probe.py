"""Deep DOM probe for TradingView Desktop.

Connects via CDP and inspects the live page DOM to discover the actual
CSS selectors for key UI panels.  Run this with each panel open to
capture its structure.

Usage:
  python scripts/dom_probe.py                    # one-shot full dump
  python scripts/dom_probe.py --panel symbol      # probe just symbol search
  python scripts/dom_probe.py --interactive       # guided panel-by-panel
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services.cdp_connection import CDPConnection


# Interesting CSS attributes/classes to search for in the DOM
INTERESTING_PATTERNS = [
    "symbol", "search", "ticker", "market",
    "timeframe", "resolution", "interval",
    "chart", "canvas", "pane",
    "indicator", "study", "pine", "editor", "code",
    "backtest", "strategy", "tester", "trade",
    "alert", "notification", "alarm",
    "drawing", "toolbar", "trendline", "fib", "annotation",
    "order", "ticket", "panel", "position", "entry",
    "replay", "playback", "timeline",
    "toolbar", "button-bar", "action",
    "dialog", "modal", "popup", "dropdown",
    "input", "textbox", "field",
    "menu", "context",
]


async def dump_dom_structure(cdp, depth: int = 3) -> list[dict]:
    """Recursively walk the DOM tree and return interesting nodes."""
    js = f"""
    (function walk(node, depth) {{
        if (depth <= 0) return [];
        const results = [];
        const tag = node.tagName ? node.tagName.toLowerCase() : '';
        const id = node.id || '';
        const className = (node.className && typeof node.className === 'string')
            ? node.className : '';
        const role = node.getAttribute('role') || '';
        const ariaLabel = node.getAttribute('aria-label') || '';
        const dataAttr = node.getAttribute('data-name')
            || node.getAttribute('data-value')
            || node.getAttribute('data-symbol') || '';

        const text = (node.childNodes.length === 1 && node.childNodes[0].nodeType === 3)
            ? node.textContent.trim().slice(0, 60) : '';

        const combined = (tag + ' ' + id + ' ' + className + ' ' + role
            + ' ' + ariaLabel + ' ' + dataAttr + ' ' + text).toLowerCase();

        const interesting = {json.dumps(INTERESTING_PATTERNS)};
        const matched = interesting.filter(p => combined.includes(p));

        if (matched.length > 0 || (id || (role && role !== 'none'))) {{
            const rect = node.getBoundingClientRect();
            const visible = rect.width > 0 && rect.height > 0;
            results.push({{
                tag: tag,
                id: id,
                className: className.slice(0, 120),
                role: role,
                ariaLabel: ariaLabel.slice(0, 80),
                dataAttr: dataAttr.slice(0, 80),
                text: text.slice(0, 80),
                visible: visible,
                rect: {{w: Math.round(rect.width), h: Math.round(rect.height)}},
                matchedKeywords: matched.slice(0, 5),
                children: walk(node, depth - 1),
            }});
        }}
        for (const child of node.children) {{
            results.push(...walk(child, depth - 1));
        }}
        return results;
    }}(document.body, {depth}))
    """
    result = await cdp.execute_js(js)
    return result.get("result", {}).get("value", [])


async def probe_symbol_search(cdp) -> str | None:
    """Find the symbol search input and its container."""
    probes = [
        "document.querySelector('input[class*=\"symbol\"]')?.closest('div')?.outerHTML?.slice(0, 500)",
        "document.querySelector('input[placeholder*=\"symbol\"]')?.closest('div')?.outerHTML?.slice(0, 500)",
        "document.querySelector('[class*=\"search\"] input')?.closest('div')?.outerHTML?.slice(0, 500)",
        "document.querySelector('[class*=\"ticker\"]')?.outerHTML?.slice(0, 500)",
        "document.querySelector('[class*=\"symbol\"]')?.outerHTML?.slice(0, 500)",
    ]
    for js in probes:
        result = await cdp.execute_js(js)
        html = result.get("result", {}).get("value")
        if html and len(html) > 20:
            return html[:500]
    return None


async def probe_timeframe_buttons(cdp) -> str | None:
    """Find timeframe/resolution buttons."""
    probes = [
        "Array.from(document.querySelectorAll('button')).filter(b => /\\d+[smhdw]/.test(b.textContent)).map(b => b.outerHTML.slice(0, 200)).join('\\n')",
        "document.querySelector('[class*=\"resolution\"]')?.outerHTML?.slice(0, 500)",
        "document.querySelector('[class*=\"timeframe\"]')?.outerHTML?.slice(0, 500)",
    ]
    for js in probes:
        result = await cdp.execute_js(js)
        val = result.get("result", {}).get("value")
        if val and len(val) > 20:
            return val[:500]
    return None


async def probe_open_panels(cdp) -> list[dict]:
    """Find any currently-open dialogs/modals/panels."""
    js = """
    (() => {
        const results = [];
        // Look for open dialogs
        document.querySelectorAll('[role=\"dialog\"], [class*=\"dialog\"], [class*=\"modal\"], [class*=\"popup\"]')
            .forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0) {
                    results.push({
                        tag: el.tagName,
                        id: el.id,
                        class: (el.className || '').slice(0, 100),
                        role: el.getAttribute('role') || '',
                        rect: {w: Math.round(rect.width), h: Math.round(rect.height)},
                        html: el.outerHTML.slice(0, 300),
                    });
                }
            });
        return results;
    })()
    """
    result = await cdp.execute_js(js)
    return result.get("result", {}).get("value", [])


async def get_full_page_structure(cdp) -> str:
    """Get a text outline of the full page structure."""
    js = """
    (function outline(node, depth) {
        if (depth > 4 || !node || !node.tagName) return '';
        const tag = node.tagName.toLowerCase();
        const id = node.id ? '#' + node.id : '';
        const cls = (node.className && typeof node.className === 'string')
            ? '.' + node.className.trim().split(/\\s+/).slice(0, 3).join('.') : '';
        const visible = node.getBoundingClientRect ? (node.getBoundingClientRect().width > 0) : false;
        const indent = '  '.repeat(depth);
        let result = indent + tag + id + cls + (visible ? '' : ' [hidden]') + '\\n';
        for (const child of node.children) {
            result += outline(child, depth + 1);
        }
        return result;
    })(document.body, 0)
    """
    result = await cdp.execute_js(js)
    return result.get("result", {}).get("value", "")


@click.command()
@click.option("--port", default=8315)
@click.option("--interactive", is_flag=True, help="Guide through each panel")
@click.option("--panel", type=click.Choice(["symbol", "timeframe", "all"]), default="all")
def main(port: int, interactive: bool, panel: str):
    """Probe TV Desktop DOM to discover actual CSS selectors."""
    async def _run():
        cdp = CDPConnection(debug_port=port)
        await cdp.connect()

        try:
            if interactive:
                await _interactive_mode(cdp)
            else:
                await _auto_probe(cdp, panel)
        finally:
            await cdp.disconnect()

    asyncio.run(_run())


async def _auto_probe(cdp, panel: str):
    click.echo("\n=== DOM Structure Probe ===\n")

    # Full page outline
    click.echo("--- Page Structure (top-level) ---")
    outline = await get_full_page_structure(cdp)
    # Only show first 200 lines
    for line in outline.split("\\n")[:200]:
        click.echo(line)

    # Interesting elements
    click.echo("\n--- Interesting Elements ---")
    elements = await dump_dom_structure(cdp, depth=2)
    for el in elements[:50]:
        cls_short = el.get("className", "")[:80]
        click.echo(f"  <{el['tag']}> id={el['id']!r} class={cls_short!r}")
        if el.get("matchedKeywords"):
            click.echo(f"    keywords: {el['matchedKeywords']}")
        if el.get("ariaLabel"):
            click.echo(f"    aria-label: {el['ariaLabel']}")
        if el.get("text"):
            click.echo(f"    text: {el['text']}")

    # Symbol search
    click.echo("\n--- Symbol Search Probe ---")
    html = await probe_symbol_search(cdp)
    if html:
        click.echo(f"  Found: {html[:300]}")
    else:
        click.echo("  No symbol search element found (panel may not be open)")

    # Timeframe buttons
    click.echo("\n--- Timeframe Probe ---")
    html = await probe_timeframe_buttons(cdp)
    if html:
        click.echo(f"  Found: {html[:300]}")
    else:
        click.echo("  No timeframe buttons found")

    # Open panels
    click.echo("\n--- Open Panels/Dialogs ---")
    panels = await probe_open_panels(cdp)
    if panels:
        for p in panels:
            click.echo(f"  <{p['tag']}> class={p['class'][:80]!r} role={p['role']!r}")
            click.echo(f"    HTML: {p['html'][:200]}")
    else:
        click.echo("  No open dialogs/panels")


async def _interactive_mode(cdp):
    """Walk through each panel one at a time so the user can open it."""
    panels = [
        ("Symbol Search", "Click the symbol search field to open it", probe_symbol_search),
        ("Timeframe Selector", "Click the timeframe dropdown to open it", probe_timeframe_buttons),
        ("Pine Editor", "Open the Pine Editor (Pine Editor tab at bottom)", None),
        ("Strategy Tester", "Open the Strategy Tester tab", None),
        ("Alert Creation", "Right-click chart → Add Alert to open the dialog", None),
        ("Alert List", "Open the alerts panel/manager", None),
        ("Drawing Toolbar", "Click any drawing tool to activate the toolbar", None),
        ("Order Panel", "Open the order/ trading panel", None),
        ("Replay Toolbar", "Enter Replay mode to show the toolbar", None),
    ]

    for name, instruction, probe_fn in panels:
        click.echo(f"\n{'=' * 60}")
        click.echo(f"Panel: {name}")
        click.echo(f"Action: {instruction}")
        input("  Press Enter when the panel is open...")

        if probe_fn:
            result = await probe_fn(cdp)
            if result:
                click.echo(f"  Found: {result[:400]}")
            else:
                click.echo(f"  No result from probe")
        else:
            # Generic: dump any open dialogs + try class* pattern
            dialogs = await probe_open_panels(cdp)
            if dialogs:
                click.echo(f"  Found {len(dialogs)} open dialog(s):")
                for d in dialogs:
                    click.echo(f"    <{d['tag']}> class={d['class'][:100]!r}")
                    click.echo(f"    HTML snippet: {d['html'][:250]}")
            # Also dump body classes for context
            result = await cdp.execute_js(
                "document.body.className"
            )
            body_cls = result.get("result", {}).get("value", "")
            click.echo(f"  body classes: {str(body_cls)[:200]}")

        click.echo(f"  ✓ {name} probed")


if __name__ == "__main__":
    main()
