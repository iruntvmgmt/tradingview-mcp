# ADR-0003: Unit tests mock the DOM/CDP boundary; this means a passing suite proves dispatch correctness, not real-world function

**Status:** accepted (documenting existing practice) — recommend adding an integration tier, see § Consequences
**Date:** 2026-07-03
**Author(s):** audit session

## Context

`tests/*.py` (69 tests as of this writing) universally mock `DomUtils` and
`CDPConnection` at the constructor boundary:

```python
@pytest.fixture
def mock_dom():
    dom = MagicMock()
    dom.click = AsyncMock()
    dom.type_text = AsyncMock()
    ...
```

This is a reasonable default — CI can't launch a real TradingView Desktop
instance, and most of these tests exist to verify plumbing: does the
controller call the right backend method with the right arguments, does the
factory dispatch to the right backend class for a given `path`, does
`order_place` correctly refuse to submit without `confirm=True`, etc. All of
that is legitimately worth testing this way, and worth keeping.

The risk shows up when this test tier is the *only* one: a backend method
can have completely wrong CSS selectors, or use a Monaco-write approach
already proven broken (ADR-0002), and every test still passes — because the
test never asked the mock to actually resolve a selector against real DOM.
This is exactly what happened with `DomSettingsBackend` and
`DomIndicatorBackend.apply` (see `docs/known_issues.json`): both had full
green test coverage while being non-functional in practice.

## Decision

Two explicit test tiers, not one:

1. **Unit tests** (existing, default `pytest tests/ -m "not integration"` in
   CI) — mock the DOM/CDP boundary, verify controller/backend/factory
   plumbing. Fast, no live app required, run on every change.
2. **Integration tests** (`@pytest.mark.integration`, opt-in, require a live
   TradingView Desktop session with CDP debug port open) — exercise real
   `Dom*Backend` classes against the actual app DOM. Slower, require manual
   setup, run before marking a capability `verified: true` in
   `recon_findings.json`.

A capability should only be marked `verified: true` in
`recon_findings.json` after an integration-tier check has actually
succeeded against a live session — not after unit tests pass, and not on
the strength of code review alone. `recon_findings.json`'s `verified` flag
is meant to answer "does this actually work against the real app," and unit
tests structurally cannot answer that question.

## Consequences

- **What this doesn't change:** existing unit tests stay as-is; they're
  correctly scoped to what they test.
- **What this requires going forward:** any backend fix that changes
  selector logic (e.g. the `DomSettingsBackend` rewrite tracked in
  `docs/known_issues.json`) should ship with a new integration test under
  `@pytest.mark.integration`, not just an updated mocked unit test. The
  mocked unit test proves the fix didn't break dispatch; the integration
  test is the only thing that proves the fix works.
- **What this doesn't yet have:** an integration test *runner* — there's no
  documented one-command way to point pytest at a live TradingView Desktop
  session today. Until that exists, "integration-tested" in practice means
  "manually verified against a live session and noted in a handoff log
  entry" (see `docs/handoff/`). Building a real integration harness is a
  reasonable follow-up but is not blocking — manual verification with a
  written record is sufficient for now, as long as it's actually recorded
  somewhere (`docs/known_issues.json` / `docs/handoff/*.md`), not just
  claimed in a commit message.

## Evidence / how to verify this is still true

Check `pyproject.toml` / `pytest.ini` for the `integration` marker
definition and confirm the default test command still excludes it
(`pytest tests/ -m "not integration"`). Check whether any `dom` backend has
a corresponding integration test before trusting a `verified: true` flag
for it — if not, treat that flag with the same skepticism this ADR
describes, regardless of what the field says.
