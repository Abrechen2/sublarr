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
./scripts/docker-build.sh -t sublarr:dev .   # wie oben, zeigt vorher Versionsvorschläge (Patch/Minor/Major)
# Windows: .\scripts\docker-build.ps1 -t sublarr:dev .
docker compose up -d             # Production (Port 5765, /config, /media)
```

**Versionierung:** Einzige Quelle für die Release-Version ist `backend/VERSION`. Bei Release die Zeile dort anpassen; `backend/version.py` nicht manuell editieren (liest aus VERSION).

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

**Pflicht vor jedem Build:** `backend/VERSION` inkrementieren — dann committen, dann bauen.
- Patch (`0.9.x`) → Bugfixes, UI-Fixes, kleine Korrekturen
- Minor (`0.x.0`) → neue Features, groessere Aenderungen
- Major (`x.0.0`) → Breaking Changes

```bash
# Workflow (immer in dieser Reihenfolge):
# 1. VERSION anpassen (z.B. 0.9.3-beta → 0.9.4-beta)
# 2. git commit -m "chore: bump version to 0.9.4-beta"
# 3. docker build -t ghcr.io/abrechen2/sublarr:0.9.4-beta .
# 4. docker save ... | ssh root@<CARDINAL_IP> docker load
# 5. SSH → docker compose ... up -d
```
