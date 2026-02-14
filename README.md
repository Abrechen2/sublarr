# Sublarr

<p align="center">
  <img src="logo.png" alt="Sublarr Logo" width="128" />
</p>

**Standalone Subtitle Manager & Translator** — *arr-Style Open-Source Tool

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/React_19-TypeScript-blue.svg)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue.svg)](https://github.com/denniswittke/sublarr/pkgs/container/sublarr)
[![CI](https://github.com/denniswittke/sublarr/workflows/CI%20-%20Tests%2C%20Linting%20%26%20Type%20Checking/badge.svg)](https://github.com/denniswittke/sublarr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/denniswittke/sublarr/branch/main/graph/badge.svg)](https://codecov.io/gh/denniswittke/sublarr)

Sublarr ist ein eigenstaendiger Subtitle-Manager und Uebersetzer fuer Anime und Medien. Er durchsucht Subtitle-Provider direkt, downloadt die besten Untertitel (ASS bevorzugt) und uebersetzt sie automatisch via Ollama LLM. Integration mit Sonarr, Radarr und Jellyfin/Emby.

## Features

- **ASS-first Scoring** — ASS-Format bekommt +50 Bonus gegenueber SRT
- **4 Provider** — AnimeTosho, Jimaku, OpenSubtitles, SubDL
- **LLM-Uebersetzung** — Automatische Uebersetzung via Ollama (konfigurierbare Sprachen)
- **Language Profiles** — Pro Serie/Film mehrere Zielsprachen
- **Wanted-System** — Fehlende Subs automatisch erkennen und suchen
- **\*arr Integration** — Sonarr, Radarr Webhooks + Jellyfin Library-Refresh
- **\*arr-Style UI** — React 19 + TypeScript + Tailwind v4, Dark Theme
- **Docker Ready** — Multi-Stage Build, GHCR CI/CD

## Quick Start

### Docker (empfohlen)

```bash
# .env erstellen und anpassen
cp .env.example .env

# Build & Start
docker compose up -d --build
```

Erreichbar unter `http://localhost:5765`

### Development

**Erstmaliges Setup:**
```bash
# Windows (PowerShell)
npm run setup:ps1

# Linux/Mac (Bash)
npm run setup:sh
# oder
./scripts/setup-dev.sh
```

Das Setup-Script installiert automatisch:
- Backend Dependencies (Python)
- Frontend Dependencies (Node.js)
- Pre-commit Hooks (optional)
- Führt optional Tests aus zur Verifizierung

**Nach dem Setup:**
```bash
# Backend + Frontend parallel starten
npm run dev
```

Oder mit den Skripten unter `scripts/` (PowerShell + Bash).

## Tests

```bash
# Backend
cd backend && python -m pytest

# Frontend
cd frontend && npm test

# With coverage
cd backend && python -m pytest --cov=. --cov-report=html
cd frontend && npm run test:coverage
```

**Coverage Goals:**
- Backend: 80%+ (see `backend/pytest.ini`)
- Frontend: 70%+ (see `frontend/vitest.config.ts`)

## Code Quality

This project uses automated code quality checks:

- **Pre-commit Hooks**: Run automatically before each commit
- **CI Pipeline**: Runs on every push/PR (GitHub Actions)
- **Linting**: `ruff` (Python), `eslint` (TypeScript)
- **Formatting**: `ruff format` (Python), `prettier` (Frontend)
- **Type Checking**: `mypy` (Python), `tsc` (TypeScript)

**Setup Pre-commit Hooks:**
```bash
pip install pre-commit
pre-commit install
```

**Manual Checks:**
```bash
# Backend
cd backend
ruff check .
ruff format --check .
mypy .

# Frontend
cd frontend
npm run lint
npm run format:check
npx tsc --noEmit
```

## Dokumentation

| Datei | Inhalt |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Architektur, Commands, API-Referenz |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Detaillierte Systemarchitektur |
| [docs/API.md](docs/API.md) | Vollstaendige API-Dokumentation |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Provider-System Dokumentation |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Contribution Guidelines |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Troubleshooting & FAQ |
| [CHANGELOG.md](CHANGELOG.md) | Versionshistorie |
| [ROADMAP.md](ROADMAP.md) | Entwicklungs-Roadmap |
| [.env.example](.env.example) | Alle konfigurierbaren Variablen |

## Branding

- **Primaerfarbe:** Teal (#1DB8D4)
- **Stil:** *arr-Suite kompatibel (Sonarr, Radarr, Prowlarr)

## License

GPL-3.0 — siehe [LICENSE](LICENSE)
