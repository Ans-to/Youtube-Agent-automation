# Offline Agent HQ

**A local-first, Android/Termux-friendly task command center with a holographic dashboard and an optional, allowlisted GitHub control bridge.**

The project is designed for a low-cost phone-first setup. It uses Python's standard library for the task runner, dashboard, and bridge. It does not require a paid AI API.

## Start on Windows PC or Android

- **Windows (recommended):** extract the ZIP, then double-click `START_HERE.bat`. It installs missing prerequisites with winget, installs renderer dependencies, optionally installs Ollama plus the free `llama3.2:3b` local model, configures the local model, and starts the dashboard. Windows deliberately does not auto-run programs just because a ZIP was extracted. If App Installer/winget is missing, install/update App Installer from Microsoft Store. For manual setup, run `setup_windows.ps1`, then `start_windows.bat`.
- **Android:** use the Termux steps below.
- **Mobile/PC behavior and limitations:** read [MOBILE_PC_GUIDE.md](MOBILE_PC_GUIDE.md). The dashboard is responsive, but separate local installs do not automatically synchronize, and the loopback-only dashboard is not remotely exposed.

## Architecture and maintenance

See the [roadmap](docs/ROADMAP.md) for the honest gap to professional motion design and general task automation, and [the architecture and maintenance guide](docs/ARCHITECTURE.md) for module boundaries, configuration overrides, error-handling conventions, state management rules, the sandboxed tool layer, and the staged refactoring plan.

**Data reports measure, they do not interpret.** Ask for a CSV to be analysed and `tools/data_analysis.py` profiles every column with the standard library — counts, ranges, central tendency, missing values — and charts real order statistics. It states in the artifact that it performed no interpretation, treats `1,234` and `12%` as text rather than guessing, and never fetches data from the network.

**Every write is shown as a change.** Each builder leaves a bounded diff of the files it wrote (`changes.md`, `changes.json`) and each run an index pointing at them, so reviewing a run means reading what changed rather than re-reading the artifact. The verifier refuses a change record that describes an edit without showing it.

**An interrupted run can be resumed.** `--resume` reads the stages already finished in the output directory and reuses them instead of re-running: the model is not called again, files are not rewritten, and nothing is duplicated. It refuses to continue a different task or a different set of stages.

**It remembers what earlier runs did.** `tools/memory.py` appends every finished run to a local log, and the next run finds the relevant ones by keyword and receives them as history — explicitly to verify, not a plan to repeat. Add `--note "one page, no bullets"` and that review comment travels with the run. `--no-memory` turns it off; nothing leaves the machine.

**It installs as a real app on Windows and Android.** Edge, Chrome and the Android browser all offer **Install** for it, which puts Agent HQ in its own window with its own icon, Start-menu entry or home-screen shortcut. The manifest advertises the bitmap icons a browser actually requires, and the server returns them as `image/png` rather than text, which is the difference between an install prompt and a bookmark. `start_windows.bat` and `dashboard.py` now open the app for you, and a busy port is explained instead of crashing. See [docs/INSTALL.md](docs/INSTALL.md).

**It stops when the time you gave it runs out.** One wall clock covers the whole run. A stage that cannot finish inside what is left is never started, and is reported as `skipped_out_of_time` with the reason instead of producing half a deliverable. The final reviewer keeps a reserved slot, and a run that skipped work can never be reported as complete. `--budget-minutes 45` sets the total; without it the device tier decides. `budget.json` records where the time went. See [docs/ADAPTIVE.md](docs/ADAPTIVE.md).

**It runs on a weak machine without falling over.** `tools/resources.py` measures the box, picks a tier, and hands every stage the same limits: one heavy job at a time, a bounded wait per model call, a bounded dataset read, a bounded number of repairs. A smaller machine gets a **slower** run, not a different artifact — resolution, language, document content and chart values are declared unchangeable in the plan itself. The decision, its reasons and anything it had to shrink are printed at startup and written to `pipeline-status.json`. Force it with `--profile low` if detection is wrong. See [docs/ADAPTIVE.md](docs/ADAPTIVE.md).

**A repair counts only when the tests pass.** Ask for a failing suite to be fixed and `tools/test_fix.py` runs it, reads the failure, and will not report a fix unless the following run goes green. An edit that does not help is reverted, test files are hashed before and after so a suite cannot be talked into passing, and with no model available it repairs only what the output proves — otherwise it hands you the failing test, file, line, and message.

