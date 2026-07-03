# Documentation System

This repo is worked on across many separate AI agent sessions (and possibly
concurrent agents) with no shared memory between them except what's checked
into git. That's a specific, unusual constraint compared to a normal
engineering team — a human developer retains context between Tuesday and
Thursday even if they don't write anything down; an agent session doesn't.
Everything that matters has to survive in the repo itself, in a form the
*next* session can trust without re-deriving it from scratch or re-reading
an entire chat transcript.

The prior documentation set (`PROJECT_BRIEF.md`, `CHANGELOG.md`, 6 sprint
folders under `docs/sprint-*`, `docs/qa/`, `OPENCLAW.md`, etc.) is not bad —
`docs/qa/sprint-1.md` in particular has a genuinely good severity-tiered bug
report format, kept below. The problem this system fixes is narrower and
more specific: **prose documentation drifts from code, silently, and
nothing catches it.** `indicator_apply` sat marked `verified: true` while
being broken. That's not a documentation *style* problem — it's a
documentation *architecture* problem, and it needs a structural fix, not
just cleaner prose.

## The core principle: separate generated truth from human narrative

Four kinds of information live in this repo now, in four different places,
on purpose:

| Kind of information | Lives in | Who/what writes it | Can it drift from reality? |
|---|---|---|---|
| Machine-verified capability status | `recon_findings.json` | Recon tooling, after a live-session check | Only if recon is run against a stale app version |
| Human-observed issues that recon alone won't catch | `docs/known_issues.json` | Any agent, by hand, one JSON object per issue | Only if someone forgets to update it — but it's the *only* place this info lives, so there's nothing to fall out of sync with |
| The merged, human-readable picture | `docs/STATUS.md` | **Generated** by `scripts/generate_status.py` from the two above | No — it's rebuilt from source every time, never hand-edited |
| Why a non-obvious decision was made | `docs/adr/NNNN-*.md` | Whoever made the decision, once, immutably | No — ADRs are never edited, only superseded |
| What happened in a given session | `docs/handoff/YYYY-MM-DD-*.md` | Whoever ran the session, once, append-only | No — same reason |

The key move is `docs/STATUS.md` being **generated, not hand-maintained**.
This is the standard trick for the whole "docs drift from code" problem in
professional codebases (it's the same logic behind generating API docs from
docstrings, or a changelog from commit messages) — a hand-written status
page will always eventually lie, because updating it is a separate action
from making the change it's supposed to describe, and separate actions get
forgotten. A generated page can only be as wrong as its inputs, and its
inputs are either machine-checked (`recon_findings.json`) or a single
authoritative human-edited file (`known_issues.json`) with a validator
(`generate_status.py` exits non-zero on a typo'd capability name).

Run it any time recon changes or an issue is opened/closed:

```bash
python3 scripts/generate_status.py
```

## The four pieces, in practical terms

### 1. `docs/STATUS.md` — "what's true right now"

Read this first in any new session. It answers "can I trust capability X"
without reading code. Never edit it directly — edit `known_issues.json` or
re-run recon, then regenerate.

### 2. `docs/adr/` — "why is it built this way"

An **Architecture Decision Record** captures a decision, its context, and
its consequences, once, and never changes after being accepted. If the
decision later turns out wrong, you write ADR-0007 that supersedes ADR-0003
— you don't rewrite ADR-0003. This preserves the history of *why* the
codebase looks the way it does, which matters enormously here because
several of this project's key decisions (the Monaco clipboard trick, the
DOM-first routing) were arrived at through real trial-and-error against
TradingView's undocumented internals. That knowledge is expensive to
re-derive and cheap to lose if it only lives in a commit message or a chat
transcript. Numbered sequentially, one decision per file, see
`docs/adr/0000-template.md`.

**Rule of thumb for when to write one:** if a future agent could plausibly
"fix" something by undoing your work because the reasoning wasn't written
down, it needed an ADR. (This already happened once, implicitly —
`indicator_apply` reimplemented a Monaco-write approach that had already
been proven broken and fixed elsewhere in the same codebase, because the
fix's reasoning wasn't linked from anywhere the second implementation would
have seen it. ADR-0002 exists specifically to stop that from happening
again.)

