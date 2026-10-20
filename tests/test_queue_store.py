import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import queue_store
from queue_store import load_tasks, save_tasks, task_queue_lock


class QueueStoreTests(unittest.TestCase):
    def test_atomic_round_trip_and_lock_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            with task_queue_lock(path):
                save_tasks(path, [{"id": "TASK-1", "status": "pending"}])
                self.assertTrue(Path(str(path) + ".lock").exists())
            self.assertFalse(Path(str(path) + ".lock").exists())
            self.assertEqual(load_tasks(path), [{"id": "TASK-1", "status": "pending"}])
            self.assertFalse(Path(str(path) + ".tmp-" + str(__import__("os").getpid())).exists())

    def test_stale_lock_owned_by_live_process_is_not_stolen(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            lock = Path(str(path) + ".lock")
            lock.write_text(str(os.getpid()), encoding="ascii")
            old = time.time() - 601
            os.utime(lock, (old, old))
            with self.assertRaises(TimeoutError):
                with task_queue_lock(path, timeout=0.01):
                    self.fail("Should not acquire another live process's lock.")
            self.assertEqual(lock.read_text(encoding="ascii"), str(os.getpid()))

    def test_process_liveness_helper_handles_missing_pid(self):
        # Exercise POSIX semantics explicitly; os.kill(pid, 0) is unsafe on Windows.
        with patch("queue_store._IS_WINDOWS", False):
            with patch("queue_store.os.kill", side_effect=ProcessLookupError):
                self.assertFalse(queue_store.process_is_alive(987654321))
            with patch("queue_store.os.kill", side_effect=PermissionError):
                self.assertTrue(queue_store.process_is_alive(987654321))

    def test_windows_process_liveness_uses_non_destructive_probe(self):
        with patch("queue_store._IS_WINDOWS", True):
            with patch("queue_store._windows_process_is_alive", return_value=True) as windows_probe:
                with patch("queue_store.os.kill", side_effect=AssertionError("must not send a signal on Windows")):
                    self.assertTrue(queue_store.process_is_alive(987654321))
                windows_probe.assert_called_once_with(987654321)

    def test_rejects_non_list_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text(json.dumps({"task": "not a list"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_tasks(path)

    def test_rejects_duplicate_task_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text(json.dumps([{"id": "TASK-1"}, {"id": "TASK-1"}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                load_tasks(path)

    def test_rejects_non_object_task_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text(json.dumps([{"id": "TASK-1"}, "invalid"]), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_tasks(path)


if __name__ == "__main__":
    unittest.main()
