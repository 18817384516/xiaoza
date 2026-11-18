$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$studioExe = Join-Path $studioRoot '.venv\Scripts\python.exe'
$studioProcesses = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python' -and $_.CommandLine -and
    $_.CommandLine.Contains($studioExe) -and $_.CommandLine.Contains('uvicorn server.app:app') -and
    $_.CommandLine.Contains('--port 8765')
}
foreach ($studioProcess in $studioProcesses) { Stop-Process -Id $studioProcess.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host 'Xiaozao stopped. Your saved models remain in data\models.' -ForegroundColor Green