**The rules are enforced, not just described.** [docs/NORTH_STAR.md](docs/NORTH_STAR.md) is the project's contract: no paid services, no API keys, loopback-only inference, deterministic local rendering, writes confined to `workspace/`, and approval gates on irreversible actions. `python tools/check_invariants.py` fails the build if first-party code starts depending on a billable service, commits a credential-shaped literal, points the model at a non-loopback endpoint, or removes a safety mechanism.

## What is implemented

- **Local dashboard:** mobile-friendly command deck at `http://127.0.0.1:8765`.
- **Task queue:** stores tasks in local `tasks.json`; writes Markdown results to `outputs/` and operational logs to `logs/`. The dashboard includes a detailed YouTube production-package task type.
- **CEO-led task intake:** all queued tasks, video requests, and digital-product requests route through AGENT-01, which delegates distinct subtasks and assigns a quality-review stage.
- **Research before work:** each executed specialist attempts five complementary web searches and fetches up to five bounded public pages, prioritizing official documentation, independent evidence, limitations/risks, and recent updates. Successful research and failures are saved as Markdown plus structured JSON under `workspace/research/agent-runs/`; common secrets and direct identifiers are redacted from search queries. Network failure is reported, never presented as successful research.
- **Better offline deliverables:** when no model is configured, plans, drafts, reviews, YouTube packages, and basic app/software prototypes use clearly labelled deterministic templates with acceptance criteria, scene plans, motion direction, fact-check gates, metadata, and release QA. Template output is never labelled as AI-written or fact-checked.
- **Task routing:** `agents/routing.py` decides which pipeline a goal needs — video package, web build, document, CLI tool, data report, test repair, or product prototype — instead of a regular expression buried in the executor. With a local model the model chooses from a declared pipeline catalog and the tool catalog, and its answer is validated entry by entry; with no model an explicit pattern router reproduces the previous behaviour. Deterministic vetoes (an advisory request, no build verb, "YouTube automation studio" being software rather than a video) apply to model choices too, so routing adds coverage without removing a guard. Every decision, the deterministic comparison, and every veto are written to `routing.json` and to `manifest["routing"]`. See [docs/ROUTING.md](docs/ROUTING.md).
- **Sandboxed tool execution:** web pages and apps, structured documents (`deliverable.md` plus `deliverable.json`), standard-library CLI tools (`tool.py` with a working `--self-test`), and measured data reports (`summary.json`, `analysis.md`, `chart.svg` plus a re-runnable `analyze.py`) are built by a confined tool loop; a failing Python test suite can be diagnosed and, when a fix can be verified, repaired (`tools/tool_agent.py`) instead of a fixed template. The planner sees a catalog of schema-validated tools, writes real files inside `workspace/`, and the run is reported as complete only when every acceptance check passes; the orchestrator then re-verifies the artifact against the requested deliverable's contract. With no local model the loop still produces a verified multi-file scaffold, labelled `deterministic_scaffold`, which carries structure and plumbing rather than researched content; with a model it plans from the goal and repairs failed checks (up to two attempts). Command execution stays disabled unless `AGENT_HQ_ALLOW_EXEC=1`.
- **Offline content auditor:** `video_studio/audit_video.py` checks a finished video for content safety, brand safety, legal, and technical QA — black frames, dead air, freezes, strobing, A/V drift, profanity rate, competitor mentions, disclosure legibility, and more. Every rule declares the evidence it needs: a check that did not run is reported as unverified, never as a pass. It reads local vision observations (objects, faces, actions, scenes, logos) for temporal, context-aware judgement — a knife in a kitchen is downgraded, a gun without context is not. `python video_studio/audit_video.py video.mp4 --report audit.md`. See [docs/AUDITOR.md](docs/AUDITOR.md).
- **Professional motion direction:** `video_studio/motion_director.py` turns a brief into a tone-aware direction sheet and a render-ready storyboard: 4K UHD (landscape or portrait) at 30/60 fps, five art-directed palettes with measured WCAG contrast, a bundled Inter/Space Grotesk type system, 7 cubic-Bezier curves (linear is rejected), anticipation/follow-through/overshoot, six designed transitions, nine camera moves with parallax and deterministic shake, procedural SFX cues snapped to detected beats, and a shot timeline with computed hold windows. The same command audits any storyboard against the spec and reports `MOTION SPEC: PASSED` or the exact clause that failed. `python video_studio/motion_director.py --brief video_studio/brief.example.json --out-dir build`. Production runs attach this automatically: `video_studio/production.py` upgrades the storyboard, writes `motion-report.json`/`motion-report.txt` beside it, records the result in `status.json`, and can fail the run with `--strict-motion`. A complete 20-second 4K film built by this pipeline — frames, procedural soundtrack, encode and audit — lives in `workspace/generated/motion-film/`. See [docs/MOTION.md](docs/MOTION.md).
- **Specialist execution:** 52 configured role profiles (51 executable specialists plus AGENT-50 human approval) share one configured local model. Role profiles guide delegation; they are not separate model processes.
- **Optional local model:** uses an OpenAI-compatible endpoint on loopback only. With the model disabled, the CEO uses deterministic keyword-based routing and specialists produce limited template/checklist outputs; this is not general-purpose AI.
- **GitHub bridge:** polls approved JSON requests from `bridge/requests/`; supported actions are `status`, `self_test`, and guarded `run_task`.
- **Sanitized result reporting:** attempts to write minimal result metadata to `bridge/results/<request-id>.json`. Task prompts, generated output, raw logs, local paths, and configuration values are not included in the GitHub report.
- **Safety checks:** no remote shell, arbitrary Python, or package installation. Research only fetches bounded public text pages discovered by the search module after URL, public-address, and redirect checks; it does not accept arbitrary URLs as executable instructions. Publishing, messaging, payments, and deletion remain outside automatic execution.
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
6. Open `http://127.0.0.1:8765` in the browser on the same phone. Submit a task; **Run pending** sends queued tasks through the CEO-led delegation pipeline.

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

