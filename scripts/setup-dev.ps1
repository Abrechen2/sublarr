# Development setup script for Sublarr (PowerShell)
# Installs all dependencies and sets up development environment

Write-Host "🚀 Setting up Sublarr development environment..." -ForegroundColor Cyan
Write-Host ""

# Backend Setup
Write-Host "🐍 Backend Setup..." -ForegroundColor Yellow
Set-Location backend

Write-Host "  - Installing Python dependencies..." -ForegroundColor Gray
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "  - ✅ Backend dependencies installed" -ForegroundColor Green
Set-Location ..

# Frontend Setup
Write-Host ""
Write-Host "⚛️  Frontend Setup..." -ForegroundColor Yellow
Set-Location frontend

Write-Host "  - Installing Node.js dependencies..." -ForegroundColor Gray
npm install

Write-Host "  - ✅ Frontend dependencies installed" -ForegroundColor Green
Set-Location ..

# Pre-commit Hooks
Write-Host ""
Write-Host "🔧 Pre-commit Hooks Setup..." -ForegroundColor Yellow
if (Get-Command pre-commit -ErrorAction SilentlyContinue) {
    Write-Host "  - Installing pre-commit hooks..." -ForegroundColor Gray
    pre-commit install
    Write-Host "  - ✅ Pre-commit hooks installed" -ForegroundColor Green
} else {
    Write-Host "  - ⚠️  pre-commit not found. Install with: pip install pre-commit" -ForegroundColor Yellow
}

# Optional: Dependency Pinning
Write-Host ""
$generateRequirements = Read-Host "Generate pinned requirements.txt from requirements.in? (y/N)"
if ($generateRequirements -eq "y" -or $generateRequirements -eq "Y") {
    Set-Location backend
    if (Get-Command pip-compile -ErrorAction SilentlyContinue) {
        Write-Host "  - Generating requirements.txt from requirements.in..." -ForegroundColor Gray
        pip-compile requirements.in --output-file requirements.txt --upgrade
        Write-Host "  - ✅ requirements.txt generated" -ForegroundColor Green
    } else {
        Write-Host "  - ⚠️  pip-compile not found. Install with: pip install pip-tools" -ForegroundColor Yellow
    }
    Set-Location ..
}

# Optional: Run tests
Write-Host ""
$runTests = Read-Host "Run tests to verify setup? (y/N)"
if ($runTests -eq "y" -or $runTests -eq "Y") {
    Write-Host ""
    Write-Host "🧪 Running tests..." -ForegroundColor Yellow
    
    # Backend tests
    Write-Host "  - Backend tests..." -ForegroundColor Gray
    Set-Location backend
    python -m pytest tests/ -v --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  - ⚠️  Some backend tests failed" -ForegroundColor Yellow
    }
    Set-Location ..
    
    # Frontend tests
    Write-Host "  - Frontend tests..." -ForegroundColor Gray
    Set-Location frontend
    npm test -- --run
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  - ⚠️  Some frontend tests failed" -ForegroundColor Yellow
    }
    Set-Location ..
}

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Configure your .env file (copy .env.example)"
Write-Host "   2. Start development: npm run dev (from project root)"
Write-Host "   3. Or start separately:"
Write-Host "      - Backend: cd backend && python -m flask run --host=0.0.0.0 --port=5765"
Write-Host "      - Frontend: cd frontend && npm run dev"
