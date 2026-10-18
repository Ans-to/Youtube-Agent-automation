import json
import tempfile
import unittest
from pathlib import Path

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

    def test_rejects_non_list_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text(json.dumps({"task": "not a list"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_tasks(path)

    def test_rejects_non_object_task_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text(json.dumps([{"id": "TASK-1"}, "invalid"]), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_tasks(path)


if __name__ == "__main__":
    unittest.main()
