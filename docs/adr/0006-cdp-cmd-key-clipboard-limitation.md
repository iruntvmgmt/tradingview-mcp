# ADR-0006: CDP synthetic Cmd-key events do not trigger native clipboard actions on macOS — switch to pynput OS-level keystrokes

**Status:** accepted
**Date:** 2026-07-03
**Author(s):** Sage (backend) — live-session investigation

## Context

ADR-0002 established that Pine Editor read/write must use the system
clipboard as transport (Monaco ignores direct `textarea.value`).  It
documented CDP `Input.dispatchKeyEvent` with Cmd+A / Cmd+V / Cmd+C as the
keystroke delivery mechanism, asserting these are "trusted" events that
Monaco processes natively.

On 2026-07-03, a live session tried to use `DomPineScriptBackend.write()`
and `.read()` against a running TradingView Desktop 3.2.0 instance on macOS
and discovered **two independent failure modes** that together mean
pine_read and pine_write have never genuinely worked via pure CDP on this
platform:

### Failure 1: `navigator.clipboard.writeText` requires document focus

The clipboard write step in `type_text_monaco` uses
`navigator.clipboard.writeText()` injected via `Runtime.evaluate`.  When
the TradingView Desktop page is not the frontmost document (e.g., when
connected via CDP from a background terminal), this call fails:

> `NotAllowedError: Failed to execute 'writeText' on 'Clipboard':
> Document is not focused.`

**Fixable**: Call `Page.bringToFront` before clipboard operations.
Confirmed working — after `Page.bringToFront`, `writeText` succeeds and
clipboard read-back verifies the correct content.

### Failure 2: CDP Cmd+V / Cmd+C do not trigger ClipboardEvents on macOS

Even after fixing focus (Failure 1) and confirming the clipboard contains
the correct content, `Input.dispatchKeyEvent` with Meta modifier (`4`)
for Cmd+A / Cmd+V / Cmd+C reaches the Monaco textarea as trusted keyboard
events (confirmed via event monitoring: `keydown` with `metaKey: true`,
`isTrusted: true`) but **never generates the corresponding `paste` or
`copy` ClipboardEvent**.

macOS intercepts Cmd-modified synthetic keystrokes at the window-server
level.  The keystrokes are delivered to the app, but the OS-level
Cmd+V → Paste mapping (which generates the `paste` ClipboardEvent that
Monaco's handler listens for) happens in a layer above CDP's event
injection.  This is a macOS-specific limitation — on Windows/Linux,
Ctrl-modified CDP keystrokes may behave differently (not tested in
this session).

**Not fixable via CDP alone**.  We tested and ruled out:

| Approach | Result |
|---|---|
| `Input.dispatchKeyEvent(Cmd+V)` with modifiers=4 | keydown reaches textarea; no paste event fires |
| `Input.dispatchKeyEvent` with Meta key-down before V | same — no paste event |
| `Input.insertText` | writes to textarea but Monaco ignores (no IME composition) |
| `Input.imeSetComposition` | no composition events triggered |
| `document.execCommand('paste')` | returns false |
| `new ClipboardEvent('paste')` + `dispatchEvent` | `isTrusted: false` — Monaco rejects |
| `Object.defineProperty(ClipboardEvent.prototype, 'isTrusted', {get: () => true})` | silently ignored — `isTrusted` is a native getter, not overridable from JS |
| `element.click()` via JS on `button[title="Add to chart"]` | ✅ works (React synthetic events) — this is the compile path |
| pynput `Controller().press(Key.cmd)` | silently fails without Accessibility permission |
| AppleScript `keystroke "v" using command down` | `osascript is not allowed assistive access` |
| `CGEventPostToPid` via Quartz | silently fails without Accessibility permission |

## Decision

**Pine Editor write and read must use pynput OS-level keystrokes**
(Cmd+A / Cmd+V / Cmd+C) dispatched by `pynput.keyboard.Controller`, with
`Page.bringToFront` called before clipboard operations.

The code path is:

```
Write: Page.bringToFront → navigator.clipboard.writeText → focus textarea
       → activate TradingView (open -a) → pynput Cmd+A → pynput Cmd+V

Read:  Page.bringToFront → focus textarea
       → activate TradingView → pynput Cmd+A → pynput Cmd+C
       → navigator.clipboard.readText
```

**Compile** uses JS `element.click()` on `button[title="Add to chart"]`
(confirmed working) and does NOT require pynput.

### Environment dependency

This adds a **hard environment dependency**: macOS Accessibility
permission must be granted to the process running the MCP server
(Terminal.app, iTerm2, or VS Code's integrated terminal) in:

```
System Preferences → Privacy & Security → Accessibility
```

Without this permission, pynput keystrokes are silently dropped by macOS.
The CDP fallback path (which does not trigger paste on macOS) is retained
for platforms where it works (Windows/Linux) but **must not be used on
macOS** as the primary mechanism.

### Detection

The MCP server should check `AXIsProcessTrusted()` (or equivalent
pynput/CGEvent probe) at startup and report Accessibility status in
`tv_health_check` diagnostics.  See `core/services/diagnostics.py`.

## Consequences

- pine_read and pine_write are verified: **false** in recon_findings.json
  as of 2026-07-03.  They cannot be flipped to verified: true until
  Accessibility permission is granted AND a full write→read round-trip
  passes against a live Pine Editor.
- indicator_apply inherits this dependency (its write step delegates to
  `DomPineScriptBackend.write`).
- `type_text_monaco` / `read_text_monaco` in `dom_utils.py` were updated
  (session 2026-07-03b) with a two-tier approach: pynput primary, CDP
  fallback.  The `Page.bringToFront` fix for clipboard focus was also
  added but may need integration into the existing pipeline.
- All downstream consumers of `DomPineScriptBackend` (directly or via
  `DomIndicatorBackend.apply`) are affected and should check
  Accessibility status before attempting writes.
- This ADR supersedes ADR-0002's keystroke-delivery section but NOT its
  core insight (clipboard for transport, never `.value` for Monaco).

## Compliance

- **`type_text_monaco`** (dom_utils.py): Updated to call
  `_paste_via_pynput()` as primary, `_paste_via_cdp()` as fallback.
  **Still needs**: `Page.bringToFront` call before clipboard write.
- **`read_text_monaco`** (dom_utils.py): Updated similarly with
  `_copy_via_pynput()` / `_copy_via_cdp()`.
  **Still needs**: `Page.bringToFront` call before clipboard operations.
- **`DomPineScriptBackend.compile`** (dom_backend.py): Updated to click
  `button[title="Add to chart"]` via JS (works cross-platform, no
  Accessibility dependency).

## Evidence

Full reproduction steps and event-monitoring logs are in the session
transcript for 2026-07-03b.  Key empirical findings:

1. `Page.bringToFront` → clipboard write succeeds; without it, fails
   with "Document is not focused".
2. Event monitoring on `#pine-editor-dialog textarea.inputarea` confirms
   CDP keystrokes arrive (`keydown`, `metaKey: true`, `isTrusted: true`)
   but no `paste`/`copy` ClipboardEvent follows.
3. JS `element.click()` on `button[title="Add to chart"]` successfully
   triggers React's synthetic event → compile works.
4. `isTrusted` cannot be overridden on ClipboardEvent — it is a native
   (C++-level) getter, not a JavaScript property.
