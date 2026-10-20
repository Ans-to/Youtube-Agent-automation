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
        # Windows PowerShell 5.1 may otherwise negotiate an obsolete TLS version.
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath -UseBasicParsing -TimeoutSec 180
        if (-not (Test-Path $ZipPath) -or (Get-Item $ZipPath).Length -lt 1000000) {
            throw "The FFmpeg download is missing or unexpectedly small; check internet access or proxy filtering."
        }
        $ExtractRoot = Join-Path $ToolsRoot "ffmpeg-extract"
        if (Test-Path $ExtractRoot) { Remove-Item $ExtractRoot -Recurse -Force }
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractRoot -Force
        $Found = Get-ChildItem -Path $ExtractRoot -Filter ffmpeg.exe -Recurse -File | Select-Object -First 1
        if (-not $Found) { throw "The downloaded archive did not contain ffmpeg.exe." }
        $SourceBin = $Found.Directory.FullName
        if (Test-Path $FfmpegRoot) { Remove-Item $FfmpegRoot -Recurse -Force }
        $FfmpegBin = Join-Path $FfmpegRoot "bin"
        New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null
        # Copy each archive member explicitly. Pipeline-based Copy-Item can behave
        # inconsistently with FileInfo/DirectoryInfo objects in Windows PowerShell 5.1.
        Get-ChildItem -LiteralPath $SourceBin -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $FfmpegBin -Recurse -Force
        }
        $FfmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
        $FfprobeExe = Join-Path $FfmpegBin "ffprobe.exe"
        # Some archive layouts put binaries in a nested bin folder; locate and flatten
        # the required executables if the first copy did not preserve the expected layout.
        if (-not (Test-Path -LiteralPath $FfmpegExe)) {
            $NestedBin = Get-ChildItem -Path $FfmpegRoot -Filter ffmpeg.exe -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($NestedBin) {
                Get-ChildItem -LiteralPath $NestedBin.Directory.FullName -Force | ForEach-Object {
                    Copy-Item -LiteralPath $_.FullName -Destination $FfmpegBin -Recurse -Force
                }
            }
        }
        if (-not (Test-Path -LiteralPath $FfmpegExe)) {
            $Copied = Get-ChildItem -Path $FfmpegRoot -Filter ffmpeg.exe -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
            $Listing = (Get-ChildItem -Path $ExtractRoot -Force | Select-Object -ExpandProperty Name) -join ", "
            throw "FFmpeg archive was extracted, but ffmpeg.exe was not copied to the expected location. Extracted folders: $Listing. Expected: $FfmpegExe"
        }
        if (-not (Test-Path -LiteralPath $FfprobeExe)) {
            Write-Warning "ffprobe.exe was not found beside ffmpeg.exe; video validation may be unavailable."
        }
        $env:Path = "$FfmpegBin;$env:Path"
        # Test the executable directly instead of relying only on PATH command discovery.
        # Capture the complete native-process output before selecting a display line.
        # Piping ffmpeg directly into Select-Object -First 1 can close stdout early;
        # FFmpeg may then exit non-zero even though the executable works.
        $VersionOutput = @(& $FfmpegExe -version 2>&1)
        $FfmpegExitCode = $LASTEXITCODE
        $VersionLine = if ($VersionOutput.Count -gt 0) { [string]$VersionOutput[0] } else { "(no version output)" }
        if ($FfmpegExitCode -ne 0) { throw "FFmpeg executable exists but failed its version check (exit code $FfmpegExitCode). Output: $VersionLine" }
        Write-Host $VersionLine -ForegroundColor DarkGray
        Remove-Item $ExtractRoot -Recurse -Force
        Remove-Item $ZipPath -Force
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

