# Offline Agent HQ for Android

A local-first Android task dashboard designed for Termux. It queues tasks, runs them through Coordinator → Planner → Worker → Reviewer stages, saves Markdown outputs, and optionally calls a language model hosted on the same phone.

## What this version is (and is not)

- It is a runnable local task manager with a mobile-friendly dashboard.
- Without a local language model, it can run simple template-based tasks and workspace summaries. That mode is **not a capable general AI**.
- For useful natural-language reasoning offline, install a compatible local inference server and model, then enable the localhost endpoint in `config.json`.
- “Agents” here are specialist stages in one Python process, not separate autonomous beings. This is deliberate for low RAM.
- It does not browse the internet, send messages, publish videos, buy anything, execute model-generated shell commands, or access other apps.
- Android can stop background processes. Overnight operation is best-effort, not guaranteed.

## Install on Android

1. Install **Termux** from F-Droid or the official Termux GitHub releases. Avoid obsolete Play Store versions.
2. Extract this ZIP to your phone's Downloads folder. In Termux:

```sh
pkg update
pkg install python
termux-setup-storage
cd ~/storage/downloads/OfflineAgentHQ
chmod +x start.sh run_once.sh
./start.sh
```

If you extracted it to a different folder, `cd` to that folder instead.

3. The dashboard opens at `http://127.0.0.1:8765`. Open that address in your phone browser. Keep Termux open.
4. Add a task in the dashboard and tap **Queue task**.
5. Tap **Run pending tasks** or run `./run_once.sh` in Termux.

## Overnight mode

In Termux:

```sh
termux-wake-lock
python agent.py --loop --interval 60
```

Connect the phone to power. In Android settings, set Termux battery use to **Unrestricted** or disable battery optimization if your phone offers that option. Android vendors vary, and background execution is never guaranteed. Stop the loop with Ctrl+C; release the wake lock with `termux-wake-unlock`.

## Optional local AI model

To use stronger offline reasoning, you need a local inference server running on the same phone and a model downloaded to local storage. The server must expose an OpenAI-compatible endpoint at:

`http://127.0.0.1:8080/v1/chat/completions`

Edit `config.json` and set `"enabled": true` in `"model"`. The program rejects non-loopback model URLs to prevent accidentally sending task data to a remote service.

This ZIP does **not** include model weights or an inference server because model files are large and device compatibility varies. On an 8 GB phone, start with a small quantized 1B–3B model, short context, and test memory use. Some Android chipsets may not run the recommended model efficiently.

## Supported task types

- `plan`: create a step-by-step plan
- `draft`: draft text based on your prompt
- `summarize_workspace`: summarize local notes (with a model) or list their content (fallback)
- `review_output`: review local notes (with a model) or produce a checklist (fallback)

Place `.txt`, `.md`, or `.json` files in `workspace/`. Outputs go to `outputs/`; logs go to `logs/`.

## Troubleshooting

- If `python` is missing: `pkg install python`
- If the browser page does not open: check the Termux window for the server URL; use `http://127.0.0.1:8765`.
- If the dashboard is stopped, restart with `./start.sh`.
- If the phone sleeps and tasks stop: connect to power, use `termux-wake-lock`, and set battery usage to unrestricted.
- If local AI requests fail: confirm your local model server is running, the endpoint is loopback, and its API format is OpenAI-compatible.

## Privacy and safety

This project has no external network integrations. The dashboard binds to `127.0.0.1`, so it is available only from the phone itself. Tasks are stored locally as JSON and Markdown. Do not enter passwords, API keys, or sensitive personal information.
