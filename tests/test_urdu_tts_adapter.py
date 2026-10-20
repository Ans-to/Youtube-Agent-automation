import json
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import urdu_tts_adapter as adapter


class FakeTtsPipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return {
            "audio": [0.22 * math.sin(index * 0.075) for index in range(6000)],
            "sampling_rate": 22050,
        }


class UrduTtsAdapterTests(unittest.TestCase):
    def test_manifest_synthesizes_all_scenes_with_one_loaded_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = []
            for index, text in enumerate(
                ("یہ Python code ایک API request بناتا ہے۔", "اب ہم result کو verify کرتے ہیں۔"), 1
            ):
                text_path = root / ("text-%02d.txt" % index)
                output_path = root / ("audio-%02d.wav" % index)
                text_path.write_text(text, encoding="utf-8")
                items.append({"text_file": str(text_path), "output_file": str(output_path)})

            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"items": items}), encoding="utf-8")
            fake = FakeTtsPipeline()
            reports = adapter.synthesize_manifest(manifest, pipeline_instance=fake)

            self.assertEqual(len(fake.calls), 2)
            self.assertEqual(len(reports), 2)
            for item, report in zip(items, reports):
                output_path = Path(item["output_file"])
                self.assertTrue(output_path.is_file())
                self.assertGreater(output_path.stat().st_size, 1024)
                self.assertGreater(report["duration_seconds"], 0.1)
                with wave.open(str(output_path), "rb") as audio:
                    self.assertEqual(audio.getnchannels(), 1)
                    self.assertEqual(audio.getsampwidth(), 2)
                    self.assertEqual(audio.getframerate(), 22050)
                    self.assertEqual(audio.getnframes(), 6000)

    def test_kani_speech_token_section_decodes_four_codebook_offsets(self):
        base = adapter.DEFAULT_MODEL_REVISION
        tokenizer_length = 64400
        audio_start = tokenizer_length + 10
        codebook_size = 4032
        expected = [1, 2, 3, 4]
        encoded = [
            audio_start + codebook_size * index + value
            for index, value in enumerate(expected)
        ]
        output = [1, tokenizer_length + 1, *encoded, tokenizer_length + 2, tokenizer_length + 6]
        self.assertEqual(
            adapter.extract_kani_audio_codebook_rows(output),
            [expected],
        )

    def test_kani_token_parser_rejects_missing_markers_and_partial_frames(self):
        with self.assertRaisesRegex(ValueError, "speech-token section"):
            adapter.extract_kani_audio_codebook_rows([1, 2, 3, 4])
        with self.assertRaisesRegex(ValueError, "not divisible by four"):
            adapter.extract_kani_audio_codebook_rows([64401, 64411, 64402])

    def test_kani_token_parser_rejects_invalid_codebook_values(self):
        with self.assertRaisesRegex(ValueError, "invalid codebook token"):
            adapter.extract_kani_audio_codebook_rows(
                [64401, 64410 + 4032, 64410 + 4032 + 1,
                 64410 + 8064 + 1, 64410 + 12096 + 1, 64402]
            )

    def test_silence_fails_closed_instead_of_writing_a_silent_voiceover(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "silent.wav"
            with self.assertRaisesRegex(ValueError, "effectively silent"):
                adapter.write_wav(output, [0.0] * 6000, 22050)
            self.assertFalse(output.exists())

    def test_manifest_rejects_duplicate_output_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "one.txt"
            b = root / "two.txt"
            a.write_text("یہ Urdu text ہے۔", encoding="utf-8")
            b.write_text("یہ دوسرا text ہے۔", encoding="utf-8")
            output = root / "same.wav"
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"items": [
                {"text_file": str(a), "output_file": str(output)},
                {"text_file": str(b), "output_file": str(output)},
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


if __name__ == "__main__":
    unittest.main()
