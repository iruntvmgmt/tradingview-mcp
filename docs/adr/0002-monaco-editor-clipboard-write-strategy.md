# ADR-0002: Read/write the Pine Editor via clipboard + trusted keystrokes, never via direct textarea `.value` assignment

**Status:** accepted (see § Compliance below for a known violation of this decision elsewhere in the codebase)
**Date:** 2026-07-03 (reconstructed from `docs/monaco-editor-integration.md` and commit history; original investigation predates this ADR)
**Author(s):** reconstructed by audit session; original investigation documented in `docs/monaco-editor-integration.md`

## Context

The Pine Editor in TradingView Desktop is a Monaco Editor instance (the
same editor component VS Code uses). Monaco virtualizes its DOM: the
`<textarea class="inputarea">` that appears to hold the editor's content is
**not** a real reflection of the document — Monaco renders only the visible
viewport into DOM nodes and keeps the actual source in an internal model
object, syncing the textarea only for IME/accessibility purposes.

The naive approach —
```js
textarea.value = newSource;
textarea.dispatchEvent(new Event('input', { bubbles: true }));
```
— was tried and **silently fails**: it appears to succeed (no error thrown)
but the write is truncated/ignored because Monaco's internal model never
sees it. Full investigation and reproduction steps are in
`docs/monaco-editor-integration.md`.

Separately, TradingView's compile/save button uses React's synthetic event
system. CDP's `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent` generate
*trusted* browser-level events, but React's synthetic event layer in some
configurations doesn't pick these up reliably for click handlers attached
via React's event delegation — see `docs/monaco-editor-integration.md`
§ "CDP vs React" for specifics.

## Decision

`DomPineScriptBackend` (`core/services/backends/dom_backend.py`) implements
three operations, each with a specific, non-obvious mechanism required
because of the above:

| Operation | Mechanism | Why |
|---|---|---|
| **Read** (`read`) | Focus editor → `execCommand('selectAll')` → dispatch synthetic `ClipboardEvent('copy')` with a one-shot listener that captures Monaco's internal model → `DomUtils.read_text_monaco` | Reads Monaco's real model, not the virtualized textarea |
| **Write** (`write`) | System clipboard write → CDP `Cmd+A` (select all, real keystroke) → CDP `Cmd+V` (paste, real keystroke) → `DomUtils.type_text_monaco` | Paste is treated by Monaco as a real user action, updating its internal model correctly; `.value =` is not |
| **Compile** (`compile`) | **Primary:** find the Save button via `document.querySelectorAll('button')` + text/position match, call `.click()` via injected JS (not CDP mouse events) — this reaches React's synthetic handler. **Fallback:** CDP `Cmd+Enter` trusted keystroke if the button isn't found. | JS `.click()` triggers React's synthetic event system directly; CDP-dispatched mouse events don't reliably reach it in this app |

**Any code that reads or writes Pine Editor content must use this same
mechanism** (`DomUtils.type_text_monaco` / `read_text_monaco`), not
reimplement a simpler version. There is no shortcut — the virtualization
problem applies to *any* code touching the Monaco textarea, not just this
specific backend.

## Consequences

- Writing/reading Pine source is slower (clipboard round-trip + real
  keystrokes) than a hypothetical direct DOM write would be, but the direct
  approach doesn't work at all, so this isn't a real tradeoff.
- This mechanism depends on the system clipboard being available and not
  fought over by concurrent operations — don't parallelize multiple
  Pine read/write operations against the same TradingView Desktop instance.
- Any new code path that touches the Pine Editor (or likely any other
  Monaco-backed input in TradingView Desktop, if one exists elsewhere in the
  app) must reuse `type_text_monaco`/`read_text_monaco`, not reinvent
  textarea manipulation.

## Compliance — known violation

**`DomIndicatorBackend.apply()`** (`dom_backend.py`, ~line 101, backing the
`tv_apply_script` tool) does **not** follow this decision. It uses the exact
naive `ta.value = pine_code` pattern this ADR documents as broken, instead
of delegating to `DomPineScriptBackend.write`. This is tracked as an open
blocker in `docs/known_issues.json` (`indicator_apply`). Until fixed,
`tv_apply_script` should not be trusted for writing new Pine source — see
`docs/STATUS.md` for current status, and `docs/handoff/2026-07-03-audit-findings.md`
§2 for the fix plan (delegate to `DomPineScriptBackend` rather than
reimplementing).

## Evidence / how to verify this is still true

Re-run the reproduction steps in `docs/monaco-editor-integration.md`
against the current TradingView Desktop build: attempt a direct
`textarea.value =` write, read it back via `read_text_monaco`, and confirm
it does not match what was written. If TradingView ever changes its editor
component away from Monaco, or Monaco's internals change how they sync the
shadow textarea, this entire ADR needs re-validation.
