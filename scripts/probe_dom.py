#!/usr/bin/env python3
"""Deep DOM probe: Read full Pine Script source and Strategy Tester data."""
import asyncio, sys, json
sys.path.insert(0, '.')
from core.services.cdp_connection import CDPConnection

async def main():
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()

    # ── 1. Read full Pine source ──
    js = """
    (function() {
        var result = {};

        // Try reading all text from the lines-content div (Monaco renders all lines here)
        var linesContent = document.querySelector('.lines-content.monaco-editor-background');
        if (linesContent) {
            result.fullText = linesContent.textContent || '';
            result.linesFromContent = result.fullText.split('\\n').length;
        }

        // Also get the editor viewport info
        var scrollable = document.querySelector('.monaco-scrollable-element.editor-scrollable');
        if (scrollable) {
            result.scrollHeight = scrollable.scrollHeight;
            result.clientHeight = scrollable.clientHeight;
        }

        // Count view-lines
        var viewLines = document.querySelectorAll('.view-line');
        result.viewLineCount = viewLines.length;

        // Get textarea value
        var editor = document.querySelector('#pine-editor-dialog');
        if (editor) {
            var textarea = editor.querySelector('textarea');
            if (textarea) {
                result.textareaLen = (textarea.value || '').length;
            }
        }

        return result;
    })()
    """
    r = await cdp.execute_js(js.strip())
    val = r.get("result", {}).get("value", {})
    print("=== Pine Editor Probe ===")
    print(f"  linesFromContent: {val.get('linesFromContent', 0)}")
    print(f"  viewLineCount: {val.get('viewLineCount', 0)}")
    print(f"  scrollHeight: {val.get('scrollHeight', 0)}")
    print(f"  clientHeight: {val.get('clientHeight', 0)}")
    print(f"  textareaLen: {val.get('textareaLen', 0)}")

    if val.get("fullText"):
        full = val["fullText"]
        print(f"\n=== Full Source ({len(full)} chars) ===")
        print(full[:7000])

    # ── 2. Probe Strategy Tester ──
    js2 = """
    (function() {
        var result = {};

        // Find bottom panel / strategy tester
        var bottomPanel = document.querySelector('.bottom-window, [class*="bottom"], [class*="strategy"], [class*="tester"], [class*="backtest"]');
        result.bottomPanelFound = !!bottomPanel;

        if (bottomPanel) {
            result.bottomPanelClass = bottomPanel.className;
            result.bottomPanelText = (bottomPanel.textContent || '').substring(0, 500);
        }

        // Try to find all visible panels
        var allPanels = [];
        var panelSelectors = [
            '.strategy-tester', '.backtesting-report', '.report-content',
            '.bottom-window', '.chart-bottom-panel',
            '[data-name="strategy-tester"]', '[data-role="strategy-tester"]'
        ];
        for (var i = 0; i < panelSelectors.length; i++) {
            var el = document.querySelector(panelSelectors[i]);
            if (el && el.offsetParent !== null) {
                allPanels.push({selector: panelSelectors[i], className: el.className, visible: true});
            } else if (el) {
                allPanels.push({selector: panelSelectors[i], className: el.className, visible: false});
            }
        }
        result.allPanels = allPanels;

        // Look for the tabs at the bottom
        var bottomTabs = document.querySelectorAll('.bottom-window .tab, [class*="bottom"] [class*="tab"]');
        result.bottomTabs = [];
        for (var i = 0; i < bottomTabs.length; i++) {
            result.bottomTabs.push({
                text: bottomTabs[i].textContent?.trim(),
                active: bottomTabs[i].getAttribute('aria-selected') === 'true',
                className: bottomTabs[i].className
            });
        }

        return result;
    })()
    """
    r2 = await cdp.execute_js(js2.strip())
    val2 = r2.get("result", {}).get("value", {})
    print(f"\n=== Strategy Tester Probe ===")
    print(json.dumps(val2, indent=2, default=str))

    await cdp.disconnect()

asyncio.run(main())
