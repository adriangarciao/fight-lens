<#
.SYNOPSIS
  Scheduled FightLens job: fetch new data, import it, score finished bouts, predict new ones.

.DESCRIPTION
  Wraps `fightlens refresh` (which never retrains). Ensures the Postgres container is up first
  and writes a dated log to data/logs so failures leave a trace. Register it with
  scripts/register-refresh-task.ps1.
#>
# Exit codes are checked explicitly below. "Stop" would make Windows PowerShell 5.1 treat any
# native stderr output (docker and uv print progress there) as a terminating error.
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repo "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("refresh-{0:yyyy-MM-dd_HHmm}.log" -f (Get-Date))

function Write-Log([string]$message) {
    "{0:u}  {1}" -f (Get-Date), $message | Tee-Object -FilePath $log -Append
}

try {
    Write-Log "Starting FightLens refresh"
    docker info --format "{{.ServerVersion}}" *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker isn't running; start Docker Desktop and re-run." }

    Push-Location $repo
    docker compose up -d --wait db 2>&1 | ForEach-Object { Write-Log "docker: $_" }
    if ($LASTEXITCODE -ne 0) { throw "Couldn't start the database container." }

    Set-Location (Join-Path $repo "backend")
    & uv run fightlens refresh 2>&1 | ForEach-Object { Write-Log "$_" }
    if ($LASTEXITCODE -ne 0) { throw "fightlens refresh exited with code $LASTEXITCODE." }
    Write-Log "Refresh finished"
}
catch {
    Write-Log "FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
}
