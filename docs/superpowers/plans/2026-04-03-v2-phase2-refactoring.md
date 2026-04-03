---
phase: 2
title: "Code Refactoring — LOC Violations"
version_target: "0.39.0-beta"
created: 2026-04-03
status: planned
---

# Phase 2 — Code Refactoring (LOC Violations)

**Ziel:** Alle Dateien >800 LOC auf <800 LOC bringen durch Extraktion von Submodulen.
Kein funktionaler Code ändert sich — nur Dateiorganisation. Barrel Re-Exports sichern
Backwards-Compatibility für alle bestehenden Imports.

**Parallelisierung:** Backend-Tasks (1–3) und Frontend-Tasks (4–7) sind vollständig
unabhängig voneinander und können parallel ausgeführt werden.

---

## Zusammenfassung

| # | Datei | Ist-LOC | Ziel | Extrakte |
|---|-------|---------|------|----------|
| 1 | `backend/providers/__init__.py` | 1404 | ~600 | `search_coordinator.py` (~600) |
| 2 | `backend/wanted_search/process.py` | 1067 | <800 | `post_processor.py` + `score_selector.py` |
| 3 | `backend/tests/test_security.py` | 1159 | gelöscht | 4 Domain-Dateien (je ~250–350) |
| 4 | `frontend/src/pages/Settings/ConnectionsSettings.tsx` | 938 | ~150 | 4 Sub-Komponenten |
| 5 | `frontend/src/pages/Settings/EventsTab.tsx` | 903 | ~300 | `EventsHooksTabContent.tsx` + `ScoringTabContent.tsx` |
| 6 | `frontend/src/pages/SeriesDetail.tsx` | 889 | ~400 | `SeriesEpisodeList.tsx` + `SeriesStatsPanel.tsx` |
| 7 | `frontend/src/api/system.ts` | 888 | ~100 | 6 Subdomain-Dateien + Barrel |

---

## BACKEND-TASKS (Tasks 1–3, parallel ausführbar)

---

### Task 1 — Split `backend/providers/__init__.py` (1404 LOC)

**Parallel mit:** Tasks 2, 3, 4, 5, 6, 7

**Analyse der Struktur:**

```
__init__.py enthält:
  - Zeilen 1–160:   Modul-Docstring, Imports, Registry-Dict, Decorator
                    register_provider(), get_provider_manager(),
                    invalidate_manager(), update_manager_providers(),
                    Flask-Context-Helpers (_has_flask_app_context etc.)
  - Zeilen 161–759: ProviderManager.__init__, _load_plugins, _init_providers,
                    _get_provider_config, _get_rate_limit,
                    _compute_dynamic_timeout, _get_timeout, _get_retries,
                    _check_rate_limit, _get_cache_backend,
                    _deserialize_results, _make_cache_key,
                    _search_provider_with_retry, _check_auto_disable
  - Zeilen 760–1122: ProviderManager.search() (die Thread-Pool-Orchestration)
  - Zeilen 1123–1404: search_with_fallback, download, search_and_download_best,
                      save_subtitle, get_provider, get_provider_status,
                      _get_provider_config_fields, shutdown, update_providers
```

**Extraktionsstrategie:**

Erstelle `backend/providers/search_coordinator.py` mit einer Mixin-Klasse
`SearchCoordinatorMixin`, die alle Search-spezifischen Methoden enthält.
`ProviderManager` in `__init__.py` erbt davon.

**Dateien:**

- `backend/providers/search_coordinator.py` (neu, ~620 LOC)
- `backend/providers/__init__.py` (modifiziert, ~780 LOC Ziel)

**Konkrete Schritte:**

1. Lese `backend/providers/__init__.py` vollständig.

2. Erstelle `backend/providers/search_coordinator.py`:

```python
"""Search coordination logic for ProviderManager.

Extracted from providers/__init__.py — contains the parallel search
orchestration, caching, retry logic, and result scoring.

Not instantiated directly — used as mixin by ProviderManager.
"""
```

   Enthält als `SearchCoordinatorMixin`-Klasse (keine eigene `__init__`):
   - `_get_cache_backend()` (static)
   - `_deserialize_results()` (static)
   - `_make_cache_key()`
   - `_search_provider_with_retry()`
   - `_check_auto_disable()`
   - `search()` (die gesamte ThreadPoolExecutor-Logik, Zeilen 760–1121)
   - `search_with_fallback()`

   Alle nötigen Imports werden in `search_coordinator.py` deklariert
   (json, logging, ThreadPoolExecutor, FutureTimeoutError, SubtitleResult etc.).
   Imports die Flask-Context oder DB benötigen bleiben als lokale Imports
   innerhalb der Methoden (Muster aus `config_instances.py` folgen, um
   zirkuläre Imports zu vermeiden).

