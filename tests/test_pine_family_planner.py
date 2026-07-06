"""Tests for PineFamilyPlanner — real fixtures, real assertions.

Uses actual .pine files from tests/fixtures/pine_scripts/ as
test fixtures.  No synthetic toy examples for the core assertions.
"""

import json
from pathlib import Path

import pytest

from core.services.pine_family_planner import PineFamilyPlanner

FIXTURES = Path(__file__).parent / "fixtures" / "pine_scripts"

# ── Helpers ────────────────────────────────────────────────────

def _read_fixture(name: str) -> str:
    path = FIXTURES / name
    assert path.exists(), f"Fixture not found: {path}"
    return path.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# GT_VP — the 211-input monster
# ═══════════════════════════════════════════════════════════════

class TestGTVP:
    """GT_VP_v9.9.6_STRAT.pine — largest fixture, 211 inputs, 17 groups,
    real coupling candidate at line ~4144."""

    @pytest.fixture(scope="function")
    def plan(self, request) -> dict:
        cls = request.cls
        planner = PineFamilyPlanner()
        source = _read_fixture("GT_VP_v9.9.6_STRAT.pine")
        request.cls._gtvp_plan = planner.parse(source, "GT_VP_v9.9.6_STRAT")
        return request.cls._gtvp_plan

    def test_total_inputs_in_neighborhood_of_211(self, plan):
        """Not an exact number (Pine files get re-versioned), but must
        be in a reasonable range."""
        count = plan["total_inputs_found"]
        assert 190 <= count <= 230, (
            f"Expected GT_VP to have roughly 211 inputs, got {count}"
        )

    def test_requires_strategy_harness_is_false(self, plan):
        """GT_VP has strategy.entry calls — it IS a strategy."""
        assert plan["requires_strategy_harness"] is False

    def test_group_colors_inputs_land_in_excluded_cosmetic(self, plan):
        """All 34 group_colors inputs should be cosmetic."""
        cosmetic = plan["excluded_cosmetic"]
        color_inputs = [c for c in cosmetic if "color" in c.get("group", "").lower()]
        assert len(color_inputs) >= 30, (
            f"Expected roughly 34 color inputs in excluded_cosmetic, got {len(color_inputs)}"
        )

    def test_families_has_multiple_tiers(self, plan):
        """GT_VP should have inputs spread across tiers."""
        families = plan["families"]
        tiers = {f["tier"] for f in families.values()}
        assert len(tiers) >= 3, f"Expected at least 3 tiers, got {tiers}"

    def test_coupling_candidates_not_empty(self, plan):
        """GT_VP has known real couplings; the heuristic should find some."""
        candidates = plan["coupling_candidates"]
        assert len(candidates) >= 1, (
            "Expected at least one coupling candidate for GT_VP"
        )


# ═══════════════════════════════════════════════════════════════
# PATTERNFORGE — indicator, no strategy entry/exit calls
# ═══════════════════════════════════════════════════════════════

class TestPatternforge:
    @pytest.fixture(scope="function")
    def plan(self, request) -> dict:
        planner = PineFamilyPlanner()
        source = _read_fixture("PATTERNFORGE_5_24.pine")
        return planner.parse(source, "PATTERNFORGE_5_24")

    def test_requires_strategy_harness_is_true(self, plan):
        """PATTERNFORGE has zero entry/exit calls — it's an indicator."""
        assert plan["requires_strategy_harness"] is True


# ═══════════════════════════════════════════════════════════════
# CRSI — toggle-heavy (42 bools vs ~39 numerics)
# ═══════════════════════════════════════════════════════════════

class TestCRSI:
    @pytest.fixture(scope="function")
    def plan(self, request) -> dict:
        planner = PineFamilyPlanner()
        source = _read_fixture("CRSI_Prestige_Strategy.pine")
        return planner.parse(source, "CRSI_Prestige_Strategy")

    def test_toggle_count_close_to_tunable_count(self, plan):
        """CRSI is the 'toggle-heavy' case: ~42 bools vs ~39 numerics."""
        toggles = 0
        tunables = 0
        for fam in plan["families"].values():
            for inp in fam["inputs"]:
                if inp["classification"] == "structural_toggle":
                    toggles += 1
                elif inp["classification"] == "tunable":
                    tunables += 1

        # Allow reasonable tolerance — Pine files get re-versioned
        assert toggles >= 30, f"Expected >= 30 toggles for CRSI, got {toggles}"
        assert tunables >= 25, f"Expected >= 25 tunables for CRSI, got {tunables}"
        # The ratio should be close — not more than 2:1 either way
        ratio = max(toggles, tunables) / max(min(toggles, tunables), 1)
        assert ratio <= 2.0, (
            f"CRSI toggle/tunable ratio too skewed: {toggles} toggles vs "
            f"{tunables} tunables (ratio {ratio:.1f})"
        )


# ═══════════════════════════════════════════════════════════════
# SMC — LF-only, short-form input(), SCREAMING_SNAKE_CASE groups
# ═══════════════════════════════════════════════════════════════

class TestSMC:
    @pytest.fixture(scope="function")
    def plan(self, request) -> dict:
        planner = PineFamilyPlanner()
        source = _read_fixture("Smart_Money_Concepts_LuxAlgo_Strategy_Engine.pine")
        return planner.parse(source, "Smart_Money_Concepts_LuxAlgo_Strategy_Engine")

    def test_parses_lf_only_file(self, plan):
        """SMC is the ONLY file with LF (not CRLF) line endings."""
        assert plan["total_inputs_found"] > 0

    def test_requires_strategy_harness_is_false(self, plan):
        """SMC has strategy.entry calls."""
        assert plan["requires_strategy_harness"] is False