One-shot poll (default branch is `main`):
```sh
python bridge/bridge.py
```

For the separate mobile inbox branch, set the branch explicitly before polling. On Android/Termux:
```sh
export AGENT_HQ_BRANCH=mobile-agent-inbox
python bridge/bridge.py --watch --interval=30
```

On Windows PowerShell:
```powershell
$env:AGENT_HQ_BRANCH = "mobile-agent-inbox"
python bridge/bridge.py --watch --interval=30
```

The branch variable controls both request reads and sanitized result writes. The bridge never changes branches or writes to `main` when this variable is set.

Stop watch mode with Ctrl+C. Before approving a `run_task` request, inspect the local task queue and confirm the exact task is safe to run. Do not queue a task that contains secrets or private personal data.

### Mobile task intake from a separate operational branch

A separate operational branch, `mobile-agent-inbox`, is available for requests created from the GitHub mobile app. It is a separate operational branch so task prompts and result metadata stay isolated from application source code.

- Open [the mobile inbox instructions](https://github.com/Ans-to/Youtube-Agent-automation/blob/mobile-agent-inbox/bridge/requests/README.md) on the `mobile-agent-inbox` branch.
- Add a new JSON request under `bridge/requests/` with `action: "create_task"`, `approved: true`, and bounded `title`, `kind`, and `input` fields.
- For the simplest setup, use the current `main` branch code in your Termux clone and configure it to poll/write only the inbox branch using `AGENT_HQ_BRANCH=mobile-agent-inbox`. The older `mobile-bridge-runtime` branch is a point-in-time snapshot and may lag behind `main`; use it only if you have a specific reason, after backing up local changes.
- The bridge creates a local pending task atomically. It does not start the task when it is created. A task only runs when the local queue runner is started or a separately approved, allowed run request is processed.
- The phone and PC still have separate local queues and output folders. A task queued on the phone is not automatically transferred to the PC; for PC processing later, run the bridge on the PC against the same inbox branch or recreate the task in its local queue.
- The mobile bridge does not accept shell commands or arbitrary code. Video rendering may be too resource-intensive for Android; queue video tasks on mobile and render on the Windows PC when available.
- **Repository visibility warning:** this repository is public, so any task JSON or status report committed to `mobile-agent-inbox` is publicly readable even though that branch is separate. Use only non-sensitive prompts there; use a private repository or the local dashboard for confidential work.

Do not put secrets, credentials, confidential source material, or sensitive personal information into GitHub request files. Request JSON is committed to a public branch and remains in Git history. Keep `mobile-agent-inbox` separate; do not merge it into `main`.

### Recovering an interrupted bridge request safely

The bridge stores local request state under `~/.local/state/offline-agent-hq/` by default; override this with `AGENT_HQ_STATE_DIR` if needed. For each request ID, the state may include a `.result.json` completion record or a `.processing.json` marker. The bridge now fails closed when deduplication state is unreadable and refuses to automatically replay a request that has an unfinished processing marker.

If the bridge reports an interrupted request:

1. Stop the bridge and inspect that request ID's `.result.json` and `.processing.json` files in the local state directory.
2. If a result file exists, treat the request as already handled; do not resubmit it with the same ID.
3. If only a processing marker exists, assume the task may have partially executed. Check the local queue, logs, outputs, and any relevant external service before deciding what happened.
4. Do not delete the marker or reset `seen-request-ids.json` just to force a retry. After a human has confirmed the prior attempt's outcome, create a **new request with a new ID** for any required follow-up.
5. If `seen-request-ids.json` is corrupt, back up the entire state directory and repair it only after reconciling the result and processing records. The bridge intentionally stops instead of silently forgetting which requests it has handled.

This recovery behavior prioritizes preventing duplicate task creation or repeated actions over automatic recovery. An interrupted request requires human review.

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
- `youtube_package`

All supported queued task kinds run through the CEO-led pipeline. Put non-sensitive `.txt`, `.md`, or `.json` reference files in `workspace/`. Inspect all outputs before relying on them.

## Adaptive device profile and quality-first sequential rendering

Before a render, `video_studio/studio.py` detects available RAM, CPU count, disk space, and supported GPU information using standard-library probes. It selects conservative encoding thread limits and writes a `.capabilities.json` sidecar next to the video. Run `python video_studio/studio.py --print-capabilities` to inspect the profile without rendering. A cross-process lock now serializes video renders that share frames/manifests, preventing concurrent renders from corrupting one another. Keep heavy model stages sequential by default as well (`max_parallel_heavy_jobs: 1`); the render lock does not globally serialize every model task. The profiler never silently reduces the requested resolution or frame rate: low-resource machines may take longer, and jobs can still fail if they exceed available memory or disk space. A detected GPU is not proof that every AI model supports it.

## Tests

Run the portable quality gate from the repository root in Windows PowerShell, Command Prompt, Linux, or macOS:

```sh
python tools/run_quality_gate.py
```

That compiles project Python, runs the full unit-test suite, checks renderer JavaScript syntax when Node.js is installed, and prints the device-capability profile. For actual landscape and vertical MP4 renders, use the stricter end-to-end mode after installing Node.js, FFmpeg/FFprobe, and the renderer's Puppeteer dependency:

```sh
python tools/run_quality_gate.py --render-smoke --report workspace/local-quality-gate-report.json
```

The script exits non-zero if a required check fails and can save a JSON report. GitHub Actions checks run for pull requests to `main`, pushes to `main`, and manual runs from the Actions tab. If Actions usage limits block hosted runs, execute the local gate in the imported repository workspace.

## Privacy and security

- Do not store credentials, tax/bank information, or sensitive personal data in task prompts or workspace files.
- `config.json`, `tasks.json`, logs, outputs, and workspace data are local-only and ignored by Git.
- The bridge publishes only sanitized status metadata, but **this repository is public, so anyone can read committed reports and request files**. Never include confidential task details, even though full prompts and outputs are excluded from the status report.
- This project is a constrained local task runner, not an unrestricted agent swarm or fully automated YouTube publishing system.


## Video studio (new starter module)

The `video_studio/` folder includes a JSON storyboard, deterministic Canvas2D renderer (Puppeteer/Chromium), FFmpeg encoder, Piper narration (English and the pinned Pakistani Urdu-English backend), and required SRT/WebVTT subtitles. Urdu-English production remains blocked until the exact local voice profile has been auditioned and human-approved. See `video_studio/README.md` for Windows setup. The renderer supports hero, statistic, diagram, timeline, comparison, code, quote, waveform, kinetic-typography, and animated bar-chart compositions, scene-level captions, and deterministic fade/wipe transitions. It is a reusable motion-graphics starter, not a complete professional nonlinear editor or anime-rig engine.

The CEO can invoke `video_studio/production.py` for a clear video request. The builder uses supplied CEO/specialist research notes when available; standalone use supports `--research` to collect public search results and extract bounded page text without an API key. With a configured loopback model, it creates a multi-scene script and storyboard; without a model, it creates a clearly labelled deterministic template package. Add `--render` after installing Node.js, Puppeteer, and FFmpeg to produce an MP4. The script never uploads or publishes automatically.

## Specialist roster and orchestration

`agents/roster.json` defines 52 profiles: 51 specialist roles plus `AGENT-50`, the human approval gate. `agents/skillbooks.json` gives every role a field-specific workflow, quality gates, failure modes, deliverable contract, and practice drill. `agents/dispatch.py` injects that playbook into each specialist prompt, and reports a concise quality-gate check. This is prompt-level guidance and evaluation scaffolding, not fine-tuning of model weights or a guarantee of expert performance. `agents/orchestrate.py` lets the CEO choose a task-specific team when a local model is enabled; without a model, it uses an explicitly labelled deterministic keyword router. Specialists receive distinct subtasks, research before work, save source reports, and pass outputs forward as unverified context. The CEO may invoke fixed local video and digital-product/app prototype builders. The manifest under `workspace/orchestration/` records assignments, stage results, research-report paths, tool status, and the final reviewer gate. An explicit reviewer FAIL or a blocked required artifact is surfaced as needing human follow-up. Retrieved pages are not automatically fact-checked; review citations and claims manually.


The video module also includes a separate optional YouTube uploader. It requires Google OAuth setup, a local approval record tied to the MP4 hash, and explicit upload confirmation; it defaults to private visibility and never publishes automatically without those checks. See video_studio/README.md.



## Source-aware full-length video production

With a compatible local model enabled in `config.json`, `video_studio/production.py` creates an outline and then generates narration scene by scene. Long-form defaults to 15 minutes and Shorts to 1 minute; the script checks scene count and minimum narration length, emits typed visual instructions, and can optionally synthesize scene-aligned narration with a local Piper voice. Without a model, it writes an explicitly labelled 20-second template. Rendering that demo requires `--render-template`; it is not a finished script. If a user requests a full MP4 without an enabled local model, the pipeline records the render as blocked while retaining the clearly labelled template package.

For standalone runs, `--research` collects DuckDuckGo result titles, links, snippets, and bounded extracted text from public webpages into `research.md` and `research.json`. The CEO pipeline normally passes its saved specialist research through `--source-file` instead of repeating the search. Search snippets and extracted text are evidence to assess, not proof: verify publication dates, source authority, corroboration, and whether each source supports the claim. Supply curated notes using `--source-file workspace/source-notes.md` when useful.

Example:

```sh
python video_studio/production.py --topic "How AI agents work" --format long --research --source-file workspace/source-notes.md --render
```

For Urdu-English narration on Windows, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1`, generate and listen to the audio-only preview, then use `--with-voice` only after the exact voice profile has been approved in `config.json`. For explicitly English narration (`--language en`), install Piper and set `PIPER_MODEL` to a verified English voice model. Use `--target-minutes 8` to change the duration. YouTube upload still requires explicit video-and-metadata approval and Google OAuth; content is never auto-published.

## Specialist practice and human-reviewed improvement

The dashboard includes a Specialist practice lab. Choose a role and submit a concrete task. The practice tool writes an artifact and assessment.json under workspace/training/runs/. Then score the artifact against each gate with a 0 (fail), 1 (partial), or 2 (pass) rating and concrete evidence:

    python agents/practice.py practice --agent AGENT-51 --task "Create an art-direction brief for a 60-second technology explainer"
    python agents/practice.py assess --report "workspace/training/runs/AGENT-51/<run-id>/assessment.json"

To create practice artifacts for all 51 executable roles (CEO plus 50 specialists), run python agents/practice.py practice --all. On a phone, start with --all --limit 5 to avoid a large queue of model work. With model.enabled=false, the output is template-only playbook material, not AI-generated practice work. Enable a compatible local model before expecting generated artifacts.

Only human-reviewed notes from actual local-model outputs are injected into later runs. Template-only reviews are marked as template reviews and are excluded from the model-feedback loop. These assessments measure a particular practice attempt; they do not certify universal mastery or update model weights. AGENT-50 is reserved for human approval and cannot be run automatically. See agents/TRAINING.md for the review loop and agents/MOTION_DESIGN_SYSTEM.md for visual scene and transition rules.

## Digital product prototype builder

The `product_studio/` folder can generate a local-first single-file HTML utility prototype and ZIP package. It uses the configured loopback model only when enabled; otherwise it creates a starter template. The static scan is only a warning aid, not a security audit, and product deployment/sales remain manual. See `product_studio/README.md`.




Run the default specialist pipeline from the repository root:

```sh
python agents/orchestrate.py --task "Prepare a fact-checkable technology video script and storyboard" --context-file workspace/source-notes.md
```

The source-notes file is optional. Without an enabled local model, the pipeline produces transparent template/checklist outputs. With a local model, it can use retrieved page text and source URLs supplied by the research module. Research is not automatic fact verification; important claims still require corroboration and human review. Review `pipeline-status.json` and all stage outputs before using them.

Run a configured specialist role locally with `python agents/dispatch.py --agent AGENT-09 --task "Draft a clear script outline"`. Add `--context-file path/to/source-notes.md` to supply local evidence. With the model disabled, the dispatcher returns a transparent template checklist, not AI-generated work. There are 52 role profiles: AGENT-01 is the CEO, 50 are specialist workers, and AGENT-50 is the human approval boundary. They share the same configured local model endpoint; they are not separate model processes.

## CEO-led execution and research reports

The primary queue runner and the CEO Command Deck both use `agents/orchestrate.py`. AGENT-01 (CEO/Coordinator) selects distinct role-specific assignments when the local model is enabled. Without a model, a transparent keyword router chooses a small team and marks the mode `heuristic_no_model`; it does not pretend to be AI planning. Every specialist stage attempts research before producing its deliverable. Research attempts are saved to `workspace/research/agent-runs/`, and the final queue output aggregates the CEO plan and specialist deliverables. `workspace/orchestration/` contains the assignment plan and per-stage artifacts. The final fact-check role reviews evidence, but the system does not guarantee correctness or independently validate every claim.
For clear video-generation requests, the CEO can invoke the repository-owned video package builder; full MP4 rendering requires an enabled local model unless the user explicitly requests a short template demo. For clear digital-product/prototype requests, the CEO can invoke the local product builder to create an HTML/ZIP artifact. These are fixed local tools, not arbitrary shell access. Their status and artifact paths are recorded in `pipeline-status.json` and the aggregated queue output.
The dashboard’s video and digital-product forms also enqueue tasks for the CEO rather than bypassing delegation. Source notes are validated as local workspace files and passed to specialists and applicable artifact builders. The CEO can produce research-grounded scripts/storyboards, local MP4s when configured, and HTML/ZIP product prototypes. Publishing and other consequential external actions remain outside automatic execution.

## Automatic web research

Every specialist stage attempts five complementary free search queries (task, official documentation, independent research/data, limitations/risks, and recent updates), then attempts to fetch up to five public text pages selected across different queries. The research module blocks non-public IP addresses and validates redirect targets, limits response size, extracts readable text, and records page-fetch failures. No search API key is required. Results and extracted text are included in research reports and supplied to the worker. Search availability depends on internet connectivity and the search provider. Page retrieval is not the same as fact verification: compare independent sources, prioritize primary sources, check dates and context, and cite the source URLs in deliverables. If research fails, the system must disclose that failure rather than claim research was completed.

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

## ADHD-friendly agent output style

The project bundles the upstream MIT-licensed `i-have-adhd` skill at `skills/i-have-adhd/SKILL.md` (source: [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd)). `agents/dispatch.py` injects a compact version of its response-structure rules into local-model specialist and CEO prompts. It prioritizes action-first answers, bounded numbered steps, explicit progress, matter-of-fact errors, and a single next action when work remains. Requested artifact formats and existing safety/approval boundaries take priority; this is prompt guidance, not model fine-tuning or a guarantee of output quality. No external plugin or new runtime dependency is required.

To update the bundled skill, review the upstream `skills/i-have-adhd/SKILL.md`, replace the bundled copy and its MIT license together, then update the compact mapping in `agents/adhd_style.py` and run `python -m unittest discover -s tests -v`.
