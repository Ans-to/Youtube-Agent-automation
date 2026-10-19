$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Has-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage([string]$Id, [string]$Label) {
    if (-not (Has-Command "winget")) {
        throw "Windows Package Manager (winget) is unavailable. Install/update 'App Installer' from Microsoft Store, then run START_HERE.bat again. Missing prerequisite: $Label."
    }
    Write-Host "Installing $Label if needed..." -ForegroundColor Cyan
    & winget install --id $Id --exact --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget did not report a successful install for $Label. Checking whether the command is available already."
    }
    Refresh-Path
}

Write-Host ""
Write-Host "Offline Agent HQ - automatic Windows setup" -ForegroundColor Cyan
Write-Host "Project: $Root"
Write-Host "This setup never needs administrator access intentionally; winget may request it for a selected package."
Write-Host ""

if (-not (Has-Command "py") -and -not (Has-Command "python")) {
    Install-WingetPackage "Python.Python.3.12" "Python 3.12"
}
if (-not (Has-Command "node") -or -not (Has-Command "npm")) {
    Install-WingetPackage "OpenJS.NodeJS.LTS" "Node.js LTS and npm"
}
if (-not (Has-Command "ffmpeg")) {
    Install-WingetPackage "Gyan.FFmpeg" "FFmpeg video encoder"
}

Refresh-Path
if (-not (Has-Command "py") -and -not (Has-Command "python")) {
    throw "Python was not detected after installation. Close this window, reopen START_HERE.bat, or install Python 3.12 from https://www.python.org/downloads/windows/."
}
if (-not (Has-Command "node") -or -not (Has-Command "npm")) {
    throw "Node.js/npm was not detected after installation. Reopen START_HERE.bat after installation finishes."
}
if (-not (Has-Command "ffmpeg")) {
    throw "FFmpeg was not detected after installation. Reopen START_HERE.bat after installation finishes."
}

Write-Host "Installing/checking project dependencies..." -ForegroundColor Cyan
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "setup_windows.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Project dependency setup failed. See the error above."
}

Write-Host ""
$answer = Read-Host "Install free local AI runtime + llama3.2:3b model (about 2 GB download; recommended) [Y/n]"
if ([string]::IsNullOrWhiteSpace($answer) -or $answer.Trim().ToLowerInvariant() -eq "y" -or $answer.Trim().ToLowerInvariant() -eq "yes") {
    if (-not (Has-Command "ollama")) {
        Install-WingetPackage "Ollama.Ollama" "Ollama local AI runtime"
    }
    Refresh-Path
    $Ollama = Get-Command "ollama" -ErrorAction SilentlyContinue
    if (-not $Ollama) {
        throw "Ollama was installed but is not yet available on PATH. Restart Windows or open a new terminal, then rerun START_HERE.bat."
    }

    try {
        & ollama list *> $null
        if ($LASTEXITCODE -ne 0) { throw "Ollama server not ready" }
    } catch {
        Start-Process -FilePath $Ollama.Source -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 4
    }

    Write-Host "Downloading local model llama3.2:3b. This may take several minutes..." -ForegroundColor Cyan
    & ollama pull llama3.2:3b
    if ($LASTEXITCODE -ne 0) {
        throw "The local model download failed. Dashboard/video tools are installed, but model-based CEO and specialist work is not enabled. Rerun START_HERE.bat when internet is stable."
    }

    $ConfigPath = Join-Path $Root "config.json"
    $Config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
    if (-not $Config.model) {
        $Config | Add-Member -NotePropertyName model -NotePropertyValue ([pscustomobject]@{})
    }
    $Config.model.enabled = $true
    $Config.model.base_url = "http://127.0.0.1:11434/v1/chat/completions"
    $Config.model.model = "llama3.2:3b"
    if (-not $Config.model.max_output_tokens) { $Config.model.max_output_tokens = 2200 }
    if (-not $Config.model.product_max_output_tokens) { $Config.model.product_max_output_tokens = 3500 }
    if (-not $Config.model.timeout_seconds) { $Config.model.timeout_seconds = 180 }
    $Config | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 -Path $ConfigPath
    Write-Host "Local model configured. No paid API key was added." -ForegroundColor Green
} else {
    Write-Host "Skipped local AI model. The dashboard and deterministic tools work, but advanced AI output requires a compatible local model." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete. Starting Agent HQ..." -ForegroundColor Green
& (Join-Path $Root "start_windows.bat")
