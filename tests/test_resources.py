"""Tests for the device-tier resource plan.

The plan is the promise that a small machine gets a slow run instead of a dead
one, so these tests pin the two halves of that promise: limits really do fall as
the machine gets smaller, and the things the user asked for do not move at all.
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import resources

GIB = 1024 ** 3


class TierSelectionTests(unittest.TestCase):
    def test_two_gigabytes_is_minimal(self):
        self.assertEqual(resources.tier_for(2 * GIB, 4), "minimal")

    def test_just_under_four_gigabytes_is_still_minimal(self):
        self.assertEqual(resources.tier_for(int(3.9 * GIB), 4), "minimal")

    def test_four_gigabytes_is_low(self):
        self.assertEqual(resources.tier_for(4 * GIB, 4), "low")

    def test_eight_gigabytes_is_balanced(self):
        self.assertEqual(resources.tier_for(8 * GIB, 4), "balanced")

    def test_sixteen_gigabytes_is_high(self):
        self.assertEqual(resources.tier_for(16 * GIB, 8), "high")

    def test_one_core_is_minimal_however_much_memory_it_has(self):
        self.assertEqual(resources.tier_for(64 * GIB, 1), "minimal")

    def test_unknown_memory_is_balanced_not_minimal(self):
        # Guessing low would quietly cut a capable machine's limits, which is the
        # same kind of wrong answer as guessing high on a weak one.
        self.assertEqual(resources.tier_for(None, 8), "balanced")

    def test_zero_cores_does_not_crash(self):
        self.assertEqual(resources.tier_for(2 * GIB, 0), "minimal")


class PlanShapeTests(unittest.TestCase):
    def _plan(self, **overrides):
        args = dict(cpu_count=2, ram_bytes=3 * GIB, available_bytes=2 * GIB,
                    free_disk_bytes=10 ** 10, gpu={"detected": False})
        args.update(overrides)
        return resources.plan("auto", **args)

    def test_a_weak_machine_plans_a_minimal_run(self):
        plan = self._plan()
        self.assertEqual(plan["tier"], "minimal")
        self.assertEqual(plan["detected_tier"], "minimal")
        self.assertIsNone(plan["pressure"])

    def test_the_plan_records_where_its_facts_came_from(self):
        self.assertEqual(self._plan()["facts"]["source"], "supplied")

    def test_every_tier_runs_one_heavy_job_at_a_time(self):
        for tier in resources.TIERS:
            with self.subTest(tier=tier):
                self.assertEqual(resources.TIER_LIMITS[tier]["max_parallel_heavy_jobs"], 1)

    def test_limits_never_rise_as_the_machine_gets_smaller(self):
        ordered = list(reversed(resources.TIERS))  # high -> minimal
        for smaller, larger in zip(ordered[1:], ordered[:-1]):
            with self.subTest(smaller=smaller, larger=larger):
                for key, value in resources.TIER_LIMITS[smaller].items():
                    self.assertLessEqual(value, resources.TIER_LIMITS[larger][key],
                                         f"{key} grew for the smaller tier")

    def test_a_smaller_tier_never_asks_for_a_longer_wait_or_bigger_read(self):
        self.assertLess(resources.TIER_LIMITS["minimal"]["model_timeout_seconds"],
                        resources.TIER_LIMITS["high"]["model_timeout_seconds"])
        self.assertLess(resources.TIER_LIMITS["minimal"]["dataset_max_bytes"],
                        resources.TIER_LIMITS["high"]["dataset_max_bytes"])

    def test_quality_settings_are_declared_unchangeable(self):
        text = " ".join(self._plan()["never_changes"])
        for promise in ("resolution", "language", "chart values"):
            self.assertIn(promise, text)

    def test_degradations_are_named_in_words_for_the_smallest_tier(self):
        degradations = self._plan()["degradations"]
        self.assertTrue(degradations)
        self.assertTrue(any("token" in line for line in degradations))

    def test_the_largest_tier_admits_no_degradation(self):
        plan = self._plan(cpu_count=16, ram_bytes=64 * GIB, available_bytes=60 * GIB)
        self.assertEqual(plan["tier"], "high")
        self.assertEqual(plan["degradations"], [])

    def test_the_same_facts_produce_the_same_plan(self):
        self.assertEqual(self._plan(), self._plan())

    def test_an_explicit_profile_wins_and_says_so(self):
        plan = resources.plan("high", cpu_count=2, ram_bytes=2 * GIB,
                              available_bytes=1 * GIB, free_disk_bytes=10 ** 10)
        self.assertEqual(plan["tier"], "high")
        self.assertEqual(plan["detected_tier"], "minimal")
        self.assertTrue(any("requested explicitly" in line for line in plan["reasons"]))

    def test_an_unknown_profile_falls_back_to_auto_and_records_it(self):
        plan = resources.plan("turbo", cpu_count=2, ram_bytes=2 * GIB,
                              available_bytes=1 * GIB, free_disk_bytes=10 ** 10)
        self.assertEqual(plan["requested"], "auto")
        self.assertEqual(plan["tier"], "minimal")
        self.assertTrue(any("unknown profile" in line for line in plan["reasons"]))

    def test_blank_profile_means_auto(self):
        self.assertEqual(resources.plan("", cpu_count=2, ram_bytes=2 * GIB,
                                        available_bytes=1 * GIB)["tier"], "minimal")


class MemoryPressureTests(unittest.TestCase):
    def _plan(self, free, available):
        return resources.plan("auto", cpu_count=4, ram_bytes=8 * GIB,
                              available_bytes=available, free_disk_bytes=free)

    def test_a_healthy_machine_is_not_downgraded(self):
        plan = self._plan(free=10 ** 10, available=int(6 * GIB))
        self.assertEqual(plan["tier"], "balanced")
        self.assertIsNone(plan["pressure"])

    def test_almost_no_free_memory_lowers_the_limits_for_this_run(self):
        plan = self._plan(free=10 ** 10, available=int(0.4 * GIB))
        self.assertEqual(plan["tier"], "low")
        self.assertEqual(plan["detected_tier"], "balanced")
        self.assertEqual(plan["pressure"], "low")
        self.assertTrue(any("available right now" in line for line in plan["reasons"]))

    def test_pressure_never_pushes_below_minimal(self):
        plan = resources.plan("auto", cpu_count=2, ram_bytes=2 * GIB,
                              available_bytes=int(0.05 * GIB), free_disk_bytes=10 ** 10)
        self.assertEqual(plan["tier"], "minimal")
        self.assertEqual(resources.TIERS[0], "minimal")

    def test_no_available_memory_figure_means_no_pressure_verdict(self):
        plan = self._plan(free=10 ** 10, available=None)
        if plan["facts"]["available_memory_bytes"] is None:
            self.assertIsNone(plan["pressure"])

    def test_low_disk_is_a_warning_and_not_a_refusal(self):
        plan = self._plan(free=10 ** 7, available=int(6 * GIB))
        self.assertTrue(plan["warnings"])
        self.assertTrue(any("disk" in line for line in plan["warnings"]))

    def test_plenty_of_disk_raises_no_warning(self):
        self.assertEqual(self._plan(free=10 ** 10, available=int(6 * GIB))["warnings"], [])


class FakeClock:
    """A clock the test advances by hand, so budget arithmetic is exact."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RunBudgetTests(unittest.TestCase):
    def _budget(self, total=600):
        clock = FakeClock()
        return resources.RunBudget(total, clock=clock), clock

    def test_a_fresh_budget_has_all_of_its_time(self):
        budget, _ = self._budget(600)
        self.assertEqual(budget.remaining(), 600)
        self.assertEqual(budget.spent(), 0)

    def test_time_is_charged_as_it_passes(self):
        budget, clock = self._budget(600)
        clock.advance(120)
        self.assertEqual(budget.spent(), 120)
        self.assertEqual(budget.remaining(), 480)

    def test_remaining_never_goes_negative(self):
        budget, clock = self._budget(60)
        clock.advance(10_000)
        self.assertEqual(budget.remaining(), 0)
        self.assertFalse(budget.can_start(1))

    def test_a_stage_that_fits_is_allowed_and_one_that_does_not_is_refused(self):
        budget, _ = self._budget(600)
        self.assertTrue(budget.can_start(300))
        self.assertFalse(budget.can_start(601))

    def test_reserved_time_is_kept_back_for_later_work(self):
        budget, _ = self._budget(600)
        self.assertTrue(budget.can_start(200, reserve_seconds=300))
        self.assertFalse(budget.can_start(400, reserve_seconds=300))

    def test_the_reviewer_only_gets_a_reservation_when_it_is_still_ahead(self):
        budget, _ = self._budget(600)
        self.assertEqual(budget.reserve_for(reviewer_waiting=True, min_stage_seconds=150), 150)
        self.assertEqual(budget.reserve_for(reviewer_waiting=False, min_stage_seconds=150), 0)

    def test_a_slice_is_the_smaller_of_the_ceiling_and_what_is_left(self):
        budget, clock = self._budget(600)
        self.assertEqual(budget.slice_for(900), 600)
        clock.advance(400)
        self.assertEqual(budget.slice_for(900), 200)
        self.assertEqual(budget.slice_for(900, reserve_seconds=100), 100)
        clock.advance(1000)
        self.assertEqual(budget.slice_for(900), 0)

    def test_skipping_is_remembered_and_reported(self):
        budget, _ = self._budget(600)
        budget.note_stage("AGENT-02", 30)
        budget.note_stage("AGENT-09", 0, skipped_reason="out of time")
        record = budget.as_dict()
        self.assertTrue(record["stopped_early"])
        self.assertEqual(record["skipped"], ["AGENT-09"])
        self.assertEqual(record["stages"][0], {"agent_id": "AGENT-02", "seconds": 30.0})

    def test_a_run_inside_its_budget_is_not_reported_as_stopped(self):
        budget, clock = self._budget(600)
        budget.note_stage("AGENT-02", 30)
        clock.advance(30)
        record = budget.as_dict()
        self.assertFalse(record["stopped_early"])
        self.assertEqual(record["skipped"], [])
        self.assertEqual(record["remaining_seconds"], 570)

    def test_every_tier_has_a_budget_and_a_floor(self):
        for tier in resources.TIERS:
            with self.subTest(tier=tier):
                limits = resources.TIER_LIMITS[tier]
                self.assertGreater(limits["run_budget_seconds"], limits["min_stage_seconds"])

    def test_a_bigger_machine_gets_more_time_not_less(self):
        order = list(reversed(resources.TIERS))
        for smaller, larger in zip(order[1:], order[:-1]):
            self.assertLess(resources.TIER_LIMITS[smaller]["run_budget_seconds"],
                            resources.TIER_LIMITS[larger]["run_budget_seconds"])


