# Smoke-Tests für Sublarr — prüft Kern-Workflows
# Verwendung: .\scripts\smoke-tests.ps1 [BASE_URL]
# Default: http://localhost:5765

param(
    [string]$BaseUrl = "http://localhost:5765"
)

$ErrorActionPreference = "Stop"

$ApiUrl = "$BaseUrl/api/v1"

Write-Host "🧪 Sublarr Smoke-Tests" -ForegroundColor Cyan
Write-Host "======================"
Write-Host "Base URL: $BaseUrl"
Write-Host ""

$Passed = 0
$Failed = 0

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$ExpectedContent = ""
    )
    
    Write-Host -NoNewline "Testing: $Name... "
    
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -ErrorAction Stop
        
        if ($ExpectedContent -and $response.Content -notmatch $ExpectedContent) {
            Write-Host "✗ FAILED" -ForegroundColor Red
            $script:Failed++
            return $false
        }
        
        Write-Host "✓ PASSED" -ForegroundColor Green
        $script:Passed++
        return $true
    }
    catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Yellow
        $script:Failed++
        return $false
    }
}

# Test 1: API ist erreichbar
Test-Endpoint "API Health Check" "$ApiUrl/health" "status"

# Test 2: Detailed Health Check
Test-Endpoint "Detailed Health Check" "$ApiUrl/health/detailed" "database"

# Test 3: Provider-System funktioniert
Test-Endpoint "Provider System" "$ApiUrl/providers" "name"

# Test 4: Wanted-System funktioniert
Test-Endpoint "Wanted System" "$ApiUrl/wanted" "items"

# Test 5: Settings-API funktioniert
Test-Endpoint "Settings API" "$ApiUrl/settings" "config"

# Test 6: Frontend-Build (wenn im Projekt-Verzeichnis)
if (Test-Path "frontend") {
    Write-Host -NoNewline "Testing: Frontend Build... "
    
    try {
        Push-Location frontend
        $null = npm run build 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ PASSED" -ForegroundColor Green
            $Passed++
        }
        else {
            Write-Host "✗ FAILED" -ForegroundColor Red
            $Failed++
        }
        Pop-Location
    }
    catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Yellow
        $Failed++
        Pop-Location
    }
}
else {
    Write-Host "⚠ SKIPPED: Frontend-Build (frontend-Verzeichnis nicht gefunden)" -ForegroundColor Yellow
}

# Zusammenfassung
Write-Host ""
Write-Host "======================"
Write-Host "Ergebnis: $Passed bestanden, $Failed fehlgeschlagen"

if ($Failed -eq 0) {
    Write-Host "✓ Alle Smoke-Tests bestanden!" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "✗ Einige Smoke-Tests sind fehlgeschlagen" -ForegroundColor Red
    exit 1
}
