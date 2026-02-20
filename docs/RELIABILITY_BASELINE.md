# Reliability Baseline — Stand 2026-02-XX

> **Zweck:** Dokumentation des aktuellen Zuverlässigkeits-Status als Ausgangspunkt für Stabilisierungsmaßnahmen.
> Diese Baseline wird wöchentlich aktualisiert, um Fortschritt zu messen.

## Executive Summary

**Status:** ⚠️ **Stabilisierungsbedarf erkannt**

- **CI-Pipeline:** 15+ Checks mit `continue-on-error: true` — Fehler werden ignoriert
- **Test-Suite:** Struktur vorhanden, aber Flaky-Tests nicht isoliert
- **Error-Handling:** Strukturiertes System vorhanden, aber nicht alle kritischen Pfade abgedeckt
- **Health-Checks:** Basis vorhanden, aber nicht alle Ausfallursachen überwacht

---

## 1. CI-Pipeline Status

### Fail-Open Checks (kritisch)

Die folgenden Checks schlagen nicht fehl, auch wenn sie Fehler finden:

| Check | Job | Status | Priorität |
|-------|-----|--------|-----------|
| `mypy` (Type Checking) | `backend` | `continue-on-error: true` | 🔴 **Hoch** |
| Coverage Upload | `backend`, `frontend` | `fail_ci_if_error: false` | 🟡 Mittel |
| Code Quality (vulture, bandit, radon) | `code-quality` | `continue-on-error: true` | 🟡 Mittel |
| Security Scans (pip-audit, npm audit, trivy) | `security-scan` | `continue-on-error: true` | 🔴 **Hoch** |
| License Checks | `license-check` | `continue-on-error: true` | 🟢 Niedrig |
| E2E Tests | `e2e-tests` | `continue-on-error: true` | 🔴 **Hoch** |
| Performance Tests | `performance-tests` | `continue-on-error: true` | 🟢 Niedrig |

**Gesamt:** 15+ Checks, die Fehler verstecken können.

### Verbindliche Checks (funktionieren)

- ✅ `ruff check` (Linting)
- ✅ `ruff format --check` (Formatting)
- ✅ `pytest` (Backend Tests)
- ✅ `vitest` (Frontend Tests)
- ✅ `eslint` (Frontend Linting)
- ✅ `prettier --check` (Frontend Formatting)
- ✅ `tsc --noEmit` (TypeScript Type Check)
- ✅ Integration Tests

**Problem:** `ci-status` Job prüft nur `backend` und `frontend` Jobs — andere Fehler werden ignoriert.

---

## 2. Kritische User-Flows

### Flow 1: Subtitle-Suche und Download (Kern-Workflow)

**Pfad:**
1. Wanted-Scanner erkennt fehlende Untertitel
2. Provider-Suche (AnimeTosho, Jimaku, OpenSubtitles, SubDL)
3. Beste Subtitle auswählen (Scoring)
4. Download + Extraktion (ZIP/RAR/XZ)
5. Optional: Übersetzung via LLM (Ollama/DeepL/etc.)
6. Datei speichern + Jellyfin/Emby/Plex Refresh

**Risikopunkte:**
- Provider-API-Fehler (Rate Limits, Timeouts)
- Datei-Extraktion (ZIP/RAR/XZ kann fehlschlagen)
- Übersetzungs-Pipeline (Ollama-Verbindung, Model-Fehler)
- Dateisystem-Operationen (Berechtigungen, Speicherplatz)

**Smoke-Test:**
```bash
# API-Endpoint testen
curl http://localhost:5765/api/v1/wanted/refresh
curl http://localhost:5765/api/v1/wanted/<id>/search
```

### Flow 2: Übersetzung (ASS/SRT)

**Pfad:**
1. Embedded Subtitle Detection (ffprobe)
2. ASS-Parsing (Styles, Events)
3. Style-Klassifizierung (Dialog vs. Signs/Songs)
4. LLM-Übersetzung (Batch-Processing)
5. Re-Assembly (Tags, Formatting)
6. Validierung (Zeilenanzahl, Halluzination)

**Risikopunkte:**
- ffprobe nicht verfügbar oder fehlerhaft
- ASS-Parsing-Fehler (ungültige Dateien)
- LLM-Verbindung (Ollama nicht erreichbar)
- Übersetzungsqualität (Halluzinationen, falsche Sprachen)

**Smoke-Test:**
```bash
# Health-Check
curl http://localhost:5765/api/v1/health/detailed
# Sollte "ollama" oder Translation-Backend-Status enthalten
```

