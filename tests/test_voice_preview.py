import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))
import voice_preview


class VoicePreviewPathTests(unittest.TestCase):
    def test_workspace_prefixed_output_resolves_from_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            output = voice_preview.resolve_preview_output(
                "workspace/urdu-voice-preview.wav",
                workspace=workspace,
                project_root=project,
            )
            self.assertEqual(output, (workspace / "urdu-voice-preview.wav").resolve())

    def test_bare_filename_resolves_directly_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            output = voice_preview.resolve_preview_output(
                "preview.wav",
                workspace=workspace,
                project_root=project,
            )
            self.assertEqual(output, (workspace / "preview.wav").resolve())

    def test_parent_traversal_and_external_absolute_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            with self.assertRaisesRegex(ValueError, "inside the project workspace"):
                voice_preview.resolve_preview_output("../outside.wav", workspace, project)
            with self.assertRaisesRegex(ValueError, "inside the project workspace"):
                voice_preview.resolve_preview_output(project / "outside.wav", workspace, project)

    def test_preview_requires_wav_extension_and_not_workspace_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            with self.assertRaisesRegex(ValueError, "must use the .wav extension"):
                voice_preview.resolve_preview_output("clip.mp3", workspace, project)
            with self.assertRaisesRegex(ValueError, "not the workspace directory"):
                voice_preview.resolve_preview_output(".", workspace, project)


if __name__ == "__main__":
    unittest.main()
