# Sublarr Code Quality v2 — Roadmap

**Basis-Analyse:** `docs/superpowers/specs/2026-04-03-code-quality-v2-analysis.md`  
**Datum:** 2026-04-03  
**Ausgangspunkt:** v0.38.1-beta (alle Phase-1–6 des ersten Plans abgeschlossen)

## Phase 1 — Feature Completeness & Security Fixes
**Ziel:** Kritische Lücken schließen: fehlendes Feature, Sicherheitslücken, Rate Limiting

### Aufgaben
1. `post_processing_enabled` vollständig implementieren
   - Config-Feld bereits in `config.py` vorhanden
   - Route-Logic in `backend/post_download.py` erweitern: Guard mit `post_processing_enabled` Flag
   - UI-Toggle in Settings (AutomationSettings oder neuer SubTab)
2. `is_safe_path()` zu allen Stream-Endpunkten in `backend/routes/media.py` hinzufügen
3. Rate Limiting auf kritische Route-Gruppen ausrollen:
   - Auth-Routes (login, change-password, setup)
   - Config-Routes (import, export)
   - Provider-Routes (search, download)
4. `auth_ui.py` Privilege-Check Review: change_password, toggle müssen @require_auth haben

### Erfolgskriterien
- `post_processing_enabled=True` führt Post-Processing-Hook aus, `False` überspringt ihn
- `GET /api/v1/media/stream?path=../../etc/passwd` → 403
- Brute-Force auf `/api/v1/auth/login` wird nach 10 Requests/min geblockt
- Ruff + Tests grün

---

## Phase 2 — Code Refactoring (LOC-Violations)
**Ziel:** Alle Dateien >800 LOC auf <800 LOC bringen (außer dokumentierte Ausnahmen)

### Backend
1. `backend/providers/__init__.py` (1404 LOC)
   - Extract: `providers/search_coordinator.py` (~600 LOC) — Thread-Pool-Orchestration, Score-Aggregation
   - Behalte in `__init__.py`: Registry, Provider-Base, Re-exports
2. `backend/wanted_search/process.py` (1067 LOC)
   - Extract: `wanted_search/post_processor.py` — Post-Download-Logic, Upgrade-Handling
   - Extract: `wanted_search/score_selector.py` — Score-Comparison, Best-Match-Selection
3. `backend/tests/test_security.py` (1159 LOC)
   - Split in: `test_security_download.py`, `test_security_paths.py`, `test_security_prompt.py`, `test_security_auth.py`

### Frontend
4. `frontend/src/pages/Settings/ConnectionsSettings.tsx` (938 LOC)
   - Extract: `ConnectionsMediaServers.tsx`, `ConnectionsNotifications.tsx`, `ConnectionsPlugins.tsx`
5. `frontend/src/pages/EventsTab.tsx` (903 LOC)
   - Extract: `EventsBrowser.tsx` (Event-List + Filter), `WebhooksPanel.tsx`
6. `frontend/src/pages/SeriesDetail.tsx` (889 LOC)
   - Extract: `SeriesEpisodeList.tsx`, `SeriesStatsPanel.tsx`
7. `frontend/src/api/system.ts` (888 LOC)
   - Split analog zu anderen API-Modulen: `system/health.ts`, `system/logs.ts`, `system/tasks.ts`

### Erfolgskriterien
- Alle genannten Dateien < 800 LOC
- Keine broken imports (Barrel re-exports wo nötig)
- Alle Tests grün

---

## Phase 3 — Test Coverage Expansion
**Ziel:** 15+ untestete Routes mit HTTP-Tests abdecken

### Backend Route-Tests (Priorität)
1. `backend/tests/test_routes_config.py` — Config-CRUD, Import/Export, Path-Mapping
2. `backend/tests/test_routes_mediaservers.py` — Sonarr/Radarr/Jellyfin Integration
3. `backend/tests/test_routes_audio.py` — Audio-Track-Liste, Language-Detection
4. `backend/tests/test_routes_media.py` — Stream-Endpunkte (inkl. is_safe_path Tests)
5. `backend/tests/test_routes_plugins.py` — Plugin-Install, List, Remove
6. `backend/tests/test_routes_blacklist.py` — Blacklist CRUD
7. `backend/tests/test_routes_nfo.py` — NFO-Export
8. `backend/tests/test_routes_ocr.py` — OCR-Trigger, Status

