# ADR-0004: Settings dialog selectors depend on hashed CSS-module class names that will break on TradingView updates

**Status:** accepted
**Date:** 2026-07-03
**Author(s):** Sage (ai-team-dev)

## Context

The Settings dialog backend (`DomSettingsBackend`, `dom_backend.py`) relies on
selectors discovered from a live TradingView Desktop 3.2.0 session on
2026-07-03. TradingView Desktop is an Electron app that bundles its frontend
as a React app with CSS Modules. CSS Modules generate per-build hashed class
names (e.g. `cell-RLntasnw`, `first-RLntasnw`, `input-gr1VjUfr`) that are
**not semantically meaningful and will almost certainly change** on the next
TradingView Desktop update.

The current Settings backend depends on the following hashed class names
(observed against TV Desktop 3.2.0, Unknown build date, recorded 2026-07-03):

| Selector | Type | Will survive update? |
|---|---|---|
| `div[data-name="indicator-properties-dialog"]` | Semantic (`data-name`) | ✅ Yes |
| `div.cell-RLntasnw.first-RLntasnw` | Hashed CSS module | ❌ No |
| `input[data-qa-id="ui-lib-Input-input"]` | Semantic (`data-qa-id`) | ✅ Likely |
| `button[role="combobox"]` | Semantic (`role`) | ✅ Likely |
| `input[type="checkbox"][data-qa-id="ui-lib-checkbox-input-input"]` | Semantic (`data-qa-id`) | ✅ Likely |
| `button[data-name="submit-button"]` | Semantic (`data-name`) | ✅ Likely |
| `button[name="cancel"]` | Semantic (`name`) | ✅ Likely |

The **critical fragility** is `div.cell-RLntasnw.first-RLntasnw` — this is
the only selector that identifies per-field **label** cells in the dialog
row layout. Without a working label-row selector, `list_fields`, `read`, and
`write` all break: `list_fields` returns an empty list, `write` cannot find
any field to target.

## Decision

Accept that the row-label selector (`div.cell-RLntasnw.first-RLntasnw`) is
a hash-dependent breakage point. Document exactly how to re-discover it when
it breaks, so the fix is mechanical rather than investigative.

The approach for fixing this when it breaks is the same DOM-dump technique
used during the original recon on 2026-07-03 (documented in
`docs/handoff/2026-07-03-fix-settings-and-indicator-apply.md` §1):
1. Open a live TradingView Desktop session with CDP debug port open.
2. Open the Settings dialog for any indicator.
3. Dump the dialog HTML via `ReconRunner._snapshot_outer_html` or a direct
   CDP `Runtime.evaluate` call.
4. Identify the new hash for the label cell class — it will follow the same
   structural pattern: a `<div>` wrapping label text, with a class
   containing a short random suffix like `-RLntasnw` or similar.
5. Update `recon_findings.json`:
   - `settings_list_fields.row_label_selector`
   - `settings_read.row_label_selector`
   - `settings_write.row_label_selector`
6. Re-run `list_fields` against a live dialog to confirm the fix.

## Consequences

- **What this makes easier:** The fix procedure is documented. A future
  agent encountering "settings backend returns empty fields" can diagnose
  this as a CSS hash change and apply the mechanical fix without re-doing
  the entire settings backend investigation.
- **What this makes harder:** The settings backend cannot run unattended
  across TV Desktop version upgrades — it must be manually re-verified
  after each update. This is the same class of problem as the Monaco
  selectors (ADR-0002) and is inherent to DOM-based automation of an
  unversioned, Electron-packaged web app.
- **When to revisit:** If a future TV Desktop version replaces the table-row
  layout entirely (e.g. switches from `<div>` rows to a different widget
  component), the label-selection approach documented here becomes obsolete
  and a new ADR should supersede this one documenting the replacement
  selector strategy.

## Evidence / how to verify this is still true

Open a TradingView Desktop instance at a version **different** from the one
where these selectors were observed (3.2.0, recorded 2026-07-03). If
`list_fields` returns results, the hashes are stable across builds. If it
returns an empty list, the hashes have changed and the fix procedure above
applies.
