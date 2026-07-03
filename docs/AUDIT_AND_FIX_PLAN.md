# TV Desktop MCP Controller — Audit Findings & Fix Plan

**Repo:** `iruntvmgmt/tradingview-mcp` (local clone dir: `tv-desktop-controller-qa`)
**Audited commit:** `2109133` — "cleanup: remove old codebase remnants from merge" (main, post v1.0.0 tag)
**Audit date:** 2026-07-03
**Audience:** the next agent (Ivy/Sage/Remy or successor) picking up this codebase.

**Goal driving this audit:** the owner wants AI agents to have full programmatic
control over TradingView Desktop — specifically to **read/write Pine Script**,
**read/write indicator & strategy Input settings**, run backtests, and read
results, so an agent can iterate on a strategy and verify whether changes
actually improve performance. This doc is scoped to get that loop fully
working, in priority order.

---

## 0. TL;DR — what to fix, in order

| # | Item | Status | Blocks the owner's goal? |
|---|------|--------|---------------------------|
| 1 | `DomSettingsBackend` (Inputs tab read/write) | **Not functional** — guessed selectors | **Yes — critical** |
| 2 | `DomIndicatorBackend.apply` (`tv_apply_script`) | **Likely broken** — wrong dialog, unfixed Monaco write | **Yes — critical** |
| 3 | `get_ohlcv` (chart + network) | **Dead end on both paths** | Yes — agent is blind to price data |
| 4 | `server.py` hardcoded `allow_unverified=True` | Safety gate disabled in "prod" | Indirect — hides the above |
| 5 | Test suite is 100% mocked at the backend boundary | False confidence, not a bug per se | Indirect |
| 6 | `DomBacktestBackend.health_check` dead code | Cosmetic | No |
| 7 | `network_backend.py` self-contradicting docstring | Cosmetic | No |

Items 1–3 are the actual blockers. Fix them in that order — settings first,
since it's the piece the owner explicitly needs and the one furthest from
working.

---

## 1. CRITICAL: Settings backend (Inputs tab) is not really implemented

**Files:** `core/services/backends/dom_backend.py` (`DomSettingsBackend`, lines ~459–518)
**Recon entries:** `settings_list_fields`, `settings_read`, `settings_write` — all `"verified": false` in `recon_findings.json`

### What's wrong

```python
async def write(self, study_name: str, values: dict[str, Any]) -> None:
    detail = _cap(self._caps, "settings_write")
    dialog_sels = detail.get("dialog_selectors", [])
    if dialog_sels:
        await self._dom.click(dialog_sels)
    for field, value in values.items():
        field_sels = [f"input[name='{field}']", f"[data-name='{field}']",
                      f"input[placeholder*='{field}']"]
        await self._dom.type_text(field_sels, str(value), clear_first=True)
    apply_sels = detail.get("apply_selectors", [])
    if apply_sels:
        await self._dom.click(apply_sels)
```

Problems:
1. `field_sels` are **guessed generic CSS selectors**, never confirmed against
   the real TradingView Desktop Inputs dialog. TradingView's settings dialog
   renders each input as a row (`div[data-name="..."]` or similar container)
   with the actual `<input>`/`<select>`/`<button>` nested inside — it does
   **not** expose `name="length"` attributes matching your Pine input
   identifiers. This will silently fail to match, or worse, match nothing and
   raise a selector-timeout deep in `type_text`.
2. `list_fields` returns raw dialog text split by newline with
   `{"type": "unknown"}` for every field — not usable to programmatically
   target a specific field for `write()`.
3. `read()` returns `{"raw": <whole dialog text blob>, "study_name": ...}` —
   not parsed key/value pairs.
4. `recon_findings.json` confirms none of this was ever verified against a
   live instance (`"verified": false` on all three).

### Fix plan

**Step 1 — Recon the real DOM structure.** This cannot be done blind; it
requires a live TradingView Desktop session with CDP debug port open
(`--remote-debugging-port=9222`, see `scripts/launch_tv_desktop.sh`).

Add a targeted recon routine (extend `core/services/recon.py` or write a
one-off script under `scripts/`, following the pattern in
`scripts/dom_probe.py` / `scripts/probe_dom.py`) that:

1. Opens Settings (gear icon) on a known study, e.g. a chart with a plain
   Moving Average applied.
