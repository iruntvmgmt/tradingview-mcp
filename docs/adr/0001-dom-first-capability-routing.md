# ADR-0001: Route all capabilities through the DOM backend; treat JS and Network backends as stubs until proven otherwise

**Status:** accepted
**Date:** 2026-07-03 (reconstructed retroactively from existing code/recon evidence — see note below)
**Author(s):** reconstructed by audit session; original decision predates this ADR

> **Note on retroactive ADRs:** this decision was already made and implemented
> across `core/services/backends/{dom,js,network}_backend.py` and
> `recon_findings.json` before this ADR existed. Writing it down now, after
> the fact, is itself a deliberate practice — undocumented architectural
> decisions are indistinguishable from accidents to the next reader. When you
> find a significant decision baked into the code with no ADR, write one
> instead of leaving it implicit.

## Context

`core/services/backends/__init__.py` dispatches every capability (chart
control, indicators, settings, Pine script, etc.) to one of three backend
implementations based on a `"path"` field per capability in
`recon_findings.json`: `dom`, `js`, or `network`.

Three paths exist because there are three plausible ways to control
TradingView Desktop programmatically:

1. **JS injection** (`js_backend.py`) — call into a public JS API exposed by
   the app itself (e.g. `window.tvWidget`, `activeChart()`), the way
   TradingView's own Charting Library does for embedded/web contexts.
2. **DOM automation** (`dom_backend.py`) — drive the Electron/Chromium DOM
   directly via CDP: click buttons, type into inputs, read rendered text.
3. **Network interception** (`network_backend.py`) — listen to CDP's
   `Network` domain and parse data out of WebSocket frames / XHR responses
   TradingView's own frontend uses internally.

Recon (`core/services/recon.py`, `_dump_window_globals`) checked for (1) and
found nothing: TradingView Desktop does not expose `window.tvWidget` or
equivalent. Path (3) was scaffolded but never completed — it requires event
buffering infrastructure in `cdp_connection.py` that doesn't exist yet (see
`docs/known_issues.json` → `ohlcv_read`).

## Decision

Every capability in `recon_findings.json` currently has `"path": "dom"`.
`js_backend.py` and `network_backend.py` are fully-stubbed mixins
(`_JsStubMixin`, `_NetworkStubMixin`) that raise `CapabilityUnavailable` on
every method call, by design — not bugs, placeholders for paths that may
become viable later:

- If a future TradingView Desktop version adds a JS API, recon's
  `_dump_window_globals` will detect it and `js_backend.py` should be
  implemented then, not speculatively now.
- `network_backend.py` is a real target for OHLCV specifically (see
  `docs/known_issues.json`) but is not currently implemented.

Because 100% of capabilities route through `dom` today, **the DOM backend
(`dom_backend.py`) is the only backend that matters for correctness review.**
Bugs in `js_backend.py`/`network_backend.py` are inert until a capability's
`path` changes — don't spend audit time there unless you're the one
implementing the network path for OHLCV.

## Consequences

- All capability correctness depends entirely on selector accuracy against
  TradingView Desktop's actual DOM, which is unversioned and can change
  between app updates. This is the single largest source of fragility in
  the project (see ADR-0002 for the Monaco-specific instance of this).
- `recon_findings.json`'s `verified` flag is the closest thing this project
  has to a test oracle for DOM correctness, since unit tests mock the DOM
  layer entirely (see ADR-0003). Treat `verified: true` as a claim that
  needs periodic re-confirmation, not a permanent guarantee.
- Implementing the network path for `ohlcv_read` would reduce dependence on
  DOM scraping for at least that one capability, at the cost of building
  CDP event-buffering infra that doesn't exist yet.

## Evidence / how to verify this is still true

Run recon's `_dump_window_globals` (`core/services/recon.py`) against a
live TradingView Desktop session and check for `window.tvWidget` or similar.
If found, path (1) becomes viable and `js_backend.py` should be implemented
for the relevant capabilities — update this ADR's Status to "superseded" and
write a new one.
