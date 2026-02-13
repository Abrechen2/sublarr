# Check Sublarr Server Status

Write-Host "Checking Sublarr Server Status..." -ForegroundColor Cyan
Write-Host ""

# Check Backend (Port 5765)
Write-Host "Backend (Port 5765):" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5765/api/v1/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    $data = $response.Content | ConvertFrom-Json
    Write-Host "   [OK] Running" -ForegroundColor Green
    Write-Host "   Status: $($data.status)" -ForegroundColor $(if ($data.status -eq 'healthy') { 'Green' } else { 'Yellow' })
    Write-Host "   Version: $($data.version)" -ForegroundColor Cyan
} catch {
    Write-Host "   [FAIL] Not running or unreachable" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Check Frontend (Port 5173)
Write-Host "Frontend (Port 5173):" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "   [OK] Running" -ForegroundColor Green
    Write-Host "   Status Code: $($response.StatusCode)" -ForegroundColor Cyan
} catch {
    Write-Host "   [FAIL] Not running or unreachable" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Check Ports
Write-Host "Port Status:" -ForegroundColor Yellow
$port5765 = Get-NetTCPConnection -LocalPort 5765 -ErrorAction SilentlyContinue
$port5173 = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue

if ($port5765) {
    Write-Host "   Port 5765: [OK] In use (PID: $($port5765.OwningProcess))" -ForegroundColor Green
} else {
    Write-Host "   Port 5765: [FAIL] Not in use" -ForegroundColor Red
}

if ($port5173) {
    Write-Host "   Port 5173: [OK] In use (PID: $($port5173.OwningProcess))" -ForegroundColor Green
} else {
    Write-Host "   Port 5173: [FAIL] Not in use" -ForegroundColor Red
}

Write-Host ""
Write-Host "Tip: Start servers with:" -ForegroundColor Cyan
Write-Host "   scripts\dev-backend.ps1" -ForegroundColor White
Write-Host "   scripts\dev-frontend.ps1" -ForegroundColor White
