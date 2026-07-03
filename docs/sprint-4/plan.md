# Sprint 4 — Expansion Controllers (Phase 3, Part 2)

**Goal:** Build and test the four new domain controllers: Alerts, Drawings, Order Panel, and Replay Mode.

## Prerequisites
- Sprint 3 complete
- Backend factory functions for alert/drawing/order/replay debugged and working

## Files to Create

### 1. `core/services/alert_controller.py`
- `class TVAlertController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_alert_backend()`
  - Methods: `create(symbol, condition, message)`, `edit(alert_id, condition, message)`, `delete(alert_id)`, `list()`, `health_check()`

### 2. `core/services/drawing_controller.py`
- `class TVDrawingController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_drawing_backend()`
  - Methods: `create(drawing_type, points)`, `remove(drawing_id)`, `list()`, `health_check()`
  - `points` format: list of `{"bar_index" or "time": ..., "price": ...}` dicts

### 3. `core/services/order_controller.py`
- `class TVOrderController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_order_backend()`
  - Methods: `place(symbol, side, size, order_type, sl, tp, confirmed)`, `modify(order_id, size, sl, tp)`, `cancel(order_id)`, `status()`, `health_check()`
  - **Safety:** `place()` checks `confirmed` at controller level too (defense in depth) — raises `OrderSubmissionBlocked` if not confirmed

### 4. `core/services/replay_controller.py`
- `class TVReplayController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_replay_backend()`
  - **State guards:** `_in_replay` flag tracks mode — `enter()` sets True, `exit()` sets False
  - Methods: `enter(start_bar)`, `step(bars=1)`, `exit()`, `state()`, `health_check()`
  - Raises `ReplayStateError` on invalid transitions (step before enter, enter while entered, exit while not in replay)

### 5. Tests
- `tests/test_alert_controller.py` — mocked backend, confirm create→list→delete dispatch
- `tests/test_drawing_controller.py` — mocked backend
- `tests/test_order_controller.py` — **critical:** confirm `place(confirmed=False)` raises before reaching backend; confirm `place(confirmed=True)` dispatches correctly
- `tests/test_replay_controller.py` — confirm state-guard sequences raise `ReplayStateError` correctly

## Definition of Done
- [ ] All 4 controllers implemented with state guards where applicable
- [ ] All 4 test files created and passing
- [ ] Order controller has defense-in-depth: controller-level + backend-level confirmed guard
- [ ] Replay controller correctly catches invalid mode transitions
