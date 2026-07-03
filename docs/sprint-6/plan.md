# Sprint 6 — MCP Server + Integration (Phase 4)

**Goal:** Wire all controllers into the MCP server, add startup validation, create launch scripts, and run end-to-end integration tests against the live app.

## Prerequisites
- All 9 controllers built and unit-tested (Sprint 3 + Sprint 4)
- `recon_findings.json` with all 24 capabilities verified

## Files to Create/Modify

### 1. `server.py`
- Create MCP server instance
- **Startup validation (§6.1):**
  - Load `recon_findings.json`
  - Check `schema_version == 2` — if not, raise `ReconRequired`
  - Construct all 9 domain controllers with `allow_unverified=False`
- **MCP Tools (28 total):**

| Tool | Function |
|------|----------|
| `tv_recon_run()` | Run recon interactively |
| `tv_desktop_launch(port=8315)` | Launch TV Desktop with debug port |
| `tv_set_symbol(symbol)` | Change chart symbol |
| `tv_set_timeframe(timeframe)` | Change chart timeframe |
| `tv_apply_script(pine_code, name)` | Apply indicator/strategy |
| `tv_remove_indicator(name)` | Remove indicator |
| `tv_get_chart_data(limit=500)` | Get OHLCV data |
| `tv_run_backtest(name)` | Run strategy backtest |
| `tv_get_backtest_summary()` | Get backtest results |
| `tv_get_backtest_trades()` | Get trade list |
| `tv_get_backtest_equity_curve()` | Get equity curve |
| `tv_alert_create(symbol, condition, message)` | Create price alert |
| `tv_alert_edit(alert_id, condition, message)` | Edit alert |
| `tv_alert_delete(alert_id)` | Delete alert |
| `tv_alert_list()` | List active alerts |
| `tv_drawing_create(drawing_type, points)` | Create drawing |
| `tv_drawing_remove(drawing_id)` | Remove drawing |
| `tv_drawing_list()` | List drawings |
| `tv_order_place(symbol, side, size, order_type, sl, tp, confirm)` | Place paper order (confirm required) |
| `tv_order_modify(order_id, size, sl, tp)` | Modify order |
| `tv_order_cancel(order_id)` | Cancel order |
| `tv_order_status()` | Read positions/orders |
| `tv_replay_enter(start_bar)` | Enter replay mode |
| `tv_replay_step(bars=1)` | Step replay |
| `tv_replay_exit()` | Exit replay mode |
| `tv_replay_state()` | Read replay state |
| `tv_screenshot()` | Capture chart screenshot |
| `tv_settings_list_fields(study_name)` | List inputs |
| `tv_settings_read(study_name)` | Read input values |
| `tv_settings_write(study_name, values)` | Write input values |
| `tv_pine_read(script_name)` | Read Pine source |
| `tv_pine_write(script_name, source)` | Write Pine source |
| `tv_pine_compile(script_name)` | Trigger compile |
| `tv_pine_compile_errors()` | Read compile errors |
| `tv_pine_logs(script_name)` | Read Pine Logs |
| `tv_diagnostics()` | Full health check |
| `tv_disconnect()` | Disconnect CDP |

### 2. `tests/test_integration.py`
- One live-app test per domain (annotated with `@pytest.mark.integration`)
- Chart: set symbol, set timeframe, get data
- Backtest: run one, get summary
- Alerts: create + list + delete
- Drawings: create + list + remove
- Orders: place (confirmed=True) + status + cancel
- Replay: enter + step + state + exit

### 3. `scripts/launch_tv_desktop.sh` (macOS/Linux)
- Launch TradingView Desktop with `--remote-debugging-port=8315` baked in
- Detect OS and use correct app path

### 4. `scripts/launch_tv_desktop.ps1` (Windows) — optional, stub if no Windows
### 5. `README.md`
- Installation, configuration, usage examples
- Safety warnings about order panel
- Maintenance protocol (tv_diagnostics → tv_recon_run → fix → commit)

## Definition of Done
- [ ] `server.py` registers all 36 MCP tools
- [ ] Startup validation rejects schema_version != 2
- [ ] All 9 controllers constructed on startup with `allow_unverified=False`
- [ ] Integration tests pass against live TV Desktop
- [ ] Launch scripts working on macOS
- [ ] README complete with safety warnings
- [ ] `tv_diagnostics()` returns health for all 9 domains
