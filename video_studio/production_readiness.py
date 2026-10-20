"""Editorial/production readiness gate separate from technical media QA.

Technical FFmpeg checks cannot establish factual sourcing, runtime adequacy,
narration quality, or phoneme-aligned lip-sync. This gate intentionally fails
closed until each requirement is backed by package metadata.
"""


def evaluate_production_readiness(status, research_evidence, storyboard):
    """Return a transparent readiness verdict and machine-readable blockers."""
    status = status if isinstance(status, dict) else {}
    research_evidence = research_evidence if isinstance(research_evidence, dict) else {}
    storyboard = storyboard if isinstance(storyboard, dict) else {}
    scenes = storyboard.get("scenes", [])
    scenes = scenes if isinstance(scenes, list) else []
    blockers = []

    generated_by = status.get("generated_by")
    if generated_by != "local_model_multi_pass":
        blockers.append("Content is a deterministic template, not a researched model-generated episode.")

    if status.get("duration_target_met") is not True:
        blockers.append("Rendered duration has not met the requested target.")

    try:
        words = int(status.get("narration_words", 0))
        target_minutes = float(status.get("target_minutes", 0))
    except (TypeError, ValueError):
        words, target_minutes = 0, 0
    minimum_words = max(100, int(target_minutes * 100))
    if words < minimum_words:
        blockers.append(
            "Narration is too short for the requested runtime "
            f"({words} words; minimum gate {minimum_words})."
        )

    try:
        fetched_pages = int(research_evidence.get("fetched_page_count", 0))
        independent_domains = int(research_evidence.get("independent_domain_count", 0))
    except (TypeError, ValueError):
        fetched_pages, independent_domains = 0, 0
    if fetched_pages < 2 or independent_domains < 2:
        blockers.append("At least two fetched, traceable source pages from two independent domains are required.")

    if not scenes:
        blockers.append("Storyboard has no scenes.")
    else:
        missing_presenter = [
            index + 1 for index, scene in enumerate(scenes)
            if not isinstance(scene, dict)
            or not isinstance(scene.get("character"), dict)
            or scene["character"].get("enabled") is not True
        ]
        if missing_presenter:
            blockers.append("Presenter is missing or disabled in scene(s): " + ", ".join(map(str, missing_presenter)) + ".")
        missing_narration = [
            index + 1 for index, scene in enumerate(scenes)
            if not isinstance(scene, dict) or not str(scene.get("narration", "")).strip()
        ]
        if missing_narration:
            blockers.append("Narration is missing in scene(s): " + ", ".join(map(str, missing_narration)) + ".")

    alignment = status.get("character_animation", {})
    if not isinstance(alignment, dict) or alignment.get("phoneme_aligned") is not True:
        blockers.append("True phoneme-aligned lip-sync is not verified; approximate mouth cues are insufficient.")

    subtitle_files = status.get("subtitle_files", [])
    if not isinstance(subtitle_files, list) or not {"video.srt", "video.vtt"}.issubset(set(subtitle_files)):
        blockers.append("Both SRT and WebVTT subtitle outputs are required.")

    return {
        "passed": not blockers,
        "verdict": "production_ready" if not blockers else "not_production_ready",
        "blockers": blockers,
        "technical_qa_is_not_artistic_review": True,
        "human_visual_and_audio_review_required": True,
    }
