"""Regression tests for the content pipeline's research-first policy."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_studio.production import create_scene, run_strict_quality_audit, should_collect_research, validate_research_evidence
from video_studio.quality_audit import file_sha256


class ResearchPolicyTests(unittest.TestCase):
    def test_research_is_default_for_non_template_packages(self):
        self.assertTrue(should_collect_research(research_requested=False, render_template=False))

    def test_offline_template_smoke_stays_network_free_by_default(self):
        self.assertFalse(should_collect_research(research_requested=False, render_template=True))

    def test_explicit_research_is_honored_for_any_mode(self):
        self.assertTrue(should_collect_research(research_requested=True, render_template=True))

    def test_research_gate_rejects_snippets_without_fetched_page_text(self):
        metadata = {"pages_attempted": 3, "pages_fetched": 0, "verified": False}
        results = [
            {"url": "https://example.com", "snippet": "Search snippet only", "fetch_status": "failed", "page_text": ""}
        ]
        with self.assertRaisesRegex(ValueError, "Search snippets alone"):
            validate_research_evidence(metadata, results)

    def test_scene_rejects_unknown_source_ids_and_marks_supported_refs(self):
        base_scene = {
            "eyebrow": "Evidence",
            "headline": "A supported claim",
            "subhead": "A short explanation",
            "narration": "This system records source evidence for review.",
            "visual_type": "hero",
            "source_refs": ["S1"],
            "unresolved_notes": [],
        }
        with patch("video_studio.production.model_json", return_value=dict(base_scene)):
            scene = create_scene(
                "Research pipeline", {"thesis": "Evidence matters"},
                {"name": "Evidence", "purpose": "Explain provenance"},
                "Source notes", {"model": {}}, 1, 1, 12, {}, "en", ["S1"],
            )
        self.assertEqual(scene["source_refs"], ["S1"])
        self.assertEqual(scene["evidence_status"], "source_linked_requires_review")

        invalid_scene = dict(base_scene, source_refs=["S99"])
        with patch("video_studio.production.model_json", return_value=invalid_scene):
            with self.assertRaisesRegex(ValueError, "unavailable or unfetched source IDs"):
                create_scene(
                    "Research pipeline", {"thesis": "Evidence matters"},
                    {"name": "Evidence", "purpose": "Explain provenance"},
                    "Source notes", {"model": {}}, 1, 1, 12, {}, "en", ["S1"],
                )

    def test_generated_scene_always_has_an_integrated_speaking_presenter(self):
        base_scene = {
            "eyebrow": "Evidence", "headline": "A supported claim",
            "subhead": "A short explanation",
            "narration": "This system records source evidence for review.",
            "visual_type": "hero", "source_refs": [], "unresolved_notes": [],
        }
        with patch("video_studio.production.model_json", return_value=dict(base_scene)):
            scene = create_scene(
                "Research pipeline", {"thesis": "Evidence matters"},
                {"name": "Evidence", "purpose": "Explain provenance"},
                "Source notes", {"model": {}}, 2, 4, 12, {}, "en", [],
            )
        self.assertTrue(scene["character"]["enabled"])
        self.assertTrue(scene["character"]["speaking"])
        self.assertGreater(scene["character"]["scale"], 0)
        self.assertIn("pose", scene["character"])

    def test_fallback_preview_has_presenter_in_every_scene(self):
        from video_studio.production import fallback
        storyboard = fallback("Integrated motion design")
        self.assertGreaterEqual(len(storyboard["scenes"]), 4)
        self.assertTrue(all(
            isinstance(scene.get("character"), dict)
            and scene["character"].get("enabled") is True
            and scene["character"].get("speaking") is True
            for scene in storyboard["scenes"]
        ))

    def test_research_gate_records_fetched_domains_and_text_digests(self):
        page_text = "Fetched primary-source text"
        digest = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
        metadata = {"pages_attempted": 2, "pages_fetched": 2, "verified": False}
        results = [
            {"fetch_status": "fetched", "page_text": page_text, "page_text_sha256": digest, "final_domain": "docs.example.com"},
            {"fetch_status": "fetched", "page_text": page_text, "page_text_sha256": digest, "final_domain": "research.example.org"},
        ]
        summary = validate_research_evidence(metadata, results)
        self.assertEqual(summary["status"], "multiple_domains_fetched")
        self.assertEqual(summary["fetched_page_count"], 2)
        self.assertEqual(summary["independent_domain_count"], 2)
        self.assertFalse(summary["independently_verified"])
        self.assertEqual(summary["page_text_sha256"], [digest])


    def test_automatic_quality_audit_accepts_a_strict_report_bound_to_video(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            video = output_dir / "video.mp4"
            video.write_bytes(b"video bytes " * 100)
            report = {
                "file": str(video.resolve()),
                "video_sha256": file_sha256(video),
                "duration_seconds": 12.5,
                "audio_stream_count": 1,
                "warnings": [],
                "passed": True,
                "strict": True,
            }
            (output_dir / "video.qc.json").write_text(json.dumps(report), encoding="utf-8")
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with patch("video_studio.production.subprocess.run", return_value=completed):
                self.assertEqual(run_strict_quality_audit(output_dir), report)

    def test_automatic_quality_audit_blocks_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="audit failed")
            with patch("video_studio.production.subprocess.run", return_value=completed):
                with self.assertRaises(RuntimeError):
                    run_strict_quality_audit(Path(directory))


class OfflineDegradationTests(unittest.TestCase):
    """No internet must not mean no run — but it must never mean invented facts."""

    def _run_offline(self, directory):
        import sys as sys_module
        import urllib.error
        from video_studio import production

        root = Path(directory)
        (root / "workspace").mkdir()
        argv = [
            "production.py", "--topic", "Local models beat paid APIs",
            "--out", "workspace/offline", "--scenes", "4",
            "--target-minutes", "1", "--language", "en",
        ]
        with (
            patch.object(production, "ROOT", root),
            patch.object(production, "load_config", return_value={}),
            patch.object(production, "collect_research",
                         side_effect=urllib.error.URLError("network is down")),
            patch.object(sys_module, "argv", argv),
        ):
            production.main()
        out = root / "workspace" / "offline"
        return out

    def test_research_failure_without_a_model_writes_a_labelled_template(self):
        with tempfile.TemporaryDirectory() as directory:
            out = self._run_offline(directory)
            script = (out / "script.md").read_text(encoding="utf-8")
            status = json.loads((out / "package-status.json").read_text(encoding="utf-8"))

        self.assertIn("Research unavailable", script)
        self.assertIn("Do not publish it as an explainer", script)
        self.assertEqual(status["status"], "template_demo")
        self.assertEqual(status["research_evidence"]["status"], "unavailable_offline_template")
        self.assertEqual(status["research_evidence"]["error_type"], "URLError")
        self.assertFalse(status["web_research_performed"])
        self.assertTrue(status["human_review_required"])

    def test_the_offline_package_states_no_sources_were_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            out = self._run_offline(directory)
            status = json.loads((out / "package-status.json").read_text(encoding="utf-8"))
        self.assertFalse(status["research_evidence"]["independently_verified"])
        self.assertEqual(status["research_evidence"]["fetched_page_count"], 0)
        self.assertEqual(status["scenes_with_source_refs"], 0)


if __name__ == "__main__":
    unittest.main()