class LimitsFromConfigTests(unittest.TestCase):
    def test_a_config_without_a_plan_behaves_like_balanced(self):
        self.assertEqual(resources.limits_from({}),
                         resources.TIER_LIMITS["balanced"])

    def test_a_none_config_is_tolerated(self):
        self.assertEqual(resources.limits_from(None),
                         resources.TIER_LIMITS["balanced"])

    def test_a_carried_plan_is_used(self):
        limits = resources.limits_from(
            {"_resources": {"limits": {"dataset_max_bytes": 500_000}}})
        self.assertEqual(limits["dataset_max_bytes"], 500_000)

    def test_unknown_keys_cannot_be_injected(self):
        limits = resources.limits_from(
            {"_resources": {"limits": {"run_anything": True}}})
        self.assertNotIn("run_anything", limits)

    def test_non_integer_values_are_ignored(self):
        limits = resources.limits_from(
            {"_resources": {"limits": {"dataset_max_bytes": "huge"}}})
        self.assertEqual(limits["dataset_max_bytes"],
                         resources.TIER_LIMITS["balanced"]["dataset_max_bytes"])

    def test_a_malformed_plan_does_not_raise(self):
        self.assertEqual(resources.limits_from({"_resources": "broken"}),
                         resources.TIER_LIMITS["balanced"])


