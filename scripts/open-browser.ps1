# Open Sublarr in Browser

Write-Host "Opening Sublarr in browser..." -ForegroundColor Cyan

# Frontend
Write-Host "Opening Frontend: http://localhost:5173" -ForegroundColor Green
Start-Process "http://localhost:5173"

# Backend API
Write-Host "Opening Backend API: http://localhost:5765/api/v1/health" -ForegroundColor Green
Start-Process "http://localhost:5765/api/v1/health"

Write-Host ""
Write-Host "Frontend UI: http://localhost:5173" -ForegroundColor Yellow
Write-Host "Backend API: http://localhost:5765/api/v1/health" -ForegroundColor Yellow
Write-Host "Backend Docs: http://localhost:5765/api/v1/config" -ForegroundColor Yellow
