# Start the API (port 8000) and the Next.js dashboard (port 3000) in two windows.
# Usage, from the project root:  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-Command",
    ".\.venv\Scripts\python.exe -m uvicorn src.api.main:app --port 8000"
)

$web = Join-Path $root "web"
if (-not (Test-Path (Join-Path $web "node_modules"))) {
    Write-Host "Installing dashboard packages (first run only)..."
    Push-Location $web
    npm install
    Pop-Location
}
Start-Process powershell -WorkingDirectory $web -ArgumentList @("-NoExit", "-Command", "npm run dev")

Write-Host "API:       http://localhost:8000/docs"
Write-Host "Dashboard: http://localhost:3000"
