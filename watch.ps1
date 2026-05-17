# Watch the repo for changes and rsync to the Pi automatically.
#
# Runs on the [LAPTOP]. Pairs with the systemd unit on the [PI] which uses
# `uvicorn --reload` to pick up rsync'd file changes within ~1 second.
#
# Usage (from PowerShell, in the repo root):
#   .\watch.ps1
#
# Stop with Ctrl+C. Files actually pushed are filtered by the same exclude
# list as deploy.sh.

[CmdletBinding()]
param(
    [string]$PiHost = $(if ($env:PI_HOST) { $env:PI_HOST } else { "rpclaw@UMDCLAW.local" }),
    [int]$DebounceMs = 750
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$watchPaths = @("src", "frontend", "scripts", "tests", "docs", "systemd", "pyproject.toml", "Makefile", "deploy.sh")

Write-Host "watching $repo for changes; syncing to $PiHost" -ForegroundColor Cyan
Write-Host "press Ctrl+C to stop" -ForegroundColor DarkGray

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $repo
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]::LastWrite -bor `
                       [System.IO.NotifyFilters]::FileName -bor `
                       [System.IO.NotifyFilters]::DirectoryName

$script:lastEvent = [DateTime]::MinValue
$script:syncPending = $false

function Should-Ignore($relPath) {
    $rel = $relPath -replace '\\','/'
    if ($rel -match '^\.venv/') { return $true }
    if ($rel -match '^\.git/') { return $true }
    if ($rel -match '__pycache__') { return $true }
    if ($rel -match '\.pyc$') { return $true }
    if ($rel -match '^data/(logs|calibration|defects)/') { return $true }
    if ($rel -match '\.pytest_cache/') { return $true }
    if ($rel -match '\.mypy_cache/') { return $true }
    if ($rel -match '\.ruff_cache/') { return $true }
    return $false
}

function Do-Sync {
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] syncing..." -ForegroundColor Yellow
    $env:PI_HOST = $PiHost
    & bash "$repo/deploy.sh"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] synced. uvicorn --reload will pick it up" -ForegroundColor Green
    } else {
        Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] rsync FAILED ($LASTEXITCODE)" -ForegroundColor Red
    }
}

$action = {
    $full = $Event.SourceEventArgs.FullPath
    $rel = $full.Substring($using:repo.Length).TrimStart('\','/')
    if (Should-Ignore $rel) { return }
    $script:lastEvent = [DateTime]::Now
    $script:syncPending = $true
}

$handlers = @(
    Register-ObjectEvent $watcher Changed -Action $action
    Register-ObjectEvent $watcher Created -Action $action
    Register-ObjectEvent $watcher Deleted -Action $action
    Register-ObjectEvent $watcher Renamed -Action $action
)

try {
    while ($true) {
        Start-Sleep -Milliseconds 200
        if ($script:syncPending) {
            $age = ([DateTime]::Now - $script:lastEvent).TotalMilliseconds
            if ($age -gt $DebounceMs) {
                $script:syncPending = $false
                Do-Sync
            }
        }
    }
}
finally {
    foreach ($h in $handlers) { Unregister-Event -SourceIdentifier $h.Name -ErrorAction SilentlyContinue }
    $watcher.Dispose()
    Write-Host "watcher stopped" -ForegroundColor DarkGray
}
