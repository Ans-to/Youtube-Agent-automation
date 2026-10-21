# Architecture and maintenance guide

## Current runtime map

This repository has three connected but distinct execution surfaces. Keep their contracts separate:

- **Local task application:** `dashboard.py` is the HTTP/UI entry point; `agent.py` runs queued work; `queue_store.py` owns cross-process queue locking and atomic task persistence.
- **Agent domain and orchestration:** `agents/orchestrate.py` coordinates specialist stages; `agents/dispatch.py` resolves role assignments; `agents/practice.py` contains training/practice workflows; `quality_outputs.py` creates explicitly labelled offline fallback artifacts.
- **Video production:** `video_studio/production.py` coordinates research, script/storyboard creation, rendering, QA and readiness; `video_studio/studio.py` renders the storyboard; `render.js` and `render.html` implement the Canvas2D visual layer. Technical media QA is not editorial or artistic approval.
- **Digital products:** `product_studio/build_product.py` owns the product artifact build workflow.
- **External boundary:** `bridge/bridge.py` accepts only its allowlisted request types. YouTube publishing remains separate and approval-gated in `video_studio/publish_youtube.py`.
- **Shared infrastructure:** `app_config.py` is the shared configuration boundary; `tools/path_utils.py` owns canonical path and workspace-containment helpers; `queue_store.py` is the source of truth for task persistence.

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
