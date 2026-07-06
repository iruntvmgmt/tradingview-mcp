# Handoff: 2026-07-07 — Absolute date-window investigation: no working approach found on TV Desktop 3.2.0

**Agent:** Sage (backend)
**Preceding handoff:** `docs/handoff/2026-07-07-window-guard-and-free-tier-preflight.md`
**Branch / commit at session end:** `main`

## Investigation goal

Find a reliable way to set exact absolute visible/date ranges in TradingView
Desktop 3.2.0, so ADR-0010 live experiments can run with real chronological
train/validation/holdout windows instead of trailing presets.

## Path 1: Alt+G / Go to Date dialog 🔴 — blocked by macOS CDP limitation

- `_widgetOptions.goToDateEnabled` is `true` — the feature exists.
- CDP `Input.dispatchKeyEvent` with Alt+G modifier does NOT trigger
  TradingView's keyboard shortcut handler on macOS. The CDP key event
  reaches the renderer but the app-level menu shortcut is handled at the
  Electron layer, not the Chromium renderer.
- Same limitation documented in ADR-0006 (Cmd+A/C/V for paste/copy).
- **Potential workaround**: `CGEventPostToPid` could send a real Alt+G
  keystroke at the OS level — but this requires macOS Accessibility
  permission (`AXIsProcessTrusted`), which is currently disabled on the
  test machine.
- **If Alt+G can be opened**: The dialog would need to be inspected for
  its date fields. Likely a single "go to" date (not a start/end range).

## Path 2: Strategy Tester date-range controls 🔴 — presets only

- The date range expanded area (`.dateRangeExpanded-MzM01zOE`) contains
  only preset tab buttons:
  `1D, 5D, 1M, 3M, 6M, YTD, 1Y, 5Y, All`
- Zero `<input>` elements, zero date pickers, zero custom range controls.
- No text inputs for typing start/end dates.
- The `_activeChartRangeState._value` confirms all options are
  `type: "period-back"` (preset trailing ranges), not absolute ranges.

## Path 3: Time-axis interaction 🔴 — canvas/SVG rendering

- Chart time axis at `y=878, height=28` renders dates as canvas/SVG.
- No clickable DOM elements, no date labels as text nodes.
- The `_timeAxisWidget` has a `chart` property, but the chart object has
  no `timeScale()` method or range-setting functions.

## Path 4: Internal TradingView globals 🔴 — no range API exposed

Systematically inspected every known global:

| Global | Range/time methods found | Result |
|---|---|---|
| `_exposed_chartWidgetCollection` | `_dateRangeLock`, `_internalDateRangeLock` (reactive values only), `_onZoom`, `_onScroll`, `_muteSyncDateRangeEvents` | No `setRange` or `setVisibleRange` |
| `TradingViewApi` | `_activeChartRangeState` (preset descriptors only) | No range-setting methods |
| `ChartApiInstance` | No range/time methods (data/metadata API) | No chart controls |
| `widgetbar` | `chartWidgetCollection` (same as `_exposed`) | Layout-only methods |
| `_subscribedChartWidget` | `_timeAxisWidget`, `_onWheelBound`, `_updateScalesActions` | UI-level only, no range API |
| `_timeAxisWidget.chart` | `_updateThemedColorBound`, `_updateScalesActions` | No `timeScale()`, no range methods |
| `_activeChartWidgetWV` | Zero functions — pure state object | No methods at all |
| `_dateRangeLock._value` | Reactive value (MobX-style), listens to preset changes | Contains preset list, not current range |

**Key finding**: TV Desktop 3.2.0's internal API does not expose any
`setVisibleRange()`, `setRange()`, `goToDate()`, or equivalent method.
The chart rendering engine is encapsulated and only manipulated through
the preset UI and mouse gestures (scroll-to-zoom, drag-to-pan).

## What MIGHT work (not tested)

1. **CGEventPostToPid Alt+G** (requires Accessibility permission):
   - Send real Alt+G keystroke → Go to Date dialog opens
   - Type date → Enter → chart navigates to that date
   - This only sets ONE anchor date, not a start/end range
   - Would need two separate operations (go to start, then zoom/scroll to end)

2. **OS-level mouse automation**: Simulate clicking and dragging on the
   time axis to set a specific range. Extremely fragile — depends on
   pixel coordinates and chart zoom state.

## Current status

| Item | Status |
|---|---|
| `supports_absolute_visible_range()` | `False` (all backends) |
| `WindowGuardError` | Active — blocks unsafe ADR-0010 experiments |
| `chart_set_visible_range` known_issue | Still open |
| `chart_set_visible_range` recon verified | `False` |

## Recommendation

**Do NOT attempt to implement absolute date-window control via internal
API on TV Desktop 3.2.0. No such API exists.**

The most viable path forward is:
1. Enable macOS Accessibility permission on the test machine
2. Use `CGEventPostToPid` to trigger Alt+G
3. Inspect the Go to Date dialog DOM for its date input fields
4. If the dialog supports a date picker, implement a two-step approach:
   navigate to start date, then zoom/scroll to end date
5. Even this only provides approximate windows (not exact start/end pairs)

**Alternative**: Accept the preset limitation for now and use the widest
available preset ("All") for single-window experiments, documenting that
ADR-0010 window discipline cannot be enforced until either:
- TV Desktop exposes a date range API in a future version, or
- Accessibility-enabled CGEventPostToPid proves the Alt+G path viable

## Next session

If Accessibility permission can be enabled:
```
Read docs/handoff/2026-07-07-absolute-date-window-investigation.md.
1. Verify AXIsProcessTrusted() returns True
2. Send Alt+G via CGEventPostToPid
3. Dump the Go to Date dialog DOM
4. Test typing a specific date and pressing Enter
5. Verify the chart navigates to that date
```
