#!/usr/bin/env python3
"""CLI entry point for PineFamilyPlanner — generates a generation_plan.json
and companion .md from a local .pine file without needing TradingView
Desktop running.

Usage::

    python3 scripts/plan_generation.py path/to/strategy.pine
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root without PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.services.pine_family_planner import PineFamilyPlanner


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/plan_generation.py <path-to-pine-file>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    source = path.read_text(encoding="utf-8")
    strategy_name = path.stem

    planner = PineFamilyPlanner()
    plan = planner.parse(source, strategy_name)

    output_dir = Path("docs/generation_plans")
    json_path, md_path = planner.write_plan(plan, output_dir)

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print()
    print(f"  Total inputs found: {plan['total_inputs_found']}")
    print(f"  Families: {len(plan['families'])}")
    print(f"  Excluded cosmetic: {len(plan['excluded_cosmetic'])}")
    print(f"  Unclassified: {len(plan['unclassified'])}")
    print(f"  Coupling candidates: {len(plan['coupling_candidates'])}")
    if plan.get("requires_strategy_harness"):
        print("  ⚠️  No strategy.entry/exit/close calls — requires harness wrapper")


if __name__ == "__main__":
    main()