2. Dumps the outer HTML of the dialog root
   (reuse `ReconRunner._snapshot_outer_html`, `recon.py` line ~287) to a file
   for manual inspection.
3. From that dump, identify the **stable per-row selector pattern** —
   TradingView typically uses one of:
   - `div[data-name="<input-id>"]` wrapping a labeled input, or
   - a row with a `label`/`div` containing the field's display name as text,
     with the actual input as a sibling or nested descendant.
   Confirm which one TradingView Desktop's current build uses; do **not**
   assume — check the actual dump.
4. Record the exact selector pattern, the input type per field (number
   input vs. checkbox vs. select vs. color picker vs. source dropdown), and
   the exact "Apply/OK" button selector, into `recon_findings.json` under
   `settings_list_fields` / `settings_read` / `settings_write`, matching the
   existing detail-dict shape:

```json
"settings_write": {
  "path": "dom",
  "verified": true,
  "detail": {
    "dialog_selectors": ["div[role=\"dialog\"][class*=\"settings\"]"],
    "row_selector_template": "div[data-name=\"{field}\"]",
    "input_selector_within_row": "input, select, button[role=\"checkbox\"]",
    "apply_selectors": ["button:has(div:text(\"OK\"))"]
  }
}
```

(Exact keys are up to you — just keep them consistent with how `dom_backend.py`
reads them via `_cap()`.)

**Step 2 — Rewrite `DomSettingsBackend` around real structure**, not generic
guesses. Sketch (adjust once real selectors are known):

```python
async def list_fields(self, study_name: str) -> list[dict[str, Any]]:
    detail = _cap(self._caps, "settings_list_fields")
    gear_sels = detail.get("gear_icon_selectors", [])
    if gear_sels:
        await self._dom.click(gear_sels)

    # Enumerate row containers, not raw text.
    row_sels = detail.get("row_selectors", [])
    rows_js = f"""
    (() => {{
        const rows = document.querySelectorAll({json.dumps(row_sels[0]) if row_sels else "''"});
        return Array.from(rows).map(r => ({{
            name: r.getAttribute('data-name') || r.innerText.split('\\n')[0],
            type: r.querySelector('input[type=checkbox]') ? 'bool'
                : r.querySelector('select') ? 'enum'
                : r.querySelector('input[type=number]') ? 'number'
                : 'string',
            current_value: (r.querySelector('input')?.value)
                ?? (r.querySelector('input[type=checkbox]')?.checked)
                ?? null,
        }}));
    })()
    """
    result = await self._cdp.execute_js(rows_js)
    return result.get("result", {}).get("value", []) or []

async def read(self, study_name: str) -> dict[str, Any]:
    fields = await self.list_fields(study_name)
    return {f["name"]: f["current_value"] for f in fields}

async def write(self, study_name: str, values: dict[str, Any]) -> None:
    detail = _cap(self._caps, "settings_write")
    row_template = detail.get("row_selector_template")  # e.g. 'div[data-name="{field}"]'
    for field, value in values.items():
        row_sel = row_template.format(field=field)
        # Use get_attribute / is_visible first to confirm the row exists
        # before attempting to type — fail loud with a clear error instead
        # of silently no-op'ing like the old version.
        exists = await self._dom.is_visible([row_sel], timeout=2.0)
        if not exists:
            raise SelectorResolutionError(
                f"Settings field '{field}' not found for study '{study_name}'",
                details={"field": field, "selector": row_sel},
            )
        input_sel = f"{row_sel} input, {row_sel} select"
        await self._dom.type_text([input_sel], str(value), clear_first=True)
    apply_sels = detail.get("apply_selectors", [])
    if apply_sels:
        await self._dom.click(apply_sels)
```

This is a **sketch**, not final code — the row structure and JS above must
be validated against the real dump from Step 1 before trusting it. The key
behavioral change vs. the current code: **fail loudly with
`SelectorResolutionError` if a field isn't found**, instead of silently
attempting a doomed generic selector and either no-op'ing or throwing a
confusing low-level timeout.

**Step 3 — Verify.** Manually test against a real chart with at least one
indicator with a `number` input, one `bool` (checkbox) input, and one
`select`/enum input (e.g. MA Type dropdowns are common) to make sure all
three input kinds round-trip correctly. Only then flip `verified: true` in
`recon_findings.json`.

