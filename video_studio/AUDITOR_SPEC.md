# Multimodal video auditor: requirements and adapter contract

## Goal

Audit the rendered MP4 as evidence, not merely the prompt, storyboard, or script. The
auditor must return a timestamped structured report and must never claim a clean pass
when a required detector did not run successfully.

## Capability groups

- **Visual understanding:** optional local vision-model analysis of sampled objects, environments, faces, actions/gestures over time, and OCR.
- **Audio and speech:** ASR with word/segment timestamps, profanity and sentiment/tone analysis,
  non-speech sound/music classification, and licensed-reference fingerprint matching.
- **Temporal context:** correlate frames, OCR, ASR, scene boundaries, and sound events; a knife
  in a cooking context is not automatically violence.
- **Content safety:** violence/gore, weapons/self-harm, hate/harassment, adult content,
  restricted contraband, unsafe on-screen text.
- **Brand safety:** configured competitor/logo/product references, profanity frequency,
  aggressive tone, controversial topics.
- **Legal:** music/visual reference matching plus license/provenance metadata; required disclosure
  presence and readability; child-directed suitability/privacy review.
- **Technical QA:** silence/dead air, black frames/dropped signals, photosensitivity, AV duration
  parity, and actual speech-to-mouth alignment when a visible speaker exists.

## Adapter contract

A configured detector adapter contributes observations to an evidence bundle:

```json
{
  "video": "video.mp4",
  "duration_seconds": 83.4,
  "coverage": {
    "object_action_detection": "complete",
    "face_scene_analysis": "complete",
    "ocr": "complete",
    "asr_transcription": "complete",
    "text_policy_classification": "complete",
    "audio_event_music_analysis": "complete",
    "temporal_context": "complete",
    "brand_logo_matching": "complete",
    "copyright_reference_matching": "complete",
    "disclosure_ocr_readability": "complete",
    "children_safety_context": "complete",
    "dead_air_black_screen": "complete",
    "photosensitivity": "complete",
    "av_sync": "complete"
  },
  "findings": [
    {
      "start_seconds": 12.1,
      "end_seconds": 14.7,
      "rule": "violence_gore",
      "description": "Temporal action classifier detected a physical altercation.",
      "confidence": 0.94,
      "source": "vision_temporal_v1",
      "evidence": {"frame_times": [12.1, 12.8, 13.5, 14.2]}
    }
  ]
}
```

`coverage` statuses are `complete` only after a detector finishes successfully.
A failed, skipped, or unconfigured required detector leaves the audit INCOMPLETE; it must
not emit the clean-pass phrase. Confidence is a detector score, not a legal or policy verdict.
Adapters must calibrate scores against a labeled evaluation set and preserve supporting evidence.

## Output

Each finding contains exactly these user-facing fields:

- Timestamp: `HH:MM:SS - HH:MM:SS`
- Violation Category
- Rule Broken
- Description
- Confidence Score

The report is JSON for machine integration. With no findings **and complete required coverage**,
the summary must be exactly `AUDIT STATUS: PASSED - No violations detected.`

## Important boundaries

- Competitor detection requires a configurable competitor/brand reference list.
- Copyright checks require reference fingerprints and license/asset-provenance records; similarity
  alone does not establish infringement or authorization.
- Required disclosures must be configured per video/campaign and checked for both presence and
  readable duration/size/contrast.
- Photosensitivity should use a validated flashing/luminance-change detector and an explicit
  threshold policy; do not infer it from generic motion.
- Lip-sync must compare speech/phoneme timing against mouth motion on visible speakers. Audio/video
  duration parity alone is not lip-sync verification.
- Sensitive categories require context-aware review and human escalation for low-confidence,
  ambiguous, or consequential findings.

## Current implementation status

`multimodal_auditor.py` is the dependency-free evidence validation and report layer. It does not
yet ship vision/OCR/ASR/music-fingerprint/lip-sync inference engines. The existing `quality_audit.py`
continues to provide FFmpeg-based technical checks; those checks should be adapted into evidence
events and merged with model-backed findings as detector integrations are added. Do not describe
the system as fully multimodal until these adapters are installed, configured, and tested on a
labeled video evaluation set.
