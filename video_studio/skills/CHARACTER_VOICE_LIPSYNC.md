# Character Animation, Voice and Lip-Sync Plan

## Current honest baseline

The current Canvas2D renderer is a deterministic motion-graphics renderer. It does **not** currently provide a production-quality skeletal character rig, body mechanics, face rig, phoneme-level lip sync, or a verified natural male voice. Piper can generate speech, but voice quality depends on the exact installed model and language support. A valid audio stream is not proof of human-like narration. Do not claim these capabilities until an end-to-end sample passes review.

## Choose the right character pipeline

Do not attempt to make a fully articulated, fluid anime character by drawing isolated geometric parts in Canvas2D. Use a separate character pipeline and composite its output into the main edit.

### Tier A — lightweight, dependable presenter (recommended first milestone)
- Use a properly licensed, layered 2D character with separate head, torso, upper/lower arms, hands, pelvis, thighs, shins, feet, eyes, brows, and mouth shapes.
- Rig with a 2D skeletal/deformation system (e.g. Blender Grease Pencil/2D rig or a compatible open-source 2D rigging tool) and use keyframed pose-to-pose animation with arcs, anticipation, overlap and follow-through.
- Build reusable idle, turn, point, walk-in, reaction and emphasis cycles. Use motion retargeting where licenses permit.
- For speech, use a viseme timeline generated from phoneme alignment (phoneme/viseme sequence + timestamps), not random mouth toggles. Support closed lips for M/B/P, teeth/lip contact for F/V, open vowels, rounded vowels, and rest/neutral. Blend adjacent visemes and keep jaw movement continuous.
- Add blinking, eye saccades, head nods and small torso shifts at phrase-level beats. Keep these secondary motions restrained and not synchronized identically on every line.
- Render character to transparent RGBA frames/video, then composite with graphics and captions in FFmpeg.

### Tier B — single-image talking avatar
Use a maintained audio-driven talking-head model only when a still portrait is acceptable. Evaluate SadTalker, Wav2Lip/MuseTalk-like methods against identity preservation, mouth artifacts, head motion, temporal stability and synchronization. Wav2Lip-like mouth replacement can improve lip timing but often leaves the head rigid and can blur the mouth; head-animation models can add motion but may introduce identity drift or artifacts. These approaches are not substitutes for full-body character animation.
- Require compatible model weights, license review, and a real benchmark on the target machine before integration.
- Treat GPU as optional/unknown; CPU inference may be slow. Never make the entire pipeline depend on a large model that cannot run within available RAM/storage.
- Use a real speech clip as input and inspect the output at 1x speed; static images and audio-only tests cannot prove lip-sync quality.

### Tier C — full-body anime performance
This requires an actual 2D/3D rig, animation curves or motion capture/retargeting, facial controls, camera blocking, lighting, and compositing. It is a separate renderer and asset pipeline—not a prompt-only upgrade to the current Canvas2D renderer. Begin with a 5–10 second shot containing one walk/gesture and one spoken line before attempting a full episode.

## Voice requirements

Required language: English only, for every narration line and every subtitle. Target a clear conversational English voice with intelligible consonants, controlled pace, natural pauses, and non-monotone prosody. A model's language metadata is a minimum gate, not proof of naturalness.

1. Use a licensed English voice model whose adjacent config explicitly identifies an English language code. Reject non-English model configs and non-Latin-script narration before synthesis.
2. Produce scene/phrase-level clips, normalize loudness consistently, preserve natural pauses, and never speed speech up merely to fit arbitrary scene durations.
3. Fit visuals and subtitle timings to measured speech duration. Never trim the last phoneme to meet a fixed runtime; extend the scene or re-time visuals.
4. If a neural TTS model is unavailable or quality fails, fail the release gate and request a human-approved English voice asset. Do not silently fall back to eSpeak or call synthetic test speech “natural.”
5. Run audio checks: clipping/true peak, loudness, silence gaps, speech presence, and phrase duration. Automated checks can detect defects but cannot certify that a voice sounds human.
6. Human listen-test on phone speakers and headphones. Review English pronunciation, technical terms, breath timing, sibilants, pacing, and emotional emphasis.
7. Emit both SRT and WebVTT subtitles for every render. Keep burned-in captions identical to the spoken English narration; validate cue ordering and durations. Scene-level timing is not forced word alignment.

## Synchronization and acceptance tests

- Generate forced phoneme/word timestamps for the final audio and align captions/visemes to those timestamps.
- Compare video-mouth motion to speech at 1x speed and frame-by-frame around plosives and vowels.
- Use an objective audio-visual synchronization metric (e.g. SyncNet-derived score where a compatible model is licensed and available), but do not trust one metric alone.
- Check identity consistency, facial texture stability, no mouth/teeth warping, no jitter, no frozen head, no repeating blink pattern, and no body-part popping.
- A release sample must include a continuous 5–10 second speaking shot plus a gesture; require a human reviewer to accept it before scaling up.

## Research sources

- SadTalker (CVPR 2023), “Learning Realistic 3D Motion Coefficients for Stylized Audio-Driven Single Image Talking Face Animation”: https://arxiv.org/abs/2211.12194
- 2025 review, “Advancements in talking head generation: a comprehensive review of techniques, metrics, and challenges”: https://doi.org/10.1007/s00371-025-04232-w
- Scientific Reports (2025), “Audio-driven single image talking face animation with transformers”: https://www.nature.com/articles/s41598-025-33928-1
- Spatially and Temporally Optimized Audio-Driven Talking Face Generation (Computer Graphics Forum, 2024): https://doi.org/10.1111/cgf.15228
- Wav2Lip-HR (2024), high-resolution audio-driven talking head generation: https://doi.org/10.1002/cav.2226

## Integration acceptance gate

Do not mark character animation complete until the repository can produce, in one reproducible command:
1. source script and approved audio;
2. aligned phoneme/viseme timing;
3. character render with body/face motion;
4. composited 16:9 and 9:16 outputs;
5. machine QA report and human review report;
6. output hashes proving the reviewed files are the exact release candidates.
