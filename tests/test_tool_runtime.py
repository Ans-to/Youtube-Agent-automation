import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.tool_runtime import (
    ALLOWED_PROGRAMS,
    MAX_READ_BYTES,
    MAX_WRITE_BYTES,
    ToolRegistry,
    WorkspaceSandbox,
    build_registry,
    task_sandbox,
    validate_arguments,
)

PYTHON = shutil.which("python3") or shutil.which("python")
PYTHON_PROGRAM = "python3" if shutil.which("python3") else "python"


class SchemaValidationTests(unittest.TestCase):
    def test_object_schema_rejects_missing_unknown_and_wrong_types(self):
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string", "maxLength": 5}, "count": {"type": "integer", "minimum": 1}},
            "required": ["path"],
            "additionalProperties": False,
        }
        self.assertEqual(validate_arguments({"path": "a"}, schema), {"path": "a"})
        for payload, message in (
            ({}, "missing required field"),
            ({"path": "a", "extra": 1}, "unsupported field"),
            ({"path": 5}, "must be a string"),
            ({"path": "abcdef"}, "at most 5 characters"),
            ({"path": "a", "count": 0}, "at least 1"),
            ({"path": "a", "count": True}, "must be an integer"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError) as caught:
                    validate_arguments(payload, schema)
                self.assertIn(message, str(caught.exception))

    def test_enum_and_array_limits(self):
        schema = {
            "type": "object",
            "properties": {
                "program": {"type": "string", "enum": ["node"]},
                "args": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
            },
            "additionalProperties": False,
        }
        self.assertEqual(validate_arguments({"program": "node"}, schema), {"program": "node"})
        with self.assertRaises(ValueError):
            validate_arguments({"program": "bash"}, schema)
        with self.assertRaises(ValueError):
            validate_arguments({"args": ["a", "b", "c"]}, schema)


class SandboxContainmentTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name) / "workspace"
        self.sandbox = WorkspaceSandbox(self.root)

    def tearDown(self):
        self._directory.cleanup()

    def test_write_read_list_round_trip(self):
        registry = ToolRegistry(self.sandbox)
        written = registry.execute("write_file", {"path": "site/index.html", "content": "<h1>hi</h1>"})
        self.assertEqual(written["status"], "ok")
        self.assertTrue(written["created"])
        self.assertEqual(written["path"], "site/index.html")

        read = registry.execute("read_file", {"path": "site/index.html"})
        self.assertEqual(read["status"], "ok")
        self.assertIn("<h1>hi</h1>", read["content"])

        listing = registry.execute("list_files", {"path": "site"})
        self.assertEqual(listing["status"], "ok")
        self.assertEqual([entry["path"] for entry in listing["entries"]], ["site/index.html"])

        overwrite = registry.execute("write_file", {"path": "site/index.html", "content": "x"})
        self.assertFalse(overwrite["created"])

    def test_escaping_paths_are_rejected(self):
        for candidate in ("../outside.txt", "a/../../outside.txt", "/etc/passwd", "", "a\0b"):
            with self.subTest(path=candidate):
                result = ToolRegistry(self.sandbox).execute("write_file", {"path": candidate, "content": "x"})
                self.assertEqual(result["status"], "error")
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_symlink_pointing_outside_is_rejected(self):
        outside = Path(self._directory.name) / "outside"
        outside.mkdir()
        link = self.root / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        result = ToolRegistry(self.sandbox).execute("write_file", {"path": "link/escape.txt", "content": "x"})
        self.assertEqual(result["status"], "error")
        self.assertIn("escapes", result["error"])
        self.assertFalse((outside / "escape.txt").exists())

    def test_size_limits_are_enforced(self):
        registry = ToolRegistry(self.sandbox)
        oversized = "x" * (MAX_WRITE_BYTES + 1)
        self.assertEqual(registry.execute("write_file", {"path": "big.txt", "content": oversized})["status"], "error")
        (self.root / "large.txt").write_text("y" * (MAX_READ_BYTES + 1), encoding="utf-8")
        too_big = registry.execute("read_file", {"path": "large.txt"})
        self.assertEqual(too_big["status"], "error")
        self.assertIn("read limit", too_big["error"])

    def test_directory_and_missing_path_errors(self):
        registry = ToolRegistry(self.sandbox)
        self.assertEqual(registry.execute("read_file", {"path": "nope.txt"})["status"], "error")
        self.assertEqual(registry.execute("write_file", {"path": ".", "content": "x"})["status"], "error")
        self.assertEqual(registry.execute("list_files", {"path": "nope"})["status"], "error")

    def test_unknown_tool_returns_available_tools(self):
        result = ToolRegistry(self.sandbox).execute("drop_database", {})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "unknown tool")
        self.assertIn("write_file", result["available_tools"])


class CommandToolTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name) / "workspace"

    def tearDown(self):
        self._directory.cleanup()

    def test_execution_is_absent_unless_enabled(self):
        default = ToolRegistry(WorkspaceSandbox(self.root))
        self.assertNotIn("run_command", [spec.name for spec in default.specs()])
        enabled = ToolRegistry(WorkspaceSandbox(self.root, allow_exec=True))
        self.assertIn("run_command", [spec.name for spec in enabled.specs()])
        self.assertTrue(next(spec for spec in enabled.specs() if spec.name == "run_command").requires_exec)

    @unittest.skipUnless(PYTHON, "a Python interpreter is required")
    def test_allowlisted_program_runs_inside_the_workspace(self):
        registry = ToolRegistry(WorkspaceSandbox(self.root, allow_exec=True))
        result = registry.execute("run_command", {
            "program": PYTHON_PROGRAM,
            "args": ["-c", "import os; print(os.getcwd())"],
        })
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(Path(result["stdout"].strip()).resolve(), self.root.resolve())

    @unittest.skipUnless(PYTHON, "a Python interpreter is required")
    def test_shell_metacharacters_stay_literal_arguments(self):
        registry = ToolRegistry(WorkspaceSandbox(self.root, allow_exec=True))
        result = registry.execute("run_command", {
            "program": PYTHON_PROGRAM,
            "args": ["-c", "print('one')", "; echo injected"],
        })
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["stdout"].strip(), "one")

    def test_non_allowlisted_programs_are_rejected(self):
        registry = ToolRegistry(WorkspaceSandbox(self.root, allow_exec=True))
        for program in ("bash", "sh", "rm", "curl", "/bin/sh"):
            with self.subTest(program=program):
                result = registry.execute("run_command", {"program": program, "args": []})
                self.assertEqual(result["status"], "error")
        self.assertEqual(set(ALLOWED_PROGRAMS), {"python", "python3", "node"})

    @unittest.skipUnless(PYTHON, "a Python interpreter is required")
    def test_timeouts_and_output_caps(self):
        registry = ToolRegistry(WorkspaceSandbox(self.root, allow_exec=True))
        timed_out = registry.execute("run_command", {
            "program": PYTHON_PROGRAM,
            "args": ["-c", "import time; time.sleep(5)"],
            "timeout_seconds": 1,
        })
        self.assertEqual(timed_out["status"], "error")
        self.assertIn("timed out", timed_out["error"])

        flooded = registry.execute("run_command", {
            "program": PYTHON_PROGRAM,
            "args": ["-c", "print('x' * 200000)"],
        })
        self.assertEqual(flooded["status"], "ok")
        self.assertTrue(flooded["stdout_truncated"])
        self.assertLessEqual(len(flooded["stdout"]), 64_000)

    @unittest.skipUnless(PYTHON, "a Python interpreter is required")
    def test_environment_is_scrubbed(self):
        registry = ToolRegistry(WorkspaceSandbox(self.root, allow_exec=True))
        with patch.dict(os.environ, {"AGENT_HQ_SECRET_MARKER": "leak"}):
            result = registry.execute("run_command", {
                "program": PYTHON_PROGRAM,
                "args": ["-c", "import os; print(os.environ.get('AGENT_HQ_SECRET_MARKER', 'missing'))"],
            })
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["stdout"].strip(), "missing")


class FactoryTests(unittest.TestCase):
    def test_task_sandbox_is_confined_and_slugged(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = task_sandbox(directory, "../../TASK 42!")
            self.assertEqual(sandbox.root.name, "task-42")
            self.assertTrue(str(sandbox.root).startswith(str(Path(directory).resolve())))

    def test_exec_opt_in_comes_from_the_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"AGENT_HQ_ALLOW_EXEC": "1"}):
                self.assertIn("run_command", [spec.name for spec in build_registry(directory, "t").specs()])
            with patch.dict(os.environ, {"AGENT_HQ_ALLOW_EXEC": "0"}):
                self.assertNotIn("run_command", [spec.name for spec in build_registry(directory, "t").specs()])

    def test_catalog_is_compact_and_has_no_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = build_registry(directory, "t", allow_exec=False)
            catalog = json.loads(registry.catalog_json())
            self.assertEqual({entry["name"] for entry in catalog}, {"list_files", "read_file", "write_file"})
            self.assertNotIn(directory, registry.catalog_json())

    def test_sandbox_rejects_invalid_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                WorkspaceSandbox(directory, max_write_bytes=MAX_WRITE_BYTES + 1)
            with self.assertRaises(ValueError):
                WorkspaceSandbox(directory, timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
