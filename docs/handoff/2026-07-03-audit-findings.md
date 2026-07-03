# Handoff: 2026-07-03 — Audit of settings/indicator-apply/OHLCV capabilities; documentation system introduced

**Agent:** audit-session (Claude, via chat — not a Claude Code session against the live repo)
**Preceding handoff:** none — first entry. Prior context lived only in chat transcripts and commit
messages (`cleanup: remove old codebase remnants from merge`, the v1.0.0 tag message, etc.); this
log did not exist before this session.
**Branch / commit at session end:** `main` @ `2109133` (no code changes made this session — audit + documentation only)

## 1. What changed this session

- No production code was modified. This was a read-only audit against the
  cloned `main` branch at commit `2109133` (the "cleanup: remove old
  codebase remnants from merge" commit, immediately after the v1.0.0 tag
  push described in the prior chat-transcript handoff).
- Introduced a documentation system (this file is part of it):
  - `docs/STATUS.md` — **generated file**, do not hand-edit. Built by
    `scripts/generate_status.py` from `recon_findings.json` +
    `docs/known_issues.json`.
  - `docs/known_issues.json` — hand-maintained source of truth for known
    issues per capability.
  - `docs/adr/0001` through `0003` — retroactive ADRs documenting decisions
    that were already implicit in the code (DOM-first routing, Monaco
    clipboard strategy, unit/integration test boundary).
  - `docs/handoff/` — this log, going forward.
- No `recon_findings.json` entries were changed. In particular,
  `indicator_apply` remains marked `verified: true` even though § 3 below
  explains why that's not trustworthy — flipping it was left to whoever
  does the actual fix, so the fix and the recon update land together.

## 2. What is now verified true (and how)

- Confirmed by direct code read (not live-session testing — no TradingView
  Desktop instance was available this session) that 100% of
  `recon_findings.json` capabilities currently use `"path": "dom"`. The
  `js` and `network` backends are fully-stubbed and inert for every
  capability today (see ADR-0001).
- Confirmed by code read that `DomPineScriptBackend.read` / `write` /
  `compile` correctly implement the clipboard-based Monaco strategy (see
  ADR-0002) and are marked `verified: true` in recon — this matches the
  commit history (`fix: add Cmd+X cut to Monaco write pipeline...`,
  `fix: use JS element.click() for Pine compile...`), which is evidence
  someone previously iterated this against a real instance. Treated as
  trustworthy on that basis, though not independently re-verified live this
  session.
- Confirmed by reading every test file that all 69 existing tests mock
  `DomUtils`/`CDPConnection` at the constructor boundary — none exercise
  real selector resolution. See ADR-0003.

## 3. What is still broken / unknown

All tracked in `docs/known_issues.json` — see `docs/STATUS.md` for the
generated table. Summary:

- **`settings_list_fields` / `settings_read` / `settings_write`**
  (blocker, blocks primary goal) — not really implemented. `write()` uses
  generic guessed selectors (`input[name=]`, `[data-name=]`, placeholder
  match) never confirmed against TradingView's actual Inputs dialog DOM.
  `list_fields`/`read` return unparsed raw dialog text, not structured
  data. Recon already correctly marks these `verified: false`.
- **`indicator_apply`** (blocker, blocks primary goal) — marked
  `verified: true` in recon, but this appears to be **incorrect**.
  `editor_selectors` and `add_to_chart_selectors` in `recon_findings.json`
  are identical (both target the built-in "Browse Indicators" dialog
  button, not the Pine Editor), and the write logic uses the naive
  `textarea.value =` approach ADR-0002 documents as broken. This was not
  re-tested live this session (no TradingView Desktop instance available)
  — flagged from code/recon inspection alone. **Recommend a live check
  before trusting this capability either way**, and either fix it or flip
  `verified: false` pending the fix.
- **`ohlcv_read`** (major, does not block primary goal) — dead end on both
  implemented paths (DOM punts to network; network stub also unconditionally
  raises `CapabilityUnavailable` despite its own docstring). Requires CDP
  `Network` domain event-buffering that doesn't exist yet in
  `cdp_connection.py`.
- Unrelated, low-priority: `CONTRIBUTING.md` still references
  `github.com/atilaahmettaner/tradingview-mcp` (a different, unrelated
  fork) rather than this repo — likely inherited during the sprint/merge
  history and never updated. Cosmetic; not tracked in `known_issues.json`
  since it's not a capability issue.

## 4. Next steps (in priority order)

See the original fix plan doc (delivered in-chat this session, not yet
committed to the repo as a file — recommend committing it as
`docs/AUDIT_AND_FIX_PLAN.md` alongside this handoff) for full detail. Order:

1. Get a live TradingView Desktop + CDP session running
   (`scripts/launch_tv_desktop.sh`), confirm `tv_diagnostics` reports
   `cdp_connected: true`.
2. Recon the real Inputs dialog DOM structure (dump via
   `ReconRunner._snapshot_outer_html`), rewrite `DomSettingsBackend`
   against real selectors, add an integration test (ADR-0003), flip
   `settings_*` to `verified: true` in recon once confirmed, update
   `docs/known_issues.json` (mark those three issues `status: fixed`) and
   regenerate `docs/STATUS.md`.
3. Recon the real "open Pine Editor for a new/blank script" trigger,
   rewrite `DomIndicatorBackend.apply` to delegate to
   `DomPineScriptBackend` (per ADR-0002) instead of reimplementing Monaco
   write. Same close-out steps as above.
4. Manually verify the full loop once: write/apply a strategy → tune an
   input via settings → run backtest → read summary → confirm an agent can
   actually tell whether a change helped.
5. `ohlcv_read` — lower priority, only needed if raw price-series access
   (beyond backtest summaries) is required.
6. Housekeeping: fix `CONTRIBUTING.md`'s wrong repo reference; remove the
   dead unreachable code in `DomBacktestBackend.health_check`
   (`dom_backend.py`, ~line 221).

## Decisions made this session (if any)

- `docs/adr/0001-dom-first-capability-routing.md` — documents the existing
  (already-implemented) decision to route all capabilities through DOM and
  treat JS/Network backends as inert stubs.
- `docs/adr/0002-monaco-editor-clipboard-write-strategy.md` — documents the
  existing Monaco read/write/compile mechanism and formally flags
  `indicator_apply` as a violation of it.
- `docs/adr/0003-integration-vs-unit-test-boundary.md` — establishes the
  unit/integration test tier distinction and the rule that
  `recon_findings.json`'s `verified: true` should require live-session
  confirmation, not just passing unit tests.