**Step 4 — Add a real (non-mocked) test.** The existing
`tests/test_settings_controller.py` only mocks the backend — keep it, but
add a new test file, e.g. `tests/test_settings_backend_live.py`, marked
`@pytest.mark.integration` (see how `pytest.ini`/`pyproject.toml` defines
that marker; the existing CI command already does
`pytest tests/ -m "not integration"` so integration tests are opt-in) that
runs the real `DomSettingsBackend` against a live CDP connection. This is
the only way to know settings control actually works, since the current
suite provably can't tell you that (see §5).

---

## 2. CRITICAL: `tv_apply_script` (new indicator/strategy application) is likely broken

**File:** `core/services/backends/dom_backend.py` (`DomIndicatorBackend.apply`, lines ~101–143)
**Recon entry:** `indicator_apply` — marked `"verified": true`, but this is misleading (see below).

### What's wrong

1. **Selector mismatch.** `recon_findings.json`'s `indicator_apply` detail:
   ```json
   "editor_selectors": ["button[data-name=\"open-indicators-dialog\"]", "button:has(div:text(\"Indicators\"))"],
   "add_to_chart_selectors": ["button:has(div:text(\"Indicators\"))", "button[data-name=\"open-indicators-dialog\"]"]
   ```
   `editor_selectors` and `add_to_chart_selectors` are **the same buttons**.
   Both point at the button that opens TradingView's built-in "Browse
   Indicators" dialog (for adding stock/community indicators by name) — not
   the Pine Editor, and there is no distinct "Add to Chart" confirm action
   here at all. The code's own comments ("Open Pine Editor", "Click Add to
   Chart to compile & apply") don't match what these selectors actually do.

2. **Broken Monaco write.** Once inside `apply()`, the code tries to inject
   Pine source with:
   ```python
   ta.value = {json.dumps(pine_code)};
   ta.dispatchEvent(new Event('input', { bubbles: true }));
   ```
   This is exactly the approach that `docs/monaco-editor-integration.md`
   documents as **not working** — Monaco virtualizes its hidden textarea and
   silently truncates/ignores direct `.value` writes. The fix already exists
   in the codebase (`DomUtils.type_text_monaco`, used correctly by
   `DomPineScriptBackend.write`) but `apply()` was never updated to use it.

3. Despite both of the above, `indicator_apply` is marked `verified: true`
   in recon — this is false confidence and should not be trusted as-is.

### Fix plan

**Option A (recommended, fastest correct path):** Redefine what
`indicator_apply` / `tv_apply_script` actually does, to reuse the
already-working Pine Editor pipeline instead of a separate broken one:

1. Click the selector that actually opens the **Pine Editor** (not the
   Indicators browse dialog) — this needs its own recon pass. Check
   `recon_findings.json`'s `pine_read`/`pine_write` entries
   (`#pine-editor-dialog`) — there is likely already a known-good "open Pine
   Editor" trigger documented or discoverable near those selectors; if not,
   recon it the same way as in §1 Step 1.
2. Once the Pine Editor is open with a **new/blank script**, delegate to the
   already-correct `DomPineScriptBackend`:
   ```python
   async def apply(self, pine_code: str, name: str) -> None:
       open_sels = _cap(self._caps, "indicator_apply").get("open_pine_editor_selectors", [])
       await self._dom.click(open_sels)
       await asyncio.sleep(0.5)

       pine_backend = DomPineScriptBackend(self._cdp, self._dom, self._caps)
       await pine_backend.write(name, pine_code)   # uses type_text_monaco — proven working
       result = await pine_backend.compile(name)   # uses JS click bypass — proven working
       return result
   ```
   This eliminates the duplicated, broken Monaco-write logic entirely by
   reusing code that's already been validated.