3. Modifiziere `backend/providers/__init__.py`:

   - Füge oben hinzu: `from providers.search_coordinator import SearchCoordinatorMixin`
   - Ändere Klassendeklaration:
     `class ProviderManager(SearchCoordinatorMixin):` statt `class ProviderManager:`
   - Entferne die in `search_coordinator.py` extrahierten Methoden
   - Re-exports am Ende sicherstellen:
     ```python
     # Re-exports for callers that import directly from providers
     from providers.search_coordinator import SearchCoordinatorMixin as _  # noqa: F401
     ```

**Verifikation:**

```bash
cd backend && python -c "from providers import get_provider_manager; print('OK')"
cd backend && ruff check providers/__init__.py providers/search_coordinator.py
cd backend && python -m pytest tests/ -k "provider" --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  -x -q
```

**Done:** `__init__.py` < 800 LOC, `search_coordinator.py` < 700 LOC,
alle provider-Tests grün, kein Import-Fehler.

---

### Task 2 — Split `backend/wanted_search/process.py` (1067 LOC)

**Parallel mit:** Tasks 1, 3, 4, 5, 6, 7

**Analyse der Struktur:**

```
process.py enthält:
  Zeilen 1–20:     Imports
  Zeilen 22–46:    _try_auto_sync() — Post-Download-Helper
  Zeilen 48–205:   _process_forced_wanted_item() — Forced-Subtitle-Download-Pipeline
  Zeilen 207–875:  process_wanted_item() — Hauptpipeline
                     - Steps 1–4: Search & Download (Zeilen 319–875)
                     - Post-Download-Hooks (auto_sync, nfo_export,
                       record_subtitle_download, update_wanted_status)
                     - Upgrade-Logic (is_upgrade, current_score, should_upgrade)
                     - Translation-Pipeline (Steps 3+4)
                     - Job-Tracking (create_job, update_job, record_stat)
  Zeilen 877–1067: download_specific_for_item() — Manueller Download
```

**Extraktionsstrategie:**

Aufgrund der tiefen Verschachtelung der Steps in `process_wanted_item()` ist
ein vollständiger Methodenextract riskant (viele lokale Variablen als Parameter
nötig). Stattdessen: extrahiere die klar abgrenzbaren Hilfsfunktionen in
dedizierte Module, ohne die Hauptfunktion zu zerreißen.

**Dateien:**

- `backend/wanted_search/post_processor.py` (neu, ~150 LOC)
- `backend/wanted_search/score_selector.py` (neu, ~80 LOC)
- `backend/wanted_search/process.py` (modifiziert, ~800 LOC)

**Konkrete Schritte:**

1. Lese `backend/wanted_search/process.py` vollständig.

2. Erstelle `backend/wanted_search/post_processor.py`:

```python
"""Post-download processing helpers for wanted search.

Contains auto-sync triggering and NFO export logic extracted from process.py.
"""
```

   Extrahiere nach `post_processor.py`:
   - `_try_auto_sync(subtitle_path, video_path, settings)` — vollständig
     von `process.py` Zeilen 22–46 verschieben
   - `_write_download_nfo(output_path, provider_name, source_lang, target_lang, score)` —
     neue kleine Hilfsfunktion, die den `maybe_write_nfo`-Aufruf-Pattern kapselt
     (aus den 4 Stellen in `process.py` wo `maybe_write_nfo` aufgerufen wird)

3. Erstelle `backend/wanted_search/score_selector.py`:

```python
"""Score-based subtitle selection helpers for wanted search.

Contains best-match selection and upgrade comparison logic.
"""
```

   Extrahiere nach `score_selector.py`:
   - `select_best_result(results, min_score=0)` — neue Hilfsfunktion die
     die Logik `results[0] if results and results[0].score >= min_score else None`
     kapselt (an mehreren Stellen in process.py)
   - `is_score_upgrade(new_score, current_score, threshold=0)` — kapselt die
     `should_upgrade()`-Aufruf-Logik aus dem Upgrade-Check in `process_wanted_item`

