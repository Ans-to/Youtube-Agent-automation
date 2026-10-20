# Zero-cost local Agent HQ smoke tests (Windows)

This is the no-credit-card alternative to Render. It uses your own Windows PC and does not consume GitHub-hosted Actions minutes.

## Get the test branch

Download the ZIP for branch `render-ci-test-runner`:
https://github.com/Ans-to/Youtube-Agent-automation/archive/refs/heads/render-ci-test-runner.zip

Extract it to a folder you control. Do not extract over a production copy with unsaved changes.

## Prerequisites

- Windows 10/11
- Python 3.10+
- Node.js LTS and npm
- FFmpeg and ffprobe available on PATH
- Internet access for npm packages and Puppeteer's Chromium download

The script doesn't require a payment card, hosted CI service, paid AI API, local model, administrator permissions, or YouTube OAuth. It runs deterministic template mode with synthetic test data.

If Python, Node.js, FFmpeg, and ffprobe are already installed, you can run the test command directly. If FFmpeg or another prerequisite is missing, run this from the repository root first:

```powershell
.\setup_all_windows.ps1
```

It can install FFmpeg portably inside the repository if `winget` is unavailable. If it asks whether to install the optional local AI model, enter `N`; the smoke test does not need that download. The test script automatically detects `tools\ffmpeg\bin` when both FFmpeg executables are present.

## Run

Open PowerShell in the extracted repository folder. If Windows blocks the downloaded script, inspect the file first; then run it in that PowerShell session:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\ci\local\Run-SmokeTests.ps1
```

The script runs syntax checks, JSON validation, product-builder smoke test, the complete Python unit suite, npm dependency audit, renderer input-guard tests, the real synthetic queue/CEO/delegation/video-builder pipeline, and both landscape and vertical MP4 render/validation checks.

## Expected artifacts

- `workspace\render-ci-landscape.mp4`
- `workspace\render-ci-shorts.mp4`
- `workspace\orchestration\task-CI-VIDEO-E2E\pipeline-status.json`
- `workspace\orchestration\task-CI-VIDEO-E2E\video-production\video.mp4`

A PASS means the tests in this script passed on this machine. It does not certify local-model output quality, Urdu narration, actual YouTube publishing, or every possible agent task.

If any phase fails, copy the first failing section and its error output. Don't rerun it repeatedly without changing or diagnosing the cause.
