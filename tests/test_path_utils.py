import ctypes
import os
import tempfile
import unittest
from pathlib import Path

from tools.path_utils import canonical_path, is_within, safe_relative_path


class PathUtilsTests(unittest.TestCase):
    def test_containment_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            child = workspace / "run-1"
            outside = root.parent / (root.name + "-outside")
            workspace.mkdir()
            child.mkdir()
            self.assertTrue(is_within(child, workspace, allow_equal=False))
            self.assertTrue(is_within(workspace, workspace))
            self.assertEqual(safe_relative_path(child, workspace), Path("run-1"))
            self.assertFalse(is_within(outside, workspace))

    @unittest.skipUnless(os.name == "nt", "Windows short-path aliases exist only on Windows")
    def test_short_and_long_windows_paths_are_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_short_path = kernel32.GetShortPathNameW
            get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
            get_short_path.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            length = get_short_path(str(root), buffer, len(buffer))
            if not length or length >= len(buffer) or buffer.value.casefold() == str(root).casefold():
                self.skipTest("Windows runner did not expose a distinct short-path alias")
            short_root = Path(buffer.value)
            short_workspace = short_root / "workspace"
            candidate = workspace / "run-1"
            self.assertTrue(is_within(candidate, short_workspace, allow_equal=False))
            self.assertEqual(safe_relative_path(candidate, short_workspace), Path("run-1"))
            self.assertEqual(canonical_path(short_root), canonical_path(root))


if __name__ == "__main__":
    unittest.main()
