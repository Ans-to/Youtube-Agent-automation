# Architecture and maintenance guide

## Current runtime map

This repository has three connected but distinct execution surfaces. Keep their contracts separate:

- **Local task application:** `dashboard.py` is the HTTP/UI entry point; `agent.py` runs queued work; `queue_store.py` owns cross-process queue locking and atomic task persistence.
- **Agent domain and orchestration:** `agents/orchestrate.py` coordinates specialist stages; `agents/routing.py` decides which pipeline a goal needs (see [ROUTING.md](ROUTING.md)); `agents/dispatch.py` resolves role assignments; `agents/practice.py` contains training/practice workflows; `quality_outputs.py` creates explicitly labelled offline fallback artifacts.
- **Video production:** `video_studio/production.py` coordinates research, script/storyboard creation, rendering, QA and readiness; `video_studio/studio.py` renders the storyboard; `render.js` and `render.html` implement the Canvas2D visual layer. Technical media QA is not editorial or artistic approval.
- **Digital products:** `product_studio/build_product.py` owns the product artifact build workflow.
- **External boundary:** `bridge/bridge.py` accepts only its allowlisted request types. YouTube publishing remains separate and approval-gated in `video_studio/publish_youtube.py`.
- **Shared infrastructure:** `app_config.py` is the shared configuration boundary; `tools/path_utils.py` owns canonical path and workspace-containment helpers; `queue_store.py` is the source of truth for task persistence.
- **Tool layer:** `tools/tool_runtime.py` is the only sanctioned way for an agent to read, write, or execute inside a task workspace. `tools/check_invariants.py` enforces the rules in `docs/NORTH_STAR.md`.

## Dependency direction

```text
UI / CLI entry points
        |
        v
Application services (task, product, video workflows)
        |
        v
Domain logic (planning, validation, readiness, state transitions)
        |
        v
Infrastructure adapters (filesystem, local model, web research, TTS, FFmpeg)
```

- Domain modules must not import the dashboard or render UI.
- UI handlers should validate inputs, call a service, and map expected errors to safe user-facing messages.
- Keep network, subprocess, filesystem, and model calls behind narrow adapters.
- Do not duplicate task persistence or locking; use `queue_store.py`.
- Keep the renderer deterministic and data-driven. Put new visual primitives in reusable renderer functions rather than copying whole scene blocks.
- Keep external actions (publish, send, pay, delete) behind explicit approval gates.

## Tool layer (agent actions)

An agent must not receive free-form filesystem or shell access. It receives a
**registry of named tools**, each with a declarative input schema, and every
call is validated, confined, and bounded before it runs.

| Tool | Side effect | Confinement | Default |
| --- | --- | --- | --- |
| `list_files` | read | sandbox root only, 200 entries | enabled |
| `read_file` | read | sandbox root only, 500 KB | enabled |
| `write_file` | write | sandbox root only, 500 KB, no absolute paths | enabled |
| `run_command` | execute | allowlisted interpreter, sandbox working directory, scrubbed environment, 600 s cap | **disabled** |

Rules for extending it:

1. A tool is a `ToolSpec` plus a handler that returns a dict; it must never raise
   into the orchestrator. Failures are structured observations so a planner can
   repair them.
2. Paths go through `WorkspaceSandbox.resolve()`, which canonicalizes and
   rejects anything outside the sandbox — including symlink escapes.
3. A new side effect (delete, network, publish, spend) is a **policy decision**.
   It needs an approval gate and a matching entry in the North Star before it
   ships.
4. `run_command` stays opt-in (`AGENT_HQ_ALLOW_EXEC=1`) and shell-free. Its
   allowlist is a security boundary, not a convenience list: each allowed
   interpreter can execute arbitrary code from files inside the sandbox.

The planner-facing projection is `ToolRegistry.prompt_catalog()`, a compact JSON
list of tool names, summaries, side effects, and input schemas. That catalog is
what the planning prompt receives — the planner never sees the filesystem.

