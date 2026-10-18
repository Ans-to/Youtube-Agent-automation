# Offline Agent HQ — controlled GitHub bridge

The bridge is a **polling, allowlisted control channel**, not a remote shell. The user starts it on the phone; it polls this repository and performs only explicitly approved actions.

## Supported actions

- `status`: reports whether the project folder exists and records a sanitized status result.
- `self_test`: syntax-checks `agent.py` and `dashboard.py`; it does not intentionally run tasks or edit `tasks.json`.
- `run_task`: runs one specifically named, existing local task only when it is pending/queued, uses an allowlisted task kind, passes the external-action guard, and is the **only** pending/queued task.

No remote task text, arbitrary shell commands, Python snippets, package installs, arbitrary URLs, publishing, messaging, payments, or deletion actions are accepted.

## Request validation

- Every request must have `approved: true`.
- Only the exact fields required for its action are accepted; extra fields cause rejection.
- Request IDs must match `[A-Za-z0-9][A-Za-z0-9_-]{0,79}`.
- Processed IDs are stored locally and will not be run again by this client.
- The bridge rejects tasks that appear to request external actions. This is a conservative filter, not a complete natural-language safety system; review the exact task locally before approval.
- The task runner processes the queue, not a direct task ID. The bridge therefore requires the target to be the only pending/queued task.

## Results and privacy

Local results are saved under `~/.local/state/offline-agent-hq/`. After each accepted request, the bridge also attempts to create `bridge/results/<request-id>.json` on GitHub.

GitHub result reports contain only minimal metadata: request ID, action, timestamp, success flag, syntax-checked source filenames for self-tests, or task ID/status for task runs. They do **not** include task prompts, generated output, stdout/stderr, local filesystem paths, configuration values, or credentials.

The local result is written first. If GitHub reporting fails, the local result remains available and the request is marked seen to avoid repeating a task. The terminal will state that the report could not be uploaded. The bridge does not overwrite an existing result file with the same ID.

## Token requirements

The token file defaults to:

`~/.config/offline-agent-hq/github-token`

Use a token limited to this repository with **Contents: read and write** permission. Read access is needed to poll `bridge/requests/`; write access is needed to publish `bridge/results/`. If the token has read-only access, local execution can still happen, but result uploads will fail. Never commit or share the token.

Optional environment variables:

- `AGENT_HQ_REPO`
- `AGENT_HQ_PROJECT`
- `AGENT_HQ_TOKEN_FILE`
- `AGENT_HQ_STATE_DIR`

## Running

One poll:
```sh
python bridge/bridge.py
```

Poll every 30 seconds:
```sh
python bridge/bridge.py --watch --interval=30
```

Interval must be between 10 and 3600 seconds. Stop watch mode with Ctrl+C. Android may terminate background processes; continuous polling is not guaranteed.

## Request formats

Status:
```json
{
  "id": "status-010",
  "approved": true,
  "action": "status"
}
```

Syntax-only test:
```json
{
  "id": "self-test-010",
  "approved": true,
  "action": "self_test"
}
```

Run an already-existing local task only after checking its content and deciding to run it:
```json
{
  "id": "run-task-010",
  "approved": true,
  "action": "run_task",
  "task_id": "TASK-0009"
}
```

Do not use this bridge for secrets or consequential external actions. A generated plan or draft is not evidence that an external action happened.
