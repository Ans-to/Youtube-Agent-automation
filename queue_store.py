"""Cross-process locking and atomic writes for the local task queue."""
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def task_queue_lock(path, timeout=30):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 600:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for the task queue lock.")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def load_tasks(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError("tasks.json must contain a JSON array of task objects.")
    ids = [str(item.get("id", "")) for item in data if item.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("Task IDs must be unique; refusing to update an ambiguous queue.")
    return data


def save_tasks(path, tasks):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp-" + str(os.getpid()))
    temp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