$UrduTtsAnswer = Read-Host "Install optional CPU-only Urdu voice dependencies into an isolated .venv-urdu-tts? Model and codec weights add roughly 1.5 GB on first use [y/N]"
if ($UrduTtsAnswer.Trim().ToLowerInvariant() -in @("y", "yes")) {
    # Keep NeMo/Transformers/PyTorch isolated from Agent HQ's main Python runtime.
    # Kani's upstream example documents Python 3.10–3.12; probe installed interpreters
    # explicitly because "py -3" may select Python 3.13 even when Python 3.12 is installed.
    $VoicePythonSelector = $null
    $VoicePythonCommand = $null
    $VoicePythonVersion = $null

    if (Has-Command "py") {
        foreach ($Candidate in @("3.12", "3.11", "3.10")) {
            $DetectedVersion = (& py "-$Candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
            if ($LASTEXITCODE -eq 0 -and $DetectedVersion -eq $Candidate) {
                $VoicePythonSelector = "-$Candidate"
                $VoicePythonCommand = "py"
                $VoicePythonVersion = $DetectedVersion
                break
            }
        }
    }

    if (-not $VoicePythonCommand -and (Has-Command "python")) {
        $DetectedVersion = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($LASTEXITCODE -eq 0 -and $DetectedVersion -in @("3.10", "3.11", "3.12")) {
            $VoicePythonCommand = "python"
            $VoicePythonVersion = $DetectedVersion
        }
    }

    if (-not $VoicePythonCommand) {
        throw "Kani TTS dependencies require Python 3.10, 3.11, or 3.12. Install Python 3.12 side-by-side and rerun START_HERE.bat. Agent HQ's core runtime may continue using another supported Python version; the Urdu voice environment is separate."
    }

    $UrduVenvRoot = Join-Path $Root ".venv-urdu-tts"
    $UrduVenvPython = Join-Path $UrduVenvRoot "Scripts\python.exe"

    if (-not (Test-Path $UrduVenvPython)) {
        Write-Host "Creating isolated Urdu TTS environment with Python $VoicePythonVersion..." -ForegroundColor Cyan
        if ($VoicePythonCommand -eq "py") {
            & py $VoicePythonSelector -m venv $UrduVenvRoot
        } else {
            & python -m venv $UrduVenvRoot
        }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $UrduVenvPython)) {
            throw "Could not create .venv-urdu-tts with Python $VoicePythonVersion."
        }
    } else {
        $ExistingVoiceVersion = (& $UrduVenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($LASTEXITCODE -ne 0 -or $ExistingVoiceVersion -notin @("3.10", "3.11", "3.12")) {
            throw "The existing .venv-urdu-tts does not use a supported Python 3.10–3.12 interpreter. It was left untouched. Back up or remove that dedicated virtual-environment folder and rerun START_HERE.bat."
        }
        Write-Host "Reusing isolated Urdu TTS environment with Python $ExistingVoiceVersion." -ForegroundColor DarkGray
    }

    & $UrduVenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not update pip inside .venv-urdu-tts." }
    & $UrduVenvPython -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw "CPU-only PyTorch install failed inside .venv-urdu-tts. Urdu voice remains unavailable; see video_studio/README.md." }
    & $UrduVenvPython -m pip install -r (Join-Path $Root "video_studio\requirements-urdu-tts.txt")
    if ($LASTEXITCODE -ne 0) { throw "Urdu TTS dependencies did not finish installing inside .venv-urdu-tts. The main Agent HQ Python environment was not modified." }

    & $UrduVenvPython -c "import torch, transformers; from nemo.collections.tts.models import AudioCodecModel; print('Urdu TTS runtime imports OK; torch=' + torch.__version__ + '; transformers=' + transformers.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Kani/NeMo runtime import verification failed. Urdu voice remains unavailable; keep the approval flag false and inspect the error above." }

    Write-Host "Isolated Urdu voice dependencies installed and import-checked. The pinned Urdu model and codec weights download on first preview/render; allow roughly 1.5 GB of cache plus runtime memory." -ForegroundColor Green
} else {
    Write-Warning "Skipped Urdu voice dependencies. Urdu-English voice previews and production renders will fail with a clear missing-dependency error until the optional runtime is installed."
}

function Get-OllamaModelList {
    # Try the existing Ollama service first. If installed but not running,
    # start its local server and retry once instead of downloading blindly.
    if (-not (Has-Command "ollama")) {
        return @{ Available = $false; Output = ""; ExitCode = 127 }
    }
    $output = @(& ollama list 2>&1)
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        $Ollama = Get-Command "ollama" -ErrorAction SilentlyContinue
        if ($Ollama) {
            try {
                Start-Process -FilePath $Ollama.Source -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 4
                $output = @(& ollama list 2>&1)
                $code = $LASTEXITCODE
            } catch {
                # Keep diagnostics from the failed list command.
            }
        }
    }
    return @{ Available = ($code -eq 0); Output = ($output -join [Environment]::NewLine); ExitCode = $code }
}

