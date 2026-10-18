# Offline Agent HQ — local Android notes

The canonical project documentation is [README.md](README.md). This file is kept for local Android/Termux notes and may be opened from the existing phone folder.

## Local data files

These are intentionally local and ignored by Git:
- `config.json`: private runtime settings; copy from `config.example.json` when creating a fresh setup.
- `tasks.json`: local queue and task statuses.
- `workspace/`: local reference documents.
- `outputs/`: generated Markdown outputs.
- `logs/`: operational logs.

Do not commit these files or place secrets in task prompts.

## Dashboard

Start with `python dashboard.py`, then open `http://127.0.0.1:8765` in a browser on the same phone. The dashboard must remain bound to loopback. It queues tasks and invokes the local runner; it is not a public web service.

## Local task runner

Run one cycle with `python agent.py --once`. Repeated mode is optional and best-effort on Android:

```sh
termux-wake-lock
python agent.py --loop --interval 60
```

Stop with Ctrl+C and release the wake lock with `termux-wake-unlock`.

Without a compatible local language model, the runner emits limited templates and checklists, not capable general-purpose AI. A configured model endpoint must be on loopback.

## GitHub bridge

The bridge polls approved requests from GitHub while the phone runs `python bridge/bridge.py`. It supports status, syntax-only self-test, and guarded execution of an existing local task. It does not accept task text or arbitrary commands from GitHub.

Results are stored locally first. The bridge also attempts to upload sanitized metadata to `bridge/results/`; task prompts, outputs, raw logs, local paths, and configuration values are excluded. The local token file must have repository Contents read/write permission for both polling and reporting. Never commit or paste the token.

Read [bridge/README.md](bridge/README.md) and [SECURITY.md](SECURITY.md) before enabling watch mode. Android may stop background processes.

## Checks

```sh
python -m py_compile agent.py dashboard.py bridge/bridge.py
python -m unittest discover -s tests -v
```

GitHub Actions runs the same syntax and unit-test checks on Python 3.11 and 3.12.