# ═══════════════════════════════════════════════════════════════
# Hurst Cycle Channel — indicator, no strategy
# ═══════════════════════════════════════════════════════════════

class TestHurst:
    @pytest.fixture(scope="function")
    def plan(self, request) -> dict:
        planner = PineFamilyPlanner()
        source = _read_fixture("Hurst_Cycle_Channel_[RunsTV].pine")
        return planner.parse(source, "Hurst_Cycle_Channel_[RunsTV]")

    def test_requires_strategy_harness_is_true(self, plan):
        """Hurst has zero entry/exit calls — indicator only."""
        assert plan["requires_strategy_harness"] is True

    def test_has_inputs(self, plan):
        """Hurst should have ~51 inputs."""
        assert plan["total_inputs_found"] >= 40


# ═══════════════════════════════════════════════════════════════
# Multi-line input() parsing
# ═══════════════════════════════════════════════════════════════

class TestMultiLineInput:
    def test_three_line_input_parses_correctly(self):
        """An input() call spanning multiple lines with the group= on
        the last line must parse correctly."""
        source = (
            'group_test = "Test Group"\n'
            "my_param = input.int(14, \"My Parameter\",\n"
            "    minval=1, maxval=100,\n"
            "    group=group_test,\n"
            '    tooltip="A test parameter")\n'
        )
        planner = PineFamilyPlanner()
        plan = planner.parse(source, "test_strategy")

        assert plan["total_inputs_found"] == 1
        families = plan["families"]
        assert "Test Group" in families
        inp = families["Test Group"]["inputs"][0]
        assert inp["name"] == "my_param"
        assert inp["type"] == "int"
        assert inp["classification"] == "tunable"
        assert inp["default"] == 14
        assert inp["title"] == "My Parameter"

    def test_input_spanning_with_tooltip_on_last_line(self):
        """Simulate GT_VP's enable_strategy pattern — tooltip pushes
        the closing paren to a separate line."""
        source = (
            'group_strategy = "Strategy Harness"\n'
            'enable_strategy = input.bool(false, "Enable Strategy",\n'
            '    group=group_strategy,\n'
            '    tooltip="OFF keeps this script visually safe without placing orders."\n'
            ')\n'
        )
        planner = PineFamilyPlanner()
        plan = planner.parse(source, "test_strategy")

        assert plan["total_inputs_found"] == 1
        families = plan["families"]
        assert "Strategy Harness" in families
        inp = families["Strategy Harness"]["inputs"][0]
        assert inp["name"] == "enable_strategy"
        assert inp["classification"] == "structural_toggle"
        assert inp["default"] is False


# ═══════════════════════════════════════════════════════════════
# known_overrides round-trip
# ═══════════════════════════════════════════════════════════════

class TestOverridesRoundTrip:
    def test_override_survives_reparse(self, tmp_path: Path):
        """Write a plan, add an override, re-parse, assert the override
        survived and the classification in the output matches the
        override, not the original heuristic."""
        source = (
            'group_main = "Main Settings"\n'
            "my_length = input.int(14, \"Length\", group=group_main)\n"
            "my_color = input.color(color.red, \"Line Color\", group=group_main)\n"
        )
        planner = PineFamilyPlanner()
        plan = planner.parse(source, "override_test")

        # my_color should be cosmetic by heuristic (input.color → cosmetic)
        # But we override it to tunable
        plan["known_overrides"] = {"my_color": "tunable"}

        # Write
        out_dir = tmp_path / "generation_plans"
        json_path, md_path = planner.write_plan(plan, out_dir)
        assert json_path.exists()

        # Re-parse fresh (simulate source change)
        plan2 = planner.parse(source, "override_test")
        json_path2, _ = planner.write_plan(plan2, out_dir)

        # The second write should have merged the overrides
        saved = json.loads(json_path2.read_text())
        assert "my_color" in saved["known_overrides"]
        assert saved["known_overrides"]["my_color"] == "tunable"

        # The classification should match the override
        families = saved["families"]
        main_fam = families.get("Main Settings", {})
        color_inps = [i for i in main_fam.get("inputs", []) if i["name"] == "my_color"]
        assert len(color_inps) == 1
        assert color_inps[0]["classification"] == "tunable"


# ═══════════════════════════════════════════════════════════════
# CRLF handling
# ═══════════════════════════════════════════════════════════════

class TestCRLFHandling:
    def test_crlf_produces_same_result_as_lf(self):
        """A fixture with \\r\\n line endings should produce the same
        parsed result as the LF-normalized equivalent."""
        source = (
            'group_test = "Test Group"\n'
            "my_bool = input.bool(true, \"My Bool\", group=group_test)\n"
            "my_int = input.int(14, \"My Int\", group=group_test)\n"
        )
        crlf_source = source.replace("\n", "\r\n")

        planner = PineFamilyPlanner()
        plan_lf = planner.parse(source, "crlf_test")
        plan_crlf = planner.parse(crlf_source, "crlf_test")

        # Total count should match
        assert plan_lf["total_inputs_found"] == plan_crlf["total_inputs_found"]

        # Family structure should match
        assert plan_lf["families"] == plan_crlf["families"]

        # Classification counts should match
        def _count_class(plan, cls):
            count = 0
            for fam in plan["families"].values():
                for inp in fam["inputs"]:
                    if inp["classification"] == cls:
                        count += 1
            return count

        for cls in ("structural_toggle", "tunable", "cosmetic"):
            assert _count_class(plan_lf, cls) == _count_class(plan_crlf, cls), (
                f"CRLF/LF mismatch for classification {cls}"
            )
