param([switch]$NoBrowser, [switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $studioRoot
$studioUrl = 'http://127.0.0.1:8765'
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
$studioRuntime = Join-Path $studioRoot '.runtime'
New-Item -ItemType Directory -Force -Path $studioRuntime | Out-Null

try {
    $studioHealth = Invoke-RestMethod -Uri "$studioUrl/api/health" -TimeoutSec 2
    if ($studioHealth.engine -eq 'Manifold') {
        Write-Host 'Xiaozao is already running: http://127.0.0.1:8765' -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process $studioUrl }
        exit 0
    }
} catch { }

if (-not (Test-Path -LiteralPath $studioPython)) {
    Write-Host 'Preparing Python environment (first launch only)...' -ForegroundColor Cyan
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Install Python and run this launcher again.' }
}
$studioRequirements = Join-Path $studioRoot 'requirements.txt'
$studioFingerprint = (Get-FileHash -LiteralPath $studioRequirements -Algorithm SHA256).Hash
$studioMarker = Join-Path $studioRuntime 'requirements.sha256'
$studioInstalled = if (Test-Path -LiteralPath $studioMarker) { (Get-Content -LiteralPath $studioMarker -Raw).Trim() } else { '' }
if ($studioInstalled -ne $studioFingerprint) {
    Write-Host 'Installing the local modeling tools. Internet is needed on first launch...' -ForegroundColor Cyan
    & $studioPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network and launch again.' }
    Set-Content -LiteralPath $studioMarker -Value $studioFingerprint
}
if ($Rebuild -or -not (Test-Path -LiteralPath (Join-Path $studioRoot 'dist\index.html'))) {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node.js 22+ is required to build the app.' }
    Write-Host 'Building your creative workspace...' -ForegroundColor Cyan
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. Check your network and launch again.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'The app could not be built. Check the output above.' }
}
$studioProcess = Start-Process -FilePath $studioPython -ArgumentList '-m','uvicorn','server.app:app','--host','127.0.0.1','--port','8765' -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioRuntime 'server.log') -RedirectStandardError (Join-Path $studioRuntime 'server-error.log') -PassThru
Set-Content -LiteralPath (Join-Path $studioRuntime 'server.pid') -Value $studioProcess.Id
for ($studioAttempt = 0; $studioAttempt -lt 60; $studioAttempt++) {
    try {
        $studioHealth = Invoke-RestMethod -Uri "$studioUrl/api/health" -TimeoutSec 1
        if ($studioHealth.engine -eq 'Manifold') {
            Write-Host 'Ready! Xiaozao: http://127.0.0.1:8765' -ForegroundColor Green
            if (-not $NoBrowser) { Start-Process $studioUrl }
            exit 0
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'Startup did not finish. Details are in .runtime\server-error.log. Port 8765 may be occupied.'
