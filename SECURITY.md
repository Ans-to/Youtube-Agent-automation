# Security model

## Local execution boundary

- The dashboard must bind to loopback (`127.0.0.1`, `localhost`, or `::1`) and is intended for use from the same phone.
- Local model calls are accepted only for loopback endpoints.
- Model output is treated as text. The runner never evaluates model output as a shell string. Where an agent needs to act, it can call only a registered tool with a declared input schema, inside a confined task workspace (`tools/tool_runtime.py`). Command execution is opt-in, shell-free, and limited to an allowlist of interpreters.
- The GitHub bridge accepts only the allowlisted actions `status`, `self_test`, and guarded `run_task`.
- Requests must be explicitly approved, have exact expected fields, and use a path-safe request ID.
- A task run must target an existing local pending/queued task of an allowed kind; it must be the only pending/queued task and must pass the external-action guard.
- Completed, failed, or held tasks are not automatically reset or retried.

## Enforced invariants

The non-negotiable rules live in [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md). CI
and the local quality gate run `python tools/check_invariants.py`, which fails on:

| Rule | Rejects |
| --- | --- |
| `NO_PAID_SDK` | imports or requirements for hosted-AI SDKs |
| `NO_BILLABLE_ENDPOINT` | literal URLs to billable AI/TTS/vision services |
| `NO_SECRET_LITERAL` | committed API keys, tokens, and private keys |
| `LOOPBACK_MODEL_ONLY` | non-loopback model endpoints, or an example config that ships the model enabled |
| `HONEST_DEGRADATION` | removal of the offline-output labelling markers |
| `TOOL_SANDBOX_PRESENT` | removal of workspace confinement from the tool layer |
| `SAFE_SUBPROCESS` | shell-string execution (`shell=True`, `os.system`, `os.popen`) |

## GitHub reporting

- The bridge writes a local result first, then attempts to publish a sanitized report.
- Reports exclude task prompts, output text, stdout/stderr, local filesystem paths, configuration values, and credentials.
- Result paths are write-once; the bridge refuses to overwrite an existing report with the same request ID.
- The GitHub token requires repository Contents read/write permission for polling and result reporting. Keep the token in the local token file only.
- Repository collaborators can see sanitized reports. Do not place private information in task IDs or requests.

## Explicit limitations

- This is not a sandbox against a fully compromised Android device or Python runtime.
- The external-action phrase filter is heuristic and can miss requests or produce false positives. Human review is still required.
- The dashboard displays local task prompts and outputs to anyone who can access the phone's loopback browser/session.
- The bridge does not publish videos, send messages, make payments, delete files, or perform other consequential external actions.
- Android may stop the client process, and no always-on guarantee is made.
- Never put passwords, API keys, financial records, or other sensitive personal data in prompts, workspace files, or repository requests.


## Maintainer hardening checklist

These controls live in GitHub account/repository settings and cannot be enforced by application code alone.

1. Protect `main`: require pull requests, require the `pipeline` status check from **Project checks**, dismiss stale approvals if reviews are used, require branches to be up to date, block force pushes and branch deletion, and restrict who can push.
2. In **Settings → Code security and analysis**, enable Dependabot alerts and security updates, secret scanning, and push protection when available for this repository/plan. Review existing alerts rather than assuming a clean dashboard means every secret type is covered.
3. Keep the Actions token least-privileged. Workflows should declare `permissions` explicitly and grant write permissions only to the individual job that needs them.
4. Review every pull request that changes workflow files, dependency manifests, publishing code, or credential handling. Pin third-party Actions to full commit SHAs and verify the release SHA before updating it.
5. If a credential may have been committed, revoke/rotate it immediately; deleting the visible file is not sufficient because Git history can retain it.
6. Keep OAuth refresh tokens and GitHub tokens outside the repository, restrict local file permissions, and use a dedicated least-privilege token. Do not paste tokens into task prompts or issue comments.

## Dashboard request boundary

The local dashboard accepts state-changing POST requests only when Host and Origin match the dashboard's loopback address and port and the content type is a standard URL-encoded form. Requests without Origin, with a mismatched Host, or with transfer encoding are rejected. This reduces browser-based cross-site request forgery risk; it is not authentication and does not protect against malicious software running on the same device or an attacker controlling the local browser session.
