# Sprint 1 — Foundation

**Status:** 🟡 In Progress

## Progress Log
| Date | Phase | Status | Notes |
|------|-------|--------|-------|
| 2026-07-01 | Planning | ✅ | Sprint plan created |
| 2026-07-01 | Scaffold | ✅ | pyproject.toml, directory structure, __init__.py files created |
| 2026-07-01 | errors.py | ✅ | 7 domain error types implemented |
| 2026-07-01 | cdp_connection.py | ✅ | Full CDP transport: launch, connect, execute_js, listen_network, health_check |
| 2026-07-01 | dom_utils.py | ✅ | All DOM primitives: resolve_selector, click, type_text, extract_table, click_at_coordinates |
| 2026-07-01 | recon.py | ✅ | Interactive recon tool with ~4-min guided protocol |
| 2026-07-01 | Tests | ✅ | 10/10 tests passing (5 unit + 5 integration against live TV Desktop) |
| 2026-07-01 | Python env | ✅ | Python 3.12.5 venv with all deps installed |
| 2026-07-01 | QA Audit | ✅ | Ivy filed 11 bugs — Sage fixed all 11 (commit `db9a9cf`) |
| 2026-07-01 | Ready | ✅ | All blockers cleared, ready for recon session |
| 2026-07-01 | Recon Run | ✅ | 9-step guided session completed |
| 2026-07-01 | Target Fix | ✅ | Discovered TV Desktop has 10+ renderer targets; fixed `_find_main_target` to score and select the real chart page at `tradingview.com/chart` |
| 2026-07-01 | DOM Probe | ✅ | Deep DOM probe on real chart page discovered stable selectors using `data-name`, `aria-label`, `role`, and `#drawing-toolbar` ID — all hashed class names confirmed as non-portable |
| 2026-07-01 | recon_findings.json | ✅ | Populated with real selectors; 12/33 capabilities verified with confirmed selectors |
| 2026-07-01 | Interactive Panel Probe | ✅ | All 9 panels probed: Symbol Search, Timeframe, Pine Editor (#pine-editor-dialog), Strategy Tester, Alert ([data-qa-id=alerts-create-edit-dialog]), Drawing Toolbar, Order Panel, Replay |

## Next Steps
- [ ] Human review of recon_findings.json — verify verified selectors are correct
- [ ] **Begin Sprint 2** (backend interfaces: base.py, dom_backend.py, js_backend.py, network_backend.py)

## Stable Selectors Summary
| Panel | Selector |
|-------|----------|
| Symbol Search | `button[data-name="header-toolbar-symbol-search"]` |
| Timeframe (bar) | `button[role="radio"][data-value="{value}"]` |
| Timeframe (dropdown) | `button[aria-label="{N} minute(s)/hour(s)/day(s)"]` |
| Indicators | `button[data-name="open-indicators-dialog"]` |
| Alert button | Button with text "Alert" |
| Alert dialog | `[data-qa-id="alerts-create-edit-dialog"]` |
| Pine Editor | `#pine-editor-dialog` |
| Drawing Toolbar | `#drawing-toolbar` + `button[aria-label="Trendline"/"Fib retracement"/etc]` |
| Replay | Button with text "Replay" |
| Trade/Order | Button with text "Trade" |

## Key Discoveries
1. **Multi-process architecture:** TV Desktop has ~11 CDP targets (chart, toast, new-tab, tooltip, etc.)
2. **No JS API:** `window.TradingView` exists as an object but `tvWidget` / chart APIs don't — DOM (Path C) is correct for all domains
3. **Hashed CSS classes:** All class names like `button-HdKhcTye` change per build — must use `data-name`, `aria-label`, `role` for stable selectors
4. **Stable IDs found:** `#drawing-toolbar` is a stable element ID
5. **Data attributes:** Timeframe buttons use `data-value`; indicators use `data-name="open-indicators-dialog"`
