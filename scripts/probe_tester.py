#!/usr/bin/env python3
"""Targeted probe: Find Strategy Tester data in the bottom panel."""
import asyncio, sys, json
sys.path.insert(0, '.')
from core.services.cdp_connection import CDPConnection

async def main():
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()

    # Look for Strategy Tester specific elements
    js = """(function() {
        var result = {};

        // Search for Strategy Tester summary text
        var allText = document.body.innerText || '';
        
        // Look for known Strategy Tester labels
        var labels = ['Net Profit', 'Profit Factor', 'Win Rate', 'Percent Profitable',
                       'Sharpe', 'Sortino', 'Max Drawdown', 'Total Closed Trades',
                       'Avg Trade', 'Return', 'Buy & Hold'];
        result.foundLabels = [];
        for (var i = 0; i < labels.length; i++) {
            if (allText.indexOf(labels[i]) !== -1) {
                result.foundLabels.push(labels[i]);
            }
        }

        // Try to find summary table elements
        var summaryRows = document.querySelectorAll('[class*="summary"] td, [class*="summary"] th, [class*="report"] td, [class*="report"] th');
        result.summaryCells = [];
        for (var i = 0; i < Math.min(summaryRows.length, 30); i++) {
            result.summaryCells.push(summaryRows[i].textContent?.trim());
        }

        // Try data-table approach
        var dataTables = document.querySelectorAll('[class*="dataTable"], [class*="reportTable"], [class*="summaryTable"]');
        result.dataTableCount = dataTables.length;
        for (var i = 0; i < Math.min(dataTables.length, 3); i++) {
            result['table_' + i + '_text'] = (dataTables[i].textContent || '').trim().substring(0, 500);
        }

        // Try to find the bottom panel content area
        var bottomContent = document.querySelector('[class*="bottom-window"] [class*="content"], [class*="chart-widget__bottom"] [class*="content"]');
        if (bottomContent) {
            result.bottomContentText = bottomContent.textContent?.trim().substring(0, 1000);
            result.bottomContentClass = bottomContent.className;
        }

        // Look for anything with 'backtest' or 'report' in the class
        var backtestEls = document.querySelectorAll('[class*="backtest"], [class*="report"], [class*="performance"]');
        result.backtestEls = [];
        for (var i = 0; i < backtestEls.length; i++) {
            var el = backtestEls[i];
            result.backtestEls.push({
                className: el.className,
                textPreview: (el.textContent || '').trim().substring(0, 200),
                visible: el.offsetParent !== null
            });
        }

        return result;
    })()"""
    r = await cdp.execute_js(js)
    val = r.get("result", {}).get("value", {})
    print(json.dumps(val, indent=2, default=str))

    await cdp.disconnect()

asyncio.run(main())
