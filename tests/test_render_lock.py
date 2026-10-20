"""Regression tests for exclusive cross-process video rendering."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from video_studio.render_lock import render_lock


class RenderLockTests(unittest.TestCase):
    def test_second_process_times_out_while_first_holds_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / ".render.lock"
            child_code = r"""
import sys
from video_studio.render_lock import render_lock
try:
    with render_lock(sys.argv[1], timeout_seconds=0.15, poll_interval_seconds=0.02):
        raise SystemExit(0)
except TimeoutError:
    raise SystemExit(23)
"""
            with render_lock(lock_path, timeout_seconds=0):
                child = subprocess.run(
                    [sys.executable, "-c", child_code, str(lock_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            self.assertEqual(child.returncode, 23, child.stdout + child.stderr)

    def test_lock_releases_after_context_exits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / ".render.lock"
            with render_lock(lock_path, timeout_seconds=0):
                self.assertTrue(lock_path.is_file())
            with render_lock(lock_path, timeout_seconds=0):
                self.assertTrue(lock_path.is_file())


if __name__ == "__main__":
    unittest.main()
