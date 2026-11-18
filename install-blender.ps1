$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $studioRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) {
    Write-Host 'Preparing the local environment...' -ForegroundColor Cyan
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    & $studioPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the project dependencies.' }
}
& $studioPython tools\prepare_blender.py
if ($LASTEXITCODE -ne 0) { throw 'Blender installation did not finish. Run this installer again to resume.' }
Write-Host 'Blender is ready. Launch Xiaozao to create your model.' -ForegroundColor Green
