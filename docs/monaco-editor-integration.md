# Pine Script Editing: Monaco Editor Integration Deep-Dive

> **Status**: Resolved — July 1, 2026  
> **Scope**: How the MCP server reads, writes, and compiles Pine Script in
> TradingView Desktop's Monaco editor via CDP.

---

## The Problem

The MCP server's `DomPineScriptBackend` failed to reliably read/write Pine Script
source in the editor.  Reads returned only ~500-1000 characters (truncated).
Writes with `Input.insertText` only wrote ~100 characters.  Full 27K+ character
scripts would not transfer.

### Failed Approaches (and why)

| # | Approach | Failure Mode | Root Cause |
|---|----------|-------------|------------|
| 1 | `textarea.value` direct read | Returns ~1000 chars | Monaco's virtualization window |
| 2 | `textarea.value` direct write + `input` event | No-ops or truncated | Monaco overrides `.value`, clears textarea between events |
| 3 | CDP `Input.insertText` (20K chunks) | Writes ~100 chars then stops | Renderer crash; Monaco rejects bulk text injection |
| 4 | Native `Object.getOwnPropertyDescriptor` setter + `input` event | No effect on Monaco's model | Monaco reads from **its own internal model**, not the DOM textarea |
| 5 | Synthetic `ClipboardEvent('paste')` with populated `DataTransfer` | No effect | `isTrusted` is `false`; Monaco ignores untrusted clipboard events |
| 6 | `document.execCommand('insertText', ...)` | Truncates at ~1000 chars | Chrome limits `execCommand` text size; Monaco ignores remaining |
| 7 | `document.execCommand('paste')` with pre-populated clipboard | No effect | Same `isTrusted` problem as #5 |

---

## Root Cause: Monaco's Textarea Virtualization

Monaco Editor does **not** use the DOM textarea as a document store.  The hidden
`<textarea class="inputarea monaco-mouse-cursor-text">` serves exclusively as:

1. An **IME proxy** (for composing Asian characters via the OS IME)
2. A **screen-reader bridge** (for accessibility tools)

Monaco's **internal model** (an Abstract Syntax Tree / line buffer) is the
**single source of truth**.  The textarea is **never** in sync with the full
document — it only holds a small window (~500-1000 characters) around the cursor
position.  This is a deliberate performance optimization: rendering 30,000 lines
of text in a DOM textarea would freeze the browser.

```
┌─────────────────────────────────────────┐
│            Monaco Editor                │
│  ┌───────────────────────────────────┐  │
│  │     Internal Model (AST)          │  │
│  │     27,804 characters             │  │
│  │     lines 1..935                  │  │
│  └───────────┬───────────────────────┘  │
│              │ syncs ~1000 chars         │
│              ▼                           │
│  ┌───────────────────────────────────┐  │
│  │  <textarea> (virtualization       │  │
│  │   window ~1000 chars)             │  │
│  │  Only cursor-adjacent text        │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │  .view-lines (DOM)                │  │
│  │  Only visible viewport lines      │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Consequence**: Any read/write that goes through `textarea.value` will always
be truncated.  You **must** go through Monaco's event-handling pipeline.

### The `isTrusted` Firewall

Monaco intercepts `paste`, `copy`, and `cut` events on the textarea and routes
them to its internal model.  However, it checks `event.isTrusted`:

```javascript
// Simplified Monaco internal handler
textarea.addEventListener('paste', (e) => {
    if (!e.isTrusted) return;           // ← IGNORES synthetic events
    const text = e.clipboardData.getData('text/plain');
    this.model.insertText(text);       // routes to internal AST
});
```

**`isTrusted` is read-only** and cannot be overridden.  Any
`new ClipboardEvent(...)` or `el.dispatchEvent(...)` produces `isTrusted: false`.
Only events originating from genuine user interaction (or **CDP's
`Input.dispatchKeyEvent`**) have `isTrusted: true`.

---

## The Solution: System Clipboard + CDP Keystrokes

The only way to trigger Monaco's native event handlers is through **real
keyboard events** dispatched via CDP's `Input.dispatchKeyEvent`.  These events
are **trusted** by the browser (they come from the protocol level, not JS).

### Write Pipeline

```
Python                           Browser                        Monaco
──────                           ───────                        ──────
                                 navigator.clipboard
base64.encode(source)  ────────► .writeText(source)  ────────► System Clipboard
                                                                   
CDP click on                                     focus            
.monaco-editor div ───────────► editor focused ◄──────────────────
                                                                   
CDP Cmd+A              real keystroke ──────────────────────────► selectAll()
(select all)                                                       AST marked
                                                                   
CDP Cmd+V              real keystroke ──────────────────────────► paste handler
(paste)                 e.isTrusted = true                         reads clipboard
                                                                   writes to AST
```

### Read Pipeline

```
Python                           Browser                        Monaco
──────                           ───────                        ──────
CDP click on                                     focus            
.monaco-editor div ───────────► editor focused ◄──────────────────
                                                                   
CDP Cmd+A              real keystroke ──────────────────────────► selectAll()
(select all)                                                       copies to
                                                                   clipboard
                                                                   
CDP Cmd+C              real keystroke ──────────────────────────► copy handler
(copy)                   e.isTrusted = true                        AST → clipboard
                                                                   
                      navigator.clipboard                          
