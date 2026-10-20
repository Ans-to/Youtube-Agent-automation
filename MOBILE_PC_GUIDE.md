# Agent HQ on PC and Android

Offline Agent HQ uses a browser-based, responsive dashboard with a Python local backend. The same project can be run on Windows and Android/Termux; the dashboard layout adapts to narrow phone screens. This is not currently a hosted, multi-device SaaS service.

## Windows PC

1. Install Python 3.10 or newer.
2. Optional for MP4 rendering: install Node.js LTS and FFmpeg, and ensure both node and ffmpeg work in PowerShell.
3. Run setup_windows.ps1 in PowerShell to create local configuration, check Python syntax, and install renderer dependencies when Node/npm are available.
4. Run start_windows.bat, or from the project root run python dashboard.py.
5. Open the local address printed by the dashboard in your browser.

The local model is disabled by default. The dashboard and template workflows can run without API keys, but meaningful AI generation requires a compatible local inference server configured in your private config.json. Local video rendering requires Node.js, Chromium/Puppeteer, and FFmpeg. Optional Urdu narration requires a compatible local Piper model. Optional YouTube uploads require Google OAuth and explicit release approval.

## Android phone

1. Install Termux from F-Droid or the official Termux GitHub releases.
2. Put this repository in a Termux-accessible directory and open Termux there.
3. Run the following commands:

   pkg update
   pkg install python git
   cp config.example.json config.json
   python dashboard.py

   Skip the cp command if you already have a private config.json; do not overwrite your settings.

4. Open http://127.0.0.1:8765 in the phone's browser. If the server prints a different port, use the printed address.

Android can run the dashboard, manage the local task queue, and create drafts. Rendering long videos on a phone is resource-intensive and may be unreliable due to memory, heat, storage, and Android background-process limits. Use a PC for longer renders when possible.

## What “works on both devices” means today

- The interface is responsive and usable in modern desktop and mobile browsers.
- Each device runs its own local backend and local workspace when started separately.
- Local tasks, configuration, and outputs are not automatically synchronized between the phone and PC.
- The dashboard deliberately binds to loopback only. A dashboard running on the PC cannot be opened directly from the phone over Wi-Fi by replacing 127.0.0.1 with the PC address. Do not expose the unauthenticated local dashboard to a LAN or the public internet.
- The optional GitHub bridge is a separate, allowlisted request/result channel. It is not a live remote desktop, does not provide arbitrary shell access, and requires a repository-scoped token stored locally. Review the exact request before approving it.

## Submit tasks from the GitHub mobile app when the PC is unavailable

The local dashboard itself is not a hosted website, so a phone browser cannot directly control a PC that is offline. To prepare tasks from your phone without using GitHub Actions, the repository now has a separate operational branch named `mobile-agent-inbox`.

1. Open [mobile inbox instructions](https://github.com/Ans-to/Youtube-Agent-automation/blob/mobile-agent-inbox/bridge/requests/README.md) and make sure the branch selector shows `mobile-agent-inbox`.
2. In `bridge/requests`, create a **new JSON file** with a unique request ID, `approved: true`, `action: "create_task"`, a title, an allowed task kind, and the task instructions. The exact template is in the linked README.
3. To have the Android device process the request locally, update the existing Termux clone to the integration branch after reviewing any local changes, then set `AGENT_HQ_BRANCH=mobile-agent-inbox` in the shell before running `python bridge/bridge.py --watch --interval=30`. The GitHub token must remain in the local token file described in the main README.
4. The bridge polls the separate inbox branch, creates a local pending task, and uploads a sanitized status file to that same branch. Task creation is not task execution.
5. For later Windows processing, run the bridge from the Windows project checkout with the same branch setting, or enter the task in the PC dashboard. **The phone and PC queues are separate**; no background synchronization is claimed.

Important limits:
- This works without GitHub Actions and without a paid hosted worker, but the bridge only runs while Termux is active and connected. Android may suspend it.
- A phone can create drafts and smaller local-model tasks if a compatible model is configured. Long narrated MP4 rendering is likely to be slow or unreliable on a phone; keep it queued for the PC when available.
- Request JSON is committed to a private GitHub branch and remains in Git history. Never include secrets, tokens, passwords, confidential material, or sensitive personal data.
- Keep the inbox branch separate. Do not merge `mobile-agent-inbox` into `main`, and do not merge PR #11 unless separately authorized.

## Ready-to-use vs. external setup

| Capability | Works without paid APIs? | Additional setup |
|---|---|---|
| Dashboard and local task queue | Yes | Python |
| Template drafts and product starter | Yes | Python |
| AI-generated scripts and agent work | Yes, with a local model | Install/run a compatible local inference server; configure config.json |
| MP4 rendering | Yes | Node.js/npm, Puppeteer Chromium, FFmpeg |
| Urdu narration | Yes, if a compatible model is available | Piper CLI and a legally obtained Urdu-capable voice model |
| YouTube upload | No credentials bundled | Google OAuth desktop client, API access, release approval |
| Shared phone/PC workspace | Not built in | A secure authenticated remote backend/sync layer is required |

## Security

- Keep config.json, GitHub tokens, OAuth client secrets, YouTube tokens, task inputs, and private outputs out of Git.
- Do not put credentials, financial records, or other sensitive personal data into agent prompts.
- Do not disable the approval gates or expose the loopback dashboard publicly to make remote access appear to work.
- The specialist roles share a configured model and use playbooks; role profiles do not fine-tune separate model weights.
- A successful syntax check or smoke test does not prove professional visual quality or factual correctness. Inspect scripts, sources, renders, and metadata before publication.