`tools/data_analysis.py` is the measurement layer used by the `data` deliverable:
standard-library CSV parsing, per-column profiling, and deterministic SVG/Markdown
rendering. It never imports the tool loop, so it can be reasoned about (and re-run)
on its own — `analyze.py` in a finished artifact is that module, driven by a CLI.

`tools/test_fix.py` is the repair loop used by the `test_fix` pipeline. It runs a
project's own `unittest` command, parses the failure out of the output, applies at
most three repairs, and keeps a repair only when the following run passes. Code
edits are reverted when they do not help; test files are hashed before and after
and never edited. With no model it can still correct the two harness faults the
output proves — a discovery pattern that skips `*_test.py`, or a `tests` directory
unittest cannot import — and otherwise reports the failure instead of guessing.

`tools/tool_agent.py` is the loop built on top of the registry:

```text
goal -> plan (model or deterministic fallback) -> validate each step against
the tool schema -> execute in a per-task sandbox -> verify acceptance checks
-> repair with the failure observations (bounded attempts) -> report
```

`run_tool_agent()` returns a manifest-safe dict (`status`, `mode`, `attempts`,
`verification`, `artifacts`, `artifact_dir`) and writes `tool-plan.json`,
`tool-runs.json`, and `tool-summary.json` into the sandbox. File bodies are
never copied into those reports. Status semantics:

| Status | Meaning |
| --- | --- |
| `completed` | A model-planned run whose acceptance checks all passed |
| `partial` | A verified deterministic scaffold — real files, but not model-authored work |
| `failed` | At least one step or acceptance check failed; the workspace is preserved |

`agents/orchestrate.py` runs the pipelines `agents/routing.py` selected and then
independently re-verifies the artifacts (`verify_artifact_tool_runs`): a passing
tool summary, every declared acceptance check, and the contract for the requested
deliverable kind.

| Kind | Contract checked after the run |
| --- | --- |
| `web` | complete HTML document, `connect-src 'none'`, no external URLs |
| `document` | `deliverable.md` opens with a level-1 heading and has an acceptance-criteria section; `deliverable.json` declares `ai_generated: false`, `human_review_required: true`, and non-empty criteria |
| `cli` | `tool.py` parses as Python, exposes `--self-test`, and a README exists |
| `fix` | `test-report.json` declares schema 1, names the project, requires human review, and explains itself when no run happened; a `verified_fix` claim needs a passing run and a verified repair; `test_files_modified` must be false; `fix-plan.md` has a Findings and a Limits section |
| `data` | `summary.json` declares schema 1, profiles every column, claims no AI authorship or interpretation, and explains itself when empty; `analysis.md` has Findings and Limits; `chart.svg` is a complete SVG with no script or external reference; `analyze.py` parses as Python |

The kind is fixed by the caller (the router), never by the plan: a plan describes
how to meet a request, not what was asked for.

## Task routing (which pipeline runs)

`agents/orchestrate.py` no longer decides what to build; `agents/routing.py` does,
and the decision is recorded. Three rules keep that safe:

1. **The catalog is the contract.** `PIPELINES` declares every pipeline, its
   deliverable kind, its argument schema, and the phrasings it must never claim.
   The routing prompt, response validation, and execution all read it.
2. **The model chooses among code paths, it does not write them.** A response is
   validated entry by entry; unknown ids, unknown argument keys, duplicates, and
   out-of-range values are dropped with a reason. Nothing the router returns is
   executed as text.
3. **Policy applies to whoever chose.** Vetoes (advisory request, no build verb,
   automation studio ≠ video) are deterministic and are applied to model routes
   too, so enabling the model can add coverage but cannot remove a guard.

`routing.json` and `manifest["routing"]` record the mode, the chosen pipelines,
the deterministic comparison, and every veto or rejection. Execution-time guards
(no render without a model, opt-in command execution, approval-gated external
actions) stay in the executor — routing is a decision, not a permission.

## Configuration and error handling

