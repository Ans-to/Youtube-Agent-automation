$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Stop-WithHint([string]$Message, [string]$Hint) {
    Write-Host ""
    Write-Host ("FAILED: " + $Message) -ForegroundColor Red
    Write-Host ("NEXT: " + $Hint) -ForegroundColor Yellow
    exit 1
}

function Invoke-Checked([string]$Label, [string]$Command, [scriptblock]$Action) {
    Write-Host ""
    Write-Host ("=== " + $Label + " ===") -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHint ($Label + " returned exit code " + $LASTEXITCODE) "Read the error immediately above; fix that failure before proceeding."
    }
}

Write-Host "Agent HQ local smoke-test runner" -ForegroundColor Cyan
Write-Host "Repository: $Root"
Write-Host "No Render deployment, credit card, GitHub Actions minutes, or paid AI API is used."
Write-Host "The full test uses synthetic data and the no-model template renderer."

# Prefer the Python Launcher; fall back to python.exe.
$Python = $null
$PythonPrefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
    $PythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    Stop-WithHint "Python was not found." "Install Python 3.10+ from https://www.python.org/downloads/windows/ and enable its PATH option."
}
$PythonVersion = & $Python @PythonPrefix -c "import sys; print('%s.%s' % sys.version_info[:2])"
if ($LASTEXITCODE -ne 0) { Stop-WithHint "Python failed to launch." "Reopen PowerShell and check the Python installation." }
$Version = [version]$PythonVersion.Trim()
if ($Version -lt [version]"3.10") { Stop-WithHint ("Found Python " + $Version + "; Python 3.10+ is required.") "Install Python 3.12 from the official Python website." }
Write-Host ("Python " + $Version + " detected.") -ForegroundColor Green

foreach ($Tool in @("node", "npm", "ffmpeg", "ffprobe")) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        if ($Tool -in @("ffmpeg", "ffprobe")) {
            Stop-WithHint ($Tool + " was not found on PATH.") "Install FFmpeg and ensure both ffmpeg.exe and ffprobe.exe are available in PATH, or run the repository's setup_all_windows.ps1 first."
        }
        Stop-WithHint ($Tool + " was not found on PATH.") "Install Node.js LTS (which includes npm) from https://nodejs.org/ and reopen PowerShell."
    }
}
Write-Host "Node.js, npm, FFmpeg and ffprobe detected." -ForegroundColor Green

Write-Host ""
Write-Host "=== 1/8: Python compile checks ===" -ForegroundColor Cyan
$CompileTargets = @(
    "agent.py", "dashboard.py", "queue_store.py", "quality_outputs.py",
    "bridge/bridge.py", "agents/dispatch.py", "agents/adhd_style.py",
    "agents/orchestrate.py", "agents/practice.py",
    "video_studio/studio.py", "video_studio/production.py",
    "video_studio/research.py", "video_studio/validate_render.py",
    "video_studio/validate_frames.py", "video_studio/release_gate.py",
    "video_studio/publish_youtube.py", "product_studio/build_product.py"
)
& $Python @PythonPrefix -m py_compile @CompileTargets
if ($LASTEXITCODE -ne 0) { Stop-WithHint "Python compile checks failed." "Check the first Python syntax error shown above." }

Write-Host ""
Write-Host "=== 2/8: JavaScript and JSON checks ===" -ForegroundColor Cyan
& node --check video_studio/render.js
if ($LASTEXITCODE -ne 0) { Stop-WithHint "JavaScript syntax check failed." "Inspect video_studio/render.js for the reported syntax error." }
foreach ($JsonFile in @("video_studio/storyboard.example.json", "agents/roster.json", "agents/skillbooks.json")) {
    & $Python @PythonPrefix -m json.tool $JsonFile | Out-Null
    if ($LASTEXITCODE -ne 0) { Stop-WithHint ("Invalid JSON: " + $JsonFile) "Correct the JSON error before rerunning." }
}

