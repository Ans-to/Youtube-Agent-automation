"""Tests for the extracted application core.

These modules did not exist before the refactor, and their behaviour is the
contract the rest of the app now depends on:

* **errors** - every expected failure has a status and a message that is safe to
  show; the HTTP layer no longer guesses.
* **paths** - one owner of every location, overridable, so a test can point the
  whole application at a temporary directory.
* **jsonio** - reading and writing JSON without silent data loss.
* **ffmpeg** - one lookup, with the caller's own exception class preserved.
* **requests** - form validation that can be tested without a socket.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import errors
from app.infrastructure import jsonio
from app.paths import ProjectPaths
from app.services.requests import (
    build_pipeline_request,
    build_plain_request,
    build_product_request,
    build_video_request,
)


class ErrorTests(unittest.TestCase):
    def test_every_error_keeps_its_old_builtin_base(self):
        # Call sites written before the refactor catch ValueError/RuntimeError.
        self.assertIsInstance(errors.TaskInputError("x"), ValueError)
        self.assertIsInstance(errors.WorkflowBusyError("x"), RuntimeError)
        self.assertIsInstance(errors.DependencyMissing("x"), RuntimeError)
        self.assertIsInstance(errors.LocalModelError("x"), ValueError)
        self.assertIsInstance(errors.StorageError("x"), OSError)

    def test_status_mapping(self):
        self.assertEqual(errors.status_for(errors.TaskInputError("x")), 400)
        self.assertEqual(errors.status_for(errors.PayloadTooLargeError("x")), 413)
        self.assertEqual(errors.status_for(errors.WorkflowBusyError("x")), 409)
        self.assertEqual(errors.status_for(ValueError("x")), 400)
        self.assertEqual(errors.status_for(TimeoutError()), 503)
        self.assertEqual(errors.status_for(KeyError("x")), 500)

    def test_user_message_includes_short_detail_but_not_a_traceback(self):
        exc = errors.StorageError("Could not queue the task.", detail="PermissionError")
        self.assertEqual(exc.user_message(), "Could not queue the task. (PermissionError)")
        self.assertNotIn("Traceback", exc.user_message())

    def test_detail_is_bounded(self):
        exc = errors.HQError("m", detail="x" * 5000)
        self.assertEqual(len(exc.detail), errors.MAX_DETAIL_CHARS)

    def test_busy_error_remembers_the_holder(self):
        exc = errors.WorkflowBusyError("busy", active="video workflow")
        self.assertEqual(exc.active, "video workflow")
        self.assertEqual(exc.status, 409)

    def test_describe_collapses_newlines_so_one_failure_is_one_line(self):
        self.assertEqual(errors.describe(OSError("a\nb")), "OSError: a b")


class PathTests(unittest.TestCase):
    """Paths must behave the same for a Windows install and a Linux one.

    Every fixture is a real temporary directory rather than a literal ``/tmp``
    path: on Windows ``Path('/tmp/x')`` is drive-relative, so a literal would
    test the drive mapping instead of the code.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_every_location_is_derived_from_root(self):
        paths = ProjectPaths(self.root)
        self.assertEqual(paths.tasks, self.root / "tasks.json")
        self.assertEqual(paths.deck, self.root / "web" / "deck.html")
        self.assertEqual(
            paths.task_progress("TASK-0001"),
            self.root / "workspace" / "orchestration" / "task-TASK-0001" / "pipeline-progress.json",
        )

    def test_every_location_stays_inside_root(self):
        paths = ProjectPaths(self.root)
        for location in (paths.tasks, paths.config, paths.workspace, paths.logs,
                         paths.outputs, paths.deck, paths.roster, paths.pipeline_dir):
            with self.subTest(location=location.name):
                self.assertEqual(location.relative_to(self.root), location.relative_to(self.root))
                self.assertTrue(str(location).startswith(str(self.root)))

    def test_the_root_can_come_from_the_environment(self):
        paths = ProjectPaths.discover(environ={"AGENT_HQ_HOME": str(self.root)})
        self.assertEqual(paths.root, self.root)

    def test_an_explicit_root_wins_over_the_environment(self):
        other = self.root / "other"
        paths = ProjectPaths.discover(str(other), environ={"AGENT_HQ_HOME": str(self.root)})
        self.assertEqual(paths.root, other.resolve())

    def test_relative_never_raises_for_an_outside_path(self):
        outside = Path(tempfile.gettempdir()) / "definitely-outside-the-project.txt"
        paths = ProjectPaths(self.root)
        self.assertEqual(paths.relative(outside), str(outside))

    def test_relative_reports_a_path_inside_the_project(self):
        paths = ProjectPaths(self.root)
        inside = self.root / "workspace" / "notes.md"
        self.assertEqual(Path(paths.relative(inside)), Path("workspace") / "notes.md")

    def test_runtime_directories_are_created(self):
        paths = ProjectPaths(self.root)
        paths.ensure_runtime_dirs()
        for directory_name in ("logs", "outputs", "workspace"):
            self.assertTrue((self.root / directory_name).is_dir())


class JsonIoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data.json"

    def test_a_missing_file_returns_the_default(self):
        self.assertEqual(jsonio.read_json(self.path, {"a": 1}), {"a": 1})

    def test_a_corrupt_file_returns_the_default_unless_strict(self):
        self.path.write_text("{broken", encoding="utf-8")
        self.assertEqual(jsonio.read_json(self.path, []), [])
        with self.assertRaises(jsonio.JsonFileError):
            jsonio.read_json(self.path, [], strict=True)

    def test_atomic_write_leaves_no_temporary_file(self):
        jsonio.write_json_atomic(self.path, {"ok": True})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"ok": True})
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name != "data.json"]
        self.assertEqual(leftovers, [])

    def test_a_failed_write_does_not_leave_a_temporary_file(self):
        with patch("os.replace", side_effect=OSError("nope")):
            with self.assertRaises(OSError):
                jsonio.write_json_atomic(self.path, {"ok": True})
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_extract_json_object_ignores_prose_and_picks_the_object(self):
        text = 'Sure! Here is the plan:\n```json\n{"steps": [1, 2]}\n```\nHope that helps.'
        self.assertEqual(jsonio.extract_json_object(text), {"steps": [1, 2]})

    def test_extract_json_object_returns_none_when_there_is_nothing(self):
        self.assertIsNone(jsonio.extract_json_object("no json here"))
        self.assertIsNone(jsonio.extract_json_object(None))

    def test_extract_json_object_skips_a_broken_brace_and_finds_the_next(self):
        self.assertEqual(jsonio.extract_json_object('{oops} {"ok": true}'), {"ok": True})


