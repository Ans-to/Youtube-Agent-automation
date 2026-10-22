# Running Agent HQ from VS Code

The dashboard is a plain Python HTTP server with no third-party dependencies. VS Code only needs to launch `dashboard.py`; everything else is the same as running it from a terminal.

The repository ships three small files so this is one keypress:

- `.vscode/launch.json` — debug configurations (F5)
- `.vscode/tasks.json` — Background tasks (Terminal → Run Task)
- `.vscode/extensions.json` — recommended extensions

Do not confuse `.vscode/tasks.json` (VS Code task definitions) with the repository-root `tasks.json` (the local task queue, deliberately Git-ignored).

## Prerequisites

1. **Python 3.10 or newer.** On Windows, install from python.org and tick *Add python.exe to PATH*. Verify in a terminal:

   ```powershell
   python --version
   ```

2. **VS Code** with the Python extension. Opening the folder prompts you to install the recommended extensions; accept, or install `ms-python.python` manually.

3. **Open the project folder**, not a single file: *File → Open Folder* → select the repository root. The launch configuration resolves `${workspaceFolder}` relative to it.

## First run

The dashboard works without a configuration file, but creating one gives you a place to set the port and enable a local model later.

In the VS Code terminal (`` Ctrl+` ``):

```powershell
copy config.example.json config.json
```

On Linux/macOS use `cp config.example.json config.json`. `config.json` is Git-ignored; keep it local and never commit it.

## Start the dashboard

1. Press **F5** and pick **Agent HQ: Dashboard** the first time. VS Code remembers the choice.
2. The integrated terminal prints:

   ```text
   Holographic Offline Agent HQ: http://127.0.0.1:8765
   ```

3. The browser opens that address automatically (`serverReadyAction` in `launch.json`). If it does not, Ctrl+Click the printed link.

Stop it with **Shift+F5**, or click the terminal and press `Ctrl+C`.

Equivalent without debugging: **Ctrl+F5**, or Terminal → Run Task → **OfflineAgentHQ: Start dashboard**.

## What the other configurations do

| Configuration | Equivalent command | Use |
| --- | --- | --- |
| Agent HQ: Dashboard | `python dashboard.py` | Serve the UI at `127.0.0.1:8765` |
| Agent HQ: Process one queued task | `python agent.py --once` | Run the queue worker once |
| Agent HQ: Task loop (60s interval) | `python agent.py --loop --interval 60` | Repeated processing while the window stays open |

The dashboard also starts the queue worker itself when pending tasks exist, so you rarely need the second configuration for normal use.

## Debugging the request handlers

Because `HTTPServer` is single-threaded, a breakpoint in `Handler.do_GET` or `Handler.do_POST` stops the process between requests — exactly where you want it.

1. Open `dashboard.py`, click in the gutter to set a breakpoint (or press F9 on the line).
2. Press F5 with **Agent HQ: Dashboard**.
3. Reload the page or submit a form; execution pauses at the breakpoint.
4. Use the Debug sidebar to inspect `self.path`, parsed query parameters, and the request headers.

`justMyCode` is enabled, so stepping skips the standard library. Set it to `false` in `launch.json` only when you need to trace inside `http.server`.

## Running the CEO pipeline

The pipeline is a one-shot command, not a server, so it is easiest from the terminal:

```powershell
python agents/orchestrate.py --task "Describe the goal here" --out workspace/orchestration/vscode-run
```

Useful flags: `--note "review comment"`, `--resume` (continue an interrupted run), `--profile low` (force a lighter device tier). See `docs/ROUTING.md` and `docs/ADAPTIVE.md`.

## Where output goes

| Path | Contents |
| --- | --- |
| `outputs/` | Markdown results per finished task |
| `logs/` | Operational logs, including `pipeline.log` |
| `workspace/orchestration/` | Per-run pipeline artifacts (`changes.md`, `changes.json`, `routing.json`, …) |
| `workspace/research/` | Saved research findings |
| `tasks.json` | Local queue and task statuses |

All of these are Git-ignored. Review before copying anything into a tracked file.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `OSError: [Errno 98/10048] Address already in use` | Another instance is running. Stop it (Shift+F5 in the other window), or close the terminal that launched it. On Windows: `netstat -ano \| findstr :8765`, then `taskkill /PID <pid> /F`. Or change `dashboard.port` in `config.json`. |
| `python` is not recognized | Interpreter not on PATH. Press `Ctrl+Shift+P` → *Python: Select Interpreter*, pick the 3.10+ install, then retry. |
| `ModuleNotFoundError` on launch | Wrong interpreter selected, or the folder opened is not the repository root. Re-check both. |
| `Safety check: dashboard must bind to loopback only.` | `config.json` has `dashboard.host` set to something other than `127.0.0.1`, `localhost`, or `::1`. Restore it. This guard is intentional. |
| Page shows `TEMPLATE MODE` | No local model configured. Expected by default; output is labelled template content, not AI-generated text. |
| Browser opens a blank/refused page | The server may have exited on startup. Read the terminal: a port clash or config error appears there. |
| Windows Firewall prompt | Not required for loopback. Decline; the dashboard never listens on a LAN interface. |
| Using Remote-SSH / Remote-WSL | The server runs where VS Code's backend runs. WSL forwards `localhost` to Windows, so the browser still reaches it. Do **not** publish the port through a tunneling service: the dashboard rejects non-loopback `Host` headers by design. |

## Checks before committing

Terminal → Run Task offers:

- **OfflineAgentHQ: Run local tests** — `python -m unittest discover -s tests -v` (also bound to `Ctrl+Shift+P` → *Tasks: Run Test Task*)
- **OfflineAgentHQ: Syntax check** — `python -m py_compile` on the entry points

GitHub Actions runs the same checks plus the invariant guard, so a green local run is a fast pre-check, not a replacement.