4. Modifiziere `backend/wanted_search/process.py`:
   - Ersetze `_try_auto_sync` durch Import aus `post_processor`
   - Ersetze die `maybe_write_nfo`-Aufruf-Wiederholungen durch Aufrufe von
     `_write_download_nfo` aus `post_processor`
   - Importiere `select_best_result` aus `score_selector` (optional, wenn
     die Datei damit unter 800 LOC kommt; sonst reicht der Verschub von
     `_try_auto_sync` allein als erster Schritt)

   Prüfe nach jedem Teilschritt mit `wc -l` ob <800 LOC erreicht.

**Verifikation:**

```bash
cd backend && python -c "from wanted_search.process import process_wanted_item; print('OK')"
cd backend && ruff check wanted_search/
cd backend && python -m pytest tests/ -k "wanted" --tb=short -q \
  --ignore=tests/performance \
  -x -q
```

**Done:** `process.py` < 800 LOC, `post_processor.py` und `score_selector.py`
existieren, alle wanted-Tests grün, kein Import-Fehler.

---

### Task 3 — Split `backend/tests/test_security.py` (1159 LOC)

**Parallel mit:** Tasks 1, 2, 4, 5, 6, 7

**Analyse der Klassen:**

```
test_security.py enthält 14 Testklassen:

  DOWNLOAD-Domain (neue Datei: test_security_download.py):
    - TestArchiveUtils         (Zeilen 91–171)   — ZIP/RAR, ZIP-Bomb, ZIP-Slip
    - TestSubtitleSanitizer    (Zeilen 173–285)  — ASS/SRT Sanitization, XSS
    - TestProviderArchiveConsolidation (Zeilen 286–373) — Archive-Utils-Calls
    - TestValidateDownloadUrl  (Zeilen 685–808)  — Download-URL-Domain-Validation
    - TestProviderDownloadUrlValidation (Zeilen 809–839) — Provider-URL-Validation
    - TestFilenameSanitization (Zeilen 841–883)  — Path-Traversal in Filenames
    - TestMagicByteValidation  (Zeilen 961–1010) — Magic-Byte-Detection
    - TestStreamingDownload    (Zeilen 1012–1055) — Streaming-Size-Limit

  PATH-Domain (neue Datei: test_security_paths.py):
    - TestIsSafePath           (Zeilen 457–558)  — is_safe_path(), Path-Traversal

  PROMPT-Domain (neue Datei: test_security_prompt.py):
    - TestPromptInjectionGuard (Zeilen 885–959)  — Prompt-Injection Escaping

  AUTH-Domain (neue Datei: test_security_auth.py):
    - TestValidateServiceUrl   (Zeilen 374–455)  — SSRF, Dangerous Schemes
    - TestSocketIOLogSanitizer (Zeilen 560–616)  — Log-Sanitization
    - TestExtensionUrlValidation (Zeilen 618–683) — Config-API URL-Validation
    - TestWebhookExemptionWarning (Zeilen 1057–1159) — Webhook-Middleware-Exemption
```

**Gemeinsame Fixtures:**

Die Dateien `_make_zip()` (Zeilen 44–52) und `_mock_zip_infolist()` (Zeilen 53–90)
werden nur von `TestArchiveUtils` verwendet → gehören in `test_security_download.py`.

**Konkrete Schritte:**

1. Lese `backend/tests/test_security.py` vollständig (alle 1159 Zeilen).

2. Erstelle `backend/tests/test_security_download.py`:
   - Gleicher Standard-Header-Import-Block wie `test_security.py`
   - Kopiere: `_make_zip`, `_mock_zip_infolist`, `TestArchiveUtils`,
     `TestSubtitleSanitizer`, `TestProviderArchiveConsolidation`,
     `TestValidateDownloadUrl`, `TestProviderDownloadUrlValidation`,
     `TestFilenameSanitization`, `TestMagicByteValidation`, `TestStreamingDownload`

3. Erstelle `backend/tests/test_security_paths.py`:
   - Kopiere: `TestIsSafePath`

4. Erstelle `backend/tests/test_security_prompt.py`:
   - Kopiere: `TestPromptInjectionGuard`

5. Erstelle `backend/tests/test_security_auth.py`:
   - Kopiere: `TestValidateServiceUrl`, `TestSocketIOLogSanitizer`,
     `TestExtensionUrlValidation`, `TestWebhookExemptionWarning`

