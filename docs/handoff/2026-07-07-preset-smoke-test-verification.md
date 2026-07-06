# Handoff: 2026-07-07 — preset_smoke_test pipeline verification successful; ADR-0010 guard confirmed working

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-07-strategy-tester-date-range-decision.md`
**Branch / commit at session end:** `main`

## Doc/recon consistency pass

Updated to reflect live-verified selectors:

| File | Change |
|---|---|
| `recon_findings.json` | `chart_set_visible_range` updated: YTD preset added, selector confirmed `[data-name="date-ranges-menu"]`, noted `[data-qa="date-range-menu"]` does NOT match (toolbar pill, not menu opener) |
| `docs/known_issues.json` | `chart_set_visible_range` detail_ref updated to point to Strategy Tester date-range decision handoff. Summary expanded with full preset list and mode documentation. |

### Live-verified selectors

| Selector | Match? |
|---|---|
| `[data-name="date-ranges-menu"]` | ✅ Yes — opens preset menu |
| `[data-qa="date-range-menu"]` | ❌ No — toolbar pill, different element |
| `[data-name="date-range-tab-YTD"]` | ✅ Yes — YTD preset now in list |
| `[data-name="go-to-date"]` | ✅ Yes — opens chart-only Go to Date dialog |

## Preset smoke test results

### Live pipeline verification (ETHUSD.P, 5Y preset)

| Step | Result |
|---|---|
| Symbol set | `ETHUSD.P` → `ETHUSD.P` (confirmed via `#header-toolbar-symbol-search`) |
| Preset date range | 5Y preset active → "Jul 31, 2020 — Jun 30, 2026" |
| Strategy report tab | Clicked, Overview content appears |
| Backtest summary | **Real metrics returned**: net_profit +7,055.91, max_drawdown 860.10, return_pct 0.00% |
| Backtest run | Completed successfully (GT_VP produced no trades on this setup — profit_factor "—" — but the backtest ran) |

### Guard verification

| Mode | Behavior | Status |
|---|---|---|
| `preset_smoke_test` | Warning logged: "preset_smoke_test mode: experiment results are NOT ADR-0010 compliant" | ✅ Correct |
| `disciplined_live_experiment` | `WindowGuardError` raised: "Live experiment execution is blocked" | ✅ Correct |

## Status

| Item | Status |
|---|---|
| `set_symbol` | Fixed ✅ |
| `backtest_run` selectors | Fixed ✅ |
| `chart_set_visible_range` | Open — preset-only, Free tier limitation |
| `preset_smoke_test` mode | Verified working ✅ |
| `disciplined_live_experiment` | Blocked on Free tier ✅ |
| ADR-0010 live experiments | Still blocked |
| GT_VP trades | Still zero (not investigated this session) |

## Next recommended step

The plumbing is verified. The next session can now run a full scoped experiment (single family, single parameter) in `preset_smoke_test` mode using a strategy that actually produces trades (MA Cross on BINANCE:ETHUSD.P 1h with "All" history). GT_VP should be set aside until its zero-trade issue is diagnosed separately.
