param([int]$IntervalMinutes = 5)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ScriptPath = Join-Path $PSScriptRoot "sync-and-test.ps1"
$TaskName = "OfflineAgentHQ-GitHub-Safe-Sync"
if ($IntervalMinutes -lt 5) { throw "Use an interval of at least 5 minutes to avoid excessive GitHub polling." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required. Install Git for Windows first." }
if (-not (Test-Path (Join-Path $Root ".git"))) { throw "This folder is not a Git clone. Clone the repository with git before installing auto-sync." }
$TaskRun = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`""
& schtasks.exe /Create /SC MINUTE /MO $IntervalMinutes /TN $TaskName /TR $TaskRun /F
if ($LASTEXITCODE -ne 0) { throw "Task Scheduler could not register the automatic sync task." }
Write-Host "Installed scheduled task '$TaskName' (every $IntervalMinutes minutes)." -ForegroundColor Green
Write-Host "It will refuse to sync if local changes exist, and it never resets or force-pulls."
Write-Host "Logs: $env:LOCALAPPDATA\OfflineAgentHQ\sync-and-test.log"
