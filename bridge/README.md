# Offline Agent HQ — controlled GitHub bridge

This bridge is a **polling, allowlisted control channel**, not a remote shell. It is designed for Termux and the existing OfflineAgentHQ project.

## Safety boundary
- GitHub credentials stay on the phone in a local file; never commit them or paste them into chat.
- Accepted actions are `status`, `self_test`, and guarded `run_task`.
- No arbitrary shell, Python snippets, URLs, package installs, or task text are accepted from GitHub.
- `status` reports file presence and sizes only; it does not reveal task contents or configuration values.
- `self_test` syntax-checks local Python files; it does not intentionally run tasks or edit `tasks.json`.
- `run_task` can only target an existing local task ID. The task must already be pending/queued, use an allowlisted task kind, not appear to request an external action, and be the **only** pending/queued task because the current runner processes the queue rather than accepting a task ID.
- The bridge rejects unapproved requests, duplicate request IDs, and requests with extra fields. Do not treat this as a substitute for reviewing what you approve.
- Never use this bridge for passwords, private data, payments, publishing, messaging, deletion, or other consequential external actions. Such work still needs human review and execution.
- Results are saved locally under `~/.local/state/offline-agent-hq/`. This version does **not** upload results to GitHub, so the controller cannot remotely verify completion from the repository alone.

## Current stage
This repository contains the protocol and bridge client. It does not grant ChatGPT direct access to Termux; the phone must run the client and poll GitHub. The client does not start automatically and does not install itself. Android may stop background processes, so watch mode is not guaranteed to stay alive indefinitely.

## Running
Run once:
```sh
python bridge.py
```

Poll repeatedly every 30 seconds:
```sh
python bridge.py --watch
```

Custom interval is limited to 10–3600 seconds:
```sh
python bridge.py --watch --interval=30
```

Press Ctrl+C to stop watch mode. The bridge reads the token from `~/.config/offline-agent-hq/github-token` by default and uses the project directory `/storage/emulated/0/Download/OfflineAgentHQ/OfflineAgentHQ` by default. Environment variables can override these paths.

## Request formats

Status:
```json
{
  "id": "status-001",
  "approved": true,
  "action": "status"
}
```

Self-test:
```json
{
  "id": "self-test-002",
  "approved": true,
  "action": "self_test"
}
```

Guarded task run (only after checking the local queue and explicitly deciding to run that exact task):
```json
{
  "id": "run-task-001",
  "approved": true,
  "action": "run_task",
  "task_id": "TASK-ID-HERE"
}
```

The `task_id` is only an identifier for a task already stored locally; the bridge does not accept new task text or shell commands.
