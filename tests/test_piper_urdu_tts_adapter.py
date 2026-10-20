import json
import math
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))
import piper_urdu_tts_adapter as adapter


class FakeVoice:
    def __init__(self):
        self.calls = []
        self.synthesis_configs = []

    def synthesize_wav(self, text, wav_file, syn_config=None):
        self.calls.append(text)
        self.synthesis_configs.append(syn_config)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        samples = array("h", (
            int(7000 * math.sin(index * 0.08)) for index in range(6000)
        ))
        if sys.byteorder != "little":
            samples.byteswap()
        wav_file.writeframes(samples.tobytes())


class PiperUrduAdapterTests(unittest.TestCase):
    def _manifest(self, root, texts):
        items = []
        for index, text in enumerate(texts, 1):
            text_path = root / ("text-%02d.txt" % index)
            output_path = root / ("audio-%02d.wav" % index)
            text_path.write_text(text, encoding="utf-8")
            items.append({"text_file": str(text_path), "output_file": str(output_path)})
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "items": items}), encoding="utf-8")
        return manifest, items

    def test_manifest_synthesizes_scenes_with_one_loaded_piper_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, items = self._manifest(root, [
                "یہ Python API کو test کرتا ہے۔",
                "اب result کو verify کریں۔",
            ])
            voice = FakeVoice()

            class FakePiperVoice:
                calls = 0

                @classmethod
                def load(cls, model_path, use_cuda=False):
                    cls.calls += 1
                    return voice

            class FakeSynthesisConfig:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

            with patch.dict(sys.modules, {"piper": type("PiperModule", (), {
                "PiperVoice": FakePiperVoice,
                "SynthesisConfig": FakeSynthesisConfig,
            })}):
                with patch.object(adapter, "ensure_voice_model", return_value=(root / "voice.onnx", root / "voice.onnx.json")):
                    reports = adapter.synthesize_manifest(manifest)

            self.assertEqual(FakePiperVoice.calls, 1)
            self.assertEqual(len(voice.calls), 2)
            self.assertEqual(
                [item.length_scale for item in voice.synthesis_configs],
                [adapter.DEFAULT_LENGTH_SCALE, adapter.DEFAULT_LENGTH_SCALE],
            )
            self.assertEqual(len(reports), 2)
            for item, report in zip(items, reports):
                audio = Path(item["output_file"])
                self.assertTrue(audio.is_file())
                self.assertGreater(audio.stat().st_size, 1024)
                self.assertEqual(report["sample_rate"], 22050)
                self.assertGreater(report["duration_seconds"], 0.1)
                with wave.open(str(audio), "rb") as wav_file:
                    self.assertEqual(wav_file.getnchannels(), 1)
                    self.assertEqual(wav_file.getsampwidth(), 2)
                    self.assertEqual(wav_file.getframerate(), 22050)

    def test_fasih_v2_revision_and_slower_speech_profile_are_pinned(self):
        self.assertEqual(adapter.DEFAULT_MODEL_REVISION, "06202b7")
        self.assertEqual(adapter.MODEL_MD5, "f32ec2c6ebcc6bd1752cab0b932859c7")
        self.assertEqual(adapter.MODEL_SIZE_BYTES, 64_832_023)
        self.assertEqual(adapter.DEFAULT_LENGTH_SCALE, 1.15)

    def test_fasih_v2_config_adds_expected_diphthong_ids(self):
        source = {
            "audio": {"sample_rate": 22050},
            "language": {"code": "ur_PK"},
            "phoneme_id_map": {"a": [14], "b": [15]},
            "piper_version": "1.3.0",
        }
        result = adapter._build_fasih_v2_config(source)
        self.assertEqual(result["piper_version"], "1.5.0")
        for symbol, item_id in adapter.FASIH_V2_PHONEME_IDS.items():
            self.assertEqual(result["phoneme_id_map"][symbol], [item_id])
        self.assertEqual(source["piper_version"], "1.3.0")

    def test_manifest_rejects_duplicate_output_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_a = root / "a.txt"
            text_b = root / "b.txt"
            text_a.write_text("یہ پہلا متن ہے۔", encoding="utf-8")
            text_b.write_text("یہ دوسرا متن ہے۔", encoding="utf-8")
            shared = root / "same.wav"
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"items": [
                {"text_file": str(text_a), "output_file": str(shared)},
                {"text_file": str(text_b), "output_file": str(shared)},
            ]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate output"):
                adapter.read_manifest(manifest)

    def test_manifest_rejects_empty_text_before_model_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = root / "empty.txt"
            text_path.write_text("  \n", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"items": [
                {"text_file": str(text_path), "output_file": str(root / "out.wav")}
            ]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must contain 1 to"):
                adapter.read_manifest(manifest)

    def test_model_download_rejects_corrupt_content_and_never_promotes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "voice.onnx"

            class Response:
                def __init__(self):
                    self.done = False

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self, size=-1):
                    if self.done:
                        return b""
                    self.done = True
                    return b"corrupt"

            with patch.object(adapter.urllib.request, "urlopen", return_value=Response()):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    adapter.download_verified(
                        "https://example.invalid/voice.onnx",
                        destination,
                        "00000000000000000000000000000000",
                        len(b"corrupt"),
                    )
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_wav_inspection_rejects_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "silent.wav"
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(22050)
                stream.writeframes(b"\x00\x00" * 6000)
            with self.assertRaisesRegex(ValueError, "effectively silent"):
                adapter.inspect_wav(path)


if __name__ == "__main__":
    unittest.main()
