# Sublarr Code Quality v2 — Analyse 2026-04-03

## Kontext

Nach Abschluss aller 6 Phasen des ersten Verbesserungsplans (v0.38.0/0.38.1-beta) wurde am 2026-04-03 eine neue Codebase-Analyse durchgeführt. Aktuelle Codebase-Health: **7.2/10**.

## Kritische Findings

### 1. post_processing_enabled — Feature nicht implementiert
- Im CHANGELOG v0.38.0-beta dokumentiert, aber **0 Code-Referenzen** im gesamten Backend/Frontend
- Muss entweder vollständig implementiert oder aus dem Changelog entfernt werden
- Betrifft: Config-Feld + Route + UI-Toggle + Execution-Logic in `download_manager.py`

### 2. media.py — Sicherheitslücke
- Stream-Endpunkte haben kein `is_safe_path()` Check
- `/api/v1/media/*` ist path-traversal-gefährdet

### 3. Rate Limiting — fast gar nicht ausgerollt
- ~350 Routes, nur 1 mit `@rate_limiter`
- Besonders kritisch: Auth-Routes, Config-Routes, Provider-Routes

### 4. 10+ Dateien > 800 LOC (ohne dokumentierte Ausnahme)
| Datei | LOC |
|-------|-----|
| `backend/providers/__init__.py` | 1404 |
| `backend/tests/test_security.py` | 1159 |
| `backend/wanted_search/process.py` | 1067 |
| `frontend/src/pages/Settings/ConnectionsSettings.tsx` | 938 |
| `frontend/src/pages/EventsTab.tsx` | 903 |
| `frontend/src/pages/SeriesDetail.tsx` | 889 |
| `frontend/src/api/system.ts` | 888 |
| `frontend/src/pages/Settings/AutomationSettings.tsx` | 833 |
| `frontend/src/pages/Onboarding.tsx` | 792 |

### 5. 18 Routes ohne Tests
Ungetestete Routes: `audio.py`, `blacklist.py`, `config.py`, `fansub_prefs.py`, 
`filter_presets.py`, `integrations.py`, `languages.py`, `marketplace.py`, `media.py`,
`mediaservers.py`, `nfo.py`, `notifications_mgmt.py`, `ocr.py`, `plugins.py`

Ungetestete Services: `anidb_mapper.py` (357 LOC), `anidb_sync.py` (255 LOC), `archive_utils.py`

### 6. Pool-Caching fehlt
- Subtitle-Suchergebnisse werden zwischen Scans nicht gecacht
- Jeder Scan = vollständige Netzwerk-Requests zu allen Providern

### 7. Wiki nicht vorhanden
- `SublarrWiki/en/` Struktur wurde geplant aber nie angelegt
- Keine strukturierte Nutzerdokumentation für v0.38.x Features

## Phasen-Übersicht

| Phase | Fokus | Priorität |
|-------|-------|-----------|
| 1 | Feature Completeness + Security Fixes | KRITISCH |
| 2 | Code Refactoring (LOC-Violations) | HOCH |
| 3 | Test Coverage Expansion | HOCH |
| 4 | Performance + Pool-Caching | MITTEL |
| 5 | Wiki + Dokumentation | MITTEL |
