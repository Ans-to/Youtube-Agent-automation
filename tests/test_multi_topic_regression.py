import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VIDEO_STUDIO = ROOT / "video_studio"
sys.path.insert(0, str(VIDEO_STUDIO))
import multi_topic_regression as regression


class MultiTopicRegressionCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(
            (VIDEO_STUDIO / "multi_topic_regression.json").read_text(encoding="utf-8")
        )
        cls.topics = regression.validate_corpus(cls.corpus)

    def test_corpus_has_ten_genuinely_distinct_niches_and_scripts(self):
        self.assertEqual(len(self.topics), 10)
        self.assertEqual(len({topic["niche"] for topic in self.topics}), 10)
        self.assertEqual(len({topic["title"] for topic in self.topics}), 10)
        scripts = [
            " ".join(scene["narration"] for scene in topic["scenes"])
            for topic in self.topics
        ]
        self.assertEqual(len(set(scripts)), 10)
        self.assertTrue(all(len(script.split()) >= 18 for script in scripts))

    def test_all_thirty_scene_narration_lines_are_unique(self):
        narrations = [
            scene["narration"].strip().casefold()
            for topic in self.topics
            for scene in topic["scenes"]
        ]
        self.assertEqual(len(narrations), 30)
        self.assertEqual(len(set(narrations)), 30)

    def test_all_ten_niches_have_distinct_opening_compositions(self):
        opening_types = [topic["scenes"][0]["visual_type"] for topic in self.topics]
        self.assertEqual(len(opening_types), 10)
        self.assertEqual(len(set(opening_types)), 10)
        self.assertEqual(
            set(opening_types),
            {"code", "diagram", "stat", "comparison", "timeline",
             "waveform", "quote", "hero", "kinetic-type", "bar-chart"},
        )

    def test_niche_scripts_exercise_multiple_visual_types_and_transitions(self):
        visual_types = {
            scene["visual_type"]
            for topic in self.topics
            for scene in topic["scenes"]
        }
        transitions = {
            scene["transition_in"]
            for topic in self.topics
            for scene in topic["scenes"]
        }
        self.assertGreaterEqual(len(visual_types), 7)
        self.assertGreaterEqual(len(transitions), 5)

    def test_scene_padding_stays_within_declared_cap_and_voice_coverage_stays_strict(self):
        self.assertIsNone(regression.pacing_failure_reason(1, 0.220, 0.91))
        self.assertIsNone(regression.pacing_failure_reason(2, 0.219, 0.90))
        self.assertIsNotNone(regression.pacing_failure_reason(3, 0.221, 0.91))
        self.assertIsNotNone(regression.pacing_failure_reason(4, 0.220, 0.87))
        self.assertIsNotNone(regression.pacing_failure_reason(5, float("nan"), 0.91))
        self.assertAlmostEqual(
            regression.MAX_ACCEPTED_PADDING_SECONDS,
            regression.MAX_SCENE_PADDING_SECONDS + 0.000001,
        )

    def test_contact_sheet_includes_every_rendered_topic_even_if_qc_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = []
            for index in range(10):
                output_dir = f"{index:02d}-topic"
                topic_dir = root / output_dir
                topic_dir.mkdir()
                (topic_dir / "style-frame.png").write_bytes(b"style-frame-" + bytes([index]) * 96)
                entries.append({
                    "id": str(index),
                    "niche": "topic-" + str(index),
                    "output_dir": output_dir,
                    "status": "passed" if index < 2 else "failed",
                })

            captured = {}
            def fake_run(command, timeout=300):
                inputs = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-i"]
                captured["inputs"] = inputs
                Path(command[-1]).write_bytes(b"contact-sheet-" + b"x" * 1200)
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.object(regression.shutil, "which", return_value="ffmpeg"), \
                 patch.object(regression, "run", side_effect=fake_run):
                contact, error = regression.create_contact_sheet(entries, root)

            self.assertIsNone(error)
            self.assertEqual(contact, "ten-niche-contact-sheet.jpg")
            self.assertEqual(len(captured["inputs"]), 10)
            self.assertTrue(all(Path(path).is_file() for path in captured["inputs"]))

    def test_invalid_duplicate_or_short_script_corpus_fails_closed(self):
        duplicate = json.loads(json.dumps(self.corpus))
        duplicate["topics"][1]["niche"] = duplicate["topics"][0]["niche"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            regression.validate_corpus(duplicate)

        short = json.loads(json.dumps(self.corpus))
        short["topics"][0]["scenes"][0]["narration"] = "Too short."
        with self.assertRaisesRegex(ValueError, "short or malformed"):
            regression.validate_corpus(short)


if __name__ == "__main__":
    unittest.main()
