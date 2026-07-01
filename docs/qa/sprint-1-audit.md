# Sprint 1 — Code Audit

**Auditor:** Ivy (QA Engineer)  
**Date:** 2026-07-01  
**Scope:** All Sprint 1 source files (errors.py, cdp_connection.py, dom_utils.py, recon.py, backends/__init__.py, test_cdp_connection.py)  
**Status:** ❌ BLOCKED

---

## Summary

| Severity | Count | Key findings |
|----------|-------|-------------|
| 🔴 Blocker | 2 | Broken imports + late import in `backends/__init__.py` |
| 🟠 Major | 3 | Dead JS upgrade logic, redundant CDP calls, double bounds query |
| 🟡 Minor | 6 | Unused imports/vars, deprecated API, naming shadow, ignored fallbacks |
| **Total** | **11** | |

**Verdict:** Cannot proceed to Sprint 2 until Bugs 1–2 are resolved. Bugs 3–4 directly impact the quality of `recon_findings.json` and should be fixed before running the live recon session.

---

## 🔴 Blocker

### Bug 1 — `backends/__init__.py` imports nonexistent modules at top level

**File:** `core/services/backends/__init__.py` (lines 4–46)  
**Severity:** Blocker

**Description:**  
The file imports from `base.py`, `dom_backend.py`, `js_backend.py`, and `network_backend.py` — none of which exist yet (they belong to Sprint 2). Any `import` of this module crashes with `ModuleNotFoundError` immediately.

```python
from core.services.backends.base import (        # ← ModuleNotFoundError!
    ChartBackend, IndicatorBackend, ...
)
```

**Impact:** All 9 factory functions (`build_chart_backend`, `build_alert_backend`, etc.) are completely unreachable until Sprint 2 builds the backend modules.

**Fix:** Either stub the missing modules in Sprint 1, or guard the imports behind `TYPE_CHECKING` blocks.

---

### Bug 2 — `CapabilityUnavailable` used before import

**File:** `core/services/backends/__init__.py` (line 51, import at line 174)  
**Severity:** Blocker

**Description:**  
`_get_capability()` raises `CapabilityUnavailable` on line 70, but the import statement lives at the very bottom of the file:

```python
def _get_capability(recon: dict, cap_name: str, allow_unverified: bool = False) -> dict:
    caps = recon.get("capabilities", {})
    entry = caps.get(cap_name)
    if entry is None:
        raise CapabilityUnavailable(...)  # ← NameError at runtime

# ... 100+ lines of factory functions ...

# Import needed for CapabilityUnavailable used in _get_capability
from core.services.errors import CapabilityUnavailable  # ← too late
```

**Impact:** Even if Bug 1 is fixed, calling any factory function raises `NameError: name 'CapabilityUnavailable' is not defined`.

**Fix:** Move `from core.services.errors import CapabilityUnavailable` to the top of the file alongside the other imports.

---

## 🟠 Major

### Bug 3 — `_probe_known_paths` upgrade logic is dead code

**File:** `core/services/recon.py` (lines 146–158)  
**Severity:** Major

**Description:**  
The JS path upgrade logic in `_probe_known_paths` never fires because it checks for window global names against capability-name keys.

```python
CAP_JS_PATH_MAP: dict[str, str] = {
    "symbol_control": "window.tvWidget?.activeChart?.setSymbol",  # key = cap name
    ...
}

# In _probe_known_paths:
for path in KNOWN_JS_PATHS:                     # path = "window.tradingView"
    ...
    if exists and path in CAP_JS_PATH_MAP:      # "window.tradingView" in keys? → ALWAYS FALSE
```

`KNOWN_JS_PATHS` contains window global names like `"window.tradingView"`, but `CAP_JS_PATH_MAP` keys are capability names like `"symbol_control"`. The `in` check always evaluates `False`, so the capability → JS upgrade path never fires — even when a real JS API exists.

**Impact:** The recon tool will never discover JS-based capabilities, defaulting to DOM for everything even when a faster JS path exists.

**Fix:** Build a reverse map from JS path → capability name, or iterate over `CAP_JS_PATH_MAP` values and check those against the detected globals.

---

### Bug 4 — Redundant `typeof` JS call in `_probe_known_paths`

**File:** `core/services/recon.py` (lines 149–156)  
**Severity:** Major

**Description:**  
The same `typeof` expression is evaluated twice via CDP:

```python
result = await self._cdp.execute_js(f"typeof ({path})")   # ← call #1
typeof_val = result.get("result", {}).get("value", "undefined")

# ... later, for the same path ...
method_result = await self._cdp.execute_js(f"typeof ({path})")  # ← call #2 — SAME!
mtype = method_result.get("result", {}).get("value", "undefined")
```

Since `typeof_val` already contains the type string (e.g., `"function"`, `"undefined"`), call #2 is entirely redundant. It doubles CDP round-trips unnecessarily.

**Impact:** Slows down the recon session with an extra CDP call for every JS path probed.

**Fix:** Reuse `typeof_val` — replace the second call with `mtype = typeof_val`.

---