### Flow 3: Webhook-Automatisierung

**Pfad:**
1. Sonarr/Radarr sendet Webhook (Download Complete)
2. Sublarr empfängt Webhook
3. Auto-Scan → Auto-Search → Auto-Translate
4. Notification (Apprise)

**Risikopunkte:**
- Webhook-Empfang (Auth, Parsing)
- Race Conditions (mehrere Webhooks gleichzeitig)
- Sonarr/Radarr nicht erreichbar

**Smoke-Test:**
```bash
# Webhook simulieren
curl -X POST http://localhost:5765/api/v1/webhook/sonarr \
  -H "Content-Type: application/json" \
  -d '{"eventType": "Download"}'
```

### Flow 4: Frontend → Backend API

**Pfad:**
1. React-App lädt
2. API-Calls (Library, Wanted, Settings)
3. WebSocket-Verbindung (Real-Time Updates)
4. UI-Updates

**Risikopunkte:**
- API-Auth (API-Key)
- CORS-Probleme
- WebSocket-Verbindung bricht ab
- Frontend-Build-Fehler

**Smoke-Test:**
```bash
# Frontend baut?
cd frontend && npm run build
# API erreichbar?
curl http://localhost:5765/api/v1/health
```

---

## 3. Bekannte Probleme / Fehlerbilder

### Problem 1: mypy Type-Errors werden ignoriert

**Symptom:** CI läuft grün, aber Type-Errors existieren.

**Impact:** 🟡 Mittel — Kann zu Runtime-Fehlern führen.

**Lösung:** mypy schrittweise verbindlich machen (siehe Woche 3).

### Problem 2: Security-Scans werden ignoriert

**Symptom:** `pip-audit`, `npm audit`, `trivy` finden Vulnerabilities, aber CI schlägt nicht fehl.

**Impact:** 🔴 **Hoch** — Security-Risiken werden nicht erkannt.

**Lösung:** Security-Scans verbindlich machen, aber nur für kritische Vulnerabilities.

### Problem 3: E2E-Tests sind optional

**Symptom:** Playwright-Tests schlagen fehl, aber CI läuft weiter.

**Impact:** 🔴 **Hoch** — Frontend-Integration wird nicht getestet.

**Lösung:** E2E-Tests stabilisieren oder in separaten Job isolieren.

### Problem 4: Provider-Fehler werden nicht ausreichend abgefangen

**Symptom:** Provider-API-Fehler führen zu unhandled Exceptions.

**Impact:** 🔴 **Hoch** — Kern-Workflow bricht ab.

**Lösung:** Defensive Guards in `wanted_search.py` und Provider-Code.

### Problem 5: Übersetzungs-Pipeline hat keine Fallback-Mechanismen

**Symptom:** Wenn Ollama nicht erreichbar ist, bricht alles ab.

**Impact:** 🟡 Mittel — Fallback-Chains existieren, aber nicht überall.

**Lösung:** Fallback-Chains überall implementieren (siehe Woche 2).

---

## 4. Test-Suite Status

### Backend Tests

**Struktur:**
- Unit Tests: `backend/tests/test_*.py`
- Integration Tests: `backend/tests/integration/`
- Performance Tests: `backend/tests/performance/`

**Coverage-Ziel:** 80%+ (laut `pytest.ini`)

**Bekannte Flaky-Tests:** (noch zu identifizieren)

### Frontend Tests

**Struktur:**
- Unit Tests: `frontend/src/**/*.test.tsx`
- E2E Tests: `frontend/tests/e2e/` (Playwright)

**Coverage-Ziel:** 70%+ (laut `vitest.config.ts`)

**Bekannte Flaky-Tests:** E2E-Tests (werden ignoriert)

---

## 5. Error-Handling Status

### Strukturiertes Error-System vorhanden

**Datei:** `backend/error_handler.py`

**Features:**
- ✅ Exception-Hierarchie (`SublarrError`, `TranslationError`, `DatabaseError`, etc.)
- ✅ Strukturierte JSON-Responses
- ✅ Request-ID-Tracking
- ✅ Troubleshooting-Hints

**Fehlend:**
- ❌ Nicht alle kritischen Pfade nutzen strukturierte Errors
- ❌ Provider-Fehler werden nicht immer abgefangen
- ❌ Dateisystem-Operationen haben keine Guards

---

## 6. Health-Checks Status

### Basis vorhanden