class DescribeTests(unittest.TestCase):
    def test_the_line_names_the_tier_and_the_limits_that_matter(self):
        line = resources.describe(resources.plan(
            "minimal", cpu_count=2, ram_bytes=3 * GIB,
            available_bytes=2 * GIB, free_disk_bytes=10 ** 10))
        for fragment in ("tier=minimal", "cores=2", "3.0GiB", "heavy_jobs=1"):
            self.assertIn(fragment, line)

    def test_an_empty_plan_describes_itself_without_raising(self):
        self.assertIn("tier=unknown", resources.describe({}))

    def test_the_cli_prints_json_when_asked(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            resources.main(["--json", "--profile", "minimal"])
        payload = __import__("json").loads(buffer.getvalue())
        self.assertEqual(payload["tier"], "minimal")
        self.assertIn("limits", payload)

    def test_the_cli_default_output_is_one_readable_line_plus_reasons(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            resources.main(["--profile", "low"])
        text = buffer.getvalue()
        self.assertIn("tier=low", text)
        self.assertIn("requested explicitly", text)


class OrchestratorUsesThePlanTests(unittest.TestCase):
    def _config(self, profile):
        return {"model": {"enabled": True, "base_url": "http://127.0.0.1:1/x",
                          "model": "local-model", "timeout_seconds": 600},
                "_resources": resources.plan(profile, cpu_count=2, ram_bytes=3 * GIB,
                                             available_bytes=2 * GIB,
                                             free_disk_bytes=10 ** 10)}

    def test_the_model_call_is_capped_by_the_tier(self):
        sys.path.insert(0, str(ROOT / "agents"))
        import orchestrate

        seen = {}

        def fake_post(url, body, timeout):
            seen["max_tokens"] = body["max_tokens"]
            seen["timeout"] = timeout
            return {"choices": [{"message": {"content": "ok"}}]}

        with patch.object(orchestrate.dispatch, "post_local_model", side_effect=fake_post):
            call = orchestrate.tool_model_call(self._config("minimal"))
            call("hello", 4000)
        self.assertEqual(seen["max_tokens"], resources.TIER_LIMITS["minimal"]["model_max_tokens"])
        self.assertEqual(seen["timeout"], resources.TIER_LIMITS["minimal"]["model_timeout_seconds"])

    def test_a_roomy_machine_keeps_the_configured_timeout(self):
        sys.path.insert(0, str(ROOT / "agents"))
        import orchestrate

        seen = {}

        def fake_post(url, body, timeout):
            seen["timeout"] = timeout
            return {"choices": [{"message": {"content": "ok"}}]}

        with patch.object(orchestrate.dispatch, "post_local_model", side_effect=fake_post):
            call = orchestrate.tool_model_call(self._config("high"))
            call("hello", 4000)
        self.assertEqual(seen["timeout"], 600)

    def test_the_dataset_cap_is_the_tier_cap_and_says_so(self):
        sys.path.insert(0, str(ROOT / "agents"))
        import orchestrate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "big.csv").write_text("a,b\n1,2\n" + "x" * 600_000, encoding="utf-8")
            with patch.object(orchestrate, "ROOT", root):
                text, name, error = orchestrate._read_dataset(
                    "big.csv", max_bytes=resources.TIER_LIMITS["minimal"]["dataset_max_bytes"])
            self.assertEqual(text, "")
            self.assertEqual(name, "")
            self.assertIn("500,000-byte limit", error)
            # And the same file is fine for a machine that plans for it.
            with patch.object(orchestrate, "ROOT", root):
                text, name, error = orchestrate._read_dataset(
                    "big.csv", max_bytes=resources.TIER_LIMITS["high"]["dataset_max_bytes"])
            self.assertTrue(text)
            self.assertEqual(error, "")


class PipelineRecordsThePlanTests(unittest.TestCase):
    def test_a_pipeline_run_puts_the_plan_in_the_manifest(self):
        sys.path.insert(0, str(ROOT / "agents"))
        import orchestrate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "WORKSPACE", workspace), \
                 patch.object(orchestrate, "run_builtin_tools", return_value=[]), \
                 patch.object(orchestrate.dispatch, "run_role",
                              side_effect=lambda role, task, context, cfg: "# Draft\n\n" + role["id"]):
                _, manifest = orchestrate.run_pipeline(
                    "Write a short changelog for the release",
                    output_dir=workspace / "run-resources",
                    config={"model": {"enabled": False}},
                )
        recorded = manifest["resources"]
        self.assertEqual(recorded["schema"], 1)
        self.assertIn(recorded["tier"], resources.TIERS)
        self.assertIn("limits", recorded)
        self.assertIn("never_changes", recorded)

    def test_the_tier_can_be_forced_from_the_environment(self):
        sys.path.insert(0, str(ROOT / "agents"))
        import orchestrate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            with patch.dict("os.environ", {"AGENT_HQ_PROFILE": "low"}), \
                 patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "WORKSPACE", workspace), \
                 patch.object(orchestrate, "run_builtin_tools", return_value=[]), \
                 patch.object(orchestrate.dispatch, "run_role",
                              side_effect=lambda role, task, context, cfg: "# Draft\n\n" + role["id"]):
                _, manifest = orchestrate.run_pipeline(
                    "Write a short changelog for the release",
                    output_dir=workspace / "run-forced",
                    config={"model": {"enabled": False}},
                )
        self.assertEqual(manifest["resources"]["tier"], "low")


