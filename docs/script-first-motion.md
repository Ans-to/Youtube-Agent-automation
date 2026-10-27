# Script-first motion-graphics production

This is the reusable **draft** path for a narration that already exists. It does not research a topic or write, shorten, or replace the narration. The original UTF-8 bytes are saved in both `script.txt` and `script.md`; source offsets and a SHA-256 bind every beat to those bytes. Use plain text: headings and stage directions in the input are treated as spoken words.

The director plans a drawn composition for each sentence or sufficiently long clause. It records the subject, action, object, qualifiers, a literal spoken phrase, visual elements and music mood. The renderer uses the existing house typography, dark cinematic palettes and procedural drawing/product kit; no photographs or generated-image backplates are used. The graphic choice is driven by the plan, not the duration of the sentence. A negated transfer is illustrated as a crossed-out, stationary item, not an invented attempted delivery. The seed-to-plant transformation, for example, actually grows a drawn plant rather than replacing it with an unrelated object.

## Install and configure

From the repository root, install Node dependencies and FFmpeg/ffprobe. For English Kokoro narration, the project's existing setup is:

```bash
python -m venv .venv
.venv/bin/pip install numpy pillow imageio-ffmpeg kokoro-onnx onnxruntime
npm --prefix video_studio ci
.venv/bin/python video_studio/kokoro_voice.py    # one-time, pinned weights and voice pack
```

Use the Windows equivalents for activating the virtual environment and install FFmpeg/ffprobe on PATH. `AGENTHQ_KOKORO_DIR` or `XDG_CACHE_HOME` can select the voice cache. The model and voice files are cached locally, not committed to the project.

For **automatic** visual direction, enable the existing loopback-only local model in `config.json` as described in [LOCAL_MODEL_GUIDE.md](../LOCAL_MODEL_GUIDE.md). The script is supplied as data; the model is asked for declarative visuals only, never executable code or replacement narration. Requests default to two beats and at most 1,200 output tokens; optional `model.visual_batch_size` (1–8) and `model.visual_max_output_tokens` (500–4,000) can be tuned to the server's context limit. A disabled, unreachable or malformed model stops the build. There is no stock-graphic fallback. Actual visual usefulness depends on the configured model; it is not guaranteed by the prompt.

## Build a draft from a supplied script

```bash
python video_studio/production.py \
  --script path/to/exact-narration.txt --language en \
  --out workspace/my-script-film --render
```

The default language follows `config.json`, or `ur-en` if absent; explicitly choose `--language en` for an English script. For Urdu-English, the existing configured local Urdu TTS adapter is used; pronunciation, mixed-script shaping and delivery still need review. The renderer bundles Noto Naskh Arabic (SIL OFL 1.1) for Arabic-script text and uses RTL direction. Do not interpret a rendered file as proof of Urdu voice or typography quality.

Alternatively, supply an authored visual plan instead of the model:

```bash
python video_studio/production.py \
  --script video_studio/examples/script_motion/systems.txt --language en \
  --plan video_studio/examples/script_motion/systems.visuals.json \
  --out workspace/systems-example --render
```

Remove `--render` to create only the source-bound plan. `--voice-dir` accepts **one recorded WAV per planned beat**, named `b0001.wav`, `b0002.wav`, etc.; the clips are normalized to PCM before timing, but their spoken words are not automatically verified. `--captions` adds a draft SRT sidecar; without it, no captions are produced. `--scale .5` is for a small preview; the default is 1920×1080 at 30 fps. An output directory already containing a video or approval is refused: use a new directory for a new render.

The plan's supported code-drawn primitives are `focus`, `transfer`, `blocked`, `transform`, `compare`, `sequence` and `chart`. Their finite icon vocabulary is in `script_director.py`. The author or model must return `unsupported` when these cannot depict the meaning; the pipeline stops instead of filling the scene with an unrelated icon. The examples under `video_studio/examples/script_motion/` are deliberately small and hand-authored, not evidence of an AI director's performance.

## Checks and limitations

- Exact source slices and order are verified. A model cannot supply the words fed to TTS. Very long unpunctuated spans are refused rather than being cut at an arbitrary word; add an appropriate sentence/clause break without changing the wording.
- Node labels must occur in the current beat or the preceding three beats. The validator catches selected explicit negation, reversed English transfers/comparisons, direction contradictions, and chart numbers missing from or out of order in the current narration. Chart values must be literal nonnegative ASCII decimals; missing data is never fabricated. **These are narrow tripwires, not a general semantic parser.** References, irony, negation, comparisons, dates, units, and multi-action sentences can still be misunderstood. A plan that cannot cover the entire spoken idea must be marked unsupported. Visual review is mandatory even when the plan validates.
- Every picture interval is built from the actual PCM clip length on a contiguous 30 fps frame clock. The final encoded frame count and all frame timestamps are checked. This does **not** align individual words, prove that TTS spoke the text, or verify when the listener hears an action. Within-clip animation is approximate and needs watching/listening.
- Strict technical QA checks black intervals, freezes (including freezes reaching EOF), silence and content-based holds. A passing heuristic does not establish smooth or meaningful motion. The draft retains separately measurable narration and music stems. The mixer targets about −14 LUFS, a true-peak ceiling at or below −1 dBTP after encoding, narration average −18 to −12 dBFS and peaks −6 to −3 dBFS, and music under speech −30 to −24 dBFS. These are targets/recommendations, not guarantees: the saved audit reports actual measurements and flags out-of-range values. Effects, when present, should be measured separately against −18 to −10 dBFS. Listening and intelligibility checks remain essential.
- The draft SRT uses measured **line** boundaries, not verified word timing, and may need line breaks/readability corrections. Any sidecar is checked against the planned words and must also be reviewed against actual speech. The motion headline is a short quoted visual phrase, not a complete subtitle track.
- Semantic fidelity, actual pronunciation and complete narration, synchronization, visual pacing, captions, mix, ending and factual claims are not approved by automated checks. No script facts are researched by this path.

## Review and release

After rendering, initialize a **blank** checklist bound to the exact video, script, plan, clocks, QA, stems and any caption files:

```bash
python video_studio/script_audit.py --package workspace/my-script-film --init-review
# A named person watches/listens to the complete encoded file and fills script-review.json.
python video_studio/script_audit.py --package workspace/my-script-film
python video_studio/release_gate.py --package workspace/my-script-film
```

The reviewer must assess every beat's spoken span, subject, action, relationship and evidence, and separately review delivery, sync, pacing, music balance, captions, the ending and factual claims where applicable. Merely generating the checklist never passes it. Missing, failed or stale evidence blocks this profile at approval and again at upload. Automated checks cannot attest on a reviewer's behalf.

The stricter Nokia 15-minute profile remains mandatory for the Nokia rise-and-fall film; a generic script audit cannot replace its duration, facts, music, complete-narration, ending and other checks. This path does not complete or approve that film. The older topic-generated/research-first and authored-brief routes remain separate; using them is not the same as the exact-script path. Their legacy storyboard renderers now reject missing stat, quote, chart, comparison, diagram, timeline and code content rather than inventing placeholder claims; *provided* content can still be wrong or irrelevant and requires review.

[View the three unrelated draft proof clips and their incomplete audits](media/script-motion-proofs/README.md).
