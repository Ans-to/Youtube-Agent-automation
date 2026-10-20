$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "Offline Agent HQ - Windows Urdu voice setup" -ForegroundColor Cyan
Write-Host "This installs Piper (CPU/ONNX Runtime) in an isolated .venv-piper-urdu."
Write-Host "It does not modify the main Agent HQ Python environment or config.json."
Write-Host "The Pakistani Urdu male Fasih model is about 64 MB and downloads on first preview."
Write-Host ""

$PythonCommand = $null
$PythonArgs = @()
$VersionText = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    # Prefer a version explicitly listed by the Piper package, rather than silently
    # choosing a newer interpreter. Fall back to the installed default only if needed.
    foreach ($Candidate in @("3.13", "3.12", "3.11", "3.10", "3.9")) {
        $DetectedVersion = (& py "-$Candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $DetectedVersion -eq $Candidate) {
            $PythonCommand = "py"
            $PythonArgs = @("-$Candidate")
            $VersionText = $DetectedVersion
            break
        }
    }
    if (-not $PythonCommand) {
        $DetectedVersion = (& py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "py"
            $PythonArgs = @("-3")
            $VersionText = $DetectedVersion
        }
    }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
    $VersionText = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
} else {
    throw "Python 3.9+ is required. Install Python from https://www.python.org/downloads/windows/ and rerun this script."
}

if (-not $PythonCommand -or -not $VersionText) {
    throw "Could not run Python; verify that Python is installed and available on PATH."
}
$VersionParts = $VersionText.Split(".")
$Major = [int]$VersionParts[0]
$Minor = [int]$VersionParts[1]
if (($Major -lt 3) -or (($Major -eq 3) -and ($Minor -lt 9))) {
    throw "Piper requires Python 3.9 or newer; detected $VersionText."
}
if (($Major -eq 3) -and ($Minor -gt 13)) {
    Write-Warning "Piper 1.8.0 publishes a Windows ABI3 wheel but currently lists tested Python versions through 3.13. Attempting Python $VersionText; if a dependency wheel is unavailable, install Python 3.13 side-by-side and rerun this script."
}

$VenvRoot = Join-Path $Root ".venv-piper-urdu"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating isolated voice environment with Python $VersionText..." -ForegroundColor Cyan
    & $PythonCommand @PythonArgs -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        throw "Could not create .venv-piper-urdu with Python $VersionText."
    }
} else {
    $ExistingVersion = (& $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect the existing .venv-piper-urdu interpreter." }
    $ExistingParts = $ExistingVersion.Split(".")
    if ([int]$ExistingParts[0] -lt 3 -or ([int]$ExistingParts[0] -eq 3 -and [int]$ExistingParts[1] -lt 9)) {
        throw "The existing .venv-piper-urdu is older than Python 3.9. It was left untouched; rename that dedicated environment and rerun this installer."
    }
    Write-Host "Reusing isolated voice environment (Python $ExistingVersion)." -ForegroundColor DarkGray
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip inside .venv-piper-urdu." }

& $VenvPython -m pip install -r (Join-Path $Root "video_studio\requirements-urdu-tts.txt")
if ($LASTEXITCODE -ne 0) { throw "Piper/ONNX dependencies failed to install inside .venv-piper-urdu. The main Agent HQ Python was not changed." }

& $VenvPython (Join-Path $Root "video_studio\piper_urdu_tts_adapter.py") --check-dependencies
if ($LASTEXITCODE -ne 0) { throw "Piper runtime import verification failed. Inspect the error above; Urdu voice remains unavailable." }

Write-Host ""
Write-Host "Urdu voice runtime installed and import-checked." -ForegroundColor Green
Write-Host "Next, generate an audio-only preview using the command documented in video_studio\README.md." -ForegroundColor Cyan
Write-Host "The first preview downloads and checksum-verifies the pinned Urdu voice model (~64 MB)."
