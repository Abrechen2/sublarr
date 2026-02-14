# Quick setup script - non-interactive version (PowerShell)
# Use this for CI or when you want to skip prompts

Write-Host "🚀 Quick setup for Sublarr..." -ForegroundColor Cyan
Write-Host ""

# Backend
Set-Location backend
python -m pip install --upgrade pip
pip install -r requirements.txt
Set-Location ..

# Frontend
Set-Location frontend
npm install
Set-Location ..

# Pre-commit (if available)
if (Get-Command pre-commit -ErrorAction SilentlyContinue) {
    pre-commit install
}

Write-Host "✅ Quick setup complete!" -ForegroundColor Green
