# Handoff: 2026-07-07 — Alt+G Go to Date dialog works but does NOT control Strategy Tester backtest range

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-07-absolute-date-window-investigation.md`
**Branch / commit at session end:** `main`

## Accessibility status

| Item | Value |
|---|---|
| `AXIsProcessTrusted()` | `True` ✅ |
| TradingView PID | `68725` |
| `CGEventPostToPid` | Available ✅ |

## Step 1: Alt+G via CGEventPostToPid — SUCCESS ✅

Sent Option+G (macOS equivalent of Alt+G) via Quartz `CGEventPostToPid`
to PID 68725. The **Go to Date dialog opened successfully**.

This is the first time an OS-level keyboard shortcut has been successfully
dispatched to TradingView Desktop via CDP + Accessibility — confirming the
ADR-0006 pattern works for dialog-opening shortcuts, not just clipboard
operations.

## Step 2: Go to Date dialog structure

The dialog (`.wrapper-b8SxMnzX`, 302×616px) has:

### "Date" tab
- Calendar picker (month grid, navigation arrows)
- Single date selection

### "Custom range" tab — THIS HAS EXACTLY WHAT WE NEED
Four input fields:

| Field | Selector | Type | Placeholder |
|---|---|---|---|
| **Start date** | `input[data-name="start-date-range"]` | `text` | `YYYY-MM-DD` |
| Start time | `input[role="combobox"]` (disabled) | `combobox` | time picker |
| **End date** | `input[data-name="end-date-range"]` | `text` | `YYYY-MM-DD` |
| End time | `input[role="combobox"]` (disabled) | `combobox` | time picker |

Buttons:
- `button[data-name="submit-button"]` — "Go to" (submit)
- `button[data-qa-id="close"]` — close dialog

## Step 3: Custom range submission — PARTIAL SUCCESS

Dates were successfully set via native setter and submitted:
```
Set: 2024-06-03 to 2024-08-30
Submit: submitted
```

But the Strategy Tester's backtest period did NOT change — remained at
"Jul 31, 2020 — Jun 30, 2026".

### Root cause: Chart view ≠ Strategy Tester backtest period

The **Go to Date dialog controls the chart canvas's visible range**, not
the Strategy Tester's backtest date range. These are two separate controls:

| Control | What it sets | How |
|---|---|---|
| Go to Date (Alt+G) | Chart visible range | Custom date/timerange inputs |
| Strategy Tester presets | Backtest calculation period | Preset buttons (1D–All) |

The Go to Date Custom range dialog can set exact start/end dates on the
**chart view**, but the **Strategy Tester** ignores this and continues to
use its own preset-based date range for backtest calculations.

## Conclusion: ADR-0010 still blocked 🔴

Even though the Go to Date Custom range dialog provides exact start/end
date inputs, it does NOT control the Strategy Tester's backtest period.
The backtest date range remains preset-only.

| Capability | Status |
|---|---|
| `supports_absolute_visible_range()` | `False` (unchanged) |
| `WindowGuardError` | Active (unchanged) |
| Alt+G Custom range dialog | Works, but doesn't control backtest range |
| Strategy Tester date range | Preset-only (unchanged) |
| ADR-0010 live experiments | Still blocked |

## What was gained

1. **CGEventPostToPid keyboard shortcuts work** — the ADR-0006 pattern
   extends beyond clipboard to dialog-opening shortcuts.
2. **Go to Date dialog fully mapped** — selectors, fields, tabs, buttons
   are all documented.
3. **Confirmed the architectural split**: Chart view and Strategy Tester
   have independent date range controls.

## Recommendation

The Strategy Tester's preset limitation is the root issue. Future work
should explore:
1. Whether the Strategy Tester can be forced to follow the chart's Go
   to Date range (e.g., by toggling the "detached" mode or a linking
   setting)
2. Whether the Strategy Tester's date range dropdown can be extended
   with custom dates via DOM manipulation (injecting a new option into
   the presets list)
3. Whether a different TradingView plan (Pro/Premium) exposes deep
   backtesting controls that include custom date ranges

For now, `ExperimentController` remains safely blocked by the
`WindowGuardError` guard.