class FfmpegTests(unittest.TestCase):
    def test_find_returns_none_instead_of_raising(self):
        from app.infrastructure import ffmpeg

        # With nothing on PATH the answer is the bundled binary or None - never
        # an exception. Both are correct depending on whether the optional
        # imageio-ffmpeg wheel is installed on this machine.
        with patch("shutil.which", return_value=None):
            value = ffmpeg.find_ffmpeg()
        self.assertTrue(value is None or isinstance(value, str))

    def test_require_raises_the_callers_own_exception_class(self):
        from app.infrastructure import ffmpeg

        class LocalMissing(RuntimeError):
            pass

        with patch.object(ffmpeg, "find_ffmpeg", return_value=None):
            with self.assertRaises(LocalMissing):
                ffmpeg.require_ffmpeg(error=LocalMissing, message="no ffmpeg here")

    def test_require_returns_the_binary_when_present(self):
        from app.infrastructure import ffmpeg

        with patch.object(ffmpeg, "find_ffmpeg", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(ffmpeg.require_ffmpeg(), "/usr/bin/ffmpeg")

    def test_probe_requires_both_tools(self):
        from app.infrastructure import ffmpeg

        with patch.object(ffmpeg, "find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
             patch.object(ffmpeg, "find_ffprobe", return_value=None):
            with self.assertRaises(ffmpeg.DependencyMissing):
                ffmpeg.require_ffmpeg_and_probe()


class LocalModelTests(unittest.TestCase):
    def test_a_hostname_is_refused_even_if_it_resolves_to_loopback(self):
        from app.infrastructure.local_model import validate_loopback_url

        with self.assertRaises(errors.LocalModelError):
            validate_loopback_url("http://localhost:8080/v1/chat/completions")

    def test_credentials_in_the_url_are_refused(self):
        from app.infrastructure.local_model import validate_loopback_url

        with self.assertRaises(errors.LocalModelError):
            validate_loopback_url("http://user:pass@127.0.0.1:8080/v1/chat/completions")

    def test_a_plain_loopback_endpoint_is_accepted(self):
        from app.infrastructure.local_model import validate_loopback_url

        url = "http://127.0.0.1:8080/v1/chat/completions"
        self.assertEqual(validate_loopback_url(url), url)


class RequestRuleTests(unittest.TestCase):
    def resolve(self, value):
        return Path("/workspace") / "notes.md" if value == "ok" else None

    def test_a_plain_task_needs_a_title_and_text(self):
        request = build_plain_request({"title": ["Do it"], "kind": ["plan"], "input": ["text"]})
        self.assertEqual(request.title, "Do it")
        with self.assertRaises(errors.TaskInputError):
            build_plain_request({"title": [""], "input": ["text"]})

    def test_video_defaults_to_long_and_draft(self):
        request = build_video_request({"topic": ["AI agents"]}, resolve_file=self.resolve,
                                      model_enabled=False)
        self.assertEqual(request.kind, "youtube_package")
        self.assertIn("Format: long.", request.text)
        self.assertIn("Requested mode: draft.", request.text)

    def test_video_render_requires_a_model_and_voice_requires_render(self):
        with self.assertRaisesRegex(errors.TaskInputError, "local model is disabled"):
            build_video_request({"topic": ["x"], "render_mode": ["render"]},
                                resolve_file=self.resolve, model_enabled=False)
        with self.assertRaisesRegex(errors.TaskInputError, "full render mode"):
            build_video_request({"topic": ["x"], "with_voice": ["yes"]},
                                resolve_file=self.resolve, model_enabled=True)

    def test_video_target_minutes_are_bounded(self):
        with self.assertRaisesRegex(errors.TaskInputError, "between 0.25 and 16"):
            build_video_request({"topic": ["x"], "target_minutes": ["99"]},
                                resolve_file=self.resolve, model_enabled=True)
        with self.assertRaisesRegex(errors.TaskInputError, "must be a number"):
            build_video_request({"topic": ["x"], "target_minutes": ["lots"]},
                                resolve_file=self.resolve, model_enabled=True)

    def test_a_source_file_must_be_inside_the_workspace(self):
        request = build_video_request({"topic": ["x"], "source_file": ["ok"]},
                                      resolve_file=self.resolve, model_enabled=True)
        self.assertTrue(request.context_file.endswith("notes.md"))
        with self.assertRaisesRegex(errors.TaskInputError, "existing file inside workspace"):
            build_video_request({"topic": ["x"], "source_file": ["/etc/passwd"]},
                                resolve_file=self.resolve, model_enabled=True)

    def test_template_mode_cannot_be_combined_with_a_source_file(self):
        with self.assertRaisesRegex(errors.TaskInputError, "cannot be combined"):
            build_video_request({"topic": ["x"], "render_mode": ["template"], "source_file": ["ok"]},
                                resolve_file=self.resolve, model_enabled=True)

    def test_narration_is_refused_outside_a_full_render(self):
        with self.assertRaisesRegex(errors.TaskInputError, "full render mode"):
            build_video_request({"topic": ["x"], "render_mode": ["template"], "with_voice": ["yes"]},
                                resolve_file=self.resolve, model_enabled=True)

    def test_product_bounds(self):
        request = build_product_request({"product_title": ["T"], "product_idea": ["I"]})
        self.assertEqual(request.title, "Digital product: T")
        with self.assertRaises(errors.TaskInputError):
            build_product_request({"product_title": ["T" * 101], "product_idea": ["I"]})

    def test_the_pipeline_refuses_manual_specialist_selection(self):
        with self.assertRaisesRegex(errors.TaskInputError, "Manual specialist selection"):
            build_pipeline_request({"task": ["goal"], "agents": ["AGENT-19"]},
                                   resolve_file=self.resolve)
        request = build_pipeline_request({"task": ["goal"]}, resolve_file=self.resolve)
        self.assertEqual(request.task, "goal")

    def test_pipeline_context_is_validated_like_a_source_file(self):
        with self.assertRaisesRegex(errors.TaskInputError, "existing .txt, .md, or .json"):
            build_pipeline_request({"task": ["goal"], "context_file": ["/etc/passwd"]},
                                   resolve_file=self.resolve)


if __name__ == "__main__":
    unittest.main()