function Test-ModelInstalled([string]$ModelListText) {
    return [regex]::IsMatch($ModelListText, '(?im)^\s*llama3\.2:3b(?:\s|$)')
}

$ConfigPath = Join-Path $Root "config.json"
$ModelAlreadyConfigured = $false
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $ExistingConfig = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        $ModelAlreadyConfigured = ([bool]$ExistingConfig.model.enabled -and
            ([string]$ExistingConfig.model.model -eq "llama3.2:3b") -and
            ([string]$ExistingConfig.model.base_url -eq "http://127.0.0.1:11434/v1/chat/completions"))
    } catch {
        Write-Warning "Could not read config.json while checking the optional local model; it will not be overwritten unless you approve setup."
    }
}

$ModelReady = $false
$OllamaStatus = @{ Available = $false; Output = ""; ExitCode = 127 }
if ($ModelAlreadyConfigured -and (Has-Command "ollama")) {
    $OllamaStatus = Get-OllamaModelList
    $ModelReady = $OllamaStatus.Available -and (Test-ModelInstalled $OllamaStatus.Output)
}

if ($ModelReady) {
    Write-Host "Existing Ollama + llama3.2:3b installation and configuration detected. Skipping model setup; nothing needs to be downloaded." -ForegroundColor Green
} else {
    Write-Host ""
    if ($ModelAlreadyConfigured) {
        Write-Warning "config.json already enables llama3.2:3b, but its runtime/model could not be confirmed. The existing configuration will be preserved unless you choose to repair it."
    }
    $answer = Read-Host "Install or repair optional free local AI runtime + llama3.2:3b model? Only needed once [y/N]"
    if ($answer.Trim().ToLowerInvariant() -eq "y" -or $answer.Trim().ToLowerInvariant() -eq "yes") {
        if (-not (Has-Command "ollama")) {
            Install-WingetPackage "Ollama.Ollama" "Ollama local AI runtime"
        }
        Refresh-Path
        $Ollama = Get-Command "ollama" -ErrorAction SilentlyContinue
        if (-not $Ollama) {
            throw "Ollama was installed but is not yet available on PATH. Restart Windows or open a new terminal, then rerun START_HERE.bat."
        }

        $OllamaStatus = Get-OllamaModelList
        if (-not $OllamaStatus.Available) {
            throw "Ollama is installed but its local server is not responding. Start Ollama from the Start menu, then rerun START_HERE.bat. Details: $($OllamaStatus.Output)"
        }
        if (Test-ModelInstalled $OllamaStatus.Output) {
            Write-Host "llama3.2:3b is already installed; skipping model download." -ForegroundColor Green
        } else {
            Write-Host "Downloading local model llama3.2:3b. This is a one-time download..." -ForegroundColor Cyan
            & ollama pull llama3.2:3b
            if ($LASTEXITCODE -ne 0) {
                throw "The local model download failed. Dashboard/video tools are installed, but model-based CEO and specialist work is not enabled. Rerun START_HERE.bat when internet is stable."
            }
        }

        $Config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        if (-not $Config.model) {
            $Config | Add-Member -NotePropertyName model -NotePropertyValue ([pscustomobject]@{})
        }
        $Config.model.enabled = $true
        $Config.model.base_url = "http://127.0.0.1:11434/v1/chat/completions"
        $Config.model.model = "llama3.2:3b"
        if (-not $Config.model.max_output_tokens) { $Config.model.max_output_tokens = 900 }
        if (-not $Config.model.product_max_output_tokens) { $Config.model.product_max_output_tokens = 3500 }
        if (-not $Config.model.timeout_seconds) { $Config.model.timeout_seconds = 240 }
        [System.IO.File]::WriteAllText($ConfigPath, ($Config | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "Local model configured. No paid API key was added." -ForegroundColor Green
    } else {
        if ($ModelAlreadyConfigured) {
            Write-Host "Kept your existing config.json unchanged. Model runtime readiness was not confirmed." -ForegroundColor Yellow
        } else {
            Write-Host "Skipped local AI model. The dashboard and deterministic tools work, but advanced AI output requires a compatible local model." -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "Setup complete. Starting Agent HQ..." -ForegroundColor Green
& (Join-Path $Root "start_windows.bat")
