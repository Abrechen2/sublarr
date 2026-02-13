# Sublarr

**Subtitle Translation Service** — *arr-Style Open-Source Tool

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React + TypeScript](https://img.shields.io/badge/React-TypeScript-blue.svg)](https://react.dev/)

Sublarr ist ein Open-Source-Tool zur automatischen Übersetzung von Anime-Untertiteln via Ollama LLM. Es integriert sich nahtlos in das *arr-Ökosystem (Sonarr, Radarr, Bazarr) und bietet eine moderne Web-UI im *arr-Stil.

## ✨ Features

- 🌍 **Multi-Language Support** — Konfigurierbare Quell- und Zielsprache (Default: EN→DE)
- 🎨 ***arr-Style UI** — Dark Theme, React + TypeScript + Tailwind CSS
- 🔌 ***arr Integration** — Sonarr, Radarr, Bazarr, Jellyfin/Emby
- 📊 **Persistent Storage** — SQLite für Jobs, Stats, Config
- 🔐 **Optional Auth** — API-Key-Authentifizierung
- ⚡ **WebSocket** — Live-Updates für Jobs und Batch-Status
- 🐳 **Docker Ready** — Multi-Stage Build, Production-ready

## 🚀 Quick Start

### Development

```bash
# Backend DEV Server
cd backend
pip install -r requirements.txt
python -m flask run --port=5765

# Frontend DEV Server (separates Terminal)
cd frontend
npm install
npm run dev
```

Oder nutze die Skripte:

```powershell
# Windows
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1

# Oder beide zusammen
.\scripts\dev-all.ps1
```

```bash
# Linux/Mac
./scripts/dev-backend.sh
./scripts/dev-frontend.sh
```

### Docker

```bash
# .env erstellen
cp .env.example .env
# .env anpassen

# Build & Start
docker compose up -d --build
```

## 🧪 Tests

```bash
# Backend Tests
cd backend
python -m pytest tests/ -v

# Frontend Tests
cd frontend
npm run test

# Alle Tests
.\scripts\run-tests.ps1  # Windows
./scripts/run-tests.sh    # Linux/Mac
```

## 📖 Dokumentation

- [CLAUDE.md](CLAUDE.md) — Vollständige Architektur-Dokumentation
- [SUBLARR-PLAN.md](SUBLARR-PLAN.md) — Implementierungsplan
- [.env.example](.env.example) — Alle konfigurierbaren Variablen

## 🎨 Logo & Branding

- **Primärfarbe:** Teal (#1DB8D4)
- **Logo:** Sprechblase + bidirektionaler Übersetzungspfeil
- **Stil:** Flat Design, *arr-konsistent

## 📝 License

GPL-3.0 — siehe [LICENSE](LICENSE)
