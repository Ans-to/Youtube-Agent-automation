# Offline Agent HQ — deterministic video studio

This module renders local MP4s from JSON storyboards using deterministic Canvas2D in headless Chromium and FFmpeg. Final production renders use an English Piper voice and always emit English subtitles in SRT and WebVTT; captions are also drawn into the frames. The YouTube uploader is separate and approval-gated.

## Requirements
- Python 3.10 or newer
- Node.js LTS
- FFmpeg and ffprobe available on PATH
- A Windows PC is recommended; PNG-frame rendering is CPU- and storage-intensive.
- Required for final production renders: Piper CLI plus a verified English voice model and matching `.onnx.json` config. Silent rendering is for visual smoke tests only.\n- Every render requires English narration text and emits validated `.srt` and `.vtt` subtitle sidecars.
- Optional YouTube upload: Google OAuth desktop client JSON and the dependencies in requirements-publish.txt.

## Windows setup
Open PowerShell in this directory and run:

    npm install
    python studio.py --storyboard storyboard.example.json --output outputs\offline-agent-hq-demo.mp4

Puppeteer downloads a compatible Chromium build during npm install. If your network blocks this, install a supported Chrome/Chromium build and configure Puppeteer to use it.

## English narration and subtitles (local, no paid API)

Final production renders must use English narration. The CI pipeline downloads the MIT-licensed Piper `en_US-lessac-medium` model from a pinned Hugging Face revision and verifies its SHA-256 before synthesis. Voice models and config files are not committed to the repository.

1. Install Piper TTS in the active Python environment: `python -m pip install piper-tts`.
2. Download an English voice model and its matching `.onnx.json` config. Review the voice model card and license before redistribution.
3. Set `PIPER_MODEL` to the absolute path to the English `.onnx` file. The adjacent config must identify a language code beginning with `en`.

PowerShell example:

    $env:PIPER_MODEL = "C:\\path\\to\\en_US-lessac-medium.onnx"
    python studio.py --storyboard storyboard.motion-character-demo.json --output outputs\\english-demo.mp4 --with-voice
    python validate_render.py outputs\\english-demo.mp4 --require-audio

Every render also writes matching `.srt` and `.vtt` subtitle files. Subtitle text is derived from the English narration, timed across each scene's measured speech duration, and checked for valid, ordered cues. This is scene/phrase-level timing, not forced word alignment. The validator checks audio presence, signal level, clipping, dimensions, frame rate, and duration; it cannot certify naturalness, pronunciation, factual correctness, or lip-sync. Human listening and visual review remain required.
## Generate a topic package
From the repository root, run:

    python video_studio/production.py --topic "How AI agents work" --format long
    python video_studio/production.py --topic "How AI agents work" --format shorts
    python video_studio/production.py --topic "How AI agents work" --format long --render

With no enabled local model, this creates a clearly marked 20-second template, not a researched script. Rendering that demo requires the explicit `--render-template` flag. If a compatible OpenAI-style local inference server is enabled in config.json, the builder creates a structured outline and then generates each scene in a separate local-model request to support 15-minute long-form scripts. It checks scene count and minimum narration length before packaging. The model output is still a draft and does not independently verify factual claims.

Scene narration captions are paginated into readable two-line cards, while SRT and WebVTT sidecars are generated for every render. Narration is English-only. The production command refuses final rendering unless an English Piper model is configured; it automatically enables voice synthesis and creates subtitle sidecars. Use --format shorts for a 1080×1920 vertical storyboard or --format long for 1920×1080 landscape. Review script.md, storyboard.json, video.mp4, video.srt, and video.vtt manually.



## Free source discovery (optional)

Add `--research` to collect public DuckDuckGo search-result titles, links, snippets, and bounded extracted text from public webpages without an API key:

    python video_studio/production.py --topic "How AI agents work" --format long --research

The package includes `research.md` and `research.json`. The collector attempts to fetch up to the requested number of public text pages, extracts a bounded amount of readable content, validates public IP addresses and redirect targets, and records fetch failures. Search snippets and extracted page text are **not automatic verification**: check publication dates, prefer primary sources, corroborate important claims, and confirm that sources actually support the statements before publishing. Common secrets and direct identifiers are redacted from search queries. The collector does not guarantee that the search provider or target websites will always be available. You may also provide curated local notes using `--source-file workspace/source-notes.md`.

## Explicit release approval and YouTube upload
Review the script, storyboard, and rendered video. From the repository root:

    python video_studio/release_gate.py --package workspace/generated

Type the exact confirmation displayed by the program. This asks you to review the exact title, description, tags, visibility, and made-for-kids setting, then creates a local approval record bound to both those metadata and the video SHA-256. It does not publish anything. The uploader refuses any metadata that differs from the approved record.

