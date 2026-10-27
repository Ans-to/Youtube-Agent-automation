# Nokia: motion-graphics review revision

**Rejected review draft — not approved for publication.** The user identified semantic mismatch between narration and visuals and rejected the redesigned look as a departure from the earlier Nokia motion-graphics format. Do not use this video as the visual reference for the next cut. The shortened script and all final reviews remain unapproved.

- [Watch or download the 1080p motion-graphics review](nokia-15-minute-motion-review.mp4)
- [Scene-by-scene visual storyboard and approximate cue times](nokia-15-minute-motion-review-storyboard.json)
- [Technical quality report](nokia-15-minute-motion-review.qc.json) and [Nokia release audit](nokia-15-minute-motion-review.audit.json)
- [Unapproved 72-shot script](nokia-15-minute-script-draft.md), [partial facts ledger](nokia-15-minute-facts-draft.json), and [blank human review](nokia-15-minute-motion-review-human-review.json)
- [Shot clock](nokia-15-minute-review-shots.json), [voice timing](nokia-15-minute-review-voice-timing.json), and [music plan](nokia-15-minute-review-music-plan.json)
- [Motion renderer](../../../video_studio/films/nokia_motion_review.mjs), [visual plan](../../../video_studio/films/nokia_motion_review_plan.json), and [reconstructed phrase timings](../../../video_studio/films/nokia_motion_review_phrase_timing.json)

## What changed

This is a new, frame-by-frame 1920×1080, 30 fps edit: animated vector illustrations, type, diagrams, and charts only. It does not use photos, AI-generated imagery, panning stills, or interpolation of the rejected 12 fps video. Simplified device illustrations are not exact product renders. The edit plans 198 visual beats across the measured 72-shot narration clock. Headings are summaries, **not captions**; there is no subtitle track.

The individual narration clips and five-section procedural score are retained from the previous review. **A later source audit found that the old phrase splitter removed the decimal points from “5.44” and “7.2” before synthesis.** The affected narration was therefore not generated from the figures as written, and must be re-recorded, retimed, remixed and checked by ear; the code fix does not repair this MP4. The narration stem was peak-limited without changing its sample count; the music stem was not changed. A 10-second check found the limited and original narration had their highest correlation at zero sample offset. This is not a listening or intelligibility review.

The clock for each recorded narration clip is measured. To make cue placement more useful, the Kokoro phrases were regenerated with the same model settings; all 72 regenerated clip sample counts matched the existing voice files. The positions **within each phrase are still estimates**, not word-level alignment. The edit must be watched and listened to against every line; do not interpret the storyboard as proof of synchronization or visual relevance.

The score follows the requested shape: suspenseful/cinematic opening; inspiring/energetic rise; tense modern-electronic disruption; restrained emotional decline; reflective cinematic lesson. The score is procedural and has not been approved by ear.

## Technical checks and remaining approvals

The exact MP4 is **15:35.633**, 1920×1080 at 30 fps, with 28,069 generated frames and SHA-256 `7d4e12bbe195399576abef1c8af93c8a79337b9f5f54dd933848efe453138ab0`. Strict checks found **zero black intervals** at the 0.20-second threshold and **zero silence intervals** at the 1.50-second threshold; the FFmpeg freeze detector found no events at its threshold. The separate near-static-picture detector nevertheless **failed**: it identified **158 spans longer than 1 second**, the longest **7.2 seconds at 8:52**. It can flag visually active but small-area animation, so inspect the reported spans; do not treat this as a clean technical pass. The Nokia release audit is **FAILED** on strict QA and its human checks remain unverified.

The encoded master measured **−15.2 LUFS integrated** and **−2.1 dBTP**. The aligned limited narration stem measured **−17.01 dBFS active RMS** and **−3.61 dBFS sample peak**; music under narration measured **−29.04 dBFS RMS**. These are measurements, not proof of intelligibility or acceptable music balance. No separate effects bus was used.

Machine checks do not prove factual accuracy, the complete spoken script, meaningful visual timing, perceptual smoothness, absence of music masking, or a natural ending. The partial facts ledger still flags unverified claims, including the opening's unqualified “billions.” The proposed 1,688-word cut omits parts of the original longer script and is **not author-approved**.

Before release, a named reviewer must approve the script/title; verify all dates, figures and claims; watch and listen to every scene and transition; check narration completeness and timing, music balance, caption status and the ending; address any technical-QA failures; and rerun the hash-bound Nokia audit and release gate. Do not copy the old review's attestations onto this file.

## Rebuild notes

The old render and its phrase-timing JSON are archival evidence, not an
approved build recipe. A [draft replacement for the financial line](audio-repair-draft/README.md)
was synthesized with both decimal points retained; the model's phoneme
sequence contains “point” for each amount, but it still needs listening review.
A scratch 72-shot clock and five-section mix were rebuilt from the changed
voice duration, and phrase resynthesis matched all 72 sample counts. Those
results are not the existing MP4, do not verify word-level synchronization,
and are not final-release evidence.

Do not overwrite the archival phrase data and do not reuse the old hard-coded
frame count or timings with the changed audio. A complete new picture must use
the new clock, match each spoken idea in the original house format, and pass
fresh technical, factual and human review. Re-synthesizing the complete script
and constructing a new package is described in [the release workflow](nokia-release-audit.md).
