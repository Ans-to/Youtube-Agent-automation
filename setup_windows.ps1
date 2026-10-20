$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "Offline Agent HQ - Windows setup" -ForegroundColor Cyan
Write-Host "Project: $Root"
Write-Host ""

$PythonCommand = $null
$PythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
    $PythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
} else {
    throw "Python 3.10+ is required. Install it from https://www.python.org/downloads/windows/ and enable Add Python to PATH."
}

$VersionText = & $PythonCommand @PythonArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) { throw "Could not run Python. Reopen PowerShell after installing Python." }
$VersionParts = $VersionText.Trim().Split(".")
$Major = [int]$VersionParts[0]
$Minor = [int]$VersionParts[1]
if (($Major -lt 3) -or (($Major -eq 3) -and ($Minor -lt 10))) {
    throw "Python 3.10 or newer is required. Found $VersionText."
}
Write-Host "Python $VersionText detected." -ForegroundColor Green

if (-not (Test-Path (Join-Path $Root "config.json"))) {
    Copy-Item (Join-Path $Root "config.example.json") (Join-Path $Root "config.json")
    Write-Host "Created local config.json from config.example.json."
} else {
    Write-Host "Keeping existing local config.json unchanged."
}

Write-Host "Checking Python syntax..."
$CompileTargets = @(
    "agent.py", "dashboard.py", "queue_store.py",
    "bridge/bridge.py", "agents/dispatch.py", "agents/orchestrate.py",
    "agents/practice.py", "video_studio/studio.py", "video_studio/production.py",
    "video_studio/voice_backends.py", "video_studio/urdu_tts_adapter.py",
    "video_studio/research.py", "video_studio/validate_render.py",
    "video_studio/validate_frames.py", "video_studio/release_gate.py",
    "video_studio/publish_youtube.py", "product_studio/build_product.py"
)
& $PythonCommand @PythonArgs -m py_compile @CompileTargets
if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed. Do not launch until it is fixed." }

$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm -ErrorAction SilentlyContinue
$FFmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($Node -and $Npm) {
    Write-Host "Installing video renderer dependencies..."
    Push-Location (Join-Path $Root "video_studio")
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
    } finally {
        Pop-Location
    }
    if ($FFmpeg) {
        Write-Host "FFmpeg detected; video rendering prerequisites are present." -ForegroundColor Green
    } else {
        Write-Warning "FFmpeg is missing. The dashboard and task tools can still run, but MP4 rendering cannot. Install FFmpeg and add its bin folder to PATH: https://ffmpeg.org/download.html"
    }
} else {
    Write-Warning "Node.js/npm not detected. The dashboard and task tools can still run, but video rendering needs Node.js LTS, npm, and FFmpeg. See video_studio/README.md."
}

Write-Host ""
Write-Host "Setup checks finished. Run .\start_windows.bat to open Agent HQ." -ForegroundColor Green
Write-Host "The Urdu voice runtime is optional and is offered by START_HERE.bat. Voice weights (~740 MB) download on first Urdu render. English Piper and YouTube OAuth are separate optional setups."
