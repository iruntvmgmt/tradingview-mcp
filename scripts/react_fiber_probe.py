#!/usr/bin/env python3
"""React Fiber traversal probe — attempt to reach Monaco's internal editor model.

TradingView Desktop loads Monaco Editor as a React component inside Electron.
The global ``window.monaco`` is undefined (sandboxed), but React attaches
``__reactFiber$`` keys to DOM elements.  This script walks the fiber tree
from the ``.monaco-editor`` element to find the internal ``CodeEditor`` or
``EditorModel`` instance.

If successful, ``getValue()`` and ``setValue()`` become available for
full-source read/write without needing to scroll the virtual viewport.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.services.cdp_connection import CDPConnection


async def main():
    cdp = CDPConnection(debug_port=8315)
    await cdp.connect()

    js = """
    (function() {
        var result = {};

        // Find the Monaco editor container
        var editorEl = document.querySelector('.monaco-editor.pine-editor-monaco');
        if (!editorEl) {
            result.error = 'Monaco editor not found in DOM';
            return result;
        }

        // Walk React Fiber tree to find interesting nodes
        function walkFiber(fiber, depth, maxDepth) {
            if (!fiber || depth > maxDepth) return [];
            var found = [];

            // Check this fiber node for interesting properties
            var stateNode = fiber.stateNode;
            var memoizedState = fiber.memoizedState;
            var memoizedProps = fiber.memoizedProps;

            if (stateNode && typeof stateNode === 'object') {
                // Look for Monaco editor internals
                var keys = Object.keys(stateNode).filter(function(k) {
                    return k.indexOf('getValue') !== -1 ||
                           k.indexOf('setValue') !== -1 ||
                           k.indexOf('_model') !== -1 ||
                           k.indexOf('model') !== -1 ||
                           k.indexOf('editor') !== -1 ||
                           k === 'getModel' ||
                           k === 'getValue' ||
                           k === 'setValue';
                });
                if (keys.length > 0) {
                    found.push({
                        depth: depth,
                        nodeType: fiber.type?.name || fiber.tag,
                        interestingKeys: keys,
                        stateNodeType: stateNode.constructor?.name
                    });
                }

                // Check if stateNode has getValue/setValue directly
                if (typeof stateNode.getValue === 'function') {
                    try {
                        var val = stateNode.getValue();
                        found.push({
                            depth: depth,
                            method: 'getValue',
                            valueLength: val ? val.length : 0,
                            valuePreview: val ? val.substring(0, 100) : ''
                        });
                    } catch(e) {
                        found.push({depth: depth, method: 'getValue', error: e.message});
                    }
                }
            }

            // Check memoizedState for editor model
            if (memoizedState && typeof memoizedState === 'object') {
                var deps = memoizedState.memoizedState || memoizedState;
                if (deps && typeof deps.getValue === 'function') {
                    try {
                        var val2 = deps.getValue();
                        found.push({
                            depth: depth,
                            source: 'memoizedState',
                            valueLength: val2 ? val2.length : 0,
                            valuePreview: val2 ? val2.substring(0, 100) : ''
                        });
                    } catch(e) {}
                }
            }

            // Recurse into children
            var child = fiber.child;
            while (child) {
                found = found.concat(walkFiber(child, depth + 1, maxDepth));
                child = child.sibling;
            }

            return found;
        }

        // Find the React Fiber key on the editor element
        var fiberKey = null;
        for (var key in editorEl) {
            if (key.startsWith('__reactFiber$')) {
                fiberKey = key;
                break;
            }
        }

        if (!fiberKey) {
            result.error = 'No __reactFiber$ key found on Monaco element';
            return result;
        }

        result.fiberKey = fiberKey;
        result.fiberTag = editorEl[fiberKey]?.tag;
        result.fiberType = editorEl[fiberKey]?.type?.name || 'unknown';

        // Walk the fiber tree up to 15 levels deep
        var fiber = editorEl[fiberKey];
        var found = walkFiber(fiber, 0, 15);

        // Also try walking UP to the root (parent fibers)
        var parent = fiber.return;
        var upDepth = 1;
        while (parent && upDepth < 20) {
            found = found.concat(walkFiber(parent, -upDepth, 3));
            parent = parent.return;
            upDepth++;
        }

        result.interstingNodes = found.slice(0, 30);

        // Bonus: try to access Monaco via React DevTools hooks
        if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
            result.hasReactDevtoolsHook = true;
        }

        return result;
    })()
    """
    r = await cdp.execute_js(js, await_promise=False)
    val = r.get("result", {}).get("value", {})
    print(json.dumps(val, indent=2, default=str))

    await cdp.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
