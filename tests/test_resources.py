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


if __name__ == "__main__":
    unittest.main()