class PipelineBudgetTests(unittest.TestCase):
    """A run must stop at the time it was given, and say what it did not do."""

    def _run(self, directory, advance_per_stage, budget_minutes=None, cfg=None):
        sys.path.insert(0, str(ROOT / "agents"))
        import orchestrate

        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir(exist_ok=True)
        clock = FakeClock()
        real_budget = resources.RunBudget

        def factory(total_seconds, **kwargs):
            return real_budget(total_seconds, clock=clock, **kwargs)

        def fake_role(role, task, context, cfg):
            clock.advance(advance_per_stage)
            if role["id"] == "AGENT-08":
                return "# Review\n\nOVERALL QUALITY GATE: PASS"
            return "# Draft\n\n" + role["id"]

        with patch.object(orchestrate, "ROOT", root), \
             patch.object(orchestrate, "WORKSPACE", workspace), \
             patch.object(orchestrate, "run_builtin_tools", return_value=[]), \
             patch.object(orchestrate.dispatch, "run_role", side_effect=fake_role), \
             patch.object(orchestrate.resources, "RunBudget", side_effect=factory):
            return orchestrate.run_pipeline(
                "Write a short changelog for the release",
                output_dir=workspace / "run-budget",
                config=cfg or {"model": {"enabled": False}},
                budget_minutes=budget_minutes,
            )

    def test_a_run_that_runs_out_of_time_skips_the_stages_it_cannot_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            destination, manifest = self._run(directory, advance_per_stage=10_000,
                                              budget_minutes=10)
        budget = manifest["resources"]["budget"]
        self.assertTrue(budget["stopped_early"])
        self.assertTrue(budget["skipped"])
        skipped = [item for item in manifest["pipeline"]
                   if item.get("status") == "skipped_out_of_time"]
        self.assertTrue(skipped)
        self.assertTrue(all(item.get("reason") for item in skipped))

    def test_a_skipped_stage_makes_the_run_partial_not_done(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manifest = self._run(directory, advance_per_stage=10_000, budget_minutes=10)
        self.assertEqual(manifest["status"], "partial")

    def test_the_final_reviewer_still_runs_when_the_budget_is_gone(self):
        # Stopping with output nobody checked is worse than stopping earlier, so
        # the gate is never the stage that gets skipped.
        with tempfile.TemporaryDirectory() as directory:
            _, manifest = self._run(directory, advance_per_stage=10_000, budget_minutes=10)
        reviewer = [item for item in manifest["pipeline"] if item.get("agent_id") == "AGENT-08"]
        self.assertTrue(reviewer)
        self.assertNotEqual(reviewer[-1].get("status"), "skipped_out_of_time")

    def test_a_run_inside_its_budget_finishes_every_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manifest = self._run(directory, advance_per_stage=5, budget_minutes=30)
        budget = manifest["resources"]["budget"]
        self.assertFalse(budget["stopped_early"])
        self.assertNotEqual(manifest["status"], "partial")
        self.assertTrue(all(item.get("status") != "skipped_out_of_time"
                            for item in manifest["pipeline"]))

    def test_the_budget_is_written_beside_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            destination, _ = self._run(directory, advance_per_stage=5, budget_minutes=30)
            record = __import__("json").loads((destination / "budget.json").read_text())
        self.assertIn("total_seconds", record)
        self.assertEqual(record["total_seconds"], 1800)
        self.assertIn("stages", record)

    def test_every_stage_time_is_charged_to_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manifest = self._run(directory, advance_per_stage=5, budget_minutes=30)
        stages = manifest["resources"]["budget"]["stages"]
        self.assertTrue(stages)
        self.assertTrue(all(entry["seconds"] >= 5 for entry in stages))

    def test_the_budget_defaults_to_the_device_tier(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manifest = self._run(directory, advance_per_stage=0.5)
        budget = manifest["resources"]["budget"]
        self.assertEqual(budget["total_seconds"],
                         resources.TIER_LIMITS[manifest["resources"]["tier"]]["run_budget_seconds"])

    def test_a_nonsense_budget_is_refused_rather_than_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self._run(directory, advance_per_stage=1, budget_minutes="soon")


if __name__ == "__main__":
    unittest.main()
