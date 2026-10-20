# Mobile task inbox (separate operational branch)

This branch is a separate queue channel for the local Agent HQ GitHub bridge. It is **not** PR #11 and should not be merged into `main`.

## Submit a task from the GitHub mobile app

1. Open this repository, switch the branch selector to `mobile-agent-inbox`, then open `bridge/requests`.
2. Use **Add file → Create new file** and create a file such as `bridge/requests/task-20261020-001.json`. Use a unique filename and request ID each time.
3. Paste this JSON and edit the three task fields:

```json
{
  "id": "mobile-task-20261020-001",
  "approved": true,
  "action": "create_task",
  "title": "Video: topic here",
  "kind": "youtube_package",
  "input": "Create a researched Urdu-English YouTube video package about the topic. Use the CEO-led pipeline, cite fetched sources, and keep publishing disabled."
}
```

4. Commit the file to `mobile-agent-inbox` (not `main` and not the PR #11 branch).
5. On the Android device that will execute it, run the bridge in watch mode with `AGENT_HQ_BRANCH=mobile-agent-inbox`. The bridge only queues the task locally; it does not execute it automatically.
6. Check `bridge/results/` on this branch for a minimal result containing the task ID and status.

## Supported request schema

- `status`: only `id`, `approved`, `action`.
- `self_test`: only `id`, `approved`, `action`.
- `create_task`: only `id`, `approved`, `action`, `title`, `kind`, `input`.
- `run_task`: only `id`, `approved`, `action`, `task_id`. Remote execution remains restricted to low-risk task kinds already in the local queue.

Allowed task kinds for creation: `plan`, `draft`, `summarize_workspace`, `review_output`, `youtube_package`. Inputs are limited to 16,000 characters. Every request requires `"approved": true` and a unique ID.

## Privacy and safety

- **This repository is public.** Requests and results committed to this branch are publicly readable and remain in Git history. This branch is separate, not private. Use only non-sensitive task instructions here; use a private repository or the local dashboard for confidential work. **Never include passwords, API keys, tokens, private personal data, or confidential source material.**
- The bridge does not accept shell commands, arbitrary code, package installs, publishing requests, or payment/deletion actions.
- `youtube_package` can be queued from mobile, but actual MP4 rendering is resource-intensive on Android. For best output, let the Windows PC process the queued task when it is available; the phone and PC do not automatically share local task queues.
- Result files are intentionally minimal. Full prompts, local output paths, and raw logs are not uploaded.
- Do not merge this operational branch into `main`; keep request and result files separate from PR #11.
