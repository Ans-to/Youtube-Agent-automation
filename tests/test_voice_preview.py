import hashlib
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))
import voice_preview


class VoicePreviewPathTests(unittest.TestCase):
    def _write_preview_wav(self, path, duration=0.6):
        sample_rate = 22050
        frame_count = int(sample_rate * duration)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            frames = []
            for index in range(frame_count):
                sample = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
                frames.append(struct.pack("<h", sample))
            output.writeframes(b"".join(frames))

    def _write_sidecar(self, preview, workspace, config, profile_hash=None):
        sidecar = voice_preview.sidecar_path_for(preview)
        metadata = {
            "schema_version": 1,
            "status": "awaiting_human_review",
            "preview_relative_path": preview.resolve().relative_to(workspace.resolve()).as_posix(),
            "audio_sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
            "voice_profile_sha256": profile_hash or voice_preview.urdu_voice_profile_sha256(config),
            "human_approved": False,
        }
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
        return sidecar

    def _custom_profile(self, speaker_prefix="speaker-a"):
        return {
            "video_studio": {
                "narration_language": "ur-en",
                "urdu_tts_command": ["python", "workspace/custom_urdu_adapter.py", "--manifest", "{manifest_file}"],
                "kani_speaker_prefix": speaker_prefix,
                "urdu_voice_human_approved": False,
                "urdu_voice_approved_profile_sha256": "",
            }
        }

    def test_voice_approval_decline_does_not_modify_local_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            workspace.mkdir()
            config = self._custom_profile()
            config_path = project / "config.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            preview = workspace / "preview.wav"
            self._write_preview_wav(preview)
            self._write_sidecar(preview, workspace, config)

            with patch("builtins.input", return_value="NO"):
                approved = voice_preview.approve_existing_preview(
                    "workspace/preview.wav", workspace=workspace, project_root=project
                )
            self.assertFalse(approved)
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertFalse(saved["video_studio"]["urdu_voice_human_approved"])
            self.assertEqual(saved["video_studio"]["urdu_voice_approved_profile_sha256"], "")
            sidecar = json.loads(voice_preview.sidecar_path_for(preview).read_text(encoding="utf-8"))
            self.assertFalse(sidecar["human_approved"])
            self.assertEqual(sidecar["status"], "awaiting_human_review")

    def test_voice_approval_requires_exact_confirmation_and_records_profile_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            workspace.mkdir()
            config = self._custom_profile()
            config_path = project / "config.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            preview = workspace / "preview.wav"
            self._write_preview_wav(preview)
            self._write_sidecar(preview, workspace, config)
            fingerprint = voice_preview.urdu_voice_profile_sha256(config)

            with patch("builtins.input", return_value="APPROVE"):
                approved = voice_preview.approve_existing_preview(
                    "workspace/preview.wav", workspace=workspace, project_root=project
                )

            self.assertTrue(approved)
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(voice_preview.urdu_voice_human_approved(saved))
            self.assertEqual(
                saved["video_studio"]["urdu_voice_approved_profile_sha256"],
                fingerprint,
            )
            sidecar = json.loads(voice_preview.sidecar_path_for(preview).read_text(encoding="utf-8"))
            self.assertTrue(sidecar["human_approved"])
            self.assertEqual(sidecar["status"], "human_approved_for_current_profile")

    def test_preview_sidecar_and_voice_fingerprint_validate_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            workspace.mkdir()
            preview = workspace / "preview.wav"
            self._write_preview_wav(preview)
            config = self._custom_profile()
            sidecar = self._write_sidecar(preview, workspace, config)

            result = voice_preview.validate_preview_artifact(preview, config, workspace=workspace)
            self.assertEqual(result["preview_path"], preview.resolve())
            self.assertEqual(result["sidecar_path"], sidecar.resolve())
            self.assertEqual(result["voice_profile_sha256"], voice_preview.urdu_voice_profile_sha256(config))
            self.assertGreater(result["audio_report"]["duration_seconds"], 0.5)
            self.assertFalse(result["metadata"]["human_approved"])

    def test_preview_sidecar_rejects_modified_wav_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            workspace.mkdir()
            preview = workspace / "preview.wav"
            self._write_preview_wav(preview)
            config = self._custom_profile()
            self._write_sidecar(preview, workspace, config)
            with preview.open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "changed after synthesis"):
                voice_preview.validate_preview_artifact(preview, config, workspace=workspace)

    def test_preview_sidecar_rejects_changed_voice_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            workspace.mkdir()
            preview = workspace / "preview.wav"
            self._write_preview_wav(preview)
            original_config = self._custom_profile("speaker-a")
            self._write_sidecar(preview, workspace, original_config)
            changed_config = self._custom_profile("speaker-b")
            with self.assertRaisesRegex(ValueError, "profile changed after this preview"):
                voice_preview.validate_preview_artifact(preview, changed_config, workspace=workspace)

    def test_preview_sidecar_rejects_wrong_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            workspace = project / "workspace"
            workspace.mkdir()
            preview = workspace / "preview.wav"
            self._write_preview_wav(preview)
            config = self._custom_profile()
            sidecar = self._write_sidecar(preview, workspace, config)
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            metadata["preview_relative_path"] = "different.wav"
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "path no longer matches"):
                voice_preview.validate_preview_artifact(preview, config, workspace=workspace)

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