Write-Host ""
Write-Host "=== 3/8: Product builder smoke test ===" -ForegroundColor Cyan
& $Python @PythonPrefix product_studio/build_product.py --title "Local CI Utility" --idea "Synthetic local smoke-test utility" --out workspace/render-ci-product
if ($LASTEXITCODE -ne 0) { Stop-WithHint "Product builder smoke test failed." "Review the builder error above." }

Write-Host ""
Write-Host "=== 4/8: Full Python unit-test suite ===" -ForegroundColor Cyan
& $Python @PythonPrefix -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { Stop-WithHint "Python unit tests failed." "Use the first failing test name and traceback to diagnose the regression." }

Write-Host ""
Write-Host "=== 5/8: Renderer install and security audit ===" -ForegroundColor Cyan
Push-Location (Join-Path $Root "video_studio")
try {
    & npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Stop-WithHint "npm install failed." "Check internet access and the npm error above." }
    & npm audit --audit-level=high
    if ($LASTEXITCODE -ne 0) { Stop-WithHint "npm audit found a high-severity dependency issue or could not complete." "Review npm audit output; do not blindly force-upgrade dependencies." }

    Write-Host ""
    Write-Host "=== 6/8: Invalid/oversized storyboard guard tests ===" -ForegroundColor Cyan
    $InvalidOutput = (& node render.js storyboard.invalid-transition.json 2>&1 | Out-String)
    $InvalidExit = $LASTEXITCODE
    if ($InvalidExit -eq 0 -or $InvalidOutput -notmatch "Unsupported transition_in") {
        Write-Host $InvalidOutput
        Stop-WithHint "Invalid-transition guard did not fail for the expected reason." "Review the renderer validation changes."
    }
    $LimitOutput = (& node render.js storyboard.over-limit.json 2>&1 | Out-String)
    $LimitExit = $LASTEXITCODE
    if ($LimitExit -eq 0 -or $LimitOutput -notmatch "30000-frame render limit") {
        Write-Host $LimitOutput
        Stop-WithHint "Frame-limit guard did not fail for the expected reason." "Review the renderer frame-limit validation."
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== 7/8: Queue -> CEO -> specialist agents -> video package -> MP4 ===" -ForegroundColor Cyan
& $Python @PythonPrefix ci/render/e2e_smoke.py
if ($LASTEXITCODE -ne 0) { Stop-WithHint "CEO-to-video end-to-end smoke test failed." "Read the pipeline manifest at workspace\orchestration\task-CI-VIDEO-E2E\pipeline-status.json and its tool log." }

Write-Host ""
Write-Host "=== 8/8: Landscape and vertical Shorts renders ===" -ForegroundColor Cyan
& $Python @PythonPrefix video_studio/studio.py --storyboard video_studio/storyboard.smoke.json --output workspace/render-ci-landscape.mp4
if ($LASTEXITCODE -ne 0) { Stop-WithHint "Landscape MP4 render or validation failed." "Check Chromium/Puppeteer dependencies, FFmpeg output, and validate_render.py diagnostics." }
& $Python @PythonPrefix video_studio/studio.py --storyboard video_studio/storyboard.smoke-shorts.json --output workspace/render-ci-shorts.mp4
if ($LASTEXITCODE -ne 0) { Stop-WithHint "Vertical Shorts render or validation failed." "Check Chromium/Puppeteer dependencies, FFmpeg output, and validate_render.py diagnostics." }

Write-Host ""
Write-Host "ALL LOCAL SMOKE TESTS PASSED" -ForegroundColor Green
Write-Host "Landscape video: workspace\render-ci-landscape.mp4"
Write-Host "Shorts video:    workspace\render-ci-shorts.mp4"
Write-Host "CEO pipeline:    workspace\orchestration\task-CI-VIDEO-E2E\pipeline-status.json"
Write-Host "This proves the synthetic no-model test path only; local-model quality and publishing are not certified."
