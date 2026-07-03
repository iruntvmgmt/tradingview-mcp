# ADR-NNNN: <short, decision-focused title>

**Status:** proposed | accepted | superseded by ADR-NNNN | deprecated
**Date:** YYYY-MM-DD
**Author(s):** <agent name / human name>

## Rules for this doc

- ADRs are **immutable** once accepted. If a decision changes, write a new
  ADR that supersedes this one and update this file's Status line to point
  to it — don't edit the reasoning below after the fact.
- One decision per ADR. If you're documenting two unrelated choices, write
  two files.
- Numbering is sequential across the whole `docs/adr/` directory, never
  reused, regardless of status.
- Link to the ADR number from code comments where the decision is
  implemented (`# See ADR-0002 for why this uses clipboard, not .value=`),
  so a reader hits the "why" without needing to search docs separately.

## Context

What problem forced a decision here? What was tried first and failed
(if anything)? What constraints (TradingView Desktop's architecture, CDP's
capabilities, React's event system, etc.) shaped the options available?

## Decision

State the decision in one or two sentences, then the implementation detail
needed for a future agent to apply the same pattern elsewhere without
re-deriving it.

## Consequences

- What this makes easier.
- What this makes harder, or what it forecloses.
- What would have to be true for this decision to need revisiting (i.e.
  when should a future agent write a superseding ADR instead of just
  patching around this one).

## Evidence / how to verify this is still true

TradingView Desktop is a moving target — a decision correct against one
build may not hold after an update. State how a future agent can re-confirm
this decision still holds (e.g. "re-run the recon probe in
`scripts/dom_probe.py` against a live session and confirm the selector
pattern in § still matches").
