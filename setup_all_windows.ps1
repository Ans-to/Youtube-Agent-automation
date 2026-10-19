$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"

    # Preserve project-local portable tools after refreshing the system PATH.
    $PortableFfmpegBin = Join-Path $Root "tools\ffmpeg\bin"
    if (Test-Path (Join-Path $PortableFfmpegBin "ffmpeg.exe")) {
        $env:Path = "$PortableFfmpegBin;$env:Path"
    }
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
$NodeMajor = 0
if (Has-Command "node") { $NodeMajor = [int]((& node -p "process.versions.node.split(String.fromCharCode(46))[0]").Trim()) }
if ($NodeMajor -gt 0 -and $NodeMajor -lt 22) { Install-WingetPackage "OpenJS.NodeJS.LTS" "Node.js 22+ LTS and npm" }
function Install-PortableFfmpeg {
    $ToolsRoot = Join-Path $Root "tools"
    $FfmpegRoot = Join-Path $ToolsRoot "ffmpeg"
    $FfmpegExe = Join-Path $FfmpegRoot "bin\ffmpeg.exe"
    if (Test-Path $FfmpegExe) {
        $env:Path = "$FfmpegRoot\bin;$env:Path"
        return
    }

    New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null
    $ZipPath = Join-Path $ToolsRoot "ffmpeg-release-essentials.zip"
    $DownloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    Write-Host "winget is unavailable. Downloading a portable FFmpeg build directly..." -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath -UseBasicParsing
        $ExtractRoot = Join-Path $ToolsRoot "ffmpeg-extract"
        if (Test-Path $ExtractRoot) { Remove-Item $ExtractRoot -Recurse -Force }
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractRoot -Force
        $Found = Get-ChildItem -Path $ExtractRoot -Filter ffmpeg.exe -Recurse -File | Select-Object -First 1
        if (-not $Found) { throw "The downloaded archive did not contain ffmpeg.exe." }
        $SourceBin = $Found.Directory.FullName
        if (Test-Path $FfmpegRoot) { Remove-Item $FfmpegRoot -Recurse -Force }
        $FfmpegBin = Join-Path $FfmpegRoot "bin"
        New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null
        Copy-Item -Path (Join-Path $SourceBin "*") -Destination $FfmpegBin -Recurse -Force
        $FfmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
        if (-not (Test-Path $FfmpegExe)) {
            throw "FFmpeg archive was extracted, but ffmpeg.exe was not copied to the expected location: $FfmpegExe"
        }
        $env:Path = "$FfmpegBin;$env:Path"
        Remove-Item $ExtractRoot -Recurse -Force
        Remove-Item $ZipPath -Force
        if (-not (Has-Command "ffmpeg")) {
            & $FfmpegExe -version | Select-Object -First 1
            if ($LASTEXITCODE -ne 0) { throw "FFmpeg executable exists but could not start." }
        }
        Write-Host "Portable FFmpeg installed inside the project; no administrator rights or winget required." -ForegroundColor Green
    } catch {
        throw "Could not install FFmpeg automatically. Check internet access, then retry. Details: $($_.Exception.Message)"
    }
}

if (-not (Has-Command "ffmpeg")) {
    if (Has-Command "winget") {
        Install-WingetPackage "Gyan.FFmpeg" "FFmpeg video encoder"
    } else {
        Install-PortableFfmpeg
    }
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
$answer = Read-Host "Install optional free local AI runtime + llama3.2:3b model (large download; requires winget or a manual install) [y/N]"
if ($answer.Trim().ToLowerInvariant() -eq "y" -or $answer.Trim().ToLowerInvariant() -eq "yes") {
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
    [System.IO.File]::WriteAllText($ConfigPath, ($Config | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Local model configured. No paid API key was added." -ForegroundColor Green
} else {
    Write-Host "Skipped local AI model. The dashboard and deterministic tools work, but advanced AI output requires a compatible local model." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete. Starting Agent HQ..." -ForegroundColor Green
& (Join-Path $Root "start_windows.bat")
