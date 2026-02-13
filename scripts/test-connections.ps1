# Test connections to all configured services

Write-Host "Testing Sublarr Service Connections..." -ForegroundColor Cyan
Write-Host ""

# Load .env
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Test Ollama
Write-Host "Ollama ($env:SUBLARR_OLLAMA_URL):" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$env:SUBLARR_OLLAMA_URL/api/tags" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $data = $response.Content | ConvertFrom-Json
    $models = $data.models | ForEach-Object { $_.name }
    $modelFound = $models | Where-Object { $_ -like "*$($env:SUBLARR_OLLAMA_MODEL)*" }
    if ($modelFound) {
        Write-Host "  [OK] Connected, model found: $modelFound" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Connected, but model '$env:SUBLARR_OLLAMA_MODEL' not found" -ForegroundColor Yellow
        Write-Host "  Available models: $($models -join ', ')" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [FAIL] Cannot connect: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test Bazarr
if ($env:SUBLARR_BAZARR_URL) {
    Write-Host "Bazarr ($env:SUBLARR_BAZARR_URL):" -ForegroundColor Yellow
    try {
        $headers = @{ "X-API-KEY" = $env:SUBLARR_BAZARR_API_KEY }
        $response = Invoke-WebRequest -Uri "$env:SUBLARR_BAZARR_URL/api/system/status" -Headers $headers -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        Write-Host "  [OK] Connected" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] Cannot connect: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Test Sonarr
if ($env:SUBLARR_SONARR_URL) {
    Write-Host "Sonarr ($env:SUBLARR_SONARR_URL):" -ForegroundColor Yellow
    try {
        $headers = @{ "X-Api-Key" = $env:SUBLARR_SONARR_API_KEY }
        $response = Invoke-WebRequest -Uri "$env:SUBLARR_SONARR_URL/api/v3/system/status" -Headers $headers -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        Write-Host "  [OK] Connected" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] Cannot connect: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "Done!" -ForegroundColor Green
