# Run all tests (Backend + Frontend)

Write-Host "🧪 Running Sublarr Tests..." -ForegroundColor Cyan
Write-Host ""

# Backend Tests
Write-Host "🐍 Backend Tests (pytest)..." -ForegroundColor Yellow
Set-Location backend
python -m pytest tests/ -v --tb=short
$backendExit = $LASTEXITCODE
Set-Location ..

Write-Host ""

# Frontend Tests
Write-Host "⚛️  Frontend Tests (vitest)..." -ForegroundColor Yellow
Set-Location frontend
npm run test -- --run
$frontendExit = $LASTEXITCODE
Set-Location ..

Write-Host ""
if ($backendExit -eq 0 -and $frontendExit -eq 0) {
    Write-Host "✅ All tests passed!" -ForegroundColor Green
} else {
    Write-Host "❌ Some tests failed" -ForegroundColor Red
    exit 1
}
