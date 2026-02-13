# Sublarr Backend DEV Server
# Startet Flask Development Server mit Hot-Reload

Write-Host "Starting Sublarr Backend DEV Server..." -ForegroundColor Cyan

$env:FLASK_APP = "server.py"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "1"

# Lade .env Datei falls vorhanden
if (Test-Path "..\.env") {
    Write-Host "Loading .env file..." -ForegroundColor Yellow
    Get-Content "..\.env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Setze Defaults falls nicht gesetzt
if (-not $env:SUBLARR_PORT) { $env:SUBLARR_PORT = "5765" }
if (-not $env:SUBLARR_DB_PATH) { $env:SUBLARR_DB_PATH = "..\dev.db" }
if (-not $env:SUBLARR_MEDIA_PATH) { $env:SUBLARR_MEDIA_PATH = "..\test-media" }

Write-Host "Working Directory: $(Get-Location)" -ForegroundColor Yellow
Write-Host "Port: $env:SUBLARR_PORT" -ForegroundColor Yellow
Write-Host "DB Path: $env:SUBLARR_DB_PATH" -ForegroundColor Yellow
Write-Host "Media Path: $env:SUBLARR_MEDIA_PATH" -ForegroundColor Yellow
Write-Host "Ollama URL: $env:SUBLARR_OLLAMA_URL" -ForegroundColor Yellow
Write-Host ""

# Wechsle ins Backend-Verzeichnis
Set-Location backend

# Starte Flask Dev Server
Write-Host "Flask Development Server starting..." -ForegroundColor Green
python -m flask run --host=0.0.0.0 --port=$env:SUBLARR_PORT --reload
