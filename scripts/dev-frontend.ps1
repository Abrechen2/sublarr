# Sublarr Frontend DEV Server
# Startet Vite Dev Server mit Hot-Reload

Write-Host "🚀 Starting Sublarr Frontend DEV Server..." -ForegroundColor Cyan

# Wechsle ins Frontend-Verzeichnis
Set-Location frontend

Write-Host "📁 Working Directory: $(Get-Location)" -ForegroundColor Yellow
Write-Host "🌐 Vite Dev Server starting on http://localhost:5173" -ForegroundColor Green
Write-Host ""

# Starte Vite Dev Server
npm run dev
