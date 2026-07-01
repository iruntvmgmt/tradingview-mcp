# Sprint 3 — Core Controllers (Phase 3, Part 1)

**Goal:** Build and test the two core domain controllers (Chart + Backtest) plus the two v4.1 dev controllers (Settings + PineScript).

## Prerequisites
- Sprint 2 complete — all 9 backend factory functions ready
- `recon_findings.json` confirmed

## Files to Create

### 1. `core/services/chart_controller.py`
- `class TVChartController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Creates `DomUtils` and builds backend via `build_chart_backend()`
  - Methods: `set_symbol(symbol)`, `set_timeframe(tf)`, `add_indicator(pine_code, name)`, `remove_indicator(name)`, `get_ohlcv(limit=500)`, `screenshot()`, `health_check()`
  - `screenshot()` calls CDP `Page.captureScreenshot` directly (always path A)

### 2. `core/services/backtest_controller.py`
- `class TVBacktestController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_backtest_backend()`
  - Methods: `run_strategy(name)`, `wait_for_complete()`, `get_performance_summary()`, `get_trade_list()`, `get_equity_curve()`, `health_check()`
  - `wait_for_complete()` polls until backtest finishes or timeout

### 3. `core/services/settings_controller.py` (NEW v4.1)
- `class TVSettingsController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_settings_backend()`
  - Methods: `list_fields(study_name)`, `read(study_name)`, `write(study_name, values: dict)`, `health_check()`

### 4. `core/services/pinescript_controller.py` (NEW v4.1)
- `class TVPineScriptController`:
  - Constructor takes `cdp`, `recon`, `allow_unverified=False`
  - Builds backend via `build_pinescript_backend()`
  - Methods: `read(script_name)`, `write(script_name, source)`, `compile(script_name)`, `read_compile_errors()`, `read_logs(script_name)`, `health_check()`
  - `read_logs()` checks if script is published/protected and raises `CapabilityUnavailable` gracefully

### 5. Tests
- `tests/test_chart_controller.py` — mocked backend, confirm method dispatch
- `tests/test_backtest_controller.py` — mocked backend, confirm wait_for_complete polling logic
- `tests/test_settings_controller.py` — mocked backend
- `tests/test_pinescript_controller.py` — mocked backend

## Definition of Done
- [ ] All 4 controllers implemented
- [ ] All 4 test files created and passing
- [ ] Controllers construct against factory functions, not directly against backends
