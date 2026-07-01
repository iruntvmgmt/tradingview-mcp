# Sprint Hardening — Codebase Bug Fixes

**Status:** ✅ Complete

## Summary

Comprehensive hardening of `dom_utils.py`, `cdp_connection.py`, and `dom_backend.py` addressing 11 confirmed bugs (4 CRITICAL, 4 HIGH, 3 MEDIUM severity) plus 1 additional finding.

## Changes Made

### 1. `core/services/dom_utils.py` (6 fixes)

| # | Fix | Severity | Lines Changed |
|---|-----|----------|---------------|
| 1 | Added `import json` (was missing — `extract_table` would crash with `NameError`) | CRITICAL | +1 |
| 2 | Moved `import re` to module level (was inside nested loop) | MEDIUM | +1 |
| 3 | Replaced naive `.replace("'", "\\'")` with `json.dumps()` across **10 methods** — `_count_selector`, `_get_element_bounds`, `type_text`, `extract_text`, `extract_table`, `scroll_paginated_list`, `scroll_and_collect_text`, `click_at_text`, `is_visible`, `get_attribute` | CRITICAL | 10 methods |
| 4 | `extract_text` now returns `.value` for `<input>`/`<textarea>` elements instead of `.textContent` | MEDIUM | ~5 lines |
| 5 | `extract_innertext_map` now uses a polling loop with `deadline` to respect the `timeout` parameter | MEDIUM | ~8 lines |
| 6 | Regex updated to `-?[\d,.]+(?:e[+-]?\d+)?` — handles negative numbers and scientific notation | MEDIUM | 1 line |

### 2. `core/services/cdp_connection.py` (4 fixes)

| # | Fix | Severity | Lines Changed |
|---|-----|----------|---------------|
| 7 | `_read_loop` now rejects all pending CDP response futures with `CDPConnectionError` on `WebSocketException` (was silently swallowing) | HIGH | ~8 lines |
| 8 | `disconnect()` now rejects pending futures + properly `await`s reader task after `.cancel()` (was silently leaking) | HIGH | ~15 lines |
| 9 | `connect()` cleans up stale `_ws`, `_reader_task`, and `_target_id` in the retry `except` block | MEDIUM | ~15 lines |
| 10 | Added `_reject_pending_futures()` helper to deduplicate future rejection logic | — | +8 lines |

### 3. `core/services/backends/dom_backend.py` (2 fixes)

| # | Fix | Severity | Lines Changed |
|---|-----|----------|---------------|
| 11 | `DomOrderBackend.place()` now fills SL (`stop-loss`) and TP (`take-profit`) fields from recon selectors when `sl`/`tp` args are not `None` | HIGH | +6 lines |
| 12 | `DomIndicatorBackend.apply()` replaced `.replace()` escaping with `json.dumps()` — same JS injection vulnerability as dom_utils.py | HIGH | ~5 lines |

## Test Results

**74/74 tests passing** (no regressions)

## Files Modified

- `core/services/dom_utils.py` — 100 insertions, 37 deletions
- `core/services/cdp_connection.py` — significant additions
- `core/services/backends/dom_backend.py` — SL/TP + JS injection fix

## Outstanding Items

- **`side` (Buy/Sell) and `order_type` (Market/Limit)**: Cannot be implemented for `DomOrderBackend.place()` without additional selectors in `recon_findings.json`. The current recon has no Buy/Sell toggle selectors. This is a data gap, not a code bug.