**Endpoints:**
- `/api/v1/health` — Basis-Health-Check
- `/api/v1/health/detailed` — Detaillierter Status

**Überwachte Komponenten:**
- ✅ Database-Connectivity
- ✅ Provider-Health (teilweise)
- ✅ Translation-Backend-Status (teilweise)
- ✅ Media-Server-Status (teilweise)

**Fehlend:**
- ❌ Disk-Space-Checks
- ❌ Memory/CPU-Monitoring
- ❌ Provider-Response-Time-Tracking (nur teilweise)
- ❌ Übersetzungs-Quality-Metrics

---

## 7. Smoke-Tests (Kern-Workflows)

### Definition

Smoke-Tests sind minimale Tests, die prüfen, ob die Kern-Funktionalität funktioniert.

### Test 1: API ist erreichbar

```bash
curl http://localhost:5765/api/v1/health
# Erwartet: {"status": "ok"} oder ähnlich
```

### Test 2: Frontend baut

```bash
cd frontend && npm run build
# Erwartet: Build erfolgreich, keine Fehler
```

### Test 3: Backend-Tests laufen

```bash
cd backend && pytest tests/test_server.py -v
# Erwartet: Alle Tests grün
```

### Test 4: Provider-System funktioniert

```bash
curl http://localhost:5765/api/v1/providers
# Erwartet: Liste von Providern
```

### Test 5: Übersetzungs-Backend ist erreichbar

```bash
curl http://localhost:5765/api/v1/health/detailed
# Erwartet: Translation-Backend-Status
```

---

## 8. Metriken (Vorher/Nachher)

### Baseline (Stand: 2026-02-XX)

| Metrik | Wert | Ziel |
|--------|------|------|
| CI-Checks mit `continue-on-error` | 15+ | 0 (kritische Checks) |
| Flaky-Tests | ? | 0 |
| Test-Coverage (Backend) | ? | 80%+ |
| Test-Coverage (Frontend) | ? | 70%+ |
| Bekannte kritische Bugs | ? | 0 |
| Smoke-Tests definiert | 5 | 5+ |

### Nach 30 Tagen (Ziel)

| Metrik | Ziel |
|--------|------|
| CI-Checks mit `continue-on-error` | ≤ 5 (nur optionale Checks) |
| Flaky-Tests | 0 |
| Test-Coverage (Backend) | 80%+ |
| Test-Coverage (Frontend) | 70%+ |
| Bekannte kritische Bugs | 0 |
| Smoke-Tests definiert | 10+ |

---

## 9. Prioritäten (Top-3 für Woche 2)

1. **Provider-Fehler abfangen** — Defensive Guards in `wanted_search.py`
2. **Übersetzungs-Pipeline absichern** — Fallback-Mechanismen
3. **Dateisystem-Operationen absichern** — Guards für Speicherplatz, Berechtigungen

---

## 10. Nächste Schritte

- [ ] Woche 1: Baseline dokumentiert ✅
- [ ] Woche 2: Top-3 Reliability-Bugs beheben
- [ ] Woche 3: CI-Gates verschärfen
- [ ] Woche 4: Runbook + Monitoring

---

## 11. Fortschritt (Woche 1-4)

### Woche 1 ✅ (abgeschlossen)
- [x] Reliability-Baseline dokumentiert
- [x] Smoke-Tests erstellt (Bash + PowerShell)
- [x] Kritische User-Flows identifiziert

### Woche 2 ✅ (abgeschlossen)
- [x] Provider-Fehler abgefangen (defensive Guards in `wanted_search.py`)
- [x] Dateisystem-Operationen abgesichert (Disk-Space-Check in `save_subtitle`)
- [x] Übersetzungs-Pipeline verbessert (bessere Fehlerbehandlung, Cleanup)
- [x] Regressionstests erstellt (`test_wanted_search_reliability.py`)

### Woche 3 ✅ (abgeschlossen)
- [x] mypy Type-Checking verbindlich gemacht
- [x] Security-Scans verschärft (fail on high/critical)
- [x] CI-Status-Job verbessert (kritische vs. optionale Jobs)

### Woche 4 ✅ (abgeschlossen)
- [x] Incident-Runbook erstellt (`INCIDENT_RUNBOOK.md`)
- [x] Health-Checks bereits vorhanden (`/api/v1/health/detailed`)

---

**Letzte Aktualisierung:** 2026-02-XX  
**Nächste Review:** Wöchentlich (jeden Montag)
