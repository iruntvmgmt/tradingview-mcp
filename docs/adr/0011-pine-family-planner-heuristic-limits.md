# ADR-0011: PineFamilyPlanner is a text-heuristic tool, not a Pine language parser — classification and coupling are best-effort

**Status:** accepted
**Date:** 2026-07-05
**Author(s):** Sage (ai-team-dev)

## Context

`PineFamilyPlanner` (`core/services/pine_family_planner.py`) reads raw Pine
Script source and produces a `generation_plan.json` draft with input
classification (cosmetic / tunable / structural_toggle), family clustering
by input group, tier ordering, and cross-family coupling candidates.

It exists because complex strategies (GT_VP: 211 inputs across 17 groups;
SMC: 111 tunable inputs across 17 groups) cannot safely run through
`experiment_controller.py` as one flat iteration stream without first
understanding which inputs belong together and which can be tuned
independently.

## Decision: text heuristics, not AST parsing

The planner uses regex-based parsing and keyword-matching heuristics — not
a Pine Script language parser or abstract syntax tree. It does not
understand control flow, function scoping, or conditional definitions.
This is intentional:

1. **A full Pine AST parser would need to track the entire TradingView
   standard library** (every built-in function signature, every
   `ta.*` / `request.*` / `strategy.*` namespace), handle `import`
   resolution, and implement the Pine type system. Building one correctly
   is a multi-week engineering effort for a narrow use case.

2. **Most importantly, the planner's output is a DRAFT**, not a final
   artifact. The `known_overrides` mechanism exists precisely because
   regex heuristics will misclassify some inputs. A human reviews the
   generated `_plan.md`, fixes misclassifications by adding entries to
   `known_overrides`, and re-runs the planner — the same
   human-confirms-the-draft pattern already used for
   `recon_findings.json`'s `verified` flags.

## What the heuristics will miss

- **Classification errors**: An `input.bool` in a cosmetic group will
  correctly be classified as `cosmetic` (the group-name keyword check
  catches it), but an `input.int` in a group named "Strategy Harness"
  that is actually a purely visual trailing-stop-line offset would be
  misclassified as `tunable`. This is the purpose of `known_overrides`.

- **Coupling misses**: The coupling detector checks for variable-name
  co-occurrence on the same source line. It will catch strong signals
  (GT_VP's `_strict_long_ok` tying `group_god` to `group_strategy`) but
  will miss indirect couplings through shared library functions or
  through variables that are always used together but never on the same
  line. This is why every coupling candidate is labeled
  `"confidence": "heuristic — human review required, not a proven dependency"`.

- **False positives**: Variable names appearing together coincidentally
  (e.g., in a comment or in separate unrelated `if` blocks that happen to
  be on the same line after minification) will produce coupling
  candidates where none exists. Again: human review required.

## What the planner does NOT do

- It does not execute Pine code
- It does not resolve `import` statements to pull in library source
- It does not track which variables are conditionally defined
- It does not analyze control flow to determine which inputs affect
  which outputs
- It does not compute any numeric sensitivity or backtest any strategy

## Consequences

- **What this makes easier:** A 211-input strategy that would take a
  human hours to classify and group can be reduced to a ~15-minute review
  of a generated draft. The tier ordering provides a sensible starting
  point for which families to tune first.
- **What this makes harder:** If someone treats the generated plan as
  authoritative without human review, they will make tuning decisions
  based on incorrect classifications and miss real cross-family
  couplings. The companion `.md` file's header explicitly states it is a
  generated file.
- **When to revisit:** If a trading-specialized LLM or a Pine language
  server becomes available that can do accurate AST-level input analysis,
  this heuristic planner should be retired in favor of that tool. Until
  then, it is the best available approach for the 100+ input scale.
