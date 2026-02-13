# Sublarr Full DEV Stack
# Startet Backend und Frontend parallel

Write-Host "🚀 Starting Sublarr Full DEV Stack..." -ForegroundColor Cyan
Write-Host ""

$backendScript = Join-Path $PSScriptRoot "dev-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "dev-frontend.ps1"

# Starte Backend im Hintergrund
Write-Host "🔧 Starting Backend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", $backendScript

# Warte kurz
Start-Sleep -Seconds 3

# Starte Frontend im Hintergrund
Write-Host "🌐 Starting Frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File", $frontendScript

Write-Host ""
Write-Host "✅ Both servers started!" -ForegroundColor Green
Write-Host "   Backend:  http://localhost:5765" -ForegroundColor Cyan
Write-Host "   Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to stop servers..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
