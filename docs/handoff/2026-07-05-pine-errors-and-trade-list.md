# Handoff: 2026-07-05 — pine_compile_errors_read verified; backtest_trade_list blocked by TradingView paywall

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-04c-cdp-mousemoved-dialog-fix.md`
**Branch / commit at session end:** `main` @ (will be committed)

## Priority 1: pine_compile_errors_read — VERIFIED ✅

Implemented structured error reading from the Pine Editor console panel.

### DOM structure discovered
- Error entries: `.selectable-v4HmQr2o.error-v4HmQr2o`
- Warning entries: `.selectable-v4HmQr2o.warning-v4HmQr2o`
- Timestamp: `.time-v4HmQr2o`
- Format: `HH:MM:SS AM/PM Error at LINE:COL MESSAGE`

### Implementation
`DomPineScriptBackend.read_compile_errors()` now:
1. Finds all `.selectable-v4HmQr2o` entries in the Pine Editor
2. Locates the last "Compiling..." entry (to filter out stale errors from prior runs)
3. Parses error/warning entries after that point
4. Returns structured `[{type, line, column, message}]`

### Verified results
- **Positive test** (broken script `plot(close`):
  `[{type: "error", line: 3, column: 1, message: "Syntax error: Missing closing parenthesis"}]`
- **Negative test** (valid script): `[]` — no stale errors leaked through
- Both PASS through the real `DomPineScriptBackend.read_compile_errors()` method

## Priority 2: backtest_trade_list — BLOCKED by paywall

Individual trade records are not accessible in TradingView Desktop 3.2.0 free tier. The Strategy Tester's "Trades analysis details" tab shows aggregated statistics (Outliers P&L, trade type counts) but individual per-trade Entry/Exit/P&L records are behind an "Upgrade to get full access to Strategy report data" paywall.

The `backtest_summary` capability provides net_profit, sharpe, profit_factor, max_drawdown, avg_pnl, return_pct, total_trades — sufficient for most strategy evaluation. Individual trade lists are a nice-to-have but not available without a paid plan.

Added to `known_issues.json` as major severity, blocks_goal: false.

## Files changed

| File | Change |
|------|--------|
| `core/services/backends/dom_backend.py` | Rewrote `read_compile_errors()` with structured parsing using `.error-v4HmQr2o` selectors |
| `recon_findings.json` | pine_compile_errors_read → verified:true with detailed selectors |
| `docs/known_issues.json` | Added backtest_trade_list paywall entry |
| `docs/STATUS.md` | Regenerated |

## Cold-start prompt

```
Read docs/handoff/2026-07-05-pine-errors-and-trade-list.md and docs/STATUS.md.
pine_compile_errors_read is done. backtest_trade_list is blocked by paywall.
Next: backtest_equity_curve (lowest priority), or tackle remaining unverified
capabilities (alert_*, drawing_list, order_*, replay_*).
```
