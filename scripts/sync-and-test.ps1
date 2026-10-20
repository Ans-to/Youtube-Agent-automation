param(
    [switch]$SkipSync,
    [switch]$RunTestsOnNoUpdate
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $env:LOCALAPPDATA "OfflineAgentHQ"
$LogPath = Join-Path $LogDir "sync-and-test.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -LiteralPath $LogPath -Value $line
    Write-Host $line
}
function Invoke-Git([string[]]$GitArgs) {
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE" }
}
function Invoke-Python([string[]]$PythonArgs) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @PythonArgs
    } else {
        & python @PythonArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $($PythonArgs -join ' ')" }
}

Set-Location $Root
try {
    if (-not $SkipSync) {
        $branch = (& git branch --show-current).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Could not identify the current Git branch." }
        if ($branch -ne "main") {
            throw "Safe sync only updates the main branch. Current branch is '$branch'; switch to main manually after saving any work."
        }
        $changes = @(& git status --porcelain)
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect the working tree." }
        if ($changes.Count -gt 0) {
            throw "Sync paused because local changes exist. Nothing was overwritten. Commit/stash your changes or review them in VS Code, then retry."
        }
        Write-Log "Fetching origin/main."
        Invoke-Git @("fetch", "origin", "main")
        $local = (& git rev-parse HEAD).Trim()
        $remote = (& git rev-parse origin/main).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Could not compare local HEAD with origin/main." }
        if ($local -ne $remote) {
            $base = (& git merge-base HEAD origin/main).Trim()
            if ($LASTEXITCODE -ne 0) { throw "Could not determine whether local and remote history can be fast-forwarded." }
            if ($base -ne $local) {
                throw "Local main is not a simple ancestor of origin/main. No merge/reset was attempted; resolve the branch history manually."
            }
            Invoke-Git @("merge", "--ff-only", "origin/main")
            Write-Log "Updated local main to $remote."
            $shouldTest = $true
        } else {
            Write-Log "Already up to date."
            $shouldTest = [bool]$RunTestsOnNoUpdate
        }
    } else {
        Write-Log "Sync skipped by request."
        $shouldTest = $true
    }

    if ($shouldTest) {
        $python = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } else { "python" }
        Write-Log "Running Python syntax checks."
        $compileTargets = @(
            "agent.py", "dashboard.py", "queue_store.py",
            "bridge/bridge.py", "agents/dispatch.py", "agents/adhd_style.py",
            "agents/orchestrate.py", "agents/practice.py", "video_studio/studio.py",
            "video_studio/capabilities.py", "video_studio/render_lock.py",
            "video_studio/production.py", "video_studio/voice_backends.py",
            "video_studio/piper_urdu_tts_adapter.py", "video_studio/urdu_tts_adapter.py",
            "video_studio/voice_preview.py", "video_studio/captions.py",
            "video_studio/research.py", "video_studio/validate_render.py",
            "video_studio/validate_frames.py", "video_studio/quality_audit.py",
            "video_studio/release_gate.py", "video_studio/publish_youtube.py",
            "product_studio/build_product.py", "tools/run_quality_gate.py"
        )
        Invoke-Python (@("-m", "py_compile") + $compileTargets)
        Write-Log "Checking JSON configuration examples."
        Invoke-Python @("-m", "json.tool", "video_studio/storyboard.example.json")
        Invoke-Python @("-m", "json.tool", "agents/roster.json")
        Invoke-Python @("-m", "json.tool", "agents/skillbooks.json")
        Write-Log "Running Python unit tests."
        Invoke-Python @("-m", "unittest", "discover", "-s", "tests", "-v")
        if (Get-Command node -ErrorAction SilentlyContinue) {
            Write-Log "Checking video renderer JavaScript syntax."
            & node --check "video_studio/render.js"
            if ($LASTEXITCODE -ne 0) { throw "Node.js syntax check failed." }
        } else {
            Write-Log "Node.js not installed; skipped local JavaScript syntax check. GitHub Actions remains the full CI check."
        }
        Write-Log "All configured local checks passed."
    }
} catch {
    Write-Log "FAILURE: $($_.Exception.Message)"
    Write-Log "Review this log and the VS Code terminal: $LogPath"
    exit 1
}
