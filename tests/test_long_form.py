"""Tests for sliced long-form rendering.

No browser and no FFmpeg are involved: the runner is injected, so these tests
check the part that actually goes wrong in production — the slicing, the
accounting, the resume rules, and what happens when a slice lies about what it
rendered.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import long_form


class FakeRunner:
    """Stands in for node/ffmpeg, writing the files the next step expects."""

    def __init__(self, *, node_frames=None, encode_fails_at=None, render_fails_at=None,
                 skip_manifest=False, node_exit=0):
        self.calls = []
        self.node_frames = node_frames
        self.encode_fails_at = encode_fails_at
        self.render_fails_at = render_fails_at
        self.skip_manifest = skip_manifest
        self.node_exit = node_exit

    def __call__(self, command, *, timeout):
        self.calls.append(list(command))
        command = [str(part) for part in command]
        if "render.js" in " ".join(command):
            return self._render(command)
        if "-c:v" in command and "libx264" in command:
            return self._encode(command)
        if "concat" in command:
            return self._concat(command)
        raise AssertionError("unexpected command: " + " ".join(command))

    # -- steps ---------------------------------------------------------------
    def _flag(self, command, name):
        for part in command:
            if part.startswith("--" + name + "="):
                return part.split("=", 1)[1]
        return None

    def _render(self, command):
        start = int(self._flag(command, "from-frame"))
        count = int(self._flag(command, "frame-count"))
        out_dir = Path(self._flag(command, "out-dir"))
        manifest = Path(self._flag(command, "manifest"))
        if self.render_fails_at is not None and start == self.render_fails_at:
            return _Result(1, stderr="chromium crashed")
        out_dir.mkdir(parents=True, exist_ok=True)
        frames = self.node_frames if self.node_frames is not None else count
        for offset in range(frames):
            (out_dir / ("frame-%06d.png" % (start + offset))).write_bytes(b"\x89PNG fake")
        if not self.skip_manifest:
            manifest.write_text(json.dumps({
                "frame_count": frames, "first_frame": start,
                "title": "test", "fps": 30,
            }), encoding="utf-8")
        return _Result(self.node_exit)

    def _encode(self, command):
        part = Path(command[-1])
        if self.encode_fails_at is not None and part.name == self.encode_fails_at:
            return _Result(1, stderr="encoder exploded")
        part.write_bytes(b"fake mp4 bytes")
        return _Result(0)

    def _concat(self, command):
        output = Path(command[-1])
        output.write_bytes(b"final mp4")
        return _Result(0)

    # -- inspection ----------------------------------------------------------
    def render_calls(self):
        return [call for call in self.calls if "render.js" in " ".join(call)]

    def encode_calls(self):
        return [call for call in self.calls if "libx264" in call]

    def concat_calls(self):
        return [call for call in self.calls if "concat" in call]


class _Result:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _storyboard(path, scenes, *, fps=30, width=1920, height=1080):
    data = {"title": "test", "width": width, "height": height, "fps": fps,
            "scenes": [{"duration_seconds": seconds} for seconds in scenes]}
    Path(path).write_text(json.dumps(data), encoding="utf-8")
    return Path(path)


class FrameMathTests(unittest.TestCase):
    def test_scene_frames_match_the_renderer_rounding(self):
        self.assertEqual(long_form.frames_for_scenes(
            {"fps": 30, "scenes": [{"duration_seconds": 1}, {"duration_seconds": 2.5}]}),
            [30, 75])

    def test_a_very_short_scene_still_gets_one_frame(self):
        self.assertEqual(long_form.frames_for_scenes(
            {"fps": 30, "scenes": [{"duration_seconds": 0.01}]}), [1])

    def test_a_missing_duration_is_refused_with_the_scene_number(self):
        with self.assertRaises(ValueError) as caught:
            long_form.frames_for_scenes({"fps": 30, "scenes": [{"duration_seconds": 1}, {}]})
        self.assertIn("Scene 2", str(caught.exception))

    def test_a_scene_longer_than_the_renderer_allows_is_refused(self):
        with self.assertRaises(ValueError):
            long_form.frames_for_scenes({"fps": 30, "scenes": [{"duration_seconds": 601}]})

    def test_an_empty_storyboard_is_refused(self):
        with self.assertRaises(ValueError):
            long_form.frames_for_scenes({"fps": 30, "scenes": []})


class PlanTests(unittest.TestCase):
    def test_twenty_minutes_becomes_whole_slices_that_add_up(self):
        total = 20 * 60 * 30
        plan = long_form.plan_segments(total, segment_frames=60 * 30)
        self.assertEqual(sum(item["count"] for item in plan), total)
        self.assertEqual(len(plan), 20)
        self.assertEqual(plan[0]["start"], 0)
        self.assertEqual(plan[1]["start"], 1800)

    def test_slices_are_contiguous_with_no_gap_or_overlap(self):
        plan = long_form.plan_segments(5000, segment_frames=900)
        for earlier, later in zip(plan, plan[1:]):
            self.assertEqual(earlier["start"] + earlier["count"], later["start"])

    def test_the_last_slice_is_the_remainder(self):
        plan = long_form.plan_segments(5000, segment_frames=1800)
        self.assertEqual(plan[-1]["count"], 5000 - 2 * 1800)

    def test_a_one_frame_slice_request_is_honoured_not_rounded_up(self):
        # Silently enlarging the slice would render something other than asked.
        plan = long_form.plan_segments(5, segment_frames=1)
        self.assertEqual([item["count"] for item in plan], [1, 1, 1, 1, 1])

    def test_a_slice_smaller_than_one_frame_is_still_one_frame(self):
        plan = long_form.plan_segments(3, segment_frames=0)
        self.assertEqual([item["count"] for item in plan], [1, 1, 1])

    def test_a_segment_can_never_exceed_the_renderers_own_ceiling(self):
        plan = long_form.plan_segments(90_000, segment_frames=500_000)
        self.assertLessEqual(plan[0]["count"], long_form.MAX_FRAMES_PER_CALL)

    def test_zero_frames_is_refused(self):
        with self.assertRaises(ValueError):
            long_form.plan_segments(0, segment_frames=900)

    def test_the_plan_description_reports_what_will_be_rendered(self):
        storyboard = {"width": 3840, "height": 2160, "fps": 30}
        described = long_form.describe_plan(storyboard, long_form.plan_segments(36_000, segment_frames=1800), fps=30)
        self.assertEqual(described["duration_seconds"], 1200.0)
        self.assertEqual(described["segments"], 20)
        self.assertEqual(described["resolution"], [3840, 2160])
        self.assertEqual(described["largest_slice_frames"], 1800)


class RenderTests(unittest.TestCase):
    def _render(self, directory, runner, *, scenes=(2, 2, 2), segment_seconds=2, **kwargs):
        storyboard = _storyboard(Path(directory) / "sb.json", scenes)
        output = Path(directory) / "out" / "film.mp4"
        record = long_form.render(storyboard, output, segment_seconds=segment_seconds,
                                  node="node", ffmpeg="ffmpeg", run=runner,
                                  log=lambda *_: None, **kwargs)
        return record, output

    def test_a_three_slice_storyboard_renders_three_ranges(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            record, output = self._render(directory, runner)
            self.assertTrue(output.is_file())
        self.assertEqual(len(runner.render_calls()), 3)
        self.assertEqual(record["plan"]["total_frames"], 180)
        starts = [int(call[3].split("=")[1]) for call in runner.render_calls()]
        self.assertEqual(starts, [0, 60, 120])

    def test_every_slice_is_encoded_and_then_concatenated_in_order(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, runner)
        parts = [Path(call[-1]).name for call in runner.encode_calls()]
        self.assertEqual(parts, ["part-000.mp4", "part-001.mp4", "part-002.mp4"])
        self.assertEqual(len(runner.concat_calls()), 1)

    def test_the_concat_step_copies_video_instead_of_re_encoding_it(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, runner)
        concat = runner.concat_calls()[0]
        self.assertIn("-c:v", concat)
        self.assertEqual(concat[concat.index("-c:v") + 1], "copy")

    def test_slice_frames_are_deleted_after_encoding(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, runner)
            leftovers = list(Path(directory).rglob("frame-*.png"))
        self.assertEqual(leftovers, [])

    def test_frames_can_be_kept_when_asked(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, runner, keep_frames=True)
            kept = list(Path(directory).rglob("frame-*.png"))
        self.assertEqual(len(kept), 180)

    def test_the_requested_quality_is_passed_through_unchanged(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, runner, crf=18, preset="slow")
        encode = runner.encode_calls()[0]
        self.assertEqual(encode[encode.index("-crf") + 1], "18")
        self.assertEqual(encode[encode.index("-preset") + 1], "slow")
        self.assertEqual(encode[encode.index("-framerate") + 1], "30")

    def test_the_job_record_says_what_was_rendered(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            record, output = self._render(directory, runner)
            saved = json.loads((Path(directory) / "out" / "film.long-form" / "long-form.json").read_text())
        self.assertEqual(saved["schema"], 1)
        self.assertEqual(saved["plan"]["segments"], 3)
        self.assertEqual(len(saved["slices"]), 3)
        self.assertTrue(saved["complete"])
        self.assertEqual(saved["duration_seconds"], 6.0)
        self.assertTrue(record["complete"])

    def test_audio_is_muxed_only_when_it_exists(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, runner)
            concat = runner.concat_calls()[0]
            self.assertNotIn("-c:a", concat)

    def test_existing_audio_is_muxed_once_at_the_end(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "voice.wav"
            audio.write_bytes(b"RIFF fake")
            self._render(directory, runner, audio=audio)
            concat = runner.concat_calls()[0]
        self.assertIn("-c:a", concat)
        self.assertIn(str(audio), concat)


class ResumeTests(unittest.TestCase):
    def _render(self, directory, runner, **kwargs):
        storyboard = _storyboard(Path(directory) / "sb.json", (2, 2, 2))
        return long_form.render(storyboard, Path(directory) / "out" / "film.mp4",
                                segment_seconds=2, node="node", ffmpeg="ffmpeg",
                                run=runner, log=lambda *_: None, **kwargs)

    def test_a_second_run_reuses_finished_slices_without_rendering_them(self):
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, FakeRunner())
            second = FakeRunner()
            record = self._render(directory, second)
        self.assertEqual(second.render_calls(), [])
        self.assertEqual(record["resumed_slices"], 3)

    def test_a_part_with_the_wrong_range_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, FakeRunner())
            record_path = Path(directory) / "out" / "film.long-form" / "part-001.json"
            record = json.loads(record_path.read_text())
            record["count"] = 999
            record_path.write_text(json.dumps(record))
            second = FakeRunner()
            self._render(directory, second)
        starts = [call[3] for call in second.render_calls()]
        self.assertEqual(starts, ["--from-frame=60"])

    def test_a_missing_part_file_forces_a_re_render(self):
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, FakeRunner())
            (Path(directory) / "out" / "film.long-form" / "part-002.mp4").unlink()
            second = FakeRunner()
            self._render(directory, second)
        self.assertEqual(len(second.render_calls()), 1)

    def test_resume_can_be_turned_off(self):
        with tempfile.TemporaryDirectory() as directory:
            self._render(directory, FakeRunner())
            second = FakeRunner()
            self._render(directory, second, resume=False)
        self.assertEqual(len(second.render_calls()), 3)


class FailureTests(unittest.TestCase):
    def _render(self, directory, runner, **kwargs):
        storyboard = _storyboard(Path(directory) / "sb.json", (2, 2))
        return long_form.render(storyboard, Path(directory) / "out" / "film.mp4",
                                segment_seconds=2, node="node", ffmpeg="ffmpeg",
                                run=runner, log=lambda *_: None, **kwargs)

    def test_a_crashed_slice_names_the_frame_it_failed_at(self):
        runner = FakeRunner(render_fails_at=60)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError) as caught:
                self._render(directory, runner)
        self.assertIn("frame 60", str(caught.exception))
        self.assertIn("chromium crashed", str(caught.exception))

    def test_a_slice_that_renders_the_wrong_number_of_frames_is_not_accepted(self):
        runner = FakeRunner(node_frames=10)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError) as caught:
                self._render(directory, runner)
        self.assertIn("10 of 60 frames", str(caught.exception))

    def test_a_slice_without_a_manifest_is_not_accepted(self):
        runner = FakeRunner(skip_manifest=True)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError) as caught:
                self._render(directory, runner)
        self.assertIn("no manifest", str(caught.exception))

    def test_an_encode_failure_stops_the_job(self):
        runner = FakeRunner(encode_fails_at="part-001.mp4")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError) as caught:
                self._render(directory, runner)
        self.assertIn("encode failed", str(caught.exception))

    def test_the_failure_is_reported_before_a_browser_is_started_when_node_is_missing(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            storyboard = _storyboard(Path(directory) / "sb.json", (2,))
            runner = FakeRunner()
            with patch.object(long_form.shutil, "which", return_value=None):
                with self.assertRaises(RuntimeError) as caught:
                    long_form.render(storyboard, Path(directory) / "out.mp4",
                                     node=None, ffmpeg=None, run=runner)
        self.assertIn("Node.js", str(caught.exception))
        self.assertEqual(runner.calls, [], "nothing should run when the tools are missing")

    def test_a_missing_encoder_is_reported_clearly(self):
        # FFmpeg must be *absent* for this test, not merely unset: with
        # ``ffmpeg=None`` the renderer looks on PATH, so on a machine where
        # FFmpeg is installed the render simply succeeds and the assertion about
        # a failure never runs. Patching the lookup makes the test say what it
        # means on every machine.
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            storyboard = _storyboard(Path(directory) / "sb.json", (10,))
            runner = FakeRunner()
            with patch.object(long_form.shutil, "which", return_value=None):
                with self.assertRaises(RuntimeError) as caught:
                    long_form.render(storyboard, Path(directory) / "out.mp4",
                                     node="node", ffmpeg=None, run=runner)
        self.assertIn("FFmpeg", str(caught.exception))
        self.assertEqual(runner.calls, [], "nothing should be encoded without FFmpeg")


class CliTests(unittest.TestCase):
    def test_plan_only_prints_the_plan_and_renders_nothing(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as directory:
            storyboard = _storyboard(Path(directory) / "sb.json", (600, 600), fps=30)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = long_form.main(["--storyboard", str(storyboard),
                                       "--output", str(Path(directory) / "o.mp4"),
                                       "--plan-only"])
            self.assertEqual(code, 0)
            plan = json.loads(buffer.getvalue())
            self.assertEqual(plan["duration_seconds"], 1200.0)
            self.assertFalse((Path(directory) / "o.mp4").exists())

    def test_a_failed_render_returns_a_non_zero_exit_code(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            storyboard = _storyboard(Path(directory) / "sb.json", (10,))
            with patch.object(long_form, "render", side_effect=RuntimeError("boom")):
                code = long_form.main(["--storyboard", str(storyboard),
                                       "--output", str(Path(directory) / "o.mp4")])
        self.assertEqual(code, 1)


class SliceValidationTests(unittest.TestCase):
    """A slice is validated while its frames still exist, not after the film."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "video_studio"))
        import validate_frames
        self.validate_frames = validate_frames
        sys.path.insert(0, str(ROOT / "tools"))
        import make_icons
        # 64x64 so the frame clears validate_frames' "unexpectedly small" floor.
        self.png = make_icons._png_bytes(make_icons.render(64), 64)

    def _slice(self, directory, *, start, count, first_frame=None):
        frames = Path(directory)
        frames.mkdir(parents=True, exist_ok=True)
        for offset in range(count):
            (frames / ("frame-%06d.png" % (start + offset))).write_bytes(self.png)
        manifest = frames.parent / "manifest.json"
        manifest.write_text(json.dumps({
            "width": 64, "height": 64, "frame_count": count,
            "first_frame": start if first_frame is None else first_frame,
        }), encoding="utf-8")
        return frames, manifest

    def test_a_slice_numbered_from_its_global_frame_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            frames, manifest = self._slice(directory, start=1800, count=3)
            report = self.validate_frames.validate(frames, manifest)
        self.assertTrue(report["valid"])
        self.assertEqual(report["frame_count"], 3)

    def test_a_gap_inside_a_slice_is_still_caught(self):
        # Right number of files, wrong numbering: only the sequence check sees it.
        with tempfile.TemporaryDirectory() as directory:
            frames, manifest = self._slice(directory, start=1800, count=3)
            (frames / "frame-001802.png").rename(frames / "frame-001803.png")
            with self.assertRaises(ValueError) as caught:
                self.validate_frames.validate(frames, manifest)
        self.assertIn("gap", str(caught.exception))

    def test_a_missing_frame_is_caught_by_the_count(self):
        with tempfile.TemporaryDirectory() as directory:
            frames, manifest = self._slice(directory, start=1800, count=3)
            (frames / "frame-001801.png").unlink()
            with self.assertRaises(ValueError) as caught:
                self.validate_frames.validate(frames, manifest)
        self.assertIn("Expected 3 frames, found 2", str(caught.exception))

    def test_a_whole_film_render_still_validates_from_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            frames, manifest = self._slice(directory, start=0, count=2)
            self.assertTrue(self.validate_frames.validate(frames, manifest)["valid"])

    def test_the_hook_runs_for_every_slice_before_encoding(self):
        seen = []
        runner = FakeRunner()

        def validate(frames_dir, manifest_path, item):
            seen.append((item["start"], dict(part=len(runner.encode_calls()))))

        with tempfile.TemporaryDirectory() as directory:
            storyboard = _storyboard(Path(directory) / "sb.json", (2, 2, 2))
            long_form.render(storyboard, Path(directory) / "out" / "film.mp4",
                             segment_seconds=2, node="node", ffmpeg="ffmpeg",
                             run=runner, log=lambda *_: None, validate_slice=validate)
        self.assertEqual([start for start, _ in seen], [0, 60, 120])
        # Each check happened before that slice's encode call was issued.
        self.assertEqual(seen[0][1]["part"], 0)
        self.assertEqual(seen[1][1]["part"], 1)
        self.assertEqual(seen[2][1]["part"], 2)

    def test_a_failed_validation_stops_before_encoding(self):
        runner = FakeRunner()

        def validate(frames_dir, manifest_path, item):
            raise ValueError("frame is black")

        with tempfile.TemporaryDirectory() as directory:
            storyboard = _storyboard(Path(directory) / "sb.json", (2, 2))
            with self.assertRaises(RuntimeError) as caught:
                long_form.render(storyboard, Path(directory) / "out" / "film.mp4",
                                 segment_seconds=2, node="node", ffmpeg="ffmpeg",
                                 run=runner, log=lambda *_: None, validate_slice=validate)
        self.assertIn("failed validation", str(caught.exception))
        self.assertEqual(runner.encode_calls(), [], "a bad slice must not be encoded")


