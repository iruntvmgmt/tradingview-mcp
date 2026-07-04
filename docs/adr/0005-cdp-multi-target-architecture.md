# ADR-0005: Pine Editor opens in the same CDP target as the main chart page — multi-target CDP support is not required for Pine capabilities

**Status:** accepted
**Date:** 2026-07-03
**Author(s):** Sage (ai-team-dev)

## Context

A prior session (handoff `2026-07-03-dropdown-fix-and-multi-target-discovery.md`)
hypothesized that the Pine Editor runs in a **separate CDP target** from the
main chart page, which would require multi-target CDP session support
(`Target.attachToTarget`, per-target `sessionId`) in `cdp_connection.py`.
This hypothesis was based on two observations:

1. `document.getElementById('pine-editor-dialog')` returned `null` /
   `NOT_IN_DOM` on the chart page target.
2. No element containing "Pine" or "Editor" text was found in the page's
   button/tab inventory.

## Investigation (2026-07-03)

Re-ran `cdp.list_targets()` with full target detail (recorded below) and
searched for the Pine Editor trigger button using `aria-label` and
`data-name` attribute queries.

### CDP target inventory (before opening Pine Editor)

```
Total: 10 targets

Target 0: type=worker  id=265B5904... url=''              (worker, no url)
Target 1: type=worker  id=9E893BB2... url=''              (worker, no url)
Target 2: type=worker  id=34E8778A... url=''              (worker, no url)
Target 3: type=page    id=03531402... url=file://...app/window/index.html  (window shell)
Target 4: type=page    id=9FB03BAB... url=file://...app/renderer-services/drag-service/  (drag svc)
Target 5: type=page    id=3AECAF77... url=''              (empty page, hidden)
Target 6: type=page    id=6A7EC5CC... url=file://...app/browser-api-container/  (browser api)
Target 7: type=page    id=1AC795D9... url=''              (empty page, hidden)
Target 8: type=page    id=D9EBF326... url=file://...app/tooltip/index.html  (tooltip)
Target 9: type=page    id=5AB7B314... url=https://www.tradingview.com/chart/...  (MAIN CHART — attached=True)
```

### Pine Editor trigger button discovery

A button was found on the main chart page:
- **tag:** `<button>`
- **data-name:** `pine-dialog-button`
- **aria-label:** `Pine`
- **visible:** `true`

### Pine Editor behavior on click

When `document.querySelector('button[data-name="pine-dialog-button"]').click()`
was executed via CDP `Runtime.evaluate` on the main chart target:

1. `#pine-editor-dialog` appeared in the **same** CDP target's DOM with
   dimensions 583×1585 (visible, large)
2. The CDP target count increased from 10 → 11 (one new **worker** target for
   the Pine Language Server, but no new **page** target)
3. All subsequent DOM access to the Pine Editor (read, write, compile) can
   happen on the same `cdp.execute_js()` session — no target switching needed

### Corrected understanding

The Pine Editor is a **`<div>`-based dialog** rendered inside the main
chart page target, identical in architecture to the Settings dialog
(`div[data-name="indicator-properties-dialog"]`). It is NOT a separate
Electron window or renderer process. The `#pine-editor-dialog` element
is simply **not present in the DOM** until the button is clicked — it is
created on-demand by the React application, which is why earlier queries
for it returned null.

## Decision

**Multi-target CDP session support is NOT required for Pine Editor access.**
The Pine Editor can be opened, written to, and compiled entirely within
the existing single-target CDP connection to the main chart page, using
the same `cdp.execute_js()` mechanism as every other capability.

`DomIndicatorBackend.apply()` should:
1. Click `button[data-name="pine-dialog-button"]` to open the editor dialog
2. Wait for `#pine-editor-dialog` to appear in DOM
3. Delegate to `DomPineScriptBackend.write()` (clipboard, per ADR-0002)
4. Delegate to `DomPineScriptBackend.compile()` (JS element.click, per ADR-0002)

## Consequences

- **What this makes easier:** `indicator_apply`, `pine_read`, `pine_write`,
  `pine_compile`, and `pine_logs_read` all work from a single CDP connection
  to the chart page. No `cdp_connection.py` changes needed.
- **What this rules out:** The multi-target approach (per-target
  `sessionId`, `Target.attachToTarget`) is not needed for Pine Script
  capabilities. It may still be useful for future capabilities that
  genuinely span Electron windows (e.g. Watchlist panels, which live in the
  `app/window/index.html` target #3), but that is a separate concern.
- **When to revisit:** If a future TV Desktop version moves the Pine Editor
  to a separate renderer process (as a standalone page target rather than
  an in-DOM dialog), a new ADR should be written documenting the
  multi-target CDP approach. The CDP target list recorded here serves as
  the baseline for detecting such a change.

## Evidence / how to verify this is still true

1. Connect to the chart page CDP target.
2. `document.querySelector('button[data-name="pine-dialog-button"]').click()`
3. `document.getElementById('pine-editor-dialog')?.getBoundingClientRect()` →
   should return non-zero width.
4. If step 3 returns null/zero, the Pine Editor may have moved to a
   separate target — re-run `cdp.list_targets()` and compare against the
   baseline target list in this ADR.
