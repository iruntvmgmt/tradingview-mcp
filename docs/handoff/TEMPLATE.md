# Handoff: YYYY-MM-DD — <one-line session summary>

**Agent:** <name, e.g. Ivy / Sage / Remy / audit-session>
**Preceding handoff:** `docs/handoff/YYYY-MM-DD-previous.md` (or "none — first entry")
**Branch / commit at session end:** `<branch>` @ `<short sha>`

## Rules for this log

- One file per session, named `YYYY-MM-DD-<slug>.md`. Never edit a past
  entry — if something in a past entry turns out to be wrong, say so in a
  new entry and link back to it. The log is an append-only record of what
  was believed true at each point in time, which is exactly what makes it
  useful for debugging "when did this assumption stop being true."
- Every entry must answer the same four questions below. Skipping one
  because "nothing changed" is itself useful information — write "none."
- Link to ADRs for *why* decisions were made; link to `docs/STATUS.md` /
  `docs/known_issues.json` for *current capability state*. Don't duplicate
  either here — this log is for narrative and decisions, not status, which
  drifts if hand-copied.
- Cold-start prompt for the next agent: **"Read the most recent file in
  `docs/handoff/` in full, then `docs/STATUS.md`, then proceed from
  § Next steps below."**

## 1. What changed this session

Concrete, verifiable changes only — commits, files, test runs. Not "worked
on X," but "fixed Y (commit `abc123`), added integration test for Z."

## 2. What is now verified true (and how)

Anything moved from "unverified"/"believed broken" to "confirmed working,"
with how it was confirmed (which live-session check, which test). If a
`recon_findings.json` `verified` flag was flipped, say so explicitly and
link the capability name.

## 3. What is still broken / unknown

Current known issues this session did NOT resolve. Cross-reference
`docs/known_issues.json` entries by capability name rather than
re-describing them — if the description needs updating, update
`known_issues.json` and regenerate `docs/STATUS.md`, don't fork the
description into this log.

## 4. Next steps (in priority order)

What should the next agent do first, and why that order. If this matches
an existing plan doc (e.g. an audit fix plan), point to the specific
section rather than repeating it.

## Decisions made this session (if any)

If a real architectural/technical decision was made, it belongs in a new
`docs/adr/NNNN-*.md`, not inline here — link it. This section is just an
index of which ADRs came out of this session, for quick scanning.
