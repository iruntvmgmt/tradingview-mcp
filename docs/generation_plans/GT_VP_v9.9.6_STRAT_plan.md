# Generation Plan: GT_VP_v9.9.6_STRAT

> **Generated file — do not hand-edit.** Rebuilt from `pine_family_planner.py` from the Pine Script source. To change classifications, edit the associated `generation_plan.json`'s `known_overrides` section and re-run the planner.

Generated: 2026-07-06T02:14:01.273115+00:00 · Schema v1

**Total inputs found:** 209
**Excluded (cosmetic):** 74
**Unclassified (needs human review):** 0

> ⚠️ **Known issue (2026-07-05):** GT_VP produced zero trades when tested on
> SOL/USD 1m over a ~1 month window (Jun 7 – Jul 5, 2026) — likely a
> timeframe/history mismatch given GT_VP's multi-timeframe design, not
> necessarily a bug in the strategy or harness. Confirmed working setup
> from a prior session: **BINANCE:ETHUSD.P on 15m or 1h with 2+ years of
> history.** See `docs/handoff/2026-07-05-live-pipeline-attempt.md`.

## Tuning Families

| Tier | Family | Inputs | Toggles | Tunables | Group Unresolved |
|---|---|---|---|---|---|
| signal_generation | **Auction Pattern Detection** | 23 | 8 | 15 |  |
| signal_generation | **Order Flow & Statistics** | 10 | 9 | 1 |  |
| signal_generation | **Performance Optimization** | 6 | 3 | 3 |  |
| signal_generation | **🎯 Triple MA Trend Filter** | 14 | 10 | 4 |  |
| signal_generation | **📐 Market Structure** | 10 | 9 | 1 |  |
| signal_generation | **🔶 Fair Value Gaps** | 6 | 3 | 3 |  |
| entry_and_execution | **Real-Time Execution** | 3 | 2 | 1 |  |
| entry_and_execution | **Strategy Harness** | 9 | 5 | 4 |  |
| session_and_timing | **Real-Time POC** | 2 | 2 | 0 |  |
| session_and_timing | **Session Configuration** | 2 | 2 | 0 |  |
| unordered | **Dynamic Binning System** | 11 | 6 | 5 |  |
| unordered | **God Tier Features** | 31 | 19 | 12 |  |
| unordered | **Value Area Configuration** | 8 | 5 | 3 |  |

## ⚠️ Coupling Candidates (heuristic — review required)

These variable pairs appear together in conditional contexts. **This is NOT proof of dependency** — it is a prompt to check whether these families can be tuned independently.

- **God Tier Features** ↔ **Auction Pattern Detection** (heuristic — human review required, not a proven dependency)
  - ghost_atr_filter and zz_atr_len appear together (line 2184)

## Excluded (Cosmetic) — 74 inputs

These inputs affect visual appearance only and are excluded from all tuning tiers.