6. Ersetze `backend/tests/test_security.py` durch einen Import-Hub, der
   alle 4 Domain-Dateien re-importiert (damit bestehende Pytest-Runs
   die Datei weiterhin direkt aufrufen können):

   ```python
   """Security test hub — imports all domain test files.

   Kept for backwards compatibility with existing test invocations.
   Individual domains: test_security_download, test_security_paths,
   test_security_prompt, test_security_auth.
   """
   # noqa: F401 — re-exported for pytest collection
   from tests.test_security_download import *  # noqa: F403
   from tests.test_security_paths import *      # noqa: F403
   from tests.test_security_prompt import *     # noqa: F403
   from tests.test_security_auth import *       # noqa: F403
   ```

   ALTERNATIV: Lösche `test_security.py` vollständig wenn die CI keinen
   direkten Pfad-Aufruf darauf hat (check `pytest.ini` / `pyproject.toml` zuerst).

**Verifikation:**

```bash
# Alle 4 neuen Dateien einzeln grün
cd backend && python -m pytest tests/test_security_download.py --tb=short -q
cd backend && python -m pytest tests/test_security_paths.py --tb=short -q
cd backend && python -m pytest tests/test_security_prompt.py --tb=short -q
cd backend && python -m pytest tests/test_security_auth.py --tb=short -q

# Keine doppelten Test-IDs
cd backend && python -m pytest tests/test_security_download.py \
  tests/test_security_paths.py tests/test_security_prompt.py \
  tests/test_security_auth.py --collect-only -q | grep "ERROR\|DUPLICATE" || echo "Clean"

# LOC-Check
wc -l backend/tests/test_security_download.py \
       backend/tests/test_security_paths.py \
       backend/tests/test_security_prompt.py \
       backend/tests/test_security_auth.py
```

**Done:** Alle 4 neuen Dateien < 400 LOC, alle Tests grün, keine doppelten
Test-IDs, ursprüngliche Testsuite weiterhin ausführbar.

---

## FRONTEND-TASKS (Tasks 4–7, parallel ausführbar)

---

### Task 4 — Split `ConnectionsSettings.tsx` (938 LOC)

**Parallel mit:** Tasks 1, 2, 3, 5, 6, 7

**Analyse der Struktur:**

```
ConnectionsSettings.tsx enthält:
  Zeilen 1–30:    Imports, lazy MediaServersTab
  Zeilen 31–42:   generateId(), TabSkeleton()
  Zeilen 43–99:   Interfaces: ServiceInstance, InstanceStatus, InstanceState,
                  Funktionen: parseInstances(), serializeInstances()
  Zeilen 100–270: InstanceCard-Komponente (Multi-Instance-Card UI)
  Zeilen 271–511: SonarrMultiInstanceSection() (~241 LOC)
  Zeilen 392–512: RadarrMultiInstanceSection() (~120 LOC, strukturgleich)
  Zeilen 513–728: MetadataApiKeysSection() (API-Keys: TMDb, Fanart, TVdb)
  Zeilen 729–770: FfmpegTimeoutField()
  Zeilen 771–870: MetadataSectionWrapper() + StandaloneSection()
  Zeilen 871–938: ConnectionsSettings() — Orchestrator (~67 LOC)
```

**Extraktionsstrategie:**

Die Hauptkomponente `ConnectionsSettings()` ist bereits kompakt (~67 LOC).
Das Problem ist alles davor. Extrahiere nach funktionalen Gruppen:

**Dateien:**

- `frontend/src/pages/Settings/connections/InstanceCard.tsx` (neu, ~200 LOC)
  — `ServiceInstance`, `InstanceStatus`, `InstanceState`, `parseInstances`,
    `serializeInstances`, `InstanceCardProps`, `InstanceCard`
- `frontend/src/pages/Settings/connections/MediaServerConnections.tsx` (neu, ~280 LOC)
  — `SonarrMultiInstanceSection`, `RadarrMultiInstanceSection`
- `frontend/src/pages/Settings/connections/MetadataSection.tsx` (neu, ~270 LOC)
  — `MetadataApiKeysSection`, `FfmpegTimeoutField`, `MetadataSectionWrapper`,
    `StandaloneSection`
- `frontend/src/pages/Settings/ConnectionsSettings.tsx` (modifiziert, ~120 LOC)
  — Nur noch Imports + `ConnectionsSettings()` Orchestrator