- Commit only safe defaults to `config.example.json`; keep `config.json`, tokens, credentials, local outputs, model weights and runtime state out of Git.
- Use `app_config.load_config()` for shared application configuration. Supported environment overrides are listed below.
- Errors must not include tokens, prompts, or full configuration values. Catch errors at application boundaries; preserve useful internal exception chaining for diagnostics.
- Do not silently turn invalid configuration into a successful default run. Missing optional local config is valid; malformed config is an actionable error.
- Prefer structured status fields for workflow errors and keep a distinction between failed, blocked, and human-review-required work.

## Environment overrides

Environment variables override the corresponding local JSON values:

| Variable | Setting | Validation |
| --- | --- | --- |
| `AGENT_HQ_MODEL_ENABLED` | `model.enabled` | true/false, yes/no, on/off, 1/0 |
| `AGENT_HQ_MODEL_BASE_URL` | `model.base_url` | non-empty string; endpoint security checks still apply at the caller |
| `AGENT_HQ_MODEL_NAME` | `model.model` | non-empty string |
| `AGENT_HQ_MODEL_TIMEOUT_SECONDS` | `model.timeout_seconds` | integer 1–300 |
| `AGENT_HQ_RUNNER_INTERVAL_SECONDS` | `runner.interval_seconds` | integer 1–86400 |
| `AGENT_HQ_RUNNER_MAX_TASKS_PER_CYCLE` | `runner.max_tasks_per_cycle` | integer 1–20 |
| `AGENT_HQ_DASHBOARD_HOST` | `dashboard.host` | non-empty string; loopback-only default remains recommended |
| `AGENT_HQ_DASHBOARD_PORT` | `dashboard.port` | integer 1–65535 |

Environment overrides are an allowlist, not a general environment-to-config merge. Never put credentials in source files or diagnostic logs.

## Target folder structure

The current top-level scripts are compatibility entry points used by Windows launchers, Termux instructions and automation. Do not move or rename them in a single sweeping change. As modules are extracted and tests prove parity, use this target for new code:

```text
app/
  services/       # task lifecycle and orchestration use cases
  domain/         # task states, policies, validation, readiness
  infrastructure/ # filesystem, model, web, TTS and render adapters
ui/
  dashboard/      # request handlers and presentation only
agents/           # role registry and agent-domain workflows
video_studio/     # video pipeline and rendering assets
product_studio/   # product artifact workflow
bridge/           # constrained GitHub request adapter
config.example.json
app_config.py
tests/            # behavior, integration and security regression tests
docs/             # architecture, operations, ADRs and research
```

## State management

- The task file is the durable queue source of truth. In-memory locks only coordinate active work; they are not durable state.
- Task status transitions must be persisted under `task_queue_lock`; interrupted work must not be silently replayed.
- UI-only progress may be cached, but should be derived from persisted task records when possible.
- Keep the state model explicit: pending/queued → running → completed, failed, or needs_human_action. A generated artifact does not imply that an external action occurred.
- When extracting dashboard workflow flags into a state service, preserve the existing lock ownership, exclusive-workflow behavior and queue-resumption tests.

## Naming, reuse and dead-code policy

- Python modules/functions/variables: `snake_case`; classes and exception types: `PascalCase`; constants: `UPPER_SNAKE_CASE`.
- Use descriptive names that distinguish UI handlers, domain operations, infrastructure adapters, and data schemas.
- Before deleting or renaming a file, search imports, entry points, workflows, PowerShell/BAT scripts, README commands and test fixtures. A file that looks unused may be a public launch path or a test fixture.
- Consolidate duplicated helpers only when semantics match. In particular, do not merge the dashboard's HTML-safe Markdown renderer with domain output generation.
- Keep deterministic smoke fixtures clearly labelled and never treat smoke-test success as production-readiness evidence.

## Refactoring checklist

For each extraction: add characterization tests first; move one cohesive responsibility; preserve the old public entry point as a compatibility wrapper if external scripts call it; run the full unit suite and renderer checks; inspect the diff and workflow logs; then remove obsolete code only after a repository-wide reference audit.
