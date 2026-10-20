param([int]$IntervalMinutes = 5)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ScriptPath = Join-Path $PSScriptRoot "sync-and-test.ps1"
$TaskName = "OfflineAgentHQ-GitHub-Safe-Sync"
if ($IntervalMinutes -lt 5) { throw "Use an interval of at least 5 minutes to avoid excessive GitHub polling." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required. Install Git for Windows first." }
if (-not (Test-Path (Join-Path $Root ".git"))) { throw "This folder is not a Git clone. Clone the repository with git before installing auto-sync." }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Safely fetches and fast-forward updates OfflineAgentHQ main only when the working tree is clean, then runs local tests after updates." -Force | Out-Null
Write-Host "Installed scheduled task '$TaskName' (every $IntervalMinutes minutes)." -ForegroundColor Green
Write-Host "It will refuse to sync if local changes exist, and it never resets or force-pulls."
Write-Host "Logs: $env:LOCALAPPDATA\OfflineAgentHQ\sync-and-test.log"