**Option B (if a true "Add to Chart" button exists separately from
Compile):** recon it explicitly — dump the Pine Editor toolbar HTML and
confirm whether "Add to Chart" is a distinct action from "Save"/Compile, or
whether (as is the case in current TradingView Desktop versions per the
Compile implementation's comments) Save *is* the add-to-chart action. If
Save-and-apply are the same button, Option A above is complete as-is and no
separate "add to chart" click is needed.

**Step 3 — Fix the recon entry.** Once verified, replace the duplicated
`editor_selectors`/`add_to_chart_selectors` with accurate, distinct
selectors, and only then keep `verified: true`. Until fixed, consider
manually setting `indicator_apply.verified` back to `false` in
`recon_findings.json` so `tv_apply_script` isn't silently trusted — or leave
`allow_unverified=True` as-is (see §4) but flag this specific tool as
untrusted in the tool description string in `server.py`:

```python
_register("tv_apply_script",
          "Apply a Pine Script indicator/strategy to the chart. "
          "⚠ UNVERIFIED — known selector issue, see AUDIT_AND_FIX_PLAN.md §2. "
          "Prefer manually opening a blank script, then tv_pine_write + tv_pine_compile.",
          ...)
```

**Interim workaround for the owner in the meantime:** manually create/open a
blank Pine script once in TradingView Desktop, then drive it entirely via
`tv_pine_write` → `tv_pine_compile`, which are the two capabilities already
confirmed to work.

---

## 3. Dead end: `tv_get_chart_data` (OHLCV read) does not work on any path

**Files:**
- `core/services/backends/dom_backend.py` — `DomChartBackend.get_ohlcv` (line ~74): always raises `CapabilityUnavailable("OHLCV read is not available via DOM — use network path")`.
- `core/services/backends/network_backend.py` — `NetworkChartBackend.get_ohlcv` (line ~46): also always raises `CapabilityUnavailable`, despite the module docstring claiming "the network path is expected only for `ohlcv_read`."

So the DOM path punts to the network path, and the network path is an
unfinished stub. **There is currently no way for an agent to read price data
via this MCP server**, on either implemented path.

### Fix plan

This is the largest single piece of unfinished work in the codebase — the
`network_backend.py` docstring itself says it "requires event buffering"
from CDP's `Network` domain, which hasn't been built.

1. Implement CDP `Network.enable` + a WebSocket-frame listener in
   `cdp_connection.py` (`core/services/cdp_connection.py`, 20K — check
   existing `_send_command`/event-subscription plumbing there first; it may
   already have generic CDP event handling that can be reused).
2. In `NetworkChartBackend.get_ohlcv`, buffer incoming WS frames matching
   TradingView's chart-data protocol, parse OHLCV bars out of them, and
   return the most recent `limit` bars.
3. This is meaningfully more involved than §1/§2 — recommend treating it as
   its own sprint after settings + indicator-apply are fixed, since it's not
   strictly required for the "tune settings → backtest → read results →
   iterate" loop (that loop can run on `tv_run_backtest` +
   `tv_get_backtest_summary` without raw OHLCV). Prioritize accordingly
   unless the owner specifically needs live price-series access.

---

## 4. Safety/config: `allow_unverified=True` is hardcoded "for development"

**File:** `server.py`, line 62:
```python
# allow_unverified=True during development
_recon = _load_recon()
...
_ctrl_settings = TVSettingsController(_cdp, _recon, allow_unverified=True)
```

This flag was clearly meant to be temporary but is what's shipped in `main`
at `v1.0.0`. It means every currently-"unverified" capability (settings,
`order_place`, `replay_state`, `backtest_trade_list`, etc.) runs without any
gate — the tool will attempt DOM automation using selectors that were never
confirmed to work, with no warning to the calling agent beyond whatever
exception surfaces.

**Recommendation:** keep `allow_unverified=True` while iterating (it's
genuinely useful during active development), but:
1. Add a startup log line listing every capability currently running
   unverified, so it's visible every time the server starts:
   ```python
   unverified = [name for name, c in _recon["capabilities"].items() if not c.get("verified")]
   if unverified:
       logger.warning("Running with allow_unverified=True. Unverified capabilities: %s", unverified)
   ```
2. Once §1 and §2 are fixed and re-verified, flip those specific entries to
   `verified: true` in `recon_findings.json` so they no longer rely on the
   blanket override.

---

## 5. Test suite caveat — read before trusting "69/69 passing"

Every existing test (`tests/test_settings_controller.py`,
`tests/test_backends.py`, and the rest) mocks `DomUtils` and `CDPConnection`
at the boundary. They confirm controllers call backends with the right
arguments (dispatch/plumbing correctness). **None of them exercise real CSS
selectors against a live TradingView Desktop DOM.** That's why
`DomSettingsBackend` and `DomIndicatorBackend.apply` both had "69/69 passing"
next to them while being non-functional — the tests structurally cannot
catch this class of bug.

