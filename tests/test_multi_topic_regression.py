import json
import sys
import unittest
from pathlib import Path

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

    def test_scene_padding_allows_one_frame_of_quantization_but_keeps_voice_coverage_strict(self):
        # A 0.25s measured pad is expected when 0.22s is rounded to the next 30fps frame.
        self.assertIsNone(regression.pacing_failure_reason(1, 0.250, 0.91))
        self.assertIsNone(regression.pacing_failure_reason(2, 0.258, 0.90))

        # A real overrun or insufficient speech coverage must still fail closed.
        self.assertIsNotNone(regression.pacing_failure_reason(3, 0.270, 0.91))
        self.assertIsNotNone(regression.pacing_failure_reason(4, 0.220, 0.87))
        self.assertIsNotNone(regression.pacing_failure_reason(5, float("nan"), 0.91))
        self.assertAlmostEqual(
            regression.MAX_ACCEPTED_PADDING_SECONDS,
            regression.MAX_SCENE_PADDING_SECONDS + 1.0 / regression.FPS + 0.005,
        )

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