### Service-Tests
9. `backend/tests/test_anidb_mapper.py` — AniDB-ID-Mapping Logic
10. `backend/tests/test_anidb_sync.py` — Sync-State, Offline-XML

### Frontend-Tests
11. `frontend/src/test/Library.test.tsx` — Grid, Filter, Batch-Actions
12. `frontend/src/test/SeriesDetail.test.tsx` — Episode-List, Season-Toggle

### Erfolgskriterien
- Alle 12 neuen Testdateien in CI grün
- Mindestens 3 Tests pro Route-Datei (success, validation-error, auth-error)

---

## Phase 4 — Performance & Pool-Caching
**Ziel:** Messbare Performance-Verbesserungen bei Subtitle-Suche und DB-Queries

### Pool-Caching
1. Design: `backend/services/provider_cache.py` — In-Memory + Redis Cache für Provider-Suchergebnisse
   - Cache-Key: `{serie_id}:{episode_id}:{language}:{provider}`
   - TTL: 6 Stunden (= FULL_SCAN_INTERVAL)
   - Invalidierung: bei manuellem Re-Search oder Download-Erfolg
2. Integration in `wanted_search/process.py`: Vor Provider-Call → Cache-Hit prüfen
3. Cache-Stats in `/api/v1/metrics` als neue Prometheus-Metriken

### DB Performance
4. N+1-Audit in `backend/db/repositories/wanted.py`:
   - Identifiziere Queries die per-Episode-Loops machen
   - Ersetze durch Bulk-Queries mit `IN (...)` oder JOIN
5. Missing Index-Analyse für häufige WHERE-Clauses in `wanted`, `subtitles`, `history`

### Cleanup
6. `backend/providers/gestdown.py`: `time.sleep(1)` → Configurable Backoff-Parameter
7. `backend/routes/webhooks.py`: Blocking Webhook-Delay → Job-Queue Handover

### Erfolgskriterien
- Provider-Cache: 2. Scan für gleiche Episode <50ms statt ~2-5s
- N+1 Queries: `wanted.py` Bulk-Query für Episode-Liste
- Prometheus Metrics für Cache-Hit/Miss-Rate vorhanden

---

## Phase 5 — Wiki & Dokumentation
**Ziel:** Strukturierte Nutzerdokumentation für Sublarr v0.38.x aufbauen

### Wiki-Struktur (SublarrWiki/en/)
Vorhandene Dateien sind bereits in SublarrWiki. Fehlende Seiten erstellen:

1. `user-guide/post-processing.md` — Post-Processing Shell-Hook Dokumentation
   - Variablen: `{path}`, `{media_type}`, `{language}`, `{provider}`
   - Enable/Disable via Settings
   - Beispiele: Notify-Script, Plex-Refresh, Custom-Renaming
2. `user-guide/circuit-breaker.md` — Circuit-Breaker Erklärung + State-Recovery
3. `user-guide/translation/ollama-v9.md` — Ollama Chat API Config (`use_chat_api`)
4. `user-guide/advanced/pool-caching.md` — Cache-Strategie und TTL-Konfiguration (nach Phase 4)
5. `developer/api-reference.md` — Auto-generiert aus vorhandenen Docstrings

### Route Docstrings
6. `backend/routes/auth_ui.py` — Docstrings für alle 6 Endpunkte
7. `backend/routes/media.py` — Docstrings für stream_media, generate

### CHANGELOG-Korrektur
8. `CHANGELOG.md` v0.38.0-beta: `post_processing_enabled` Eintrag korrigieren (nach Phase 1)

### Erfolgskriterien
- 5 neue Wiki-Seiten committed und gepusht
- Alle Routes in `auth_ui.py` und `media.py` haben Docstrings
- CHANGELOG korrekt und konsistent mit tatsächlicher Implementierung

---

## Abhängigkeiten

```
Phase 1 (Features + Security)
    ↓
Phase 2 (Refactoring) — parallel zu Phase 3 möglich
Phase 3 (Tests)       — parallel zu Phase 2 möglich
    ↓
Phase 4 (Performance) — baut auf Phase 2 (wanted_search split) auf
    ↓
Phase 5 (Dokumentation) — baut auf Phase 1 (post_processing impl.) und Phase 4 (pool-caching) auf
```

## STATE.md

Siehe `.planning/STATE.md` für aktuellen Fortschritt.
