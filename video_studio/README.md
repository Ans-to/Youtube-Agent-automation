# Offline Agent HQ — deterministic video studio

This module renders MP4s from JSON storyboards using Canvas2D in headless Chromium and FFmpeg. The production language profile is configurable and defaults to **Pakistani Urdu narration written in Urdu/Arabic script, preserving common English technical terms** (ur-en). English narration is supported only when explicitly requested. SRT/WebVTT subtitle text follows the narration profile. The YouTube uploader is separate and approval-gated.

## Requirements

- Python 3.10 or newer
- Node.js LTS
- FFmpeg and ffprobe on PATH
- A Windows PC is recommended; PNG-frame rendering is CPU- and storage-intensive.
- For English voice: Piper CLI plus a verified English model and matching .onnx.json config.
- For Urdu-English voice: the repository includes a KaniTTS adapter and pins the Urdu fine-tuned model revision. Choose the optional CPU-only Urdu voice dependency setup in START_HERE.bat; the model and codec weights are downloaded on first render (roughly 1.5 GB per upstream setup guidance), not committed to Git.
- The model card labels the fine-tuned model Apache-2.0, but the upstream/base model and dependencies must also be reviewed before commercial redistribution or use. A technically generated WAV is not proof of natural pronunciation. Missing dependencies, invalid audio, or silence block the render; English Piper is never substituted.
- Rendering writes matching SRT/WebVTT sidecars and uses script-aware RTL layout for Urdu captions. This does not guarantee natural pronunciation, voice quality, or phoneme-accurate lip-sync.
- Optional YouTube upload: Google OAuth desktop client JSON and the dependencies in requirements-publish.txt.

## Windows setup
Open PowerShell in this directory and run this explicitly English, silent renderer smoke demo:

    npm install
    python studio.py --storyboard storyboard.example.json --output outputs\offline-agent-hq-demo.mp4 --language en

Puppeteer downloads a compatible Chromium build during npm install. If your network blocks this, install a supported Chrome/Chromium build and configure Puppeteer to use it.

## Narration languages and local voice backends

The default production profile is ur-en: conversational Pakistani Urdu in Urdu/Arabic script, retaining familiar English technical terms such as API names, product names, and code identifiers. Use --language en only when English narration is explicitly requested (the CI smoke-test fixture does this). The language profile is stored in the storyboard and package status, and subtitle validation checks that the track contains Urdu-script text rather than merely labelling English as Urdu.

English voice setup:

1. Install Piper in the selected Python environment: python -m pip install piper-tts.
2. Download an English voice model and matching .onnx.json config. Review the exact model's license and model card before use.
3. Set PIPER_MODEL to the absolute path to the .onnx file. Its adjacent config must identify a language code starting with en.

PowerShell example for an explicitly English render:

    $env:PIPER_MODEL = "C:\path\to\en_US-lessac-medium.onnx"
    python video_studio/production.py --topic "How AI agents work" --format shorts --language en --render

Urdu-English voice setup:

The bundled KaniTTS adapter is selected automatically when video_studio.urdu_tts_command is left as an empty array in config.json; this is the default in config.example.json. Run START_HERE.bat and approve the optional CPU-only Urdu TTS dependency install. The adapter loads the pinned KaniTTS Urdu snapshot once per video and synthesizes scenes sequentially to limit memory use. The first render needs internet access and enough disk space for the Urdu model and codec caches (roughly 1.5 GB per upstream setup guidance). CPU generation can be slow on an 8 GB machine.

**Human voice approval is required before any Urdu-English production render.** The default configuration sets `video_studio.urdu_voice_human_approved` to `false`. First generate/listen to a real sample using your local setup; check that it is intelligible Pakistani Urdu, preserves English technical terms, and uses the required adult-male voice. Only after that review set `"urdu_voice_human_approved": true` in your local `config.json`. This is a user attestation, not an automated quality measurement. If the current model or speaker prefix is unsuitable, leave it false and do not release the video. Never commit the local config or tokens.

A custom adapter may be configured in config.json (never commit this file). Its command is an argument array, not a shell string, and must contain either {manifest_file} for a batch adapter or both {text_file} and {output_file} for a per-scene adapter. For example:

    {
      "video_studio": {
        "narration_language": "ur-en",
        "urdu_tts_command": ["python", "path/to/your_adapter.py", "--input", "{text_file}", "--output", "{output_file}"]
      }
    }

The custom adapter path above is a contract example, not the default engine. The bundled adapter follows the upstream Kani inference path: a causal model generates speech-code tokens, then NeMo NanoCodec decodes them to audio. The fine-tuned Urdu model card labels the model Apache-2.0; review the base-model, NVIDIA codec, and dependency licenses before commercial use. Final rendering is blocked when the backend fails or produces invalid/silent WAV output. Human listening review remains mandatory; this integration does **not** prove production-quality Urdu narration.