**Action:** once §1 and §2 land, add integration tests (marked
`@pytest.mark.integration`, excluded from the default `pytest tests/ -m "not
integration"` run but runnable on-demand against a live CDP session) that
exercise the real `DomSettingsBackend` and `DomIndicatorBackend` against an
actual open TradingView Desktop instance. Keep the current mocked tests too
— they're still useful for catching plumbing regressions — but don't treat
their pass rate as evidence that DOM automation works.

---

## 6. Minor cleanup (low priority, do opportunistically)

1. **`DomBacktestBackend.health_check`** (`dom_backend.py`, lines ~211–223)
   has dead, unreachable code from a merge:
   ```python
   async def health_check(self) -> bool:
       try:
           detail = _cap(self._caps, "backtest_run")
           sels = detail.get("bottom_panel_selectors", detail.get("tab_selectors", []))
           if sels:
               await self._dom.resolve_selector(sels, timeout=3.0)
           return True
       except Exception:
           return False
           return True        # <- unreachable
       except Exception:       # <- unreachable, duplicate
           return False
   ```
   Delete lines after the first `except Exception: return False`.

2. **`network_backend.py` docstring** contradicts its own code (claims
   `ohlcv_read` is the one supported network method; `get_ohlcv` raises
   `CapabilityUnavailable` like everything else). Fix the docstring once §3
   is implemented, or in the meantime update it to say network path is
   fully unimplemented, full stop.

3. `js_backend.py` is an intentional, documented stub (TradingView Desktop
   exposes no `window.tvWidget`/JS API) — no action needed unless a future
   TV Desktop version changes this.

---

## 7. Suggested execution order for the next agent

1. Read this file in full + `docs/monaco-editor-integration.md` (contains
   the real Monaco/CDP investigation that §1 and §2's fixes should follow
   the same pattern as).
2. Launch TradingView Desktop with CDP debug port
   (`scripts/launch_tv_desktop.sh`), confirm `tv_diagnostics` /
   `tv_health_check` report `cdp_connected: true`.
3. **§1** — recon + rewrite `DomSettingsBackend`. Verify against a chart
   with number/bool/enum inputs. Flip `verified: true` for the three
   settings capabilities once confirmed.
4. **§2** — recon the real "open Pine Editor for a new script" trigger,
   rewrite `DomIndicatorBackend.apply` to delegate to
   `DomPineScriptBackend`. Verify end-to-end: agent writes new Pine
   strategy code → compiles → appears on chart.
5. Run the full loop manually once: `tv_apply_script` (or the interim
   `tv_pine_write`+`tv_pine_compile` workaround) → `tv_settings_write` to
   tune an input → `tv_run_backtest` → `tv_get_backtest_summary` → confirm
   the agent can see whether the change helped.
6. **§3** (OHLCV via Network domain) — only if the owner needs raw
   price-series access beyond backtest summaries.
7. **§5** — add integration tests for whatever was fixed above.
8. **§6** — cleanup pass.
9. Update `recon_findings.json`, `PROJECT_BRIEF.md`, and `CHANGELOG.md` to
   reflect the corrected capability status, then commit/push/tag
   (`v1.1.0` — settings + indicator-apply fix).

---

## Appendix: relevant existing utilities to reuse (don't reinvent)

From `core/services/dom_utils.py` (`DomUtils` class):
- `click(selectors, ...)`, `type_text(selectors, text, clear_first=...)`
- `type_text_monaco(selectors, text, ...)` — **use this for any Monaco
  editor write**, not raw `.value =`.
- `read_text_monaco(selectors, ...)` — clipboard-based full-source read.
- `extract_text`, `extract_table`, `extract_innertext_map` — for
  parsing dialog/panel content into structured data.
- `resolve_selector`, `is_visible`, `get_attribute` — for existence checks
  before acting (use these to fail loudly instead of silently no-op'ing,
  per §1's `write()` rewrite).
- `click_at_text(text, exact=...)` — useful for buttons identified by
  visible label rather than a stable selector.

From `core/services/recon.py` (`ReconRunner`):
- `_snapshot_outer_html(css_selector)` — dump real DOM structure to inspect
  before writing any selector-dependent code. **Use this first, every
  time**, rather than guessing selectors (the root cause of §1's bug).