For optional YouTube upload, create a Google OAuth desktop client in Google Cloud Console, save its JSON locally as client_secret.json, and install:

    pip install -r video_studio/requirements-publish.txt

Example private upload, only after local approval:

    python video_studio/publish_youtube.py --video workspace/generated/video.mp4 --approval workspace/generated/release-approval.json --title "Video title" --description "Video description" --privacy private --made-for-kids no --confirm-publish

Public uploads require the additional --confirm-public flag. The uploader verifies the approval record and video hash, uses user OAuth rather than an API key, and defaults to private visibility. OAuth setup, account consent, YouTube API access, and upload processing cannot be completed by repository code alone. Never commit client_secret.json or youtube-token.json.

## Customize
Copy storyboard.example.json and change title, canvas size, fps, scenes, durations, headline, subhead, and narration. Width must be 320–3840, height 180–2160, fps 1–60, and each scene duration must be positive and no more than 600 seconds.

The renderer writes frames under `video_studio/frames/` and a render manifest beside the renderer. It validates field-specific array sizes to prevent silent truncation (4 diagram nodes, 4 timeline events, 3 comparison bullets per side, 6 code lines, and 2–6 chart values/labels). PNG frames are deleted after a successful MP4 render to conserve storage; pass `--keep-frames` to retain them. It sizes the Canvas2D drawing buffer to the requested storyboard dimensions, including 1080×1920 Shorts. Rendering is capped at 1000 seconds and 30000 frames to limit storage use. `ffprobe` is required and validates H.264, duration, exact dimensions, frame rate, and requested audio presence.

## Current limits
This is a starter renderer, not a professional editor or anime rig system. It currently draws typography, a grid, progress bars, and geometric accents. Advanced character rigs, scene transitions, source-grounded web research, automatically timed captions, and a full long-form research pipeline are not implemented. Uploading is optional and approval-gated; the code cannot promise monetization or income.

## Professional motion-design and character roadmap

The agent's creative/QA contract is in:
- [Professional Motion Design Director](skills/PRO_MOTION_DIRECTOR.md): transition selection, easing, staging, typography, audio-led pacing, review rubric, and render QA.
- [Character, Voice and Lip-Sync](skills/CHARACTER_VOICE_LIPSYNC.md): a realistic implementation path for a rigged presenter, viseme-aligned lip sync, natural male narration, and acceptance tests.

**Important status distinction:** these files establish requirements and a technical plan; they do not mean the current renderer has been upgraded to meet them. The current Canvas2D engine does not yet render a production-quality full-body character, and Piper output is not automatically natural-sounding. The existing README's setup command may produce a silent video unless `--with-voice` is explicitly used with a valid Piper installation and model.

Recommended implementation order:
1. Replace fixed, uniform transition behavior with a scene-pair-aware transition planner and continuous easing; render and inspect boundary samples.
2. Add voice-model selection and audio QA. Reject missing, test-only, or clipped speech; align scene duration to speech rather than trimming speech to scene duration.
3. Add a separate licensed 2D skeletal character pipeline, phrase-level facial motion and phoneme/viseme timing; composite transparent character renders into the existing edit.
4. Integrate a fail-closed multimodal reviewer, objective frame/audio checks, timestamped defects, and exact-output hashes.
5. Run a fresh end-to-end 5–10 second character-and-speech sample before attempting a long-form render.

Research references and evaluation criteria are documented in the two skill files. A prompt alone cannot train a model to professional skill; the workflow needs suitable models/assets, repeated renders, measured defects, and regression tests.

## Motion/character acceptance prototype status

The renderer now has an optional procedural 2D presenter layer (`scene.character`) with breathing/bob, arm gesture, blinking, simple body movement, and selectable mouth shapes. Storyboards may provide normalized `x`/`y`, `scale`, `walking`, colour fields, and `visemes: [{t, shape}]`. These viseme cues are normalized scene-time cues, **not** forced alignment to speech. This is a lightweight stylized presenter, not a production-quality anime rig or a full skeletal deformation system.

Scene transitions composite previous and incoming frames with eased fade, directional wipe, slide-left/right, and zoom transitions. Transition frames are bounded to the scene length and configured frame limit. Choose a transition for editorial meaning; use `none` for a deliberate hard cut.

A short regression storyboard is provided at `storyboard.motion-character-demo.json`. Render it with:

    npm install
    python studio.py --storyboard storyboard.motion-character-demo.json --output outputs/motion-character-demo.mp4

This command produces English narration plus SRT/WebVTT subtitles when run with `--with-voice` and a valid English Piper model. It is not a natural-voice acceptance test. Phoneme-aligned lip-sync, production-quality character acting, and a true multimodal artistic reviewer remain release blockers; do not describe the procedural presenter as fully lip-synced or the demo as production-ready.
