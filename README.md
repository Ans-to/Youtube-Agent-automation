# Offline Agent HQ

**A local-first, Android/Termux-friendly task command center with a holographic dashboard and an optional, allowlisted GitHub control bridge.**

The project is designed for a low-cost phone-first setup. It uses Python's standard library for the task runner, dashboard, and bridge. It does not require a paid AI API.

## What is implemented

- **Local dashboard:** mobile-friendly command deck at `http://127.0.0.1:8765`.
- **Task queue:** stores tasks in local `tasks.json`; writes Markdown results to `outputs/` and operational logs to `logs/`.
- **Four workflow stages:** Coordinator, Planner, Worker, Reviewer are logical stages in one Python process, not separate autonomous processes.
- **Optional local model:** uses an OpenAI-compatible endpoint on loopback only. With the model disabled, fallback templates are intentionally limited and are not general-purpose AI.
- **GitHub bridge:** polls approved JSON requests from `bridge/requests/`; supported actions are `status`, `self_test`, and guarded `run_task`.
- **Sanitized result reporting:** attempts to write minimal result metadata to `bridge/results/<request-id>.json`. Task prompts, generated output, raw logs, local paths, and configuration values are not included in the GitHub report.
- **Safety checks:** no remote shell, arbitrary Python, package installation, arbitrary URL fetch, publishing, messaging, payments, or deletion actions.
- **Automated checks:** Python syntax compilation and unit tests run through GitHub Actions on Python 3.11 and 3.12.

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

Only loopback endpoints are accepted. Start with a small quantized model and test memory and latency on your specific phone. A timeout means the task may fail; it does not imply the model generated a result.

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
python -m py_compile agent.py dashboard.py bridge/bridge.py
python -m unittest discover -s tests -v
```

GitHub Actions runs these checks on pushes and pull requests to `main`.

## Privacy and security

- Do not store credentials, tax/bank information, or sensitive personal data in task prompts or workspace files.
- `config.json`, `tasks.json`, logs, outputs, and workspace data are local-only and ignored by Git.
- The bridge publishes only sanitized status metadata; repository collaborators can see those reports.
- This project is a constrained local task runner, not an unrestricted agent swarm or fully automated YouTube publishing system.