### Bug 5 — `_click_selector` queries DOM bounding box twice

**File:** `core/services/dom_utils.py` (lines 74–84)  
**Severity:** Major

**Description:**  
The bounding box of the target element is fetched twice — once via `_get_element_bounds()` (a CDP `Runtime.evaluate` call) and again via `getBoundingClientRect()` inside the `execute_js` string:

```python
bounds = await self._get_element_bounds(selector)   # ← call #1
x = bounds["x"] + bounds["w"] / 2
y = bounds["y"] + bounds["h"] / 2
await self._cdp.execute_js('''
    ...
    const rect = el.getBoundingClientRect();        # ← call #2 (inside JS)
    ...
''')
```

Additionally, dispatching synthetic `MouseEvent` via JS may not work on canvas elements or WebGL contexts — CDP's native `Input.dispatchMouseEvent` command is more reliable.

**Impact:** Inefficient DOM access. May fail to click on canvas-based UI elements (e.g., chart canvases, drawing tool buttons).

**Fix:** Use computed pixel coordinates from call #1 with CDP `Input.dispatchMouseEvent`, or compute everything in a single JS call. Prefer CDP's native input dispatch over synthetic JS events.

---

## 🟡 Minor

### Bug 6 — `_snapshot_outer_html` ignores fallback selectors

**File:** `core/services/recon.py` (lines 235–247)  
**Severity:** Minor

**Description:**  
Comma-separated fallback selectors are passed to `document.querySelector()`, which only evaluates the first selector. `querySelectorAll()` is needed for fallback support.

```python
("pine_editor", "Pine Editor", "div[class*='pine-editor'], div[class*='editor']"),
#                                                            ^^^^^^^^^^^^^^^^^^
# This fallback is silently ignored by querySelector()
```

**Fix:** Use `document.querySelectorAll()` and return the first match, or split on commas and try each individually.

---

### Bug 7 — Network events collected too late, may miss OHLCV data

**File:** `core/services/recon.py` (lines 192–207)  
**Severity:** Minor

**Description:**  
Network events are drained via `get_network_events()` only after all 9 interactive steps complete. Early steps (symbol change, timeframe) may have their WebSocket frames overwritten or pushed out of the buffer. No filtering happens during capture.

**Fix:** Periodically sample events between steps, or buffer with a large capacity, or filter for OHLCV patterns during capture rather than at the end.

---

### Bug 8 — `import time` in `cdp_connection.py` is unused

**File:** `core/services/cdp_connection.py` (line 7)  
**Severity:** Minor

```python
import time  # ← never referenced in this file
```

**Fix:** Remove the unused import.

---

### Bug 9 — `DEFAULT_TV_PATHS` constant in `cdp_connection.py` is unused

**File:** `core/services/cdp_connection.py` (lines 22–27)  
**Severity:** Minor

```python
DEFAULT_TV_PATHS: dict[str, str] = {
    "darwin": "/Applications/TradingView.app/Contents/MacOS/TradingView",
    "linux": "tradingview",
    "win32": r"C:\Program Files\TradingView\TradingView.exe",
}
```

This dict is defined but never referenced. The `launch()` method has its own inline platform-detection logic.

**Fix:** Either use this dict in `launch()` or remove it.

---

### Bug 10 — `asyncio.get_event_loop()` is deprecated in Python 3.12

**File:** `core/services/cdp_connection.py` (line 310)  
**Severity:** Minor

```python
future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
```

`get_event_loop()` is deprecated in Python 3.12 in favour of `get_running_loop()`.

**Fix:** Replace with `asyncio.get_running_loop().create_future()`.

---

### Bug 11 — `errors.py` shadows Python built-in `ConnectionError`

**File:** `core/services/errors.py` (line 22)  
**Severity:** Minor

```python
class ConnectionError(TvMcpError):  # shadows builtins.ConnectionError
```

This shadows the standard library's `ConnectionError`. While not a runtime problem in the current code (the custom class is explicitly imported), it can cause confusion and may mask built-in errors in `except` clauses.

**Fix:** Rename to `CDPConnectionError` to clearly differentiate from the built-in.

---

## Files Audited

| File | Lines | Issues Found |
|------|-------|--------------|
| `core/services/errors.py` | 52 | 1 (Bug 11) |
| `core/services/cdp_connection.py` | 330 | 4 (Bugs 8, 9, 10, 11-related) |
| `core/services/dom_utils.py` | 265 | 1 (Bug 5) |
| `core/services/recon.py` | 370 | 4 (Bugs 3, 4, 6, 7) |
| `core/services/backends/__init__.py` | 175 | 2 (Bugs 1, 2) |
| `tests/test_cdp_connection.py` | 102 | 0 |

---

## Recommended Fix Order

1. **Bug 1 + Bug 2** (blockers) — fix `backends/__init__.py` imports
2. **Bug 3 + Bug 4** — fix `recon.py` JS probe logic before running recon
3. **Bug 5** — fix `dom_utils.py` click reliability before backends use it
4. **Bugs 6–11** — cleanup, can be done in parallel with Sprint 2
