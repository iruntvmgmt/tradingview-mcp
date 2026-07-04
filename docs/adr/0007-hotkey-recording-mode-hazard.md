# ADR-0007: Cmd+Enter and other keybinding-triggering keystrokes must never be sent to TradingView — hotkey-recording-mode hazard

**Status:** accepted
**Date:** 2026-07-04
**Author(s):** Sage (backend) — retrospective from session findings

## Context

On 2026-07-03, a test sent Cmd+Enter to TradingView via CGEventPostToPid
in an attempt to trigger Pine Script compilation.  TradingView interpreted
this as a keybinding-definition request and entered hotkey-recording mode,
displaying a persistent modal widget (`div.defineKeybindingWidget`) with
the message "Press desired key combination and then press ENTER."

On 2026-07-04, the start of the session found TradingView still stuck in
this state.  The modal silently intercepted subsequent keystrokes, causing
Pine Editor writes to fail until the widget was force-removed from the DOM
via JS (`widget.remove()`).

## Decision

**Never send Cmd+Enter or any other keybinding-triggering combination to
TradingView Desktop**, even in throwaway debug scripts.  These keystrokes
can trigger modal UI states that silently interfere with subsequent
operations and whose recovery is not fully understood.

### Recovery

If hotkey-recording mode is encountered (the presence of
`div.defineKeybindingWidget` in the DOM), the current recovery method is:

```js
document.querySelector('.defineKeybindingWidget').remove()
```

This removes the visual widget and returns the Pine Editor to an operable
state.  However, it has **not been confirmed** that TradingView's internal
keybinding state is fully reset — the widget removal may clean up the UI
without clearing the underlying keybinding listener.  If a recovered
session later exhibits unexpected keystroke behavior, the safest fix is to
close and reopen the Pine Editor (click `button[data-name="pine-dialog-button"]`
twice).

### Compile action

The compile action should **exclusively** use JS `element.click()` on the
Pine Editor toolbar button (`button[title="Add to chart"]` or
`button[title="Update on chart"]`).  This is confirmed working and does
not trigger hotkey recording.  Any Cmd+Enter fallback code must be
removed — it is a dead end that actively causes harm.

## Consequences

- The `pine_compile` recon entry's `use_keyboard_shortcut` and
  `compile_keys` fields are deprecated and should be removed.
- Any future code that dispatches keystrokes to TradingView must audit
  the key combination against known TradingView shortcuts that trigger
  modal states (keybinding recording, screenshot mode, etc.).

## Evidence

- 2026-07-03 session: Cmd+Enter sent via CGEventPostToPid → TradingView
  entered hotkey-recording mode.
- 2026-07-04 session: Pine Editor writes failed until
  `.defineKeybindingWidget` was removed from DOM.  Subsequent writes and
  compiles worked correctly after recovery.
