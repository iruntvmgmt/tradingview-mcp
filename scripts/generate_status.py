#!/usr/bin/env python3
"""Regenerate docs/STATUS.md from recon_findings.json + docs/known_issues.json.

STATUS.md is a GENERATED FILE. Do not hand-edit it — edits will be
overwritten the next time this script runs. This is intentional: it is the
single source of truth for "what capability is in what state," and it can
only be as accurate as the two inputs it's built from:

  - recon_findings.json   -> machine-recorded verification status per capability
  - docs/known_issues.json -> human-recorded issues per capability (the thing
                               recon verification alone can't catch, e.g. a
                               capability marked verified:true that turned out
                               to be wrong on closer inspection)

Why this exists: on 2026-07-03 an audit found `indicator_apply` marked
`verified: true` in recon_findings.json while being non-functional in
practice, and PROJECT_BRIEF.md's capability table was stale relative to the
actual code. A hand-maintained status doc will drift from reality every time
someone fixes code and forgets to update prose elsewhere. A generated doc
can't drift, because there's nowhere for prose to diverge from data — you
either update the data (recon_findings.json via a recon run, or
known_issues.json via a one-line edit) or the doc doesn't reflect the fix.

Run after any recon session or whenever known_issues.json changes:

    python3 scripts/generate_status.py

Exits non-zero if a known_issues.json entry references a capability that
doesn't exist in recon_findings.json (catches typos/stale entries).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
RECON_PATH = ROOT / "recon_findings.json"
ISSUES_PATH = ROOT / "docs" / "known_issues.json"
OUTPUT_PATH = ROOT / "docs" / "STATUS.md"

SEVERITY_ICON = {"blocker": "🔴", "major": "🟠", "minor": "🟡"}
STATUS_ICON_VERIFIED = "🟢"
STATUS_ICON_UNVERIFIED = "⚪"
STATUS_ICON_BROKEN = "🔴"


def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def build_issue_map(issues_doc: dict, known_caps: set[str]) -> dict[str, list[dict]]:
    by_cap: dict[str, list[dict]] = defaultdict(list)
    for issue in issues_doc.get("issues", []):
        cap = issue["capability"]
        if cap not in known_caps:
            print(
                f"ERROR: known_issues.json references unknown capability "
                f"'{cap}' — not found in recon_findings.json. Fix the typo "
                f"or the capability was renamed.",
                file=sys.stderr,
            )
            sys.exit(1)
        by_cap[cap].append(issue)
    return by_cap


def row_status(entry: dict, open_issues: list[dict]) -> str:
    blockers = [i for i in open_issues if i["status"] == "open" and i["severity"] == "blocker"]
    majors = [i for i in open_issues if i["status"] == "open" and i["severity"] == "major"]
    if blockers or majors:
        return f"{STATUS_ICON_BROKEN} Known issue"
    if entry.get("verified"):
        return f"{STATUS_ICON_VERIFIED} Verified"
    return f"{STATUS_ICON_UNVERIFIED} Unverified (untested against live app)"


def render(recon: dict, issues_by_cap: dict[str, list[dict]]) -> str:
    caps = recon.get("capabilities", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append("# Capability Status")
    lines.append("")
    lines.append(
        "> **Generated file — do not hand-edit.** Rebuilt from "
        "`recon_findings.json` + `docs/known_issues.json` by "
        "`scripts/generate_status.py`. To change what this file says, "
        "either fix the underlying code and re-run recon, or edit "
        "`docs/known_issues.json` and re-run the generator."
    )
    lines.append("")
    lines.append(f"Last generated: {now}")
    lines.append(f"Source: `recon_findings.json` (schema v{recon.get('schema_version', '?')})")
    lines.append("")

    total = len(caps)
    verified = sum(1 for c in caps.values() if c.get("verified"))
    with_issues = len(issues_by_cap)
    lines.append(
        f"**{verified}/{total}** capabilities recon-verified · "
        f"**{with_issues}** have open known issues that override that "
        f"verification (see table)."
    )
    lines.append("")

    lines.append("## Capability matrix")
    lines.append("")
    lines.append("| Capability | Path | Recon status | Real-world status | Open issues |")
    lines.append("|---|---|---|---|---|")
    for name in sorted(caps.keys()):
        entry = caps[name]
        path = entry.get("path", "?")
        recon_status = "verified" if entry.get("verified") else "unverified"
        open_issues = [i for i in issues_by_cap.get(name, []) if i["status"] == "open"]
        status = row_status(entry, open_issues)
        issue_summaries = "; ".join(
            f"{SEVERITY_ICON.get(i['severity'], '•')} {i['summary']}" for i in open_issues
        ) or "—"
        lines.append(f"| `{name}` | `{path}` | {recon_status} | {status} | {issue_summaries} |")
    lines.append("")

    lines.append("## Open issues (detail)")
    lines.append("")
    any_open = False
    for name in sorted(issues_by_cap.keys()):
        open_issues = [i for i in issues_by_cap[name] if i["status"] == "open"]
        for issue in open_issues:
            any_open = True
            icon = SEVERITY_ICON.get(issue["severity"], "•")
            lines.append(f"### {icon} `{name}` — {issue['summary']}")
            lines.append("")
            lines.append(f"- **Severity:** {issue['severity']}")
            lines.append(f"- **Blocks primary goal:** {'yes' if issue.get('blocks_goal') else 'no'}")
            lines.append(f"- **Opened:** {issue['opened']}")
            lines.append(f"- **Detail:** {issue['detail_ref']}")
            lines.append("")
    if not any_open:
        lines.append("None.")
        lines.append("")

    lines.append("## Test coverage caveat")
    lines.append("")
    lines.append(
        "All current automated tests (`tests/*.py`) mock `DomUtils` and "
        "`CDPConnection` at the boundary. They verify controller → backend "
        "dispatch is wired correctly; they do **not** verify that any "
        "selector actually matches a live TradingView Desktop DOM. A "
        "passing test suite is not evidence that a `dom` capability works "
        "in practice — only `recon_findings.json`'s `verified` flag "
        "(ideally backed by a manual live-session check) is. See "
        "`docs/adr/0003-integration-vs-unit-test-boundary.md`."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    recon = load_json(RECON_PATH)
    issues_doc = load_json(ISSUES_PATH)
    known_caps = set(recon.get("capabilities", {}).keys())
    issues_by_cap = build_issue_map(issues_doc, known_caps)

    output = render(recon, issues_by_cap)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
