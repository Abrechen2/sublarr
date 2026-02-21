# Docker-Build mit Versionsvorschlaegen und Build-Arg VERSION.
# Fuehrt suggest-next-version.ps1 aus, dann docker build mit --build-arg VERSION=...
# Usage: .\scripts\docker-build.ps1 [docker build args...]
# Example: .\scripts\docker-build.ps1 -t sublarr:dev .

param([parameter(ValueFromRemainingArguments = $true)] $DockerArgs)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VersionFile = Join-Path $RepoRoot "backend" "VERSION"

Set-Location $RepoRoot

Write-Host "=== Versionsvorschlaege (passend zu Aenderungen) ===" -ForegroundColor Cyan
& (Join-Path $ScriptDir "suggest-next-version.ps1")
Write-Host ""

$Version = "0.0.0-dev"
if (Test-Path $VersionFile) {
    $Version = (Get-Content $VersionFile -Raw).Trim()
}

Write-Host "=== Docker Build (VERSION=$Version) ===" -ForegroundColor Cyan
& docker build --build-arg "VERSION=$Version" @DockerArgs

Write-Host ""
Write-Host "=== Cardinal Deploy (after docker save | ssh docker load) ===" -ForegroundColor Cyan
Write-Host "VERSION=$Version docker compose -f docker-compose.yml -f docker-compose.cardinal.yml up -d"