Python ◄────────────── .readText()  ◄───────────────────────── System Clipboard
```

---

## Code Architecture

### Files Changed

| File | Change | Method |
|------|--------|--------|
| `recon_findings.json` | Added `textarea_selectors` to `pine_read`, `pine_write`, `pine_compile` | New selectors for `.monaco-editor textarea.inputarea` |
| `core/services/dom_utils.py` | Added `type_text_monaco()` | Clipboard write → CDP Cmd+A → CDP Cmd+V |
| `core/services/dom_utils.py` | Added `read_text_monaco()` | CDP click → Cmd+A → Cmd+C → clipboard read |
| `core/services/dom_utils.py` | Removed `type_text_native()` | Obsolete — `Input.insertText` approach |
| `core/services/dom_utils.py` | Removed `extract_text_native()` | Obsolete — native getter approach |
| `core/services/backends/dom_backend.py` | Rewrote `DomPineScriptBackend.write()` | Delegates to `type_text_monaco()` |
| `core/services/backends/dom_backend.py` | Rewrote `DomPineScriptBackend.read()` | Delegates to `read_text_monaco()` |
| `core/services/backends/dom_backend.py` | Rewrote `DomPineScriptBackend.compile()` | Uses keyboard shortcut `Cmd+Enter` |

### Key Methods

#### `DomUtils.type_text_monaco(selectors, text)`
1. Base64-encode `text` in Python (avoids JSON escaping pitfalls).
2. Decode in browser via `atob()` + `TextDecoder`.
3. Write to system clipboard: `navigator.clipboard.writeText(decoded)`.
4. Click visible `.monaco-editor` div via CDP to focus.
5. Send CDP `Cmd+A` (select all) — trusted keystroke.
6. Send CDP `Cmd+V` (paste) — trusted keystroke, Monaco handles natively.

#### `DomUtils.read_text_monaco(selectors)`
1. Click visible `.monaco-editor` div via CDP to focus.
2. Send CDP `Cmd+A` (select all) — trusted keystroke.
3. Send CDP `Cmd+C` (copy) — trusted keystroke, Monaco copies AST to clipboard.
4. Read system clipboard: `navigator.clipboard.readText()`.

#### `DomPineScriptBackend.compile(script_name)`
1. Dispatch `KeyboardEvent('keydown'/'keyup')` for `Meta+Enter` (Cmd+Enter).
2. Sent on `document.activeElement` so it reaches the focused editor.
3. Note: This uses JS `KeyboardEvent` (not CDP), which may have `isTrusted: false`.
   If compilation fails, fall back to: focus editor via CDP click → CDP `Cmd+Enter`.

### Selector Strategy

The recon file now has three tiers of selectors for Pine operations:

```json
{
  "editor_selectors": ["...div[class*=\"monaco-editor\"]", "..."],
  "textarea_selectors": [".monaco-editor textarea.inputarea", "..."],
  "open_tab_selectors": []
}
```

- `editor_selectors` — Used for clicking the **visible** editor container (focus).
- `textarea_selectors` — Used as the **event target** for clipboard/paste events.  
  Prioritizes `.monaco-editor textarea.inputarea` (the Monaco input proxy).
  Falls back to `#pine-editor-dialog textarea`.
- `open_tab_selectors` — Intentionally empty; the Pine Editor tab click is
  unnecessary and the old CSS `:text()` pseudo-class was invalid.

---

## Common Pitfalls

### 1. Never read/write `textarea.value` for Monaco
Monaco actively fights DOM-based manipulation.  The textarea is a **virtualization
window**, not a document store.  Reading it gives you ~1000 chars at most.

### 2. Synthetic events have `isTrusted: false`
`new ClipboardEvent(...)` + `dispatchEvent(...)` produces untrusted events that
Monaco ignores.  The only way to produce trusted events is via CDP's
`Input.dispatchKeyEvent` or genuine user input.

### 3. CDP `Input.insertText` is unreliable for bulk text
Chrome's renderer process can crash or truncate when `Input.insertText` is
called with very large strings.  Monaco also doesn't handle it well.  Use
clipboard + paste instead.

### 4. `document.execCommand('insertText')` has a size limit
Chrome limits `execCommand('insertText')` to ~1000 characters.  It also produces
untrusted events in some contexts.

### 5. Click the visible container, not the hidden textarea
The Monaco textarea is 1×18px and positioned in the corner.  CDP click
coordinates must target the visible `.monaco-editor` div (~995×1303px) for
proper focus.

### 6. Base64-encode large strings for JS interop
Passing 27K+ character strings through JSON in `Runtime.evaluate` causes
escaping issues and potential renderer crashes.  Always base64-encode in
Python and decode in the browser.

---

## Testing Checklist

When modifying Pine Script editing behavior, verify:

- [ ] **Read** returns the full source (same character count as the file)
- [ ] **Read** content matches the file line-by-line (first/last lines correct)
- [ ] **Write** with 27K+ character script succeeds (no truncation)
- [ ] **Write** content appears in the editor (verified via read-back)
- [ ] **Compile** does not error (no red squiggles in editor)
- [ ] TradingView does not crash during write (renderer stays alive)
- [ ] CDP connection stays healthy across multiple read/write cycles
- [ ] Special characters (Unicode, `//`, `{{}}`, backslashes) survive round-trip
- [ ] Works after TradingView restart (fresh session)

---

## References

- [Monaco Editor Source](https://github.com/microsoft/monaco-editor) — Code editor that powers VS Code and TradingView's Pine Editor
- [CDP Input Domain](https://chromedevtools.github.io/devtools-protocol/tot/Input/) — `Input.dispatchKeyEvent` produces trusted browser events
- [Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API) — `navigator.clipboard.writeText()` / `readText()`
- [isTrusted Property](https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted) — Read-only; only genuine user or CDP events are trusted
