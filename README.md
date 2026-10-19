# Offline Agent HQ

**A local-first, Android/Termux-friendly task command center with a holographic dashboard and an optional, allowlisted GitHub control bridge.**

The project is designed for a low-cost phone-first setup. It uses Python's standard library for the task runner, dashboard, and bridge. It does not require a paid AI API.

## Start on Windows PC or Android

- **Windows:** run `setup_windows.ps1` in PowerShell, then launch `start_windows.bat`.
- **Android:** use the Termux steps below.
- **Mobile/PC behavior and limitations:** read [MOBILE_PC_GUIDE.md](MOBILE_PC_GUIDE.md). The dashboard is responsive, but separate local installs do not automatically synchronize, and the loopback-only dashboard is not remotely exposed.

## What is implemented

- **Local dashboard:** mobile-friendly command deck at `http://127.0.0.1:8765`.
- **Task queue:** stores tasks in local `tasks.json`; writes Markdown results to `outputs/` and operational logs to `logs/`. The dashboard includes a detailed YouTube production-package task type.\n- **Better offline deliverables:** when no model is configured, plans, drafts, reviews, and YouTube packages use structured templates with acceptance criteria, scene plans, motion direction, fact-check gates, metadata, and release QA. Template output is never labelled as researched or fact-checked.
- **Four workflow stages:** Coordinator, Planner, Worker, Reviewer are logical stages in one Python process, not separate autonomous processes.
- **Optional local model:** uses an OpenAI-compatible endpoint on loopback only. With the model disabled, fallback templates are intentionally limited and are not general-purpose AI.
- **GitHub bridge:** polls approved JSON requests from `bridge/requests/`; supported actions are `status`, `self_test`, and guarded `run_task`.
- **Sanitized result reporting:** attempts to write minimal result metadata to `bridge/results/<request-id>.json`. Task prompts, generated output, raw logs, local paths, and configuration values are not included in the GitHub report.
- **Safety checks:** no remote shell, arbitrary Python, package installation, arbitrary URL fetch, publishing, messaging, payments, or deletion actions.
- **Automated checks:** Python syntax compilation, unit tests, and landscape/vertical MP4 smoke tests run through GitHub Actions on Python 3.11 and 3.12.

## Important limitations

- The bridge runs only while the user starts it on the phone. Android may stop background work.
- The GitHub bridge does not accept new task text. A `run_task` request can target only one already-existing local task that is pending/queued, has an allowlisted kind, passes the external-action guard, and is the only pending/queued task.
- Local task content and generated outputs stay on the phone. Only a small status report is uploaded to GitHub, and only if the token has repository Contents read/write permission.
- A result upload failure does not undo a task already run. The bridge retains the local result and marks the request as seen to avoid accidentally repeating the task.
- The runner cannot prove external actions occurred. Requests to publish, send, pay, delete, set alarms, or similar are held for human action.
- The dashboard binds to loopback only. Do not expose it to a public network.
- A local model must be downloaded and started separately. No model weights are included.

## Quick start on Android

1. Install Termux from F-Droid or the official Termux GitHub releases.
2. Place this repository in a folder you control and open Termux in that folder.
3. Install Python if needed:
   ```sh
   pkg update
   pkg install python git
   ```
4. Create your private local configuration from the example:
   ```sh
   cp config.example.json config.json
   ```
   Keep `config.json` local; it is intentionally ignored by Git.
5. Start the dashboard:
   ```sh
   python dashboard.py
   ```
6. Open `http://127.0.0.1:8765` in the browser on the same phone. Queue a harmless task and choose **Run pending**.

Run one queued task from Termux with:
```sh
python agent.py --once
```

Run repeated local processing with:
```sh
python agent.py --loop --interval 60
```
Stop it with Ctrl+C. On Android, background execution is best-effort; use a wake lock only when you explicitly want repeated processing.

## Optional local AI model

The default configuration keeps `model.enabled` set to `false`. To use a model, start a compatible local inference server and configure a loopback URL such as:

`http://127.0.0.1:8080/v1/chat/completions`

Only plain HTTP endpoints using a literal loopback IP and explicit port are accepted (for example `http://127.0.0.1:8080/v1/chat/completions`). Redirects are blocked. Hostnames, embedded credentials, non-loopback IPs, HTTPS endpoints, and URLs with query strings/fragments are rejected. Start with a small quantized model and test memory and latency on your specific phone. A timeout means the task may fail; it does not imply the model generated a result.

## GitHub bridge setup

The bridge client is `bridge/bridge.py`. It reads a GitHub token from:

`~/.config/offline-agent-hq/github-token`

Use a token restricted to this repository with **Contents: read and write** permission. Save it only on the phone; never commit it, print it, or paste it into a chat. The bridge needs read access to poll requests and write access to create sanitized result files. If write access is unavailable, tasks can still produce local results but GitHub reporting will fail.

