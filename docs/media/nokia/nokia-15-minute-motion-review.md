# Nokia: motion-graphics review revision

**Review draft only — not approved for publication.** The author has not approved the shortened script, and full listening, visual/synchronization, historical and ending reviews remain outstanding.

- [Watch or download the 1080p motion-graphics review](nokia-15-minute-motion-review.mp4)
- [Scene-by-scene visual storyboard and approximate cue times](nokia-15-minute-motion-review-storyboard.json)
- [Technical quality report](nokia-15-minute-motion-review.qc.json) and [Nokia release audit](nokia-15-minute-motion-review.audit.json)
- [Unapproved 72-shot script](nokia-15-minute-script-draft.md), [partial facts ledger](nokia-15-minute-facts-draft.json), and [blank human review](nokia-15-minute-motion-review-human-review.json)
- [Shot clock](nokia-15-minute-review-shots.json), [voice timing](nokia-15-minute-review-voice-timing.json), and [music plan](nokia-15-minute-review-music-plan.json)
- [Motion renderer](../../../video_studio/films/nokia_motion_review.mjs), [visual plan](../../../video_studio/films/nokia_motion_review_plan.json), and [reconstructed phrase timings](../../../video_studio/films/nokia_motion_review_phrase_timing.json)

## What changed

This is a new, frame-by-frame 1920×1080, 30 fps edit: animated vector illustrations, type, diagrams, and charts only. It does not use photos, AI-generated imagery, panning stills, or interpolation of the rejected 12 fps video. Simplified device illustrations are not exact product renders. The edit plans 198 visual beats across the measured 72-shot narration clock. Headings are summaries, **not captions**; there is no subtitle track.

The individual narration clips and five-section procedural score are retained from the previous review. The narration stem was peak-limited without changing its sample count; the music stem was not changed. A 10-second check found the limited and original narration had their highest correlation at zero sample offset. This is not a listening or intelligibility review.

The clock for each recorded narration clip is measured. To make cue placement more useful, the Kokoro phrases were regenerated with the same model settings; all 72 regenerated clip sample counts matched the existing voice files. The positions **within each phrase are still estimates**, not word-level alignment. The edit must be watched and listened to against every line; do not interpret the storyboard as proof of synchronization or visual relevance.

The score follows the requested shape: suspenseful/cinematic opening; inspiring/energetic rise; tense modern-electronic disruption; restrained emotional decline; reflective cinematic lesson. The score is procedural and has not been approved by ear.

## Technical checks and remaining approvals

The exact MP4 is **15:35.633**, 1920×1080 at 30 fps, with 28,069 generated frames and SHA-256 `7d4e12bbe195399576abef1c8af93c8a79337b9f5f54dd933848efe453138ab0`. Strict checks found **zero black intervals** at the 0.20-second threshold and **zero silence intervals** at the 1.50-second threshold; the FFmpeg freeze detector found no events at its threshold. The separate near-static-picture detector nevertheless **failed**: it identified **158 spans longer than 1 second**, the longest **7.2 seconds at 8:52**. It can flag visually active but small-area animation, so inspect the reported spans; do not treat this as a clean technical pass. The Nokia release audit is **FAILED** on strict QA and its human checks remain unverified.

The encoded master measured **−15.2 LUFS integrated** and **−2.1 dBTP**. The aligned limited narration stem measured **−17.01 dBFS active RMS** and **−3.61 dBFS sample peak**; music under narration measured **−29.04 dBFS RMS**. These are measurements, not proof of intelligibility or acceptable music balance. No separate effects bus was used.

Machine checks do not prove factual accuracy, the complete spoken script, meaningful visual timing, perceptual smoothness, absence of music masking, or a natural ending. The partial facts ledger still flags unverified claims, including the opening's unqualified “billions.” The proposed 1,688-word cut omits parts of the original longer script and is **not author-approved**.

Before release, a named reviewer must approve the script/title; verify all dates, figures and claims; watch and listen to every scene and transition; check narration completeness and timing, music balance, caption status and the ending; address any technical-QA failures; and rerun the hash-bound Nokia audit and release gate. Do not copy the old review's attestations onto this file.

## Rebuild notes

Install the studio's Node dependencies, FFmpeg/FFprobe, Python/NumPy and Kokoro model as described in the [previous review's rebuild section](nokia-15-minute-review.md). Recreate its aligned voice and music stems using the `--score-gain 0.36 --duck 0.34` mix command there. The committed phrase timing data is an aid to the original review voice, not a generic forced aligner. The command below works only when the rebuilt clips match the committed narration clock; if their lengths change, the renderer's shot/voice inputs and cue timings must be regenerated together and the edit reaudited.

With the prior balanced stems in `workspace/nokia-review-cut/balanced/`:

```bash
P=workspace/nokia-motion-rebuild
mkdir -p "$P"
# If the narration was regenerated, recover phrase timing from the new clips:
python video_studio/nokia_phrase_timing.py \
  --timing docs/media/nokia/nokia-15-minute-review-voice-timing.json \
  --voice-dir workspace/nokia-review-cut/voice \
  --out video_studio/films/nokia_motion_review_phrase_timing.json
ffmpeg -y -i workspace/nokia-review-cut/balanced/voice-stem.wav \
  -af 'alimiter=limit=0.66:attack=5:release=100:level=false:latency=true' \
  -ac 1 -c:a pcm_s16le "$P/voice-stem.wav"
ffmpeg -y -i "$P/voice-stem.wav" -i workspace/nokia-review-cut/balanced/music-stem.wav \
  -filter_complex '[0:a][1:a]amix=inputs=2:duration=longest:normalize=0,pan=stereo|c0=c0|c1=c0[m]' \
  -map '[m]' -c:a pcm_s16le "$P/master.wav"
node video_studio/films/nokia_motion_review.mjs --validate
node video_studio/films/nokia_motion_review.mjs --storyboard "$P/storyboard.json"
set -o pipefail
node video_studio/films/nokia_motion_review.mjs --pipe --fps 30 --from 0 --to 28069 \
  | ffmpeg -y -f rawvideo -pixel_format rgba -video_size 1920x1080 -framerate 30 -i - \
    -i "$P/master.wav" -map 0:v:0 -map 1:a:0 -frames:v 28069 \
    -c:v libx264 -preset veryfast -crf 21 -threads 2 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -movflags +faststart "$P/video.mp4"
```

The source WAVs are large local intermediates, not checked into Git. New builds can differ across model/encoder versions and need fresh QA, facts evidence and human review. See [the release workflow](nokia-release-audit.md).
