# Nokia: 15-minute review cut

**This is an unapproved review draft, not a finished or publishable video.** The author has not approved the shortened script or proposed title, and no one has completed the required listening, visual, caption, or factual review.

- [Watch/download the review video](nokia-15-minute-review.mp4) — 15:35.616, 960×540, 12 fps, H.264/AAC. The lower-resolution render is for review.
- [Proposed script](nokia-15-minute-script-draft.md) — 1,688 words selected verbatim from the original narration, in order, across 72 shots and all 13 scenes. It is a proposal, not authorization to omit the other passages.
- [Partial facts ledger](nokia-15-minute-facts-draft.json) — source notes for selected claims and remaining issues; **coverage is not complete**. The replacement title avoids the original unverified $300 billion figure, pending author agreement.
- [Nokia audit](nokia-15-minute-review.audit.json) and [strict technical report](nokia-15-minute-review.qc.json). The audit is **FAILED**, not approved.
- [Shot clock](nokia-15-minute-review-shots.json), [narration timing](nokia-15-minute-review-voice-timing.json), [storyboard](nokia-15-minute-review-storyboard.json), [music plan](nokia-15-minute-review-music-plan.json), and [blank human review](nokia-15-minute-review-human-review.json).

## What the measurements say

The MP4 SHA-256 is `616f17313310a7d74b8e3ca33d73b9c43cc262f5900a554aff9adb18e4bc547f`. The duration falls within the operational 14:00–16:00 target. The clock places one recorded line in every selected shot and leaves 0.95 s after the last recorded line, but that does **not** prove the actual speech is complete, synchronized or naturally finished.

Strict FFmpeg checks detected no black intervals or audio-silence intervals at the configured thresholds. However, the separate held-picture check reported **102 frozen spans**, the longest **24.7 s at 9:03**. Strict technical QA therefore failed. Add relevant visual changes/cutaways, rerender, and audit the new exact file; do not suppress or relabel the warning as a pass.

On the encoded draft, FFmpeg measured **−15.1 LUFS integrated** and **−1.2 dBTP true peak**. The aligned stems measured narration active RMS **−16.97 dBFS**, narration sample peak **−2.23 dBFS**, and music under speech **−29.04 dBFS**. The voice peak is above the recommended −6 to −3 dBFS range and needs adjustment/review. The music is 12.07 dB below active narration on average, but numerical separation cannot establish intelligibility; listen for masking. No effects bus was used, so effect-level checks do not apply to this draft. There are no subtitle streams or sidecar captions in the delivered MP4; a person must still inspect the image and confirm caption status.

The voice is a locally generated Kokoro draft (`bm_george`). The score is a procedural draft, not a reviewed cinematic composition: opening suspenseful (0:00–0:55), rise energetic (0:55–5:42), disruption tense/electronic (5:42–9:46), decline restrained (9:46–14:04), and lesson reflective (14:04–15:35.6). Listen to the whole piece and verify music and voice/model rights before release.

**Before any final approval:** author-approve the script/title; fix the held pictures and narration peak; exhaustively verify all spoken and on-screen claims (including the opening's unqualified “billions”); inspect all scenes and transitions; listen for complete, intelligible speech, music balance and a clean ending; and check captions if any are added. Then rerun strict QA and the hash-bound Nokia audit, and obtain a named human review. Machine measurements do not replace these checks.

## Rebuilding the review cut

From the repository root, with the Node packages, FFmpeg/FFprobe, NumPy, and Kokoro engine/model installed as described in the studio documentation:

```bash
PKG=workspace/nokia-review-rebuild
mkdir -p "$PKG"
node video_studio/films/nokia_empire_review_cut.mjs \
  --lines "$PKG/lines.json" --script "$PKG/script.md"
python video_studio/narrate.py synth --lines "$PKG/lines.json" \
  --out "$PKG/voice" --voice bm_george --rate 0.95 --profile calm
node video_studio/films/nokia_empire_review_cut.mjs \
  --timing "$PKG/voice/timing.json" --starts "$PKG/shots.json"
python video_studio/nokia_music.py --starts "$PKG/shots.json" \
  --plan "$PKG/music-plan.json" --score "$PKG/score-draft.wav"
python video_studio/narrate.py mix --vo "$PKG/voice" --score "$PKG/score-draft.wav" \
  --starts "$PKG/shots.json" --out "$PKG/master.wav" --target-lufs -14 \
  --ceiling-dbfs -1.5 --score-gain 0.36 --duck 0.34 \
  --timing-out "$PKG/voice-timing.json" --stems-dir "$PKG"
set -o pipefail
node video_studio/films/nokia_empire_review_cut.mjs \
  --timing "$PKG/voice/timing.json" --pipe --scale 0.75 --fps 12 \
  | ffmpeg -y -f rawvideo -pixel_format rgba -video_size 960x540 -framerate 12 -i - \
    -an -c:v libx264 -preset veryfast -crf 27 -pix_fmt yuv420p "$PKG/picture.mp4"
ffmpeg -y -i "$PKG/picture.mp4" -i "$PKG/master.wav" -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 96k -movflags +faststart "$PKG/video.mp4"
```

Rebuilds can differ across engine/model and encoder versions, so measure and review the rebuilt output rather than reusing this draft's evidence. The large WAV stems are not checked into Git; their hashes and measurements are recorded in the audit. The QC report's absolute file paths identify the original build workspace, not paths required on another machine. See [the release workflow](nokia-release-audit.md) for the complete package and approval requirements.
