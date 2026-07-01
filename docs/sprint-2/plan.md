# Sprint 2 — Backend Strategy Pattern (Phase 2)

**Goal:** Build all backend interfaces, concrete implementations, and factory functions. No controller code yet — this is the plumbing that controllers will use.

## Prerequisites
- Sprint 1 complete with a human-reviewed `recon_findings.json`
- 24 capability keys with non-null `path` and selector arrays

## Files to Create

### 1. `core/services/backends/base.py` — Abstract Interfaces

Nine interfaces total:

| Interface | Methods |
|-----------|---------|
| `ChartBackend` | set_symbol, set_timeframe, get_ohlcv, health_check |
| `IndicatorBackend` | apply, remove, health_check |
| `BacktestBackend` | run, get_summary, get_trade_list, get_equity_curve, health_check |
| `AlertBackend` | create, edit, delete, list, health_check |
| `DrawingBackend` | create, remove, list, health_check |
| `OrderBackend` | place, modify, cancel, status, health_check |
| `ReplayBackend` | enter, step, exit, state, health_check |
| `SettingsBackend` | list_fields, read, write, health_check |
| `PineScriptBackend` | read, write, compile, read_compile_errors, read_logs, health_check |

All methods async, all return types as specified in §4.1 of the build spec.

### 2. `core/services/backends/js_backend.py`
- One class per interface: `JsChartBackend`, `JsIndicatorBackend`, `JsBacktestBackend`, `JsAlertBackend`, `JsDrawingBackend`, `JsOrderBackend`, `JsReplayBackend`, `JsSettingsBackend`, `JsPineScriptBackend`
- Each method calls `cdp.execute_js()` with JS paths from recon detail
- All selectors/JS paths injected from `detail` dict — none hardcoded

### 3. `core/services/backends/network_backend.py`
- One class per interface: same set as JS
- Each method processes captured network frames (XHR responses, WebSocket messages)
- Match patterns from recon detail

### 4. `core/services/backends/dom_backend.py`
- One class per interface: same set as JS
- Each method calls `dom.click()`, `dom.type_text()`, `dom.extract_table()`, etc.
- All selectors from recon detail — none hardcoded
- `DomOrderBackend.place()` raises `OrderSubmissionBlocked` if `confirmed=False`
- `DomReplayBackend` delegates state guards to controller level

### 5. `core/services/backends/__init__.py` — Factory Functions

Nine factory functions:
- `build_chart_backend(recon, cdp, dom, allow_unverified=False)`
- `build_indicator_backend(recon, cdp, dom, allow_unverified=False)`
- `build_backtest_backend(recon, cdp, dom, allow_unverified=False)`
- `build_alert_backend(recon, cdp, dom, allow_unverified=False)`
- `build_drawing_backend(recon, cdp, dom, allow_unverified=False)`
- `build_order_backend(recon, cdp, dom, allow_unverified=False)`
- `build_replay_backend(recon, cdp, dom, allow_unverified=False)`
- `build_settings_backend(recon, cdp, dom, allow_unverified=False)`
- `build_pinescript_backend(recon, cdp, dom, allow_unverified=False)`

Each uses `_get_capability()` helper to read path from recon and dispatch to the correct concrete class.

### 6. `tests/test_backends.py`
- Test class per backend interface
- Each confirms correct DOM/JS/Network method dispatch
- Order backend: confirm `OrderSubmissionBlocked` raised when `confirmed=False`
- Replay backend: not testing state guards here (those are controller-level)

## Definition of Done
- [ ] `base.py` — all 9 abstract interfaces defined
- [ ] `js_backend.py` — all 9 concrete JS implementations
- [ ] `network_backend.py` — all 9 concrete Network implementations
- [ ] `dom_backend.py` — all 9 concrete DOM implementations
- [ ] `__init__.py` — all 9 factory functions with verified-gate pattern
- [ ] `test_backends.py` — all backend tests passing
- [ ] No hardcoded selectors in any backend class body