### 3. `docs/handoff/` — "what happened, in order"

One append-only file per session. Unlike `docs/STATUS.md`, this is
narrative, not state — it's the difference between "here's the current
balance" and "here's the transaction log." Both matter: STATUS.md tells you
where things stand, the handoff log tells you *how* they got there and what
was tried. Never edit a past entry; if something in it turns out to be
wrong, say so in a new entry.

Cold-start prompt for a new session, going forward:

> Read the most recent file in `docs/handoff/` in full, then
> `docs/STATUS.md`, then proceed from that entry's "Next steps" section.

This replaces the previous cold-start pattern ("Read PROJECT_BRIEF.md and
docs/sprint-6/progress.md. You are [Ivy/Sage/Remy]...") with something that
doesn't require the prompt itself to be updated by hand every sprint.

### 4. `docs/known_issues.json` — the one hand-edited source of truth

Every entry references a `capability` key that must exist in
`recon_findings.json` — the generator enforces this and fails loudly on a
typo or a renamed capability, rather than silently producing a wrong
`STATUS.md`. This file is intentionally small and structured (not prose)
so it stays cheap to keep accurate. When an issue is fixed, don't delete
the entry — set `"status": "fixed"` and leave it; the generator only shows
`open` issues in the main table, but the history stays queryable.

## Existing conventions worth keeping as-is

- `docs/qa/*.md`'s severity-tiered bug report format (🔴 Blocker / 🟠 Major
  / 🟡 Minor, with a summary table + per-bug detail sections) is good and
  compatible with this system — `known_issues.json`'s `severity` field maps
  directly onto it. Keep using this format for one-off audit writeups; feed
  anything that represents an ongoing capability-level issue into
  `known_issues.json` too, so it shows up in `STATUS.md`.
- `CHANGELOG.md` — keep as the record of *shipped* changes (this is the
  standard "Keep a Changelog" pattern). It answers a different question
  than the handoff log: "what changed between releases" vs. "what happened
  in this session, including things that didn't ship." Both are useful.

## Docstring convention for backend methods

Every method in `core/services/backends/dom_backend.py` (and any future
concrete backend) should state its confidence level at the top of its
docstring, not just what it does:

```python
async def write(self, study_name: str, values: dict[str, Any]) -> None:
    """Set one or more input values and click OK/Apply.

    Status: BROKEN — see docs/known_issues.json (settings_write) and
    docs/STATUS.md. Uses guessed selectors never confirmed against a live
    TradingView Desktop Inputs dialog. Do not trust until fixed per
    docs/handoff/2026-07-03-audit-findings.md § settings backend.
    """
```

For methods that *are* trustworthy, state the evidence instead:

```python
async def compile(self, script_name: str) -> dict[str, Any]:
    """Compile and add the script to the chart.

    Status: verified — see ADR-0002 for the mechanism and why the naive
    approach doesn't work.
    """
```

This means a reader hits the confidence level at the point of use, without
needing to cross-reference `STATUS.md` separately — but `STATUS.md` remains
the authoritative source if a docstring goes stale (docstrings are prose
too, and can drift the same way any hand-written doc can; they're a
convenience layer on top of the generated source of truth, not a
replacement for it).

## What this system deliberately does not solve

- **It doesn't stop code from lying.** If someone marks a capability
  `verified: true` in `recon_findings.json` without actually checking it
  live, this system will faithfully report the wrong thing — same as
  `indicator_apply` did before this audit. The fix for that isn't more
  documentation infrastructure, it's discipline: don't flip `verified` on
  anything without a live-session check, and note that check happened in a
  handoff entry (ADR-0003).
- **It doesn't replace integration tests.** `docs/STATUS.md` can tell you
  a capability is unverified; it can't tell you why in enough detail to fix
  it without also reading the linked issue/ADR/handoff entry. Building an
  actual integration test harness (ADR-0003 § Consequences) would close
  this gap further — it's a reasonable next investment, not done here.
