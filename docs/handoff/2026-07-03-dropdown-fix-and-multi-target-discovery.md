# Handoff: 2026-07-03-dropdown-fix-and-multi-target-discovery — Dropdown write confirmed; CSS hash fragility documented (ADR-0004); indicator_apply blocked by multi-target architecture

**Agent:** Sage (ai-team-dev)
**Preceding handoff:** `docs/handoff/2026-07-03-fix-settings-and-indicator-apply.md`
**Branch / commit at session end:** `main` @ `123f96e`

## 1. What changed this session

### Dropdown write fixed and live-verified

- The `DomSettingsBackend.write()` dropdown path used `setTimeout()` inside
  injected JS which never executed before the CDP round-trip returned,
  silently failing on dropdown/combobox fields.
- **Fix:** Split into three CDP calls per field: (1) find the input element
  and determine its type, (2) click combobox to open the dropdown menu,
  (3) find and click the target `[role="option"]` element.
- **Confirmed working:** Source field changed from "Open" → "High" through
  `backend.write('SMA', {'Source': 'High'})`, persisted across dialog
  close/re-open (verified via `list_fields` re-read).

### Number write confirmed working from prior session — no regression.

### Checkbox write structurally implemented but untested

- The SMA indicator has no checkbox inputs. Looking at the Settings dialog
  rows, none of the 7 fields (Length, Source, Offset, Type, Length-2,
  BB StdDev, Timeframe) are checkboxes.
- The `write()` method has a `type === "checkbox"` branch that uses
  `element.click()` — structurally correct per `list_fields` type
  classification, but untested. See `docs/known_issues.json` for current
  status.

### ADR-0004: CSS-module hash selector fragility documented

- `div.cell-RLntasnw.first-RLntasnw` (the row-label selector) is a hashed
  CSS Module class that will break on the next TradingView Desktop update.
- The semantic selectors alongside it (`data-name`, `data-qa-id`, `role`)
  are stable and expected to survive updates.
- ADR-0004 documents: which selectors are hash-dependent vs. stable, what
  it looks like when this breaks (`list_fields` returns empty), and the
  exact fix procedure (re-dump dialog HTML, find new hash class, update
  `recon_findings.json`).

### indicator_apply: blocked by multi-target architecture

- **Discovery:** The Pine Editor (`#pine-editor-dialog`) is in a **separate
  CDP target** — it is not in the chart page's DOM. The chart page at
  `tradingview.com/chart/...` has no Pine Editor elements at all.
- The delegate-to-PineEditor strategy (`DomIndicatorBackend.apply` →
  `DomPineScriptBackend.write`) cannot work without CDP target-switching
  infrastructure in `cdp_connection.py` (connect to a second target, keep
  both WebSocket connections alive, switch between them).
- `indicator_apply` remains `verified: false` in `recon_findings.json`.
- **Alternative path to explore:** The built-in Indicators browse dialog
  (opened via the "Indicators" toolbar button) is in the same chart page
  target and may provide an apply flow that doesn't need the Pine Editor.

### Documentation updates

- `known_issues.json`: `settings_write` minor issue updated (dropdown
  confirmed, checkbox untested). Indicator apply remaining.
- `STATUS.md`: Regenerated.
- `docs/adr/0004-settings-dialog-selector-fragility.md`: New ADR written.

## 2. What is now verified true (and how)

- **`settings_write` — dropdown:** ✅ Source field changed and persisted
  through `backend.write()`. Verified against live TV Desktop 3.2.0.
- **`settings_write` — number:** ✅ Confirmed in prior session, still works.
- **`settings_write` — checkbox:** ⚠️ Structurally implemented but
  untested (SMA has no checkboxes).

## 3. What is still broken / unknown

See `docs/known_issues.json` + `docs/STATUS.md`. Summary:

- **`settings_write` checkbox**: Untested. Need indicator with checkbox
  input (e.g. Style tab of any indicator).
- **`indicator_apply`**: Blocked by Pine Editor being in a separate CDP
  target. Need either (a) multi-target CDP connection support in
  `cdp_connection.py`, or (b) alternative apply path via Browse Indicators
  dialog.
- **`ohlcv_read`**: Still dead end. Untouched this session.
- **CSS hash fragility**: Documented (ADR-0004) but not yet triggered —
  will break on next TV Desktop update.

## 4. Next steps (in priority order)

1. **Recon the Indicators browse dialog**: On the live chart, click the
   "Indicators" toolbar button. Dump the dialog DOM, identify how to
   navigate to existing scripts and click "Add". This gives `indicator_apply`
   a working path without needing multi-target CDP.
2. **Test checkbox write**: Find any indicator with a checkbox (Style tab
   "Show" toggles are common). Open Settings → Style tab, test
   `backend.write()` with a bool value.
3. **Multi-target CDP**: If Pine Editor access is required for `pine_*`
   capabilities, implement target-switching in `cdp_connection.py`
   (`switch_target(target_id)`, `list_targets()` already exists).
4. **`ohlcv_read`**: CDP Network domain event-buffering.

## Decisions made this session (if any)

- **Dropdown write mechanism:** Two-step CDP call pattern (find+click combo,
  then find+click option) rather than a single JS block with `setTimeout`,
  because CDP `Runtime.evaluate` returns before async JS callbacks fire.
  Documented in commit `123f96e`.
- **Multi-target architecture accepted as a blocker for indicator_apply:**
  The Pine Editor is a separately-rendered Electron window. Until
  `cdp_connection.py` can connect to multiple targets simultaneously
  (or until we find the Pine Editor in the same target when the user
  has a specific layout), `indicator_apply` cannot use the Pine Editor
  pipeline.