**Konkrete Schritte:**

1. Lese `ConnectionsSettings.tsx` vollständig.

2. Erstelle `connections/`-Verzeichnis unter
   `frontend/src/pages/Settings/connections/`.

3. Erstelle `connections/InstanceCard.tsx`:
   - Übernimm alle Interfaces (`ServiceInstance`, `InstanceStatus`,
     `InstanceState`, `InstanceCardProps`)
   - Übernimm `parseInstances`, `serializeInstances`, `generateId`
   - Übernimm `InstanceCard`-Komponente
   - Exportiere alles named: `export function InstanceCard...`,
     `export interface ServiceInstance...` etc.

4. Erstelle `connections/MediaServerConnections.tsx`:
   - Importiere `InstanceCard` und Interfaces aus `./InstanceCard`
   - Übernimm `SonarrMultiInstanceSection`, `RadarrMultiInstanceSection`
   - Alle nötigen Hooks/API-Imports bleiben direkt in dieser Datei

5. Erstelle `connections/MetadataSection.tsx`:
   - Übernimm `MetadataApiKeysSection`, `FfmpegTimeoutField`,
     `MetadataSectionWrapper`, `StandaloneSection`
   - Alle nötigen Hooks/API-Imports bleiben direkt in dieser Datei

6. Modifiziere `ConnectionsSettings.tsx`:
   - Behalte nur: Imports der neuen Sub-Komponenten + lazy MediaServersTab +
     `TabSkeleton` + `ConnectionsSettings()` Orchestrator
   - Alle anderen Definitionen entfernen (jetzt in Sub-Dateien)
   - Exports: `ConnectionsSettings` bleibt named export (keine Breaking Change)

**Verifikation:**

```bash
cd frontend && npx tsc --noEmit
cd frontend && npm run lint -- --max-warnings=0
# Visuell: Settings → Connections — alle Sektionen (Sonarr, Radarr,
# Media Servers, Metadata API Keys, Standalone) müssen rendern
```

**Done:** `ConnectionsSettings.tsx` < 130 LOC, alle 3 neuen Sub-Dateien < 300 LOC,
`tsc --noEmit` clean, keine broken imports.

---

### Task 5 — Split `EventsTab.tsx` (903 LOC)

**Parallel mit:** Tasks 1, 2, 3, 4, 6, 7

**Analyse der Struktur:**

```
EventsTab.tsx enthält ZWEI völlig unabhängige Exports:
  Zeilen 1–17:    Imports (gemischt für beide Tabs)
  Zeilen 18–399:  export function EventsHooksTab() — Events, Hooks,
                  Webhooks, Logs (~382 LOC)
  Zeilen 400–903: export function ScoringTab() — Scoring Weights,
                  Provider Modifiers, Presets (~503 LOC)
                    - ReleaseGroupSection() (Zeilen 686–810)
                    - MtDetectionSection() (Zeilen 811–903)
```

**Extraktionsstrategie:**

Die beiden Exports sind vollständig unabhängig. Beide in eigene Dateien.
Der Dateiname `EventsTab.tsx` ist irreführend — er enthält auch das gesamte
Scoring. Aufteilen nach Export:

**Dateien:**

- `frontend/src/pages/Settings/EventsHooksTab.tsx` (neu, ~400 LOC)
  — Enthält `export function EventsHooksTab()` vollständig
- `frontend/src/pages/Settings/ScoringTab.tsx` (neu, ~510 LOC)
  — Enthält `export function ScoringTab()`, `ReleaseGroupSection`,
    `MtDetectionSection` vollständig
- `frontend/src/pages/Settings/EventsTab.tsx` (modifiziert, ~10 LOC)
  — Nur noch Barrel Re-export:
    ```typescript
    export { EventsHooksTab } from './EventsHooksTab'
    export { ScoringTab } from './ScoringTab'
    ```

**Wichtig:** Importende Dateien referenzieren `EventsTab` nicht direkt —
die Router/Settings-Index importieren `EventsHooksTab` und `ScoringTab`
direkt. Prüfe mit grep vor dem Split:

```bash
grep -rn "EventsTab\|ScoringTab\|EventsHooksTab" \
  frontend/src/pages/Settings/index.tsx \
  frontend/src/pages/Settings/SettingsOverview.tsx \
  frontend/src/ --include="*.tsx" --include="*.ts" | grep -v "EventsTab.tsx"
```