One-shot poll:
```sh
python bridge/bridge.py
```

Poll every 30 seconds:
```sh
python bridge/bridge.py --watch --interval=30
```

Stop watch mode with Ctrl+C. Before approving a `run_task` request, inspect the local task queue and confirm the exact task is safe to run. Do not queue a task that contains secrets or private personal data.

### Request protocol

Status request:
```json
{
  "id": "status-010",
  "approved": true,
  "action": "status"
}
```

Syntax-only self-test:
```json
{
  "id": "self-test-010",
  "approved": true,
  "action": "self_test"
}
```

Run an existing local task (only after reviewing that exact local task):
```json
{
  "id": "run-task-010",
  "approved": true,
  "action": "run_task",
  "task_id": "TASK-0009"
}
```

Request IDs must contain only letters, digits, hyphens, or underscores and must be at most 80 characters. IDs are processed once. Result reports are written to `bridge/results/` and intentionally contain only minimal metadata.

## Supported task kinds

- `plan`
- `draft`
- `summarize_workspace`
- `review_output`

Put non-sensitive `.txt`, `.md`, or `.json` reference files in `workspace/`. Inspect all outputs before relying on them.

## Tests

Run locally:
```sh
python -m py_compile agent.py dashboard.py queue_store.py bridge/bridge.py agents/dispatch.py agents/orchestrate.py video_studio/studio.py video_studio/production.py video_studio/research.py video_studio/validate_render.py video_studio/validate_frames.py video_studio/release_gate.py video_studio/publish_youtube.py product_studio/build_product.py
python -m unittest discover -s tests -v
```

GitHub Actions runs these checks on pushes and pull requests to `main`.

## Privacy and security

- Do not store credentials, tax/bank information, or sensitive personal data in task prompts or workspace files.
- `config.json`, `tasks.json`, logs, outputs, and workspace data are local-only and ignored by Git.
- The bridge publishes only sanitized status metadata; repository collaborators can see those reports.
- This project is a constrained local task runner, not an unrestricted agent swarm or fully automated YouTube publishing system.


## Video studio (new starter module)

The `video_studio/` folder now includes a JSON storyboard, deterministic Canvas2D renderer (Puppeteer/Chromium), FFmpeg encoder, and an optional local Piper narration path. See `video_studio/README.md` for Windows setup. The renderer supports hero, statistic, diagram, timeline, comparison, code, quote, waveform, kinetic-typography, and animated bar-chart compositions, scene-level captions, and deterministic fade/wipe transitions. It is a reusable motion-graphics starter, not a complete professional nonlinear editor or anime-rig engine.

Create a script/storyboard draft from a topic with `python video_studio/production.py --topic "Your topic"`. This uses a configured loopback local model if enabled; otherwise it writes a clearly marked 20-second template demo. Optional --research collects public search-result leads without an API key, but does not independently verify claims. The script never uploads or publishes automatically. Add --render after installing Node.js, Puppeteer, and FFmpeg to produce an MP4.

## Specialist roster and orchestration

`agents/roster.json` defines 52 profiles: 51 specialist roles plus `AGENT-50`, the human approval gate. `agents/skillbooks.json` gives every role a field-specific workflow, quality gates, failure modes, deliverable contract, and practice drill. `agents/dispatch.py` injects that playbook into each specialist prompt, and reports a concise quality-gate check. This is prompt-level guidance and evaluation scaffolding, not fine-tuning of model weights or a guarantee of expert performance. `agents/orchestrate.py` runs up to 51 non-approval roles sequentially, including the two motion-design specialists, passing previous outputs as unverified context and writing a manifest under `workspace/orchestration/`. The dashboard exposes the pipeline. No automatic web research or external action is claimed by the specialist pipeline; use the separate video research option for source discovery, then verify sources manually.


The video module also includes a separate optional YouTube uploader. It requires Google OAuth setup, a local approval record tied to the MP4 hash, and explicit upload confirmation; it defaults to private visibility and never publishes automatically without those checks. See video_studio/README.md.



## Source-aware full-length video production

With a compatible local model enabled in `config.json`, `video_studio/production.py` creates an outline and then generates narration scene by scene. Long-form defaults to 15 minutes and Shorts to 1 minute; the script checks scene count and minimum narration length, emits typed visual instructions, and can optionally synthesize scene-aligned narration with a local Piper voice. Without a model, it writes an explicitly labelled 20-second template. Rendering that demo requires `--render-template`; it is not a finished script.

Optional free discovery can be enabled using `--research`. This collects DuckDuckGo search-result titles, links and snippets into `research.md`/ `research.json` without an API key. Search snippets are unverified research leads, not source-grounded facts. Open the source links, verify publication dates and claims, and review the final script before publication. For more reliable context, supply curated notes using `--source-file workspace/source-notes.md`.

