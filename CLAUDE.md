# Sublarr — Subtitle Manager & Translator (*arr-Style)

Eigenstaendiger Subtitle-Manager fuer Anime/Media mit LLM-Uebersetzung. GPL-3.0.

## Commands

```bash
npm run dev              # Backend (:5765) + Frontend (:5173) parallel
npm run dev:backend      # nur Flask
npm run dev:frontend     # nur Vite (Proxy → :5765)

cd backend && python -m pytest   # Backend-Tests
cd frontend && npm test          # Frontend-Tests (vitest)
cd frontend && npm run lint      # ESLint

docker build -t sublarr:dev .    # Multi-Stage: Node 20 + Python 3.12 + ffmpeg + unrar
docker compose up -d             # Production (Port 5765, /config, /media)
```

## Sicherheitsregeln — IMMER EINHALTEN

1. **KEINE Medien-Dateien loeschen/ueberschreiben** — nur `.{lang}.ass`/`.{lang}.srt` erstellen
2. **Container-Rebuild** erfordert Bestaetigung
3. **Secrets** nur in `.env` oder `config_entries` DB — nie in Code/Commits
4. **Provider-Downloads** nur in Media-Verzeichnisse — kein beliebiger Dateizugriff
5. **Batch-Verarbeitung** (GPU/CPU-Last) — vorher bestaetigen

## Architektur auf einen Blick

```
backend/          # Flask, Python — @backend/CLAUDE.md
  providers/      # Subtitle-Provider — @backend/providers/CLAUDE.md
  translation/    # LLM-Backends — @backend/translation/CLAUDE.md
frontend/         # React 19 + TypeScript — @frontend/CLAUDE.md
```

**Config-Kaskade:** Env/`.env` → Pydantic Settings → `config_entries` DB-Tabelle

**API:** Alle Endpunkte unter `/api/v1/` — Details in @backend/CLAUDE.md

## Versionsstrategie (aktuell)

SemVer, konservative Beta-Strategie:
- `v0.2.0-beta` nach Milestone 13-15 | `v0.9.0-beta` Stabilisierung | `v1.0.0` Final
- Beta = Breaking Changes moeglich | RC = Feature-complete | Patch = nur Bugfixes