Passe alle gefundenen Import-Stellen an.

**Konkrete Schritte:**

1. Lese `EventsTab.tsx` vollständig.
2. Identifiziere welche Imports zu `EventsHooksTab` vs. `ScoringTab` gehören
   (alle Imports aus Zeilen 1–17 aufteilen nach Verwendung).
3. Erstelle `EventsHooksTab.tsx` mit den Imports die `EventsHooksTab` benötigt
   + der vollständigen Funktion.
4. Erstelle `ScoringTab.tsx` mit den Imports die `ScoringTab`,
   `ReleaseGroupSection`, `MtDetectionSection` benötigen + allen 3 Funktionen.
5. Ersetze `EventsTab.tsx` durch den Barrel Re-export.
6. Aktualisiere alle Import-Stellen außerhalb der Datei (Step grep oben).

**Verifikation:**

```bash
cd frontend && npx tsc --noEmit
cd frontend && npm run lint -- --max-warnings=0
# Visuell: Settings → Events (alle Hooks/Webhooks/Logs sichtbar)
# Visuell: Settings → Scoring (alle Weights/Presets sichtbar)
```

**Done:** `EventsHooksTab.tsx` < 420 LOC, `ScoringTab.tsx` < 520 LOC,
`EventsTab.tsx` < 15 LOC (Barrel), `tsc --noEmit` clean.

**Hinweis:** `ScoringTab.tsx` wird >400 LOC bleiben — das ist akzeptabel
solange es unter 800 liegt. Keine weitere Aufspaltung nötig.

---

### Task 6 — Split `SeriesDetail.tsx` (889 LOC)

**Parallel mit:** Tasks 1, 2, 3, 4, 5, 7

**Analyse der Struktur:**

```
SeriesDetail.tsx enthält eine einzige Export-Funktion:
  Zeilen 1–40:    Imports (15+ lazy-loaded Komponenten, Hooks, Types)
  Zeilen 42–200:  SeriesDetailPage() State-Setup
                  (useState, useMemo, useQuery für alle Daten)
  Zeilen 200–500: Episode-Grid-Rendering (Season-Tabs, Episode-Cards,
                  Subtitle-Status-Badges, Wanted-Actions)
  Zeilen 500–700: Episode-Detail-Panels (Search, History, Tracks, Glossary)
  Zeilen 700–800: Sidecar-Management (Subtitle-Liste, Delete, Cleanup)
  Zeilen 800–889: Page-Layout (Web-Player, Stats-Cards, Modal-Orchestration)
```

**Extraktionsstrategie:**

Die tiefe State-Abhängigkeit (viele `useState`/`useMemo` die über alle
Bereiche fließen) macht einen vollständigen Funktionsextract riskant.
Extrahiere nur die rein darstellenden Sub-Bereiche die klare Props-Grenzen haben:

**Dateien:**

- `frontend/src/pages/SeriesEpisodeList.tsx` (neu, ~250 LOC)
  — Pure Presentational Component für das Episode-Grid
  — Props: `episodes`, `seasons`, `activeSeason`, `onSeasonChange`,
    `subtitleStatusMap`, `expandedEp`, `onEpisodeAction`,
    `episodeWantedMap`, `onSkip`, `onAccept`

- `frontend/src/pages/SeriesStatsPanel.tsx` (neu, ~100 LOC)
  — Stats-Cards (Gefunden/Wanted/Prozent) + Provider-History-Summary
  — Props: `series`, `episodes`

- `frontend/src/pages/SeriesDetail.tsx` (modifiziert, ~540 LOC)
  — Behält alle State, Hooks, Daten-Loading, Modal-Orchestration
  — Verwendet `SeriesEpisodeList` und `SeriesStatsPanel` als Sub-Komponenten

**Wichtig — Verifikation vor dem Split:** `SeriesDetail.tsx` hat viele
geschützte UI-Bereiche (laut `docs/PROTECTED.md`). Vor der Extraktion:

```bash
cat "D:/Sublarr_Projekt/Sublarr/docs/PROTECTED.md" | grep -A5 -i "series\|episode"
```

Die Extraktion darf kein visuelles Verhalten ändern.

**Konkrete Schritte:**

1. Lese `SeriesDetail.tsx` vollständig.
2. Prüfe `PROTECTED.md` auf SeriesDetail-Einträge.
3. Identifiziere den Episode-Grid-Render-Block: alle JSX-Elemente die
   Season-Tabs, Episode-Karten und Subtitle-Status darstellen —
   typischerweise ein `<div>` oder `<section>` mit map über `filteredEpisodes`.
