"""Cross-process locking and atomic writes for the local task queue."""
import ctypes
import errno
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

_IS_WINDOWS = os.name == "nt"


def _windows_process_is_alive(pid):
    """Check process state using non-destructive Win32 process handles.

    Do not use os.kill(pid, 0) on Windows: signal value zero is the
    CTRL_C_EVENT constant there, not POSIX's harmless null signal.
    """
    from ctypes import wintypes

    PROCESS_SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    ERROR_INVALID_PARAMETER = 87
    ERROR_NOT_FOUND = 1168

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = open_process(PROCESS_SYNCHRONIZE, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error in (ERROR_INVALID_PARAMETER, ERROR_NOT_FOUND):
            return False
        # Access denied or an unknown API error must not cause a live owner's
        # lock to be stolen. Prefer a recoverable timeout over corrupting state.
        return True

    try:
        result = wait_for_single_object(handle, 0)
        if result == WAIT_OBJECT_0:
            return False
        if result == WAIT_TIMEOUT:
            return True
        # WAIT_FAILED or any undocumented result is treated conservatively.
        return True
    finally:
        close_handle(handle)


def process_is_alive(pid):
    """Return whether PID plausibly identifies a live process on this OS."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if _IS_WINDOWS:
        return _windows_process_is_alive(pid)

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        # Treat unknown OS errors conservatively; deleting a live owner's lock is unsafe.
        return exc.errno != errno.ESRCH


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
                    try:
                        owner_pid = int(lock.read_text(encoding="ascii").strip())
                    except (OSError, ValueError):
                        owner_pid = 0
                    if not process_is_alive(owner_pid):
                        try:
                            lock.unlink()
                        except FileNotFoundError:
                            pass
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
