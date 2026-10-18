# Offline Agent HQ — controlled GitHub bridge

This bridge is a **polling, allowlisted control channel**, not a remote shell. It is designed for Termux and the existing OfflineAgentHQ project.

## Safety boundary
- GitHub credentials stay on the phone in a local file; never commit them or paste them into chat.
- Only the actions explicitly allowlisted in `bridge.py` are accepted.
- No arbitrary shell, Python snippets, URLs, package installs, or task execution are accepted.
- Existing `tasks.json` is read-only for the initial bridge.
- The first actions are `status` and `self_test`; they must not run or modify queued tasks.
- Every request needs a unique ID and must be marked approved by the user in the private repository before the phone executes it.
- Responses contain limited status information and no secrets or task payloads.

## Current stage
This repository contains the protocol and safe bridge client. It does not grant ChatGPT direct access to Termux; the phone must run the client and poll GitHub. The client does not start automatically and does not install itself.

## Request format
A request file under `bridge/requests/<id>.json` must look like:

```json
{
  "id": "status-001",
  "approved": true,
  "action": "status"
}
```

Allowed actions are defined in the client. Treat repository write access as control access, even though the client rejects arbitrary commands.
