# Handoff: 2026-07-03 — ADR-0002 credibility crisis resolved; CGEventPostToPid is the working mechanism for Pine Editor read/write on macOS

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-03-dropdown-fix-and-multi-target-discovery.md`
**Branch / commit at session end:** `main` @ (uncommitted — changes need review and commit)

## What was done

This session was triggered by the Priority 1 request to investigate a serious finding from session 2026-07-03b: CDP `Input.dispatchKeyEvent` with Meta/Cmd modifier does NOT trigger `paste`/`copy` ClipboardEvents on macOS. This called into question ADR-0002, which documented CDP Cmd+A/V/C as the proven write/read mechanism for the Pine Editor — and pine_read/pine_write were marked `verified: true` in recon_findings.json on the strength of that ADR.

### Investigation outcome

- **ADR-0002's CDP Cmd-key approach was NEVER genuinely verified on macOS.** Live testing proved two independent failures:
  1. `navigator.clipboard.writeText()` fails with "Document is not focused" unless `Page.bringToFront` is called first (with ~0.6s delay)
  2. Even after fixing focus, CDP Cmd+V/Cmd+C does not generate paste/copy ClipboardEvents — macOS intercepts Cmd-modified synthetic keystrokes at the window-server level

- **CGEventPostToPid is the working alternative.** Using Quartz `CGEventCreateKeyboardEvent` + `CGEventPostToPid` targeting TradingView's PID successfully sends real Cmd+A/V/C keystrokes that trigger Monaco's native paste/copy handlers. Full write→read round-trip confirmed: 4-line Pine script written via `DomPineScriptBackend.write()`, 118 chars read back via `.read()`, content matches exactly.

- **`AXIsProcessTrusted()` returns True** for the VS Code integrated terminal process — Accessibility permission IS granted to this environment. Without it, CGEventPostToPid silently drops keystrokes (same as pynput).

### Files changed

| File | Change |
|------|--------|
| `core/services/dom_utils.py` | Added module-level `_get_tv_pid()`, `_has_accessibility_permission()`, `_send_cmd_key()` helpers. Rewrote `type_text_monaco` to use base64 clipboard encoding + `Page.bringToFront` + `CGEventPostToPid`. Replaced `_paste_via_pynput` with `_paste_via_cgevent`. Rewrote `read_text_monaco` and replaced `_copy_via_pynput` with `_copy_via_cgevent`. |
| `core/services/cdp_connection.py` | Extended `health_check()` to report `accessibility_permission`, `tv_pid`, and `pine_editor_write_ready` boolean. |
| `core/services/backends/dom_backend.py` | Updated `compile()` to click `button[title="Add to chart"]` (live-confirmed working). Fixed duplicate try/except. |
| `recon_findings.json` | Flipped pine_read, pine_write, and indicator_apply back to `verified: true` (confirmed this session). Added detailed notes referencing ADR-0006. |
| `docs/known_issues.json` | Closed pine_read, pine_write, indicator_apply blocker issues → minor/fixed. |
| `docs/adr/0006-cdp-cmd-key-clipboard-limitation.md` | **New ADR.** Documents the Cmd-key limitation, all approaches tried and ruled out (pynput, AppleScript, CGEventPostToPid without permission, isTrusted override), and the CGEventPostToPid solution. |
| `docs/adr/0002-monaco-editor-clipboard-write-strategy.md` | Updated Status to "superseded in part by ADR-0006"; added macOS Cmd-key caveat in Evidence section. |
| `docs/monaco-editor-integration.md` | Added "macOS Limitation" section and pitfall #7. |
| `docs/STATUS.md` | Regenerated via `scripts/generate_status.py` — now reflects pine_read/pine_write/indicator_apply as verified: true. |

## What still needs doing

1. **Checkbox settings_write** is still untested — see `docs/known_issues.json`. Needs test against an indicator with checkbox inputs (Bollinger Bands, MACD).
2. **`indicator_apply` compile timing.** The current 0.3s delay after write before compile may need tuning. The "Add to chart" button clicked successfully but the indicator didn't always render (old compile errors in the Pine Editor console may interfere). Consider: clearing the editor console before compile, or using Cmd+Enter (which needs different handling to avoid hotkey-recording mode).
3. **Base64 encoding** has been fixed in `type_text_monaco` but the `DomPineScriptBackend.write()` method also does its own clipboard write — might duplicate the base64 logic. Consolidate.
4. **Remove pynput dependency** now that CGEventPostToPid is the primary mechanism. pynput can be removed from requirements, and `_paste_via_cdp` retained as fallback for non-macOS.
5. **ADR-0006 Compliance note** says `Page.bringToFront` still needs integration into `read_text_monaco` — it's been added but should be double-checked.
6. **`_has_accessibility_permission()` import path** uses `HIServices` which may not be available on non-macOS. Needs a try/except and graceful fallback.

## Key decisions made

- **CGEventPostToPid is the primary keystroke mechanism** for Pine Editor read/write on macOS (ADR-0006). pynput is deprecated.
- **ADR-0002 remains valid for its core decision** (clipboard for transport, never `.value` for Monaco) but its keystroke-delivery section is superseded.
- **pine_read/pine_write/indicator_apply are verified: true** — confirmed via live round-trip testing this session.

## Cold-start prompt for next agent

```
Read docs/adr/0006-cdp-cmd-key-clipboard-limitation.md,
docs/STATUS.md, and docs/handoff/2026-07-03-adr2-credibility-crisis-resolved.md.
Continue from Priority 3 (checkbox settings_write test) and the
outstanding items in the "What still needs doing" section of the handoff.
```
