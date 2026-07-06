"""PineFamilyPlanner — read Pine Script source and produce a
generation_plan.json draft with input classification, family clustering,
tier ordering, and cross-family coupling candidates.

This is a **pure text-parsing tool** — no CDP, no live TradingView
Desktop dependency.  It reads Pine source as a string and is explicitly
a **heuristic engine**, not a Pine language AST parser.  Classification
will misfire on some inputs; that's what ``known_overrides`` is for.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Keyword lists (case-insensitive matching) ──────────────────

_COSMETIC_GROUP_KEYWORDS = frozenset({
    "color", "visual", "display", "dashboard", "label", "style",
})

# ── Tier 1: signal_generation ─────────────────────────────────
_TIER1_KEYWORDS = frozenset({
    "signal", "pattern", "structure", "flow", "trend",
    "oscillator", "squeeze", "cycle", "ma", "wave", "momentum",
    "divergence", "zigzag", "pivot", "fvg", "gap", "level",
    "zone", "block",
})

# ── Tier 2: scoring_and_gating ────────────────────────────────
_TIER2_KEYWORDS = frozenset({
    "context", "score", "conviction", "gate", "filter",
    "quality", "confluence", "valid", "strict", "engine",
})

# ── Tier 3: entry_and_execution ───────────────────────────────
_TIER3_KEYWORDS = frozenset({
    "strategy", "trade", "entry", "risk", "execution",
    "automation", "order", "position", "exit", "stop", "target",
})

# ── Tier 4: session_and_timing ────────────────────────────────
_TIER4_KEYWORDS = frozenset({
    "session", "time", "htf", "timeframe",
})

_TIER_KEYWORDS = [
    ("signal_generation", _TIER1_KEYWORDS),
    ("scoring_and_gating", _TIER2_KEYWORDS),
    ("entry_and_execution", _TIER3_KEYWORDS),
    ("session_and_timing", _TIER4_KEYWORDS),
]

# ── Regex patterns ─────────────────────────────────────────────

# Group variable assignment: identifier = "literal" or identifier = 'literal'
# Captures: (identifier, literal_value)
_GROUP_ASSIGN_RE = re.compile(
    r'(?:^|\n)\s*(?:var\s+)?(\w+)\s*=\s*["\']([^"\']+)["\']',
    re.MULTILINE,
)

# Input function call — matches the opening of an input.*() or input() call.
# Captures: (full_type, identifier, ...rest)
# Handles: input.bool(), input.int(), input.float(), input.string(),
#          input.color(), input.source(), input.session(), input.time(),
#          and bare input()
_INPUT_CALL_START_RE = re.compile(
    r'(?:^|\n)\s*'
    r'(\w+)\s*=\s*'
    r'input(?:\.(bool|int|float|string|color|source|session|time))?'
    r'\s*\(',
    re.MULTILINE,
)

# Match the full input() call body — from opening paren to matching
# closing paren.  This is a balanced-paren matcher that handles
# multi-line calls with nested parens in expressions.
#
# Strategy: for each match start, scan forward tracking paren depth
# until we find the matching close.

# Variable name used in group= argument — captures the identifier
_GROUP_ARG_RE = re.compile(r'\bgroup\s*=\s*(\w+)')

# Input title — second positional arg when it's a string literal
# After the first arg (default), matches a string literal title
_TITLE_RE = re.compile(r',\s*["\']([^"\']+)["\']')

# options=[...] detection
_OPTIONS_RE = re.compile(r'\boptions\s*=\s*\[', re.IGNORECASE)

# Default value extraction: the first simple literal after the opening paren
# (call_body starts after '(' so we match at the beginning, allowing whitespace/newlines)
_DEFAULT_SIMPLE_RE = re.compile(r'^\s*(true|false|-?\d+(?:\.\d+)?)\b')

# strategy.entry / strategy.exit / strategy.close calls
_STRATEGY_ENTRY_EXIT_RE = re.compile(
    r'\bstrategy\.(entry|exit|close)\s*\(',
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _normalize_line_endings(text: str) -> str:
    """Convert CRLF → LF so regex line-spanning isn't broken."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _find_matching_paren(text: str, open_pos: int) -> int:
    """Return the position of the matching ``)`` for the ``(`` at *open_pos*.

    Handles nested parens inside expressions (e.g. ``input(..., minval=...)``).
    Returns ``-1`` if no matching close is found.
    """
    depth = 0
    for i in range(open_pos, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _tier_for_group(group_name: str) -> str:
    """Assign a tier label based on keyword heuristics against *group_name*.

    Returns the first-matching tier name or ``"unordered"``.
    """
    lower = group_name.lower()
    for tier_name, keywords in _TIER_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return tier_name
    return "unordered"


# ═══════════════════════════════════════════════════════════════
# Planner
# ═══════════════════════════════════════════════════════════════

class PineFamilyPlanner:
    """Parse Pine Script source into a generation_plan.json draft.

    Pure function of the source text — no I/O.  Use ``write_plan()``
    to persist the output and merge with existing ``known_overrides``.
    """

    # ── Public API ────────────────────────────────────────────

    def parse(self, pine_source: str, strategy_name: str) -> dict[str, Any]:
        """Full pipeline: parse → classify → cluster → order → coupling.

        Returns a ``generation_plan`` dict following the schema described
        in the module docstring / ADR-0011.
        """
        source = _normalize_line_endings(pine_source)
        group_map = self._build_group_map(source)
        inputs = self._extract_inputs(source, group_map)

        plan: dict[str, Any] = {
            "schema_version": 1,
            "source_file": strategy_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requires_strategy_harness": self._check_requires_harness(source),
            "total_inputs_found": len(inputs),
            "families": {},
            "excluded_cosmetic": [],
            "unclassified": [],
            "coupling_candidates": [],
            "known_overrides": {},
        }

        # Classify
        classified = [(inp, self._classify(inp, group_map)) for inp in inputs]

        # Split cosmetic out
        cosmetic = [
            inp for inp, cls in classified if cls == "cosmetic"
        ]
        non_cosmetic = [
            (inp, cls)
            for inp, cls in classified
            if cls != "cosmetic"
        ]

        plan["excluded_cosmetic"] = [
            {"name": inp["name"], "group": inp.get("resolved_group", "?")}
            for inp in cosmetic
        ]

        # Unclassified (non-cosmetic but not confidently classified)
        unclassified = [
            inp for inp, cls in non_cosmetic if cls == "unclassified"
        ]
        plan["unclassified"] = [
            {"name": inp["name"], "reason": inp.get("_unclassified_reason", "No clear cosmetic/tunable/toggle signal")}
            for inp in unclassified
        ]

        tunable_or_toggle = [
            (inp, cls)
            for inp, cls in non_cosmetic
            if cls in ("tunable", "structural_toggle")
        ]

        # Cluster into families
        families: dict[str, dict[str, Any]] = {}
        for inp, cls in tunable_or_toggle:
            family_name = (
                inp.get("resolved_group")
                or inp.get("raw_group_identifier")
                or "(ungrouped)"
            )
            if family_name not in families:
                families[family_name] = {
                    "tier": _tier_for_group(family_name),
                    "group_name_unresolved": inp.get(
                        "group_name_unresolved", False
                    ),
                    "inputs": [],
                }
            families[family_name]["inputs"].append({
                "name": inp["name"],
                "type": inp["type"],
                "classification": cls,
                "default": inp.get("default"),
                "title": inp.get("title"),
                "raw_group_identifier": inp.get("raw_group_identifier"),
            })
            if inp.get("default_unparsed"):
                families[family_name]["inputs"][-1]["default_unparsed"] = True

        plan["families"] = families

        # Coupling candidates
        plan["coupling_candidates"] = self._detect_coupling(source, families)

        return plan

    def write_plan(
        self,
        plan: dict[str, Any],
        output_dir: Path = Path("docs/generation_plans"),
    ) -> tuple[Path, Path]:
        """Write ``generation_plan.json`` and companion ``.md`` summary.

        If a ``generation_plan.json`` already exists for this
        ``source_file``, its ``known_overrides`` are loaded and merged
        into *plan* before writing — so manual classification fixes
        survive a re-run after the Pine source changes.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        strategy_name = plan["source_file"]
        # Sanitize for filename
        safe_name = re.sub(r"[^\w\-.]", "_", strategy_name)

        json_path = output_dir / f"{safe_name}_generation_plan.json"
        md_path = output_dir / f"{safe_name}_plan.md"

        # ── Merge existing overrides ──────────────────────────
        if json_path.exists():
            try:
                existing = json.loads(json_path.read_text())
                existing_overrides = existing.get("known_overrides", {})
                # Merge: existing overrides take precedence over heuristic
                merged = {**plan.get("known_overrides", {}), **existing_overrides}
                plan["known_overrides"] = merged
                # Apply overrides to re-classify
                self._apply_overrides(plan, merged)
            except (json.JSONDecodeError, KeyError):
                pass

        # ── Write JSON ────────────────────────────────────────
        json_path.write_text(json.dumps(plan, indent=2, default=str))

        # ── Write Markdown ────────────────────────────────────
        md = self._render_markdown(plan)
        md_path.write_text(md)

        return json_path, md_path

    # ── Internal: build group variable map ────────────────────

    def _build_group_map(self, source: str) -> dict[str, str]:
        """Collect ``identifier = "literal"`` assignments to resolve
        ``group=<identifier>`` references.

        Handles both double-quoted and single-quoted strings, and
        ``var identifier = "..."`` declarations.
        """
        group_map: dict[str, str] = {}
        for m in _GROUP_ASSIGN_RE.finditer(source):
            ident = m.group(1)
            value = m.group(2)
            group_map[ident] = value
        return group_map

    # ── Internal: extract all input() calls ───────────────────

    def _extract_inputs(
        self, source: str, group_map: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Find every ``input.*(...)`` or ``input(...)`` call at the
        top level of the source and return a list of input dicts.
        """
        inputs: list[dict[str, Any]] = []

        for m in _INPUT_CALL_START_RE.finditer(source):
            var_name = m.group(1)
            input_type = m.group(2) or "auto"  # bare input()
            open_paren = m.end() - 1  # position of '('
            close_paren = _find_matching_paren(source, open_paren)
            if close_paren < 0:
                continue

            call_body = source[open_paren + 1 : close_paren]

            # Resolve group
            raw_group = None
            resolved_group = None
            group_unresolved = False
            gm = _GROUP_ARG_RE.search(call_body)
            if gm:
                raw_group = gm.group(1)
                if raw_group in group_map:
                    resolved_group = group_map[raw_group]
                else:
                    resolved_group = raw_group
                    group_unresolved = True

            # Title (second positional arg, if a string literal)
            title = None
            tm = _TITLE_RE.search(call_body)
            if tm:
                title = tm.group(1)

            # Default value (from call_body, which starts after '(')
            default = None
            default_unparsed = False
            dm = _DEFAULT_SIMPLE_RE.search(call_body)
            if dm:
                raw = dm.group(1)
                if raw == "true":
                    default = True
                elif raw == "false":
                    default = False
                else:
                    try:
                        default = int(raw)
                    except ValueError:
                        default = float(raw)
            else:
                # Expression — can't parse reliably as text
                default = None
                default_unparsed = True

            # Structural toggle: bool or string with options
            if input_type == "auto":
                # Bare input() — try to infer type from default
                if isinstance(default, bool):
                    input_type = "bool"
                elif isinstance(default, (int, float)):
                    input_type = "float" if isinstance(default, float) else "int"
                else:
                    input_type = "unknown"

            inp: dict[str, Any] = {
                "name": var_name,
                "type": input_type,
                "default": default,
                "title": title,
                "raw_group_identifier": raw_group,
                "resolved_group": resolved_group,
                "group_name_unresolved": group_unresolved,
                "raw_source": source[m.start() : close_paren + 1],
            }
            if default_unparsed:
                inp["default_unparsed"] = True

            inputs.append(inp)

        return inputs

    # ── Internal: classify ────────────────────────────────────

    def _classify(
        self, inp: dict[str, Any], group_map: dict[str, str]
    ) -> str:
        """Return ``"cosmetic"``, ``"structural_toggle"``, ``"tunable"``,
        or ``"unclassified"``.
        """
        input_type = inp["type"]
        group_name = (inp.get("resolved_group") or inp.get("raw_group_identifier") or "").lower()
        raw_group = (inp.get("raw_group_identifier") or "").lower()

        # color type → always cosmetic
        if input_type == "color":
            return "cosmetic"

        # check group name / identifier against cosmetic keywords
        if any(kw in group_name or kw in raw_group for kw in _COSMETIC_GROUP_KEYWORDS):
            return "cosmetic"

        # bool → structural toggle (unless caught by cosmetic above)
        if input_type == "bool":
            return "structural_toggle"

        # string with options → structural toggle
        if input_type == "string" and _OPTIONS_RE.search(inp.get("raw_source", "")):
            return "structural_toggle"

        # int / float → tunable
        if input_type in ("int", "float"):
            return "tunable"

        # Everything else: source, session, time, unknown
        inp["_unclassified_reason"] = (
            f"input.{input_type} with no clear cosmetic/tunable/toggle signal"
        )
        return "unclassified"

    # ── Internal: check strategy harness ──────────────────────

    def _check_requires_harness(self, source: str) -> bool:
        """Return ``True`` if the source has zero ``strategy.entry`` /
        ``strategy.exit`` / ``strategy.close`` calls.
        """
        return not bool(_STRATEGY_ENTRY_EXIT_RE.search(source))

    # ── Internal: coupling detection ──────────────────────────

    def _detect_coupling(
        self,
        source: str,
        families: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Heuristic cross-family coupling detection via variable-name
        co-occurrence in ``if`` / ternary / boolean expressions.
        """
        if len(families) < 2:
            return []

        # Build a map: variable_name → family_name
        var_to_family: dict[str, str] = {}
        for fname, fdata in families.items():
            for inp in fdata["inputs"]:
                var_to_family[inp["name"]] = fname

        family_names = list(families.keys())
        candidates: list[dict[str, Any]] = []

        for i in range(len(family_names)):
            for j in range(i + 1, len(family_names)):
                fa = family_names[i]
                fb = family_names[j]
                vars_a = {
                    inp["name"] for inp in families[fa]["inputs"]
                }
                vars_b = {
                    inp["name"] for inp in families[fb]["inputs"]
                }

                # Check each var from A for co-occurrence with any var from B
                # on the same line — a broad heuristic, not AST analysis.
                evidence_lines: list[str] = []
                for line_num, line in enumerate(source.split("\n"), 1):
                    found_a = any(re.search(rf'\b{re.escape(va)}\b', line) for va in vars_a)
                    found_b = any(re.search(rf'\b{re.escape(vb)}\b', line) for vb in vars_b)
                    if found_a and found_b:
                        # Find which specific vars matched
                        matched_a = [va for va in vars_a if re.search(rf'\b{re.escape(va)}\b', line)]
                        matched_b = [vb for vb in vars_b if re.search(rf'\b{re.escape(vb)}\b', line)]
                        evidence_lines.append(
                            f"{', '.join(matched_a[:2])} and "
                            f"{', '.join(matched_b[:2])} appear together "
                            f"(line {line_num})"
                        )
                    if len(evidence_lines) >= 3:
                        break

                if evidence_lines:
                    candidates.append({
                        "family_a": fa,
                        "family_b": fb,
                        "evidence": evidence_lines[:3],
                        "confidence": (
                            "heuristic — human review required, "
                            "not a proven dependency"
                        ),
                    })

        return candidates

    # ── Internal: apply overrides ─────────────────────────────

    def _apply_overrides(
        self, plan: dict[str, Any], overrides: dict[str, Any]
    ) -> None:
        """Re-classify inputs according to ``known_overrides``.

        Moves inputs between ``excluded_cosmetic``, ``unclassified``,
        and family buckets as needed.
        """
        for override_key, new_class in overrides.items():
            # Check excluded_cosmetic first
            cosmetic = plan.get("excluded_cosmetic", [])
            for idx, c in enumerate(cosmetic):
                if c["name"] == override_key:
                    # Remove from cosmetic, re-add to appropriate family
                    removed = cosmetic.pop(idx)
                    self._place_into_family(plan, removed, new_class)
                    break
            else:
                # Check unclassified
                unclassified = plan.get("unclassified", [])
                for idx, u in enumerate(unclassified):
                    if u["name"] == override_key:
                        removed = unclassified.pop(idx)
                        self._place_into_family(plan, removed, new_class)
                        break
                else:
                    # Already in a family — just update classification
                    for family_data in plan.get("families", {}).values():
                        for inp in family_data["inputs"]:
                            if inp["name"] == override_key:
                                inp["classification"] = new_class
                                break

    def _place_into_family(
        self,
        plan: dict[str, Any],
        inp_info: dict[str, Any],
        classification: str,
    ) -> None:
        """Move an input from cosmetic/unclassified into the right family
        with the given classification.

        We don't have the full parsed input dict anymore (only name/group),
        but we can create a minimal entry.  The override mechanism is about
        classification, not full re-parsing.
        """
        family_name = inp_info.get("group", "(unknown)")
        if family_name not in plan.get("families", {}):
            plan["families"][family_name] = {
                "tier": _tier_for_group(family_name),
                "group_name_unresolved": False,
                "inputs": [],
            }
        plan["families"][family_name]["inputs"].append({
            "name": inp_info["name"],
            "type": "unknown",
            "classification": classification,
            "default": None,
            "title": None,
            "raw_group_identifier": inp_info.get("group"),
        })

    # ── Internal: render Markdown ─────────────────────────────

    def _render_markdown(self, plan: dict[str, Any]) -> str:
        """Generate the companion ``_plan.md``."""
        lines: list[str] = []
        lines.append(f"# Generation Plan: {plan['source_file']}")
        lines.append("")
        lines.append(
            "> **Generated file — do not hand-edit.** Rebuilt from "
            "`pine_family_planner.py` from the Pine Script source. "
            "To change classifications, edit the associated "
            "`generation_plan.json`'s `known_overrides` section and "
            "re-run the planner."
        )
        lines.append("")
        lines.append(
            f"Generated: {plan.get('generated_at', '?')} · "
            f"Schema v{plan.get('schema_version', '?')}"
        )
        lines.append("")

        # Harness banner
        if plan.get("requires_strategy_harness"):
            lines.append(
                "> ⚠️ **This file has no `strategy.entry` / `strategy.exit` / "
                "`strategy.close` calls.** No experiment generation can run "
                "against it until a strategy wrapper is added."
            )
            lines.append("")

        # Summary
        lines.append(f"**Total inputs found:** {plan['total_inputs_found']}")
        lines.append(
            f"**Excluded (cosmetic):** {len(plan.get('excluded_cosmetic', []))}"
        )
        lines.append(
            f"**Unclassified (needs human review):** "
            f"{len(plan.get('unclassified', []))}"
        )
        lines.append("")

        # Families
        families = plan.get("families", {})
        if families:
            # Sort by tier then name
            tier_order = {
                "signal_generation": 1,
                "scoring_and_gating": 2,
                "entry_and_execution": 3,
                "session_and_timing": 4,
                "unordered": 99,
            }
            sorted_fams = sorted(
                families.items(),
                key=lambda x: (tier_order.get(x[1]["tier"], 99), x[0]),
            )

            lines.append("## Tuning Families")
            lines.append("")
            lines.append(
                "| Tier | Family | Inputs | Toggles | Tunables | "
                "Group Unresolved |"
            )
            lines.append(
                "|---|---|---|---|---|---|"
            )
            for fname, fdata in sorted_fams:
                toggles = sum(
                    1 for i in fdata["inputs"]
                    if i["classification"] == "structural_toggle"
                )
                tunables = sum(
                    1 for i in fdata["inputs"]
                    if i["classification"] == "tunable"
                )
                unresolved = "⚠️" if fdata.get("group_name_unresolved") else ""
                lines.append(
                    f"| {fdata['tier']} | **{fname}** | "
                    f"{len(fdata['inputs'])} | {toggles} | {tunables} | "
                    f"{unresolved} |"
                )
            lines.append("")

        # Coupling candidates
        coupling = plan.get("coupling_candidates", [])
        if coupling:
            lines.append("## ⚠️ Coupling Candidates (heuristic — review required)")
            lines.append("")
            lines.append(
                "These variable pairs appear together in conditional "
                "contexts. **This is NOT proof of dependency** — it is a "
                "prompt to check whether these families can be tuned "
                "independently."
            )
            lines.append("")
            for cc in coupling:
                lines.append(
                    f"- **{cc['family_a']}** ↔ **{cc['family_b']}** "
                    f"({cc['confidence']})"
                )
                for ev in cc.get("evidence", []):
                    lines.append(f"  - {ev}")
            lines.append("")

        # Excluded cosmetic
        cosmetic = plan.get("excluded_cosmetic", [])
        if cosmetic:
            lines.append(
                f"## Excluded (Cosmetic) — {len(cosmetic)} inputs"
            )
            lines.append("")
            lines.append(
                "These inputs affect visual appearance only and are "
                "excluded from all tuning tiers."
            )
            lines.append("")

        # Unclassified
        unclassified = plan.get("unclassified", [])
        if unclassified:
            lines.append(
                f"## Unclassified — {len(unclassified)} inputs need review"
            )
            lines.append("")
            for u in unclassified:
                lines.append(f"- **{u['name']}**: {u['reason']}")
            lines.append("")

        # Overrides
        overrides = plan.get("known_overrides", {})
        if overrides:
            lines.append("## Manual Overrides")
            lines.append("")
            for name, cls in overrides.items():
                lines.append(f"- `{name}` → `{cls}`")
            lines.append("")

        return "\n".join(lines) + "\n"
