import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "video_studio" / "auditor_adapters.py"
SPEC = importlib.util.spec_from_file_location("auditor_adapters", MODULE_PATH)
ADAPTERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTERS)


class AuditorAdapterTests(unittest.TestCase):
    def test_tesseract_tsv_parsing_keeps_text_and_confidence(self):
        tsv = (
            "level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext\\n"
            "5\\t1\\t1\\t1\\t1\\t1\\t0\\t0\\t20\\t10\\t90\\tSponsored\\n"
            "5\\t1\\t1\\t1\\t1\\t2\\t22\\t0\\t30\\t10\\t80\\tcontent\\n"
        )
        parsed = ADAPTERS.parse_tesseract_tsv(tsv)
        self.assertEqual(parsed["text"], "Sponsored content")
        self.assertEqual(parsed["confidence"], 0.85)

    def test_invalid_model_json_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            ADAPTERS.parse_json_object("not-json")

    def test_configured_terms_are_exact_word_matches_with_timestamps(self):
        observations = [{
            "start_seconds": 3.5, "end_seconds": 4.2,
            "text": "That is bullshit, but this is class.",
            "source": "faster-whisper",
        }]
        findings = ADAPTERS.find_configured_terms(observations, ["shit"])
        self.assertEqual(findings, [])
        findings = ADAPTERS.find_configured_terms(observations, ["bullshit"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["start_seconds"], 3.5)
        self.assertEqual(findings[0]["end_seconds"], 4.2)

    def test_text_classifier_maps_model_findings_to_original_timestamps(self):
        observations = [{"start_seconds": 8.0, "end_seconds": 9.5, "text": "insult", "source": "asr"}]
        def fake_call(config, messages):
            return {"findings": [{
                "evidence_id": "T0", "rule": "hate_harassment",
                "description": "Transcript contains a targeted slur.",
                "confidence": 0.88,
            }]}
        findings = ADAPTERS.classify_text_observations(observations, {}, call_model=fake_call)
        self.assertEqual(findings[0]["start_seconds"], 8.0)
        self.assertEqual(findings[0]["end_seconds"], 9.5)
        self.assertEqual(findings[0]["confidence"], 0.88)

    def test_text_classifier_ignores_unmapped_ids_and_invalid_rules(self):
        observations = [{"start_seconds": 1, "end_seconds": 2, "text": "sample", "source": "asr"}]
        def fake_call(config, messages):
            return {"findings": [
                {"evidence_id": "T9", "rule": "profanity", "description": "bad", "confidence": 0.8},
                {"evidence_id": "T0", "rule": "invented_rule", "description": "bad", "confidence": 0.8},
            ]}
        self.assertEqual(ADAPTERS.classify_text_observations(observations, {}, call_model=fake_call), [])

    def test_vision_findings_are_bounded_to_the_sampled_frame_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / "frame.jpg"
            frame.write_bytes(b"test-jpeg-bytes")
            frames = [{"timestamp": 5.0, "path": frame}, {"timestamp": 6.0, "path": frame}]
            def fake_call(config, messages, max_tokens=1800):
                return {"findings": [
                    {"start_seconds": 5.0, "end_seconds": 6.0, "rule": "violence_gore",
                     "description": "A physical altercation appears across sampled frames.", "confidence": 0.9},
                    {"start_seconds": 0.0, "end_seconds": 50.0, "rule": "violence_gore",
                     "description": "Out of sample range.", "confidence": 0.9},
                ]}
            findings = ADAPTERS.analyze_frame_batches(frames, {}, call_model=fake_call)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["start_seconds"], 5.0)
            self.assertEqual(findings[0]["rule"], "violence_gore")

    def test_optional_detectors_stay_unconfigured_by_default(self):
        result = ADAPTERS.run_optional_detectors("missing.mp4", {"video_studio": {"auditor": {"enabled": False}}})
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["coverage"], {})


if __name__ == "__main__":
    unittest.main()
