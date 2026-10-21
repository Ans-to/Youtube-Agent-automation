# Offline Agent HQ — deterministic video studio

This module renders MP4s from JSON storyboards using Canvas2D in headless Chromium and FFmpeg. The production language profile is configurable and defaults to **Pakistani Urdu narration written in Urdu/Arabic script, preserving common English technical terms** (ur-en). English narration is supported only when explicitly requested. SRT/WebVTT subtitle text follows the narration profile. The YouTube uploader is separate and approval-gated.

## Requirements

- Python 3.10 or newer
- Node.js LTS
- FFmpeg and ffprobe on PATH
- A Windows PC is recommended; PNG-frame rendering is CPU- and storage-intensive.
- For English voice: Piper CLI plus a verified English model and matching .onnx.json config.
- For Urdu-English voice on Windows/CPU: the default is Piper TTS with the pinned Pakistani Urdu voice **Fasih v2** (medium, single-speaker). Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1` to install Piper/ONNX Runtime into isolated `.venv-piper-urdu`. The approximately 65 MB voice model is downloaded and checked against its published size and MD5. Its v2 sidecar is derived locally from a separately checksum-verified v1 sidecar plus the published v2 phoneme-map additions.
- The Piper software is GPL-3.0-or-later and the pinned voice repository is MIT-licensed; review both separately before redistributing the software or voice assets. A technically generated WAV is not proof of natural pronunciation. Missing dependencies, invalid audio, or silence block the render; English voice models and silent audio are never substituted for Urdu-English narration.
- Rendering writes matching SRT/WebVTT sidecars and uses script-aware RTL layout for Urdu captions. This does not guarantee natural pronunciation, voice quality, or phoneme-accurate lip-sync.

## Character rig and mouth-shape scope

The Canvas2D presenter currently uses a procedural articulated 2D rig (renderer contract v3): separate upper/lower arm and leg segments with shoulder, elbow, wrist, hip, knee, and ankle pivots; a layered torso/head; hands; head tilt; gaze/blink/expression changes; and ten reusable mouth geometry profiles (closed, open, wide, round, teeth, tongue, sibilant, lip, open-wide, and open-round). Character cues use normalized scene timestamps. The default cue builder is still an audio-energy/grapheme approximation, not a phoneme aligner, so this is **not true phoneme-aligned lip-sync**. The renderer now supports per-scene camera moves (`push-in`, `pull-out`, `pan-left`, `pan-right`, and subtle `drift`) plus a real normalized character travel path (`walk_from_x` to `walk_to_x`) when `walking: 1` is set. The gait, arm swing, and body bounce are coordinated, and the camera easing is deterministic. It is still procedural 2D artwork, not a finished hand-drawn anime asset pack or a rig-editor workflow; inspect rendered previews before release.
- Optional YouTube upload: Google OAuth desktop client JSON and the dependencies in requirements-publish.txt.

## Windows setup
Open PowerShell in this directory and run this explicitly English, silent renderer smoke demo:

    npm install
    python studio.py --storyboard storyboard.example.json --output outputs\offline-agent-hq-demo.mp4 --language en

Puppeteer downloads a compatible Chromium build during npm install. If your network blocks this, install a supported Chrome/Chromium build and configure Puppeteer to use it.

## Narration languages and local voice backends

The default production profile is ur-en: conversational Pakistani Urdu in Urdu/Arabic script, retaining familiar English technical terms such as API names, product names, and code identifiers. Use --language en only when English narration is explicitly requested (the CI smoke-test fixture does this). The language profile is stored in the storyboard and package status, and subtitle validation checks that the track contains Urdu-script text rather than merely labelling English as Urdu.

### Narrated films (`voiceover.py` + `voice_mix.py`)

Authored films can carry a natural voice as well as a score. `video_studio/voiceover.py`
speaks a small JSON script with a local Piper voice, applies a voice chain
(high-pass, de-ess, presence lift, gentle compression, loudness normalisation)
and writes the two things the picture needs: `lines.json` (when each spoken line
actually starts and ends) and `envelope.json` (measured mouth openness per video
frame). `video_studio/voice_mix.py` then ducks the score under the voice with a
fast-attack / slow-release follower and sums the two without clipping.

Voices are never committed. `ensure_piper_voices()` fetches the public weights
once, verifies a pinned size and MD5, and falls back to a checksum-verified git
mirror when the model host is unreachable. Rendering itself is offline:

    python tools/render_authored_film.py --script video_studio/films/character_speaks.mjs \
        --voice-script video_studio/films/character_speaks.voice.json \
        --voice en_US-amy-medium --out workspace/generated/character-film

The film is retimed to the synthesised audio rather than the other way round: the
cut ends when the voice does, and the mouth is gated by the measured envelope, so
it closes in every pause.

#### The full character piece: `character_ships_it.mjs`

`video_studio/films/character_ships_it.mjs` is the long-form cut: eight chapters,
each one a different shot with its own instrument panel drawn in Canvas — the
rejected NLE timeline, a compiling terminal, the pipeline with a packet travelling
it, the raster grid, the score with the voice drawn over it, the release audit,
the local stack and the ship card. Every caption, cut, gesture and panel is
retimed from `lines.json`, so the picture follows the voice.

Two details worth knowing when reading the code:

- **The camera frames the subject it actually has.** Each chapter declares a
  zoom, but the shot is clamped to the solved skeleton's bounding box and scales
  about the soles, so a raised hand is never cropped and a figure that shrinks
  stays standing on the floor line.
- **The gate is declared by the film, not relaxed by the driver.** This cut
  promises motion in every chapter, so it ships `motion_gate: {min_mean: 0.95,
  max_static: 0.34}` in its `film.json`; the driver measures frame-to-frame luma
  on the encoded delivery copy and fails the render if the film drifts back into
  slides.

A voice that was rendered outside the repo (a hosted model, a human read) is
assembled into the exact artifacts the film consumes with `tools/assemble_voiceover.py`:

    python tools/assemble_voiceover.py \
        --script video_studio/films/character_ships_it.voice.json \
        --clips workspace/voice-source \
        --out workspace/generated/ships-it/voice

    python tools/render_authored_film.py \
        --script video_studio/films/character_ships_it.mjs \
        --voice-dir workspace/generated/ships-it/voice \
        --out workspace/generated/ships-it \
        --width 3840 --height 2160 --fps 30 --delivery-height 1080

The assembler runs the same loudness chain as `voiceover.py`, derives every
timestamp from the audio it just decoded (never from typed-in numbers), and
measures the mouth envelope from the assembled signal, so the pipeline cannot
tell an imported voice from a synthesised one.

English voice setup:

1. Install Piper in the selected Python environment: python -m pip install piper-tts.
2. Download an English voice model and matching .onnx.json config. Review the exact model's license and model card before use.
3. Set PIPER_MODEL to the absolute path to the .onnx file. Its adjacent config must identify a language code starting with en.

PowerShell example for an explicitly English render:

    $env:PIPER_MODEL = "C:\path\to\en_US-lessac-medium.onnx"
    python video_studio/production.py --topic "How AI agents work" --format shorts --language en --render

Urdu-English voice setup:

The bundled Piper adapter is selected automatically when `video_studio.urdu_tts_command` is an empty array in `config.json` (the default in `config.example.json`). Run `START_HERE.bat` and answer **yes** to its optional Urdu voice setup prompt, or run `powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1` directly. The isolated environment installs the pinned Piper Python package and CPU ONNX Runtime; it does not alter Agent HQ's main Python or local config. The first preview downloads the pinned Fasih v2 ONNX model (about 65 MB; the adapter verifies the published file size and MD5) and derives a compatible sidecar from a checksum-verified source config. Internet is needed on first use. CPU synthesis may still be slow on an 8 GB machine.

Fasih v2 is a newer full-model fine-tune of the same Pakistani Urdu voice; the published Urdu-only listening comparison improved over v1, but does not guarantee clarity on mixed Urdu-English technical narration. The adapter now slows the default speech rate by 15% to improve intelligibility. Narration prompts prefer short, complete, spoken sentences, fewer abrupt language switches, and natural Urdu wording. These are targeted improvements, not a claim that voice quality is solved. Always listen to the preview before production use. The older Kani/NeMo adapter remains in the repository for explicit custom configurations, but it is not the Windows default. Its dependency set is documented separately in `requirements-kani-tts.txt`; consult the upstream platform matrix before choosing it.

Before enabling production renders, audition an isolated WAV preview (this does not create an MP4 and does not approve the voice):

    python video_studio/voice_preview.py --text "آج ہم Python سیکھیں گے۔ پھر API کے ذریعے ڈیٹا حاصل کریں گے۔ آخر میں، نتیجہ چیک کریں گے۔" --output workspace/urdu-voice-preview-v2.wav

After the voice profile is approved locally, run the full Python regression tests and the actual narrated-video smoke gate from the repository root:

    python -m unittest discover -s tests -p "test_piper_urdu_tts_adapter.py" -v
    python -m unittest discover -s tests -p "test_video_studio.py" -v
    python tools/run_quality_gate.py --urdu-voice-smoke --report outputs/local-quality-gate-urdu-voice.json

The voice smoke gate checks that the current approval fingerprint is still valid, renders a small vertical MP4 with real Urdu-English speech, validates SRT/WebVTT and the video/audio streams, then runs strict black-frame, freeze, and silence checks. It will not silently substitute English or a silent video. Its MP4 is a technical integration demo at 320×568 and 12 fps, not a publish-ready Shorts export.

The first preview downloads the pinned Fasih v2 model if it is not already cached. The default Piper Fasih voice is single-speaker, so `kani_speaker_prefix` does not affect it; that setting is only for an explicitly configured legacy Kani adapter. For a custom Piper model, set the environment variable `AGENTHQ_PIPER_URDU_MODEL_PATH` to the absolute model path and place the matching JSON sidecar beside it using the conventional `.onnx.json` suffix. The profile fingerprint records the custom model/config hashes. Use a different WAV filename for each preview and keep voice approval disabled if the sample does not meet your requirements.

**Human voice approval is required before any Urdu-English production render.** The default configuration sets `video_studio.urdu_voice_human_approved` to `false`. First generate/listen to a real sample using your local setup; check that it is intelligible Pakistani Urdu, preserves English technical terms, and uses the required adult-male voice. Only after that review set `"urdu_voice_human_approved": true` and copy the preview command's **Voice profile SHA-256** into `"urdu_voice_approved_profile_sha256"` in your local `config.json`. The render gate compares that hash to the selected adapter, model revision and speaker prefix, so changing those settings invalidates the approval. This is a user attestation, not an automated quality measurement. If the current model or speaker prefix is unsuitable, leave approval false and do not release the video. Never commit the local config or tokens.

A custom adapter may be configured in config.json (never commit this file). Its command is an argument array, not a shell string, and must contain either {manifest_file} for a batch adapter or both {text_file} and {output_file} for a per-scene adapter. For example:

    {
      "video_studio": {
        "narration_language": "ur-en",
        "urdu_tts_command": ["python", "path/to/your_adapter.py", "--input", "{text_file}", "--output", "{output_file}"]
      }
    }

The custom adapter path above is a contract example, not the default engine. The bundled default uses Piper's ONNX voice runtime and produces CPU audio without PyTorch or NeMo. The legacy Kani adapter remains available only through an explicit `urdu_tts_command`; its dependencies are listed in `requirements-kani-tts.txt` and should be installed in a separate compatible environment (the Kani upstream docs specify Python 3.10–3.12; check the platform compatibility of NeMo before trying it on Windows). Final rendering is blocked when the configured backend fails or produces invalid/silent WAV output. Human listening review remains mandatory; this integration does **not** prove production-quality Urdu narration.

The default Fasih voice is marked as a Pakistani Urdu single-speaker voice in the upstream voice metadata. This is a useful default for the requested male Urdu narration, but the repository does not claim to have verified the subjective voice quality or your preferred accent via code alone. Listen to the actual preview for voice identity, Urdu pronunciation, the way English technical terms are spoken, volume, clipping, and intelligibility. The legacy `kani_speaker_prefix` setting applies only to an explicitly selected Kani adapter.

## Urdu voice source ledger

Implementation references inspected on **2026-10-20**:

- [Piper TTS on PyPI](https://pypi.org/project/piper-tts/) (release 1.8.0): publishes a Windows x86-64 `abi3` wheel and lists Python 3.9+; the package is GPL-3.0-or-later. Decision: use Piper and CPU ONNX Runtime instead of making the heavier Kani/NeMo/PyTorch stack the default Windows dependency.
- [Pinned Fasih voice metadata](https://huggingface.co/rhasspy/piper-voices/commit/7a6c333ec560f0e688371adc2fbb7bbe105028c6): the `ur_PK-fasih-medium` entry lists Pakistani Urdu, medium quality, one speaker, the 63,532,015-byte ONNX model and its matching JSON sidecar checksums. Decision: pin an immutable revision, verify file sizes/checksums, and require human listening approval before production. The voice repository is MIT-licensed; review the model and package licenses separately.
- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/src/piper/voice.py): documents the `PiperVoice.load` and `synthesize_wav` interface used by the batch adapter.
- [KaniTTS upstream basic example](https://github.com/nineninesix-ai/kani-tts/blob/main/examples/basic/README.md): documents its Python 3.10–3.12 setup, token model and codec dependencies. Decision: keep Kani as an explicit advanced adapter rather than a default Windows dependency.
- [Kani token generator](https://github.com/nineninesix-ai/kani-tts/blob/main/examples/basic/generation/generator.py): supplies the causal-model token-generation pattern, generation parameters, and human/text prompt format. Decision: use the model's speech-code output rather than a generic Transformers TTS pipeline.
- [Kani NanoCodec decoder](https://github.com/nineninesix-ai/kani-tts/blob/main/examples/basic/audio/player.py) and [token constants](https://github.com/nineninesix-ai/kani-tts/blob/main/examples/basic/config.py): document the four-codebook offsets, special token IDs, 22.05 kHz output, and `AudioCodecModel.decode(tokens=..., tokens_len=...)`. Decision: implement the decoder path and add dependency-free tests for token interval validation and codebook offsets.
- [NeMo NanoCodec model](https://huggingface.co/nvidia/nemo-nano-codec-22khz-0.6kbps-12.5fps): the decoder selected by the upstream example. Decision: load it once per batch and reject malformed or effectively silent WAV output.
- [Pinned Urdu fine-tune](https://huggingface.co/mahwizzzz/kani-tts-400m-ur): used by the bundled adapter at revision `6f758dcedff6f33d74dacebab2876b3e536b8c89`. Its speaker identity, adult-male quality, and Urdu-English pronunciation are **not verified by code or model metadata alone**. Decision: expose a local speaker-prefix option, provide an audio-only preview, and require human approval fingerprinted to the selected adapter/model/prefix before production rendering.

These are implementation references, not proof of naturalness or suitability for every speaker preference. The default Piper model is compatible with the Windows/CPU path, but still requires real-audio review. The Kani model and codec links above describe the optional legacy adapter, not the default. If dependency installation or human audio review fails, keep the voice approval flag false and do not release an Urdu-English production video.

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

The package includes `research.md` and `research.json`. Each result records the requested and final domains plus a SHA-256 digest of the bounded extracted page text stored in `research.json`; the prompt may use a shorter excerpt, so this digest is not a hash of a particular model call's full context. The builder now refuses to finalize a non-template package if no readable source page was fetched; search snippets alone are discovery leads, not acceptable evidence. The CEO artifact gate independently checks the research files, provenance schema, extracted-text digests, and consistency between the research JSON and `package-status.json`. A fetched page is **not** proof that a claim is true: check publication dates, prefer primary sources, corroborate important claims across independent domains, and confirm that sources actually support the statements before publishing. The manifest explicitly reports how many pages/domains were fetched and never claims independent verification. Each generated scene also carries `source_refs`, an `evidence_status`, and unresolved notes; the script contains a separate scene evidence map, and the CEO artifact gate rejects references to missing or unfetched source IDs. These links improve traceability but do not prove that a cited page supports the claim, so human fact-checking remains required. Common secrets and direct identifiers are redacted from search queries. The collector does not guarantee that the search provider or target websites will always be available. You may also provide curated local notes using `--source-file workspace/source-notes.md`.

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

## Rendering without a browser

`render.js` uses Puppeteer and needs a Chromium binary. `render_skia.js` runs the
same `render.html` drawing code through `@napi-rs/canvas`, so frames can be
produced on machines and CI images with no browser installed:

```bash
npm install --no-save @napi-rs/canvas
node render_skia.js storyboard.pro.json --out frames --format jpeg --quality 92 --scale 1
python validate_frames.py --frames frames --manifest frames/manifest.json
```

Both paths validate the same storyboard limits, load the bundled fonts before the
first frame, and write `render-manifest.json`. `--scale 0.5` renders a fast
review copy at half resolution.