4. Erstelle `SeriesEpisodeList.tsx`:
   - Definiere Props-Interface aus den benötigten Werten des Grid-Blocks
   - Extrahiere den JSX-Block als eigenständige Komponente
   - Alle benötigten Typen importieren aus `@/lib/types`
5. Erstelle `SeriesStatsPanel.tsx`:
   - Props: `series` (SeriesDetail-Typ), evtl. `episodeCount`, `foundCount`
   - Extrahiere Stats-Cards JSX
6. In `SeriesDetail.tsx`: Ersetze extrahierte JSX-Blöcke durch
   `<SeriesEpisodeList ... />` und `<SeriesStatsPanel ... />`

**Verifikation:**

```bash
cd frontend && npx tsc --noEmit
cd frontend && npm run lint -- --max-warnings=0
cd frontend && npm run test -- --run src/pages/__tests__/
# Visuell: SeriesDetail aufrufen — Episode-Grid und Stats sichtbar,
# Season-Filter funktioniert, Subtitle-Status-Badges korrekt
```

**Done:** `SeriesDetail.tsx` < 600 LOC, `SeriesEpisodeList.tsx` < 280 LOC,
`SeriesStatsPanel.tsx` < 130 LOC, `tsc --noEmit` clean, alle Episode-Tests grün.

---

### Task 7 — Split `frontend/src/api/system.ts` (888 LOC)

**Parallel mit:** Tasks 1, 2, 3, 4, 5, 6

**Analyse der Sektionen:**

```
system.ts enthält 25 benannte Sektionen (// ─── ...) und ~80 Funktionen.

Gruppierung nach Domain:
  system/blacklist.ts      — Blacklist, History (Zeilen 18–58, ~40 LOC)
  system/notifications.ts  — Notifications, Templates, QuietHours,
                             NotificationHistory, NotificationFilter (Zeilen 59–402, ~345 LOC)
  system/logs.ts           — Logs, LogRotation (Zeilen 76–184, ~60 LOC)
                             ACHTUNG: Logs überschneidet sich mit Notifications in
                             der Zeilennummerierung — Logs ist zwischen
                             Notifications-Gruppen platziert
  system/backup.ts         — FullBackup, SupportExport (Zeilen 149–209, ~60 LOC)
  system/subtitle-tools.ts — SubtitleTools, HealthCheck, AutoSync, Sync,
                             QualityFixes, FormatConversion, Waveform,
                             SubtitleDiff, SubtitleProcessing (Zeilen 210–888, ~470 LOC)
  system/tasks.ts          — SchedulerTasks (Zeilen 247–253, ~7 LOC)
  system/cleanup.ts        — CleanupSystem (Zeilen 403–478, ~75 LOC)
  system/audio.ts          — Audio, SpellChecking, OCR (Zeilen 479–587, ~108 LOC)
  system/integrations.ts   — ExternalIntegrations, VideoSync (Zeilen 588–684, ~100 LOC)
  system/standalone.ts     — StandaloneMode, Statistics (Zeilen 85–148, ~65 LOC)
```

**Praktische Zusammenfassung (LOC-orientiert, Dateien <300 LOC):**

Da viele Gruppen sehr klein sind, konsolidiere zu 5 Subdateien:

| Datei | Sektionen | Ziel-LOC |
|-------|-----------|---------|
| `system/notifications.ts` | Notifications, Templates, QuietHours, History, Filter | ~200 |
| `system/subtitle-tools.ts` | SubtitleTools, HealthCheck, AutoSync, Sync, QualityFixes, Format, Waveform, Diff, Processing | ~480 |
| `system/operations.ts` | Blacklist, History, Logs, LogRotation, Backup, SupportExport, Tasks, Cleanup | ~180 |
| `system/media.ts` | Audio, SpellCheck, OCR, ExternalIntegrations, VideoSync | ~200 |
| `system/library.ts` | StandaloneMode, Statistics | ~65 |

**Hinweis:** `system/subtitle-tools.ts` wird ~480 LOC haben — das ist unter 800
und akzeptabel. Alle Types werden aus `@/lib/types` importiert.

**Dateien:**

