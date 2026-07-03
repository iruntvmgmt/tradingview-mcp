# Handoff: 2026-07-03-fix-settings-and-indicator-apply — Settings backend rewritten with real selectors; indicator_apply delegates to clipboard-based write

**Agent:** Sage (ai-team-dev)
**Preceding handoff:** `docs/handoff/2026-07-03-audit-findings.md`
**Branch / commit at session end:** `main` @ (uncommitted — see pending commit below)

## 1. What changed this session

### Settings backend (`DomSettingsBackend`) — fully rewritten against live DOM

- **Recon:** Dumped the real Settings dialog DOM from a live TradingView Desktop 3.2.0 session. Key discoveries:
  - Dialog root: `div[data-name="indicator-properties-dialog"]`
  - Row labels: `div.cell-RLntasnw.first-RLntasnw` (text content identifies field: "Length", "Source", "Offset", etc.)
  - Number inputs: `input[data-qa-id="ui-lib-Input-input"]` (requires native `Object.getOwnPropertyDescriptor` setter — React-controlled inputs ignore direct `.value` assignment)
  - Dropdowns: `button[role="combobox"]` (displayed value = button text)
  - Checkboxes: `input[type="checkbox"][data-qa-id="ui-lib-checkbox-input-input"]`
  - OK button: `button[data-name="submit-button"]`
- **`recon_findings.json`**: Updated `settings_list_fields`, `settings_read`, `settings_write` with real selectors; flipped all three from `verified: false` → `verified: true`
- **`list_fields(study_name)`**: Now returns structured `[{name, type, current_value}, ...]` — correctly identifies number/dropdown/checkbox field types from the live DOM
- **`read(study_name)`**: Returns `{field_name: current_value}` dict
- **`write(study_name, values)`**: Uses the proven native setter + input/change event dispatch approach (confirmed working: set Length from 9 → 21, confirmed via `list_fields` re-read, clicked OK)
- **Live test confirmed**: All 7 fields read correctly (Length, Source, Offset, Type, BB StdDev, Timeframe), write confirmed via value change + re-read, OK button click confirmed

### Indicator apply (`DomIndicatorBackend.apply`) — delegates to clipboard-based write per ADR-0002

- Removed the broken `textarea.value = pine_code` approach (documented as broken in `docs/monaco-editor-integration.md`)
- Now delegates to `DomPineScriptBackend.write()` (clipboard-based + Cmd+A+V keystrokes) and `DomPineScriptBackend.compile()` (JS `element.click()` on Save button)
- `recon_findings.json`: Flipped `indicator_apply` from `verified: true` → `verified: false` (per ADR-0003 — was wrongly marked; needs live-session re-confirmation after the fix)

### Documentation updates

- `docs/known_issues.json`: All 3 settings issues marked `"status": "fixed"`, `indicator_apply` marked `"status": "fixed"` (code fix applied, pending live re-verification)
- `docs/STATUS.md`: Regenerated via `python scripts/generate_status.py`

## 2. What is now verified true (and how)

- **`settings_list_fields`**, **`settings_read`**, **`settings_write`**: ✅ Verified against live TradingView Desktop 3.2.0 with an open SMA Settings dialog. `list_fields` returned 7 correctly-typed fields; `write` changed Length from 9 → 21 which `list_fields` confirmed; OK button click dismissed the dialog. `verified: true` in `recon_findings.json`.
- **`indicator_apply` code path fixed**: Delegates to `DomPineScriptBackend` (clipboard-based, ADR-0002-compliant) instead of the broken `textarea.value` approach. ⚠️ **Still `verified: false`** per ADR-0003 — next agent must test this against a live session before trusting it.

## 3. What is still broken / unknown

See `docs/known_issues.json` + `docs/STATUS.md` for full current state. Summary:

- **`indicator_apply`**: Fixed in code but not live-tested. Needs a live session to confirm the open-tab → clipboard-write → compile pipeline works end-to-end with a real Pine script.
- **`ohlcv_read`**: Still dead end on both paths (DOM punts to network; network stub raises `CapabilityUnavailable`). Not yet addressed.
- **`CONTRIBUTING.md`**: Still references wrong repo URL. Not yet addressed.
- **`DomBacktestBackend.health_check` dead code**: Not yet addressed.

## 4. Next steps (in priority order)

1. **Live-test `tv_apply_script`**: Open TV Desktop, call `tv_apply_script` with a simple Pine script, confirm it appears on the chart. If successful, flip `indicator_apply` → `verified: true` in `recon_findings.json` and `known_issues.json`.
2. **Full end-to-end loop**: Write/apply a strategy → tune inputs via `tv_settings_write` → run backtest via `tv_run_backtest` → read `tv_get_backtest_summary`. Confirm the agent can iterate on a strategy and measure results.
3. **`ohlcv_read`**: Implement CDP Network domain event-buffering in `cdp_connection.py`, then wire `NetworkBackend.get_ohlcv` to parse WebSocket frame data.
4. **Housekeeping**: Fix `CONTRIBUTING.md` repo URL; remove `DomBacktestBackend.health_check` dead code.

## Decisions made this session (if any)

- **Settings dialog selector strategy**: Navigate rows by label text → adjacent value cell → input (three-level DOM traversal), not by generic `input[name=]` selectors. This matches the actual TradingView 3.2.0 DOM structure confirmed via live dump. If a future TV Desktop version changes this pattern, recon will need to re-dump.
- **`indicator_apply` delegation**: Chose to instantiate `DomPineScriptBackend` inside `DomIndicatorBackend.apply()` rather than refactoring clipboard logic into `DomUtils`, because the Pine backend already has the full write/compile pipeline and this keeps the ADR-0002 boundary clear.