class StudioIntegrationTests(unittest.TestCase):
    """The product path has to pick long-form itself, without a new flag."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "video_studio"))
        import studio
        self.studio = studio

    def test_a_twenty_minute_storyboard_estimates_36000_frames(self):
        storyboard = {"fps": 30, "scenes": [{"duration_seconds": 12}] * 100}
        self.assertEqual(self.studio.estimated_frames(storyboard, 30), 36000)

    def test_the_threshold_is_the_renderers_own_per_call_limit(self):
        self.assertEqual(self.studio.SINGLE_PASS_FRAME_LIMIT, long_form.MAX_FRAMES_PER_CALL)

    def test_a_short_film_stays_single_pass(self):
        storyboard = {"scenes": [{"duration_seconds": 5}] * 4}
        self.assertLess(self.studio.estimated_frames(storyboard, 30),
                        self.studio.SINGLE_PASS_FRAME_LIMIT)

    def test_a_broken_scene_gives_no_estimate_instead_of_a_crash(self):
        self.assertIsNone(self.studio.estimated_frames({"scenes": [{}]}, 30))
        self.assertIsNone(self.studio.estimated_frames({"scenes": [{"duration_seconds": 0}]}, 30))

    def test_the_render_path_actually_calls_long_form_for_a_long_film(self):
        source = (ROOT / "video_studio" / "studio.py").read_text(encoding="utf-8")
        self.assertIn("long_form.render(", source)
        self.assertIn("validate_slice=long_form.frame_validator()", source)
        self.assertIn("long_form_mode", source)


if __name__ == "__main__":
    unittest.main()