Speaker identity is deliberately not inferred. The default Kani adapter does not force an unverified speaker label. You may set `video_studio.kani_speaker_prefix` in your local config only to a prefix documented or tested for this exact fine-tuned model; that value is passed to the bundled adapter as a text prefix. No adult-male speaker prefix is currently verified by this repository. Human-listen-test the actual rendered sample before treating the adult-male voice requirement as met.

Subtitles are derived from narration text and timed within measured scene durations. The current subtitle timing is scene/phrase-level rather than forced word alignment. RTL layout improves Urdu text presentation but does not prove accurate punctuation, pronunciation, or natural voice quality.

## Device-aware rendering

Inspect the machine profile before a render:

    python video_studio/studio.py --print-capabilities
    python video_studio/capabilities.py --json

The profiler uses only Python's standard library and supported OS probes. It reports RAM, CPU count, free disk space, GPU detection, a conservative encoder thread count, and a single-heavy-job policy. Every render writes a `.capabilities.json` sidecar next to the output. The profile never silently lowers requested resolution or frame rate; low-memory rendering can be slower and may still fail if the requested project exceeds available resources. The renderer also takes a cross-process lock before touching shared frame, manifest, or voice-intermediate paths; simultaneous render requests wait instead of corrupting one another.

## Generate a topic package

From the repository root:

    python video_studio/production.py --topic "How AI agents work" --format long
    python video_studio/production.py --topic "How AI agents work" --format shorts

The language profile is read from config.json (video_studio.narration_language); the default channel profile is ur-en. Set --language en for an explicitly English package. With no enabled local language model, the builder refuses to present the generic offline scaffold as researched Urdu-English content. If Urdu-English mode is chosen, final rendering also requires the configured compatible local voice adapter. For an English final render, provide a verified English Piper model and use:

    python video_studio/production.py --topic "How AI agents work" --format shorts --language en --render

The builder uses separate model calls for outline and scene generation, verifies minimum narration length, and writes script.md, storyboard.json, and package-status.json. The output remains a draft until claims are checked and human review is recorded. A CI template render is only a pipeline smoke test; it does not demonstrate real-model content generation or Urdu TTS.

## Research-first source discovery

Every non-template package runs web research by default: up to five complementary public search queries, up to eight search results per query, and up to eight bounded public-page fetches, without an API key. Use `--research` to force research even for the deterministic offline template demo:

    python video_studio/production.py --topic "How AI agents work" --format long --research

The package includes `research.md` and `research.json`. The collector extracts a bounded amount of readable content, validates public IP addresses and redirect targets, and records fetch failures. If research fails for a non-template package, package generation stops instead of silently falling back to an unresearched script. Search snippets and extracted page text are **not automatic verification**: check publication dates, prefer primary sources, corroborate important claims, and confirm that sources actually support the statements before publishing. Common secrets and direct identifiers are redacted from search queries. The collector does not guarantee that the search provider or target websites will always be available. You may also provide curated local notes using `--source-file workspace/source-notes.md`.

## Explicit release approval and YouTube upload
Review the script, storyboard, and rendered video. The production pipeline automatically runs strict technical QA after rendering and writes `video.qc.json`. If you rendered the MP4 outside the production pipeline, create that report manually, then request human approval from the repository root:

    python video_studio/quality_audit.py workspace/generated/video.mp4 --strict --report workspace/generated/video.qc.json
    python video_studio/release_gate.py --package workspace/generated

Approval is blocked unless the strict audit passes with no warnings, confirms an audio stream and positive duration, and its SHA-256 matches the exact MP4. Type the exact confirmation displayed by the program to review the title, description, tags, visibility, and made-for-kids setting. The approval record binds the video, script, storyboard, metadata, and QA report hashes; it does not publish anything.

For optional YouTube upload, create a Google OAuth desktop client in Google Cloud Console, save its JSON locally as client_secret.json, and install:

    pip install -r video_studio/requirements-publish.txt

Example private upload, only after local approval:

    python video_studio/publish_youtube.py --video workspace/generated/video.mp4 --approval workspace/generated/release-approval.json --title "Video title" --description "Video description" --privacy private --made-for-kids no --confirm-publish

Public uploads require the additional --confirm-public flag. The uploader revalidates the strict QA report and its hash, the approved video/script/storyboard hashes, and exact metadata before upload. It uses user OAuth rather than an API key and defaults to private visibility. OAuth setup, account consent, YouTube API access, and upload processing cannot be completed by repository code alone. Never commit client_secret.json or youtube-token.json.

