#!/usr/bin/env python3
"""Quick session explorer for TV Desktop."""
import asyncio, sys
sys.path.insert(0, '/Users/matt/Documents/TRADINGVIEW_MCP/tv-desktop-controller')
from core.services.cdp_connection import CDPConnection

async def main():
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()
    
    js = """
    (function() {
        var e = document.getElementById('pine-editor-dialog');
        if (!e) return 'NOT_FOUND';
        var lines = e.querySelectorAll('.view-line');
        if (!lines.length) return 'NO_LINES';
        var out = [];
        for (var i = 0; i < Math.min(lines.length, 50); i++)
            out.push(lines[i].textContent);
        return out.join('\\n');
    })()
    """
    r = await cdp.execute_js(js.strip())
    val = r.get('result', {}).get('value', '')
    
    if val == 'NOT_FOUND':
        print('Pine Editor not found in DOM')
    elif val == 'NO_LINES':
        print('No .view-line elements found in editor')
    else:
        lines = val.split('\n')
        print(f'=== Pine Editor Source ({len(lines)} lines) ===')
        for i, line in enumerate(lines, 1):
            print(f'{i:3d}: {line}')
    
    await cdp.disconnect()

asyncio.run(main())