- `frontend/src/api/system/` (neues Verzeichnis)
- `frontend/src/api/system/notifications.ts` (neu, ~200 LOC)
- `frontend/src/api/system/subtitle-tools.ts` (neu, ~480 LOC)
- `frontend/src/api/system/operations.ts` (neu, ~180 LOC)
- `frontend/src/api/system/media.ts` (neu, ~200 LOC)
- `frontend/src/api/system/library.ts` (neu, ~65 LOC)
- `frontend/src/api/system.ts` (modifiziert, ~60 LOC — Barrel Re-export)

**Konkrete Schritte:**

1. Lese `frontend/src/api/system.ts` vollständig.
2. Identifiziere welche Types jede Gruppe braucht (aus dem `import type`-Block
   Zeilen 1–16).
3. Erstelle `frontend/src/api/system/`-Verzeichnis.
4. Erstelle jede Sub-Datei:
   - Beginne mit `import { api } from '../core'`
   - Füge nur die nötigen `import type`-Statements hinzu
   - Kopiere die zugehörigen Funktionen
5. Ersetze `frontend/src/api/system.ts` durch Barrel Re-export:
   ```typescript
   // Barrel re-export — alle Imports aus @/api/system bleiben gültig
   export * from './system/notifications'
   export * from './system/subtitle-tools'
   export * from './system/operations'
   export * from './system/media'
   export * from './system/library'
   ```
6. Prüfe ob andere Dateien `system.ts` direkt via `./system` importieren
   (nicht über `@/api/system`):
   ```bash
   grep -rn "from './system'\|from \"./system\"" frontend/src/api/
   ```
   Solche Imports müssen nicht angepasst werden — der Barrel deckt das ab.

**Verifikation:**

```bash
cd frontend && npx tsc --noEmit
cd frontend && npm run lint -- --max-warnings=0
# Smoke-Test: eine Funktion aus jeder Sub-Datei importieren
cd frontend && node -e "
  const { getLogs } = require('./src/api/system.ts')
  console.log(typeof getLogs) // 'function'
" 2>&1 || echo "(node kann TS nicht direkt — tsc reicht)"
```

**Done:** `system.ts` < 70 LOC (Barrel), alle 5 Sub-Dateien < 500 LOC,
`tsc --noEmit` clean, keine broken imports in der gesamten Frontend-Codebase.

---

## Gesamtverifikation

Nach Abschluss aller Tasks:

```bash
# 1. LOC-Check aller betroffenen Dateien
wc -l \
  backend/providers/__init__.py \
  backend/providers/search_coordinator.py \
  backend/wanted_search/process.py \
  backend/wanted_search/post_processor.py \
  backend/wanted_search/score_selector.py \
  backend/tests/test_security_download.py \
  backend/tests/test_security_paths.py \
  backend/tests/test_security_prompt.py \
  backend/tests/test_security_auth.py \
  frontend/src/pages/Settings/ConnectionsSettings.tsx \
  frontend/src/pages/Settings/EventsHooksTab.tsx \
  frontend/src/pages/Settings/ScoringTab.tsx \
  frontend/src/pages/SeriesDetail.tsx \
  frontend/src/api/system.ts

# 2. Backend — ruff + alle Tests
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook \
       or test_parse_llm_response_too_many_merge or test_record_backend_success)"

# 3. Frontend — lint + TypeScript + Tests
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

**Erfolgskriterien:**

- Alle 7 Original-Dateien < 800 LOC (oder durch Barrel ersetzt)
- Keine einzige neue Datei > 800 LOC
- Ruff: clean (kein Error, kein Warning)
- `tsc --noEmit`: clean
- Backend-Tests: alle grün (mit Standard-Ignores)
- Frontend-Tests: alle grün
- Kein funktionaler Code geändert — nur Dateiorganisation

---

## Reihenfolge-Empfehlung

```
Welle 1 (parallel starten):
  Backend:  Task 1, Task 2, Task 3
  Frontend: Task 4, Task 5, Task 6, Task 7

Welle 2 (nach Welle 1):
  Gesamtverifikation
```

Backend und Frontend können vollständig parallel bearbeitet werden, da
keine gemeinsamen Dateien berührt werden.

Innerhalb des Backends ist Task 3 (Test-Split) am risikoärmsten und kann
zuerst commitet werden. Task 1 hat das höchste Risiko (Mixin-Architektur) —
nach dem Split direkt mit `python -c "from providers import get_provider_manager"`
verifizieren bevor weitergemacht wird.