Example:

```sh
python video_studio/production.py --topic "How AI agents work" --format long --research --source-file workspace/source-notes.md --render
```

Add `--with-voice` only after installing Piper and setting `PIPER_MODEL` to a local voice model file. Use `--target-minutes 8` to change the duration. YouTube upload still requires explicit video-and-metadata approval and Google OAuth; content is never auto-published.

## Specialist practice and human-reviewed improvement

The dashboard includes a Specialist practice lab. Choose a role and submit a concrete task. The practice tool writes an artifact and assessment.json under workspace/training/runs/. Then score the artifact against each gate with a 0 (fail), 1 (partial), or 2 (pass) rating and concrete evidence:

    python agents/practice.py practice --agent AGENT-51 --task "Create an art-direction brief for a 60-second technology explainer"
    python agents/practice.py assess --report "workspace/training/runs/AGENT-51/<run-id>/assessment.json"

To create practice artifacts for all 51 executable specialist roles, run python agents/practice.py practice --all. On a phone, start with --all --limit 5 to avoid a large queue of model work. With model.enabled=false, the output is template-only playbook material, not AI-generated practice work. Enable a compatible local model before expecting generated artifacts.

Only human-reviewed notes from actual local-model outputs are injected into later runs. Template-only reviews are marked as template reviews and are excluded from the model-feedback loop. These assessments measure a particular practice attempt; they do not certify universal mastery or update model weights. AGENT-50 is reserved for human approval and cannot be run automatically. See agents/TRAINING.md for the review loop and agents/MOTION_DESIGN_SYSTEM.md for visual scene and transition rules.

## Digital product prototype builder

The `product_studio/` folder can generate a local-first single-file HTML utility prototype and ZIP package. It uses the configured loopback model only when enabled; otherwise it creates a starter template. The static scan is only a warning aid, not a security audit, and product deployment/sales remain manual. See `product_studio/README.md`.




Run the default specialist pipeline from the repository root:

```sh
python agents/orchestrate.py --task "Prepare a fact-checkable technology video script and storyboard" --context-file workspace/source-notes.md
```

The source-notes file is optional. Without an enabled local model, the pipeline produces transparent template/checklist outputs. With a local model, it can use retrieved page text and source URLs supplied by the research module. Research is not automatic fact verification; important claims still require corroboration and human review. Review `pipeline-status.json` and all stage outputs before using them.

Run a configured specialist role locally with `python agents/dispatch.py --agent AGENT-09 --task "Draft a clear script outline"`. Add `--context-file path/to/source-notes.md` to supply local evidence. With the model disabled, the dispatcher returns a transparent template checklist, not AI-generated work. There are 52 role profiles: 51 specialist roles and the human approval boundary. They share the same configured local model endpoint; they are not separate model processes.

## Automatic web research

Every queued task and every specialist pipeline stage attempts three free search queries (task, official documentation, and independent analysis), then attempts to fetch up to five public text pages. The research module blocks non-public IP addresses and validates redirect targets, limits response size, extracts readable text, and records page-fetch failures. No search API key is required. Results and extracted text are included in research reports and supplied to the worker. Search availability depends on internet connectivity and the search provider. Page retrieval is not the same as fact verification: compare independent sources, prioritize primary sources, check dates and context, and cite the source URLs in deliverables. If research fails, the system must disclose that failure rather than claim research was completed.

## PC and mobile browser app

The dashboard now exposes a web-app manifest, vector icon, service worker, and a minimal offline fallback so supported browsers can install Agent HQ as an app shortcut. The service worker deliberately does **not** cache task state, generated outputs, or form submissions.

### Windows PC

1. Install Python 3.10 or newer.
2. In PowerShell, run \`.\setup_windows.ps1\` from the project folder.
3. Start the dashboard with \`.\start_windows.bat\`.
4. Open the loopback URL printed in the terminal (normally \`http://127.0.0.1:8765\`).
5. In a supported browser, use its Install App / Install this site option if available.

For MP4 rendering, install Node.js LTS and FFmpeg as described in \`video_studio/README.md\`. The setup script checks for these dependencies and reports when rendering cannot be used.

### Android phone

1. Open the project folder in Termux.
2. Install Python if needed with \`pkg install python git\`.
3. Run \`python dashboard.py\`.
4. Open \`http://127.0.0.1:8765\` in the browser on that same phone.
5. In a supported browser, choose **Add to Home screen** or **Install app**.

### Important cross-device limitation

This is a local-first web app, not a hosted service. If you start Agent HQ separately on the PC and phone, they have separate task queues, configuration, and output folders. The installed web app does not synchronize data between devices. The local dashboard is intentionally restricted to loopback; do not change it to \`0.0.0.0\` or expose it to the public internet. A shared multi-device deployment would need a separately designed authenticated server and encrypted data synchronization.

