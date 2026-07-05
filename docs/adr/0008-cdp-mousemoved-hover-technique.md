# ADR-0008: CDP `Input.dispatchMouseEvent` (mouseMoved) is the only mechanism that triggers CSS `:hover` — use it as the default first approach for hover-gated UI elements

**Status:** accepted
**Date:** 2026-07-04
**Author(s):** Sage (backend) — live-session investigation

## Context

Multiple TradingView Desktop UI elements are gated behind CSS `:hover`:
the legend gear icon (`[data-qa-id="legend-settings-action"]`) has
`opacity: 0` until the user hovers over the indicator legend row, and
only then becomes clickable.

Three different mouse-interaction mechanisms exist in this codebase, and
they behave differently with respect to the renderer's hover tracking:

| Mechanism | Triggers CSS :hover? | Source |
|---|---|---|
| CDP `Input.dispatchMouseEvent` (mouseMoved) | ✅ Yes | Chromium's internal hover tracking treats CDP-injected mouse events as trusted synthetic input |
| `CGEventPostToPid` via Quartz | ❌ No | OS-level events bypass Chromium's hover state — the real OS cursor position governs hover, not injected events |
| JS `element.click()` | ❌ No | Dispatches a click at the DOM level without moving the virtual cursor; doesn't trigger `mouseenter`/`:hover` |

This was the root cause of multiple failed attempts to open the indicator
settings dialog programmatically — CGEvent clicks and JS `.click()` on the
gear icon silently failed because the icon was at `opacity: 0` and React
had not attached event handlers to it.

## Decision

**CDP `Input.dispatchMouseEvent` with `type: 'mouseMoved'` must be the
default first approach for any "element won't respond to clicks" problem
in this codebase**, before reaching for CGEventPostToPid, JS `.click()`,
or other workarounds.

The pattern is:

```python
# 1. Hover to reveal the element (triggers CSS :hover)
await cdp._send_command("Input.dispatchMouseEvent", {
    "type": "mouseMoved", "x": target_x, "y": target_y, "modifiers": 0,
})
await asyncio.sleep(0.4)

# 2. Click the now-visible element
await cdp._send_command("Input.dispatchMouseEvent", {
    "type": "mousePressed", "x": target_x, "y": target_y,
    "button": "left", "clickCount": 1,
})
await cdp._send_command("Input.dispatchMouseEvent", {
    "type": "mouseReleased", "x": target_x, "y": target_y,
    "button": "left", "clickCount": 1,
})
```

## Where this applies

This is implemented in `DomSettingsBackend._open_settings_dialog()`
(`dom_backend.py`) for opening the indicator properties dialog.  The same
pattern likely applies to any other hover-gated TradingView UI element:
other legend action buttons (Hide, Remove, More), toolbar buttons that
appear on hover, or any element with CSS `:hover` → `opacity: 1`
transitions.

## Evidence

- 2026-07-04 session: CDP `mouseMoved` to (107, 106) caused the gear icon
  at (181, 136) to transition from `opacity: 0` to `opacity: 1` in the
  renderer's computed style (confirmed via `window.getComputedStyle`).
  Subsequent CDP click on the gear successfully opened the dialog.
- CGEventPostToPid `kCGEventMouseMoved` to the same coordinates did NOT
  change the gear's computed opacity — the OS cursor position governs
  Chromium's `:hover` matching, and CGEvent posts don't move the OS
  cursor.
- JS `element.click()` on the gear did nothing even with `opacity` and
  `pointerEvents` forced via inline styles — React's event delegation
  does not attach handlers to the gear button until `:hover` triggers
  the actual React render of the button subtree.