## Customize
Copy storyboard.example.json and change title, canvas size, fps, scenes, durations, headline, subhead, and narration. Width must be 320–3840, height 180–2160, fps 1–60, and each scene duration must be positive and no more than 600 seconds.

The renderer writes frames under `video_studio/frames/` and a render manifest beside the renderer. It validates field-specific array sizes to prevent silent truncation (4 diagram nodes, 4 timeline events, 3 comparison bullets per side, 6 code lines, and 2–6 chart values/labels). PNG frames are deleted after a successful MP4 render to conserve storage; pass `--keep-frames` to retain them. It sizes the Canvas2D drawing buffer to the requested storyboard dimensions, including 1080×1920 Shorts. Rendering is capped at 1000 seconds and 30000 frames to limit storage use. `ffprobe` is required and validates H.264, duration, exact dimensions, frame rate, and requested audio presence.

## Current limits
This is a deterministic starter renderer, not a professional editor or anime rig system. It draws typography, grids, progress bars, geometric accents, and a procedural 2D presenter. Eased fade, wipe, slide, and zoom transitions are supported. Advanced skeletal character rigs, forced phoneme alignment, independent claim-by-claim fact verification, and automatic YouTube publishing remain outside the current implementation. Publishing is approval-gated; the code cannot promise monetization or income.

## Professional motion-design and character roadmap

The agent's creative/QA contract is in:
- [Professional Motion Design Director](skills/PRO_MOTION_DIRECTOR.md): transition selection, easing, staging, typography, audio-led pacing, review rubric, and render QA.
- [Character, Voice and Lip-Sync](skills/CHARACTER_VOICE_LIPSYNC.md): a realistic implementation path for a rigged presenter, audio-aligned lip sync, selected-language narration, and acceptance tests.

**Important status distinction:** the renderer now includes a more detailed procedural presenter (hands/fingers, clothing details, gaze, brows, expressions, blinking, and secondary head motion), but it is not a production-quality skeletal or anime rig. Piper output is not automatically natural-sounding. Direct `studio.py` renders can be silent when used for visual smoke tests; the `production.py` final-render path requires a verified English Piper model and generates SRT/WebVTT subtitles.

Recommended implementation order:
1. Improve scene-pair-aware transition planning and continuity; the renderer now supports eased fade, directional wipe, slide-left/right, and zoom, with boundary-frame regression tests.
2. Add voice-model selection and audio QA. Reject missing, test-only, or clipped speech; align scene duration to speech rather than trimming speech to scene duration.
3. Add a separate licensed 2D skeletal character pipeline, phrase-level facial motion and phoneme/viseme timing; composite transparent character renders into the existing edit.
4. Integrate a fail-closed multimodal reviewer, objective frame/audio checks, timestamped defects, and exact-output hashes.
5. Keep the topic-to-video package builder in CI: script, storyboard, the explicitly selected language's TTS, SRT/WebVTT, MP4 validation, and strict technical QC must all pass before accepting a change. English-only CI smoke renders do not certify Urdu voice output.

Research references and evaluation criteria are documented in the two skill files. A prompt alone cannot train a model to professional skill; the workflow needs suitable models/assets, repeated renders, measured defects, and regression tests.

## Motion/character acceptance prototype status

The renderer has an optional procedural 2D presenter layer (`scene.character`) with breathing/bob, arm gesture, separate hand/finger shapes, collar/seam/pocket/button details, hair highlights, gaze saccades, expression-aware brows, blinking, subtle head nod, and selectable mouth shapes. Storyboards may provide normalized `x`/`y`, `scale`, `walking`, colour fields, and `visemes: [{t, shape}]`. These viseme cues are normalized scene-time cues, **not** forced alignment to speech. This is a lightweight stylized presenter, not a production-quality anime rig or a full skeletal deformation system.

Scene transitions composite previous and incoming frames with eased fade, directional wipe, slide-left/right, and zoom transitions. Transition frames are bounded to the scene length and configured frame limit. Choose a transition for editorial meaning; use `none` for a deliberate hard cut.

Landscape and vertical regression storyboards are provided at `storyboard.motion-character-demo.json` and `storyboard.motion-character-demo-shorts.json`. Existing renderer smoke fixtures use English TTS where configured; these are technical tests, not proof of natural Urdu voice quality.

    npm install
    python studio.py --storyboard storyboard.motion-character-demo.json --output outputs/motion-character-demo.mp4 --language en

This command can produce English narration plus SRT/WebVTT subtitles when run with `--with-voice` and a valid English Piper model. It is not a natural-voice acceptance test. Phoneme-aligned lip-sync, production-quality character acting, and a true multimodal artistic reviewer remain release blockers; do not describe the procedural presenter as fully lip-synced or the demo as production-ready.
