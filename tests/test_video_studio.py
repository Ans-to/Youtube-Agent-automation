import json
import math
import struct
import wave
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))
import production
import studio
from captions import build_subtitles, normalize_narration_language, validate_narration_text, validate_english_text, validate_english_voice_model, validate_subtitle_text
from voice_backends import get_urdu_tts_command, resolve_urdu_tts_command


class VideoStudioTests(unittest.TestCase):
    def test_kani_speaker_prefix_is_optional_explicit_and_type_checked(self):
        self.assertIsNone(studio.configured_kani_speaker_prefix({}))
        self.assertEqual(
            studio.configured_kani_speaker_prefix(
                {"video_studio": {"kani_speaker_prefix": "  verified_male_speaker  "}}
            ),
            "verified_male_speaker",
        )
        self.assertEqual(
            studio.configured_kani_speaker_prefix(
                {"video_studio": {"kani_speaker_prefix": ""}}
            ),
            "",
        )
        with self.assertRaisesRegex(ValueError, "must be text"):
            studio.configured_kani_speaker_prefix(
                {"video_studio": {"kani_speaker_prefix": False}}
            )

    def test_direct_renderer_language_precedence_is_explicit_and_configurable(self):
        self.assertEqual(
            studio.resolve_narration_language(
                "en",
                {"narration_language": "ur-en"},
                {"video_studio": {"narration_language": "ur-en"}},
            ),
            "en",
        )
        self.assertEqual(
            studio.resolve_narration_language(
                None,
                {"narration_language": "ur-en"},
                {"video_studio": {"narration_language": "en"}},
            ),
            "ur-en",
        )
        self.assertEqual(
            studio.resolve_narration_language(
                None, {}, {"video_studio": {"narration_language": "ur-en"}}
            ),
            "ur-en",
        )
        self.assertEqual(studio.resolve_narration_language(None, {}, {}), "ur-en")

    def _write_pcm16_test_wav(self, path, active_seconds=0.48, duration_seconds=1.0, amplitude=10000):
        sample_rate = 22050
        total_frames = int(sample_rate * duration_seconds)
        active_frames = int(sample_rate * active_seconds)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            frames = []
            for index in range(total_frames):
                sample = int(amplitude * math.sin(2 * math.pi * 440 * index / sample_rate)) if index < active_frames else 0
                frames.append(struct.pack("<h", sample))
            output.writeframes(b"".join(frames))

    def test_audio_energy_visemes_follow_speech_activity_and_close_after_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "active-then-silent.wav"
            self._write_pcm16_test_wav(audio_path, active_seconds=0.48)
            cues = studio.build_audio_gated_visemes("یہ Python API ہے", audio_path, 1.0, 0.08)
            self.assertGreaterEqual(len(cues), 3)
            self.assertEqual(cues[0]["t"], 0.0)
            self.assertEqual(cues[-1], {"t": 1.0, "shape": "closed"})
            self.assertTrue(all(0.0 <= cue["t"] <= 1.0 for cue in cues))
            self.assertTrue(all(
                left["t"] <= right["t"] for left, right in zip(cues, cues[1:])
            ))
            self.assertTrue(all(cue["shape"] in {"closed", "open", "wide", "round"} for cue in cues))
            self.assertTrue(any(cue["shape"] != "closed" and cue["t"] < 0.45 for cue in cues))
            later_closed = [cue for cue in cues if cue["t"] >= 0.62]
            self.assertTrue(later_closed)
            self.assertTrue(all(cue["shape"] == "closed" for cue in later_closed))

    def test_silent_audio_produces_only_closed_mouth_viseme_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "silent.wav"
            self._write_pcm16_test_wav(audio_path, active_seconds=0.0, amplitude=0)
            cues = studio.build_audio_gated_visemes("یہ Urdu narration ہے", audio_path, 1.0)
            self.assertEqual(cues[0], {"t": 0.0, "shape": "closed"})
            self.assertEqual(cues[-1], {"t": 1.0, "shape": "closed"})
            self.assertTrue(all(cue["shape"] == "closed" for cue in cues))

    def test_viseme_builder_rejects_invalid_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "active.wav"
            self._write_pcm16_test_wav(audio_path)
            with self.assertRaisesRegex(ValueError, "positive scene duration"):
                studio.build_audio_gated_visemes("some narration", audio_path, 0)

    def test_example_storyboard_is_valid(self):
        path = ROOT / "video_studio" / "storyboard.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["scenes"]), 1)
        self.assertTrue(1 <= data["fps"] <= 60)
        for scene in data["scenes"]:
            self.assertGreater(scene["duration_seconds"], 0)
            self.assertIn("headline", scene)

    def test_roster_has_fifty_two_unique_role_profiles(self):
        data = json.loads((ROOT / "agents" / "roster.json").read_text(encoding="utf-8"))
        agents = data["agents"]
        self.assertEqual(len(agents), 52)
        self.assertEqual(len({agent["id"] for agent in agents}), 52)
        self.assertIn("Motion Graphics Creative Director", {agent["name"] for agent in agents})
        self.assertIn("Motion Systems & Compositing Specialist", {agent["name"] for agent in agents})
        self.assertTrue(any(agent["approval_required"] for agent in agents))

    def test_scene_builder_validates_narration_in_the_selected_language(self):
        def scene_with(narration):
            return {
                "eyebrow": "EXPLAINER",
                "headline": "Python APIs",
                "subhead": "A practical overview",
                "narration": narration,
                "visual_type": "hero",
            }

        urdu_scene = scene_with("آج ہم Python API کو step by step سمجھیں گے۔")
        with patch.object(production, "model_json", return_value=dict(urdu_scene)):
            generated = production.create_scene(
                "Python API", {"thesis": "Explain the API"},
                {"title": "Introduction"}, "", {"model": {"scene_output_tokens": 700}},
                1, 4, 20, {"headline": "", "summary": "Opening"}, "ur-en"
            )
        self.assertIn("Python API", generated["narration"])
        self.assertEqual(generated["narration_language"], "ur-en")

        with patch.object(production, "model_json", return_value=scene_with("Today we explain the Python API.")):
            with self.assertRaisesRegex(ValueError, "must contain Urdu text"):
                production.create_scene(
                    "Python API", {"thesis": "Explain the API"},
                    {"title": "Introduction"}, "", {"model": {"scene_output_tokens": 700}},
                    1, 4, 20, {"headline": "", "summary": "Opening"}, "ur-en"
                )

        with patch.object(production, "model_json", return_value=dict(urdu_scene)):
            with self.assertRaisesRegex(ValueError, "must be English text"):
                production.create_scene(
                    "Python API", {"thesis": "Explain the API"},
                    {"title": "Introduction"}, "", {"model": {"scene_output_tokens": 700}},
                    1, 4, 20, {"headline": "", "summary": "Opening"}, "en"
                )

    def test_package_status_distinguishes_audio_gated_visemes_from_phoneme_alignment(self):
        storyboard = {
            "scenes": [
                {"character": {"enabled": True, "visemes": [
                    {"t": 0.0, "shape": "closed"}, {"t": 1.0, "shape": "open"}
                ]}},
                {"character": {"enabled": True, "speaking": True}},
                {"character": {"enabled": False, "visemes": [{"t": 0.0, "shape": "closed"}]}},
                {"visual_type": "hero"},
            ]
        }
        summary = production.character_alignment_summary(storyboard)
        self.assertEqual(summary["character_scenes"], 2)
        self.assertEqual(summary["viseme_cued_character_scenes"], 1)
        self.assertFalse(summary["phoneme_aligned"])
        self.assertIn("not forced phoneme alignment", summary["viseme_alignment_method"])

        without_character = production.character_alignment_summary({"scenes": [{"visual_type": "hero"}]})
        self.assertEqual(without_character["character_scenes"], 0)
        self.assertEqual(without_character["viseme_cued_character_scenes"], 0)
        self.assertEqual(without_character["viseme_alignment_method"], "no generated character viseme cues")

    def test_fallback_is_explicitly_not_researched(self):
        result = production.fallback("Test topic")
        self.assertEqual(len(result["scenes"]), 4)
        self.assertIn("no web research was performed", result["script"])
        self.assertTrue(all(scene["duration_seconds"] > 0 for scene in result["scenes"]))
        self.assertTrue(all(scene.get("visual_type") in {"hero", "diagram", "code", "timeline"} for scene in result["scenes"]))



    def test_all_fallback_narration_is_english(self):
        result = production.fallback("Test topic")
        for index, scene in enumerate(result["scenes"], 1):
            with self.subTest(scene=index):
                self.assertEqual(validate_english_text(scene["narration"]), scene["narration"])

    def test_non_english_script_is_rejected_for_voiceover(self):
        with self.assertRaisesRegex(ValueError, "must be English"):
            validate_english_text("یہ اردو narration ہے")

    def test_subtitle_generation_emits_valid_srt_and_webvtt(self):
        storyboard = {
            "scenes": [
                {"duration_seconds": 4.0, "narration_duration_seconds": 3.2,
                 "narration": "English narration must always have matching subtitles."},
                {"duration_seconds": 3.0, "narration_duration_seconds": 2.4,
                 "narration": "Transitions should support the story, not distract."}
            ]
        }
        srt, vtt = build_subtitles(storyboard)
        report = validate_subtitle_text(srt, vtt)
        self.assertGreaterEqual(report["cue_count"], 2)
        self.assertIn("English narration must always have", srt)
        self.assertIn("matching subtitles.", srt)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertEqual(storyboard["scenes"][0]["caption"], storyboard["scenes"][0]["narration"])

    def test_voice_model_language_is_verified_from_adjacent_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "voice.onnx"
            model.write_bytes(b"model-placeholder")
            config = Path(str(model) + ".json")
            config.write_text(json.dumps({"language": {"code": "en_US"}}), encoding="utf-8")
            self.assertEqual(validate_english_voice_model(model), "en_US")
            config.write_text(json.dumps({"language": {"code": "ur_PK"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "English-only"):
                validate_english_voice_model(model)

    def test_urdu_english_profile_accepts_urdu_script_and_english_technical_terms(self):
        text = "یہ Python code اور API request کو automate کرتا ہے۔"
        self.assertEqual(normalize_narration_language("urdu"), "ur-en")
        self.assertEqual(validate_narration_text(text, "ur-en"), text)
        storyboard = {
            "narration_language": "ur-en",
            "scenes": [{"duration_seconds": 4.0, "narration_duration_seconds": 3.2, "narration": text}],
        }
        srt, vtt = build_subtitles(storyboard)
        self.assertIn("Python code", srt)
        self.assertIn("API request", vtt)
        report = validate_subtitle_text(srt, vtt, language="ur-en")
        self.assertGreaterEqual(report["cue_count"], 1)

    def test_urdu_english_profile_rejects_english_only_and_devanagari(self):
        with self.assertRaisesRegex(ValueError, "must contain Urdu text"):
            validate_narration_text("Python code builds an API", "ur-en")
        with self.assertRaisesRegex(ValueError, "another writing system"):
            validate_narration_text("यह हिन्दी है", "ur-en")

    def test_empty_urdu_tts_setting_selects_bundled_batch_adapter(self):
        command = get_urdu_tts_command({"video_studio": {"urdu_tts_command": []}})
        self.assertIn("urdu_tts_adapter.py", command[1])
        self.assertEqual(command[-2:], ["--manifest", "{manifest_file}"])
        resolved = resolve_urdu_tts_command(command, manifest_file="temp/manifest.json")
        self.assertTrue(resolved[-1].endswith("manifest.json"))
        self.assertFalse(any("{" in item or "}" in item for item in resolved))

    def test_custom_urdu_tts_adapter_requires_safe_path_placeholders(self):
        with self.assertRaisesRegex(ValueError, "output_file"):
            get_urdu_tts_command({"video_studio": {"urdu_tts_command": ["python", "adapter.py", "{text_file}"]}})
        template = ["python", "adapter.py", "--input", "{text_file}", "--output", "{output_file}"]
        config = {"video_studio": {"urdu_tts_command": template}}
        self.assertEqual(get_urdu_tts_command(config), template)
        resolved = resolve_urdu_tts_command(template, "temp/narration.txt", "temp/audio.wav")
        self.assertTrue(resolved[3].endswith("narration.txt"))
        self.assertTrue(resolved[5].endswith("audio.wav"))
        self.assertFalse(any("{" in item or "}" in item for item in resolved))

    def test_custom_urdu_tts_batch_adapter_can_use_manifest_placeholder(self):
        template = ["python", "adapter.py", "--manifest", "{manifest_file}"]
        self.assertEqual(
            get_urdu_tts_command({"video_studio": {"urdu_tts_command": template}}),
            template,
        )
        resolved = resolve_urdu_tts_command(template, manifest_file="temp/manifest.json")
        self.assertTrue(resolved[-1].endswith("manifest.json"))

    def test_urdu_track_allows_an_english_technical_term_only_cue(self):
        srt = """1
00:00:00,000 --> 00:00:01,000
یہ introduction ہے۔

2
00:00:01,100 --> 00:00:02,000
Python API version three.
"""
        vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
یہ introduction ہے۔

00:00:01.100 --> 00:00:02.000
Python API version three.
"""
        report = validate_subtitle_text(srt, vtt, language="ur-en")
        self.assertEqual(report["cue_count"], 2)

    def test_urdu_track_rejects_english_only_sidecars(self):
        srt = """1
00:00:00,000 --> 00:00:01,000
Python API version three.
"""
        vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
Python API version three.
"""
        with self.assertRaisesRegex(ValueError, "English-only captions"):
            validate_subtitle_text(srt, vtt, language="ur-en")

    def test_subtitle_validation_rejects_overlapping_cues(self):
        srt = """1
00:00:00,000 --> 00:00:02,000
First caption.

2
00:00:01,000 --> 00:00:03,000
Second caption.
"""
        vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
First caption.

00:00:01.000 --> 00:00:03.000
Second caption.
"""
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_subtitle_text(srt, vtt)

    def test_subtitle_validation_rejects_empty_files(self):
        with self.assertRaisesRegex(ValueError, "required"):
            validate_subtitle_text("", "WEBVTT\\n")

    def test_local_model_rejects_non_loopback_and_userinfo_urls(self):
        for url in ("http://example.com:8080/v1/chat/completions",
                    "http://127.0.0.1:123@example.com:80/v1/chat/completions",
                    "https://127.0.0.1:8080/v1/chat/completions",
                    "http://127.0.0.1/v1/chat/completions"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    production.post_local_model(url, {}, 1)

if __name__ == "__main__":
    unittest.main()
