# Safety Roadmap — Code Stability, Security & Best Practices

> **Fokus:** Interne Netzwerk-Nutzung (Home Lab)
> Keine externe Exposition, kein Reverse Proxy erforderlich.
> Prioritaet auf Code-Stabilitaet, Datenintegritaet und Wartbarkeit.

## Status-Uebersicht

### Phase 1: Foundation Safety (v1.0-beta) — ABGESCHLOSSEN

| Bereich | Status | Beschreibung |
|---|---|---|
| Basis-Authentifizierung | ✅ | Optional API-Key Auth (hmac.compare_digest) |
| Input Validation | ✅ | Pydantic Settings, Parameterized Queries |
| Path Traversal | ✅ | Path-Mapping, Media-Directory-Validation |
| SQL Injection | ✅ | Parameterized Queries, keine String-Interpolation |
| Secrets Management | ✅ | Secrets nie in Logs/Responses |
| Logging | ✅ | RotatingFileHandler, WebSocket-Logs, optionales JSON-Format |
| Error Handling | ✅ | Zentralisierte Exception-Hierarchie, strukturierte JSON-Responses |

### Phase 2: Code Quality & Testing — IMPLEMENTIERT

| Milestone | Status | Beschreibung | Completion |
|---|---|---|---|
| S1 | ✅ Erledigt | CI/CD Pipeline (Tests, Linting, Type-Checking) | 100% |
| S2 | ✅ Erledigt | Code Quality Tools (ruff, mypy strict, Coverage) | 100% |
| S3 | ✅ Erledigt | Erweiterte Tests (Integration, Provider, Translator) | 85% |
| S4 | ✅ Erledigt | Dependency Management & Security Scanning | 100% |
| S5 | ✅ Erledigt | Error Handling & Resilience Patterns | 95% |
| S6 | ✅ Erledigt | Database Safety & Backup-System | 90% |
| S7 | ✅ Erledigt | Monitoring & Observability | 90% |
| S8 | ✅ Erledigt | Container Safety & Best Practices | 95% |

---

## Implementierungs-Details

### S1: CI/CD Pipeline — ✅ 100%

- [x] GitHub Actions CI-Pipeline (`.github/workflows/ci.yml`)
- [x] Backend Tests: `pytest` mit Coverage
- [x] Frontend Tests: `vitest` mit Coverage
- [x] Python Linting: `ruff check`
- [x] TypeScript Linting: `eslint`
- [x] Python Type-Checking: `mypy`
- [x] TypeScript Type-Checking: `tsc --noEmit`
- [x] Pre-commit Hooks (`.pre-commit-config.yaml`)
- [x] Coverage-Badges in README (Codecov)

### S2: Code Quality Tools — ✅ 100%

- [x] `ruff` Integration (Linting + Formatting)
- [x] `mypy` strict mode (`disallow_untyped_defs`, `disallow_incomplete_defs`)
- [x] `vulture` (Dead Code Detection)
- [x] `bandit` (Security-Scanning)
- [x] `radon` (Complexity-Analyse)
- [x] TypeScript strict mode
- [x] CI-Integration mit `continue-on-error` fuer schrittweise Migration

### S3: Erweiterte Tests — ✅ 85%

- [x] Backend Integration Tests (`tests/integration/`)
  - [x] API-Endpoint-Tests
  - [x] Database-Operation-Tests
  - [x] Provider-Integration-Tests
  - [x] Webhook-Tests
  - [x] **Translation-Pipeline-Tests** (`test_translator_pipeline.py`)
  - [x] **Provider-Pipeline-Tests** (`test_provider_pipeline.py`)
- [x] Test-Fixtures (`conftest.py`): mock_ollama, mock_provider_manager, create_test_subtitle
- [ ] Frontend E2E Tests (Playwright) — geplant fuer spaeter
- [ ] Performance Tests (locust/pytest-benchmark) — geplant fuer spaeter

### S4: Dependency Management — ✅ 100%

- [x] `requirements.in` + `requirements.txt` (pip-tools)
- [x] `package-lock.json` fuer Frontend
- [x] Dependabot-Integration (`.github/dependabot.yml`)
- [x] `pip-audit` fuer Python Security-Scanning
- [x] `npm audit` fuer Frontend
- [x] License-Compliance Checks

### S5: Error Handling & Resilience — ✅ 95%

- [x] **Custom Exception-Hierarchie** (`error_handler.py`):
  ```
  SublarrError (Basis)
    ├── TranslationError (TRANS_001)
    │   ├── OllamaConnectionError (TRANS_002, 503)
    │   └── OllamaModelError (TRANS_003, 503)
    ├── DatabaseError (DB_001)
    │   ├── DatabaseIntegrityError (DB_002)
    │   ├── DatabaseBackupError (DB_003)
    │   └── DatabaseRestoreError (DB_004)
    └── ConfigurationError (CFG_001, 400)
  ```
- [x] **Flask Global Error Handlers**: SublarrError → JSON, generic 500 mit Logging
- [x] **Request-ID Tracking** (`g.request_id` via `uuid4`)
- [x] **Strukturierte Error-Responses**: `{error, code, request_id, timestamp, context, troubleshooting}`
- [x] **Circuit Breaker** (`circuit_breaker.py`): CLOSED → OPEN → HALF_OPEN → CLOSED
  - Thread-safe mit Lock
  - Konfigurierbar: `circuit_breaker_failure_threshold` (default 5), `circuit_breaker_cooldown_seconds` (default 60)
  - Integriert in ProviderManager (pro Provider ein Breaker)
  - Provider mit OPEN-Breaker werden uebersprungen
- [x] **ProviderTimeoutError** in `providers/base.py`
- [x] **Endpoint-Migration**: Kritische 500-Handler auf strukturierte Exceptions migriert
- [ ] Error-History in Database — geplant

### S6: Database Safety & Backup — ✅ 90%

- [x] **Transaction Context Manager** (`transaction_manager.py`):
  - `with transaction(db) as cursor:` — auto-commit/rollback
  - Wirft `DatabaseError` bei Fehlern
- [x] **Backup-System** (`database_backup.py`):
  - SQLite Online Backup API (`source.backup(target)`)
  - Backup-Verifizierung via `PRAGMA integrity_check`
  - Rotation: 7 taeglich, 4 woechentlich, 3 monatlich (konfigurierbar)
  - Backup-Verzeichnis: `/config/backups/`
  - Scheduler: taeglich 3 Uhr UTC (daemon Thread)
- [x] **Database Health-Checks** (`database_health.py`):
  - `check_integrity()`: PRAGMA integrity_check
  - `get_database_stats()`: Groesse, Tabellen-Counts, WAL-Status, Page-Info
  - `vacuum()`: VACUUM mit Vorher/Nachher-Vergleich
- [x] **API-Endpoints**:
  - `POST /api/v1/database/backup` — Manueller Backup-Trigger
  - `GET /api/v1/database/backups` — Liste aller Backups
  - `POST /api/v1/database/restore` — Backup wiederherstellen (mit Bestaetigung)
  - `GET /api/v1/database/health` — Integrity + Stats
  - `POST /api/v1/database/vacuum` — Optimierung
- [x] **Config-Settings**: `backup_dir`, `backup_retention_daily/weekly/monthly`
- [ ] Alle Schreib-Operationen mit `transaction()` wrappen — schrittweise Migration

### S7: Monitoring & Observability — ✅ 90%

- [x] **Prometheus Metrics** (`metrics.py`, `/metrics` Endpoint):
  - System: CPU, Memory, Disk
  - Business: translation_total, translation_duration, provider_search/download
  - Queue: job_queue_size, wanted_queue_size
  - Database: database_size_bytes
  - Resilience: circuit_breaker_state per Provider
- [x] **Structured JSON Logging**:
  - `StructuredJSONFormatter` in server.py
  - Aktivierbar via `SUBLARR_LOG_FORMAT=json` (Default: `text`)
  - Felder: timestamp, level, logger, message, module, function, line, request_id
  - Exception-Info als separate Felder
- [x] **Detaillierter Health-Endpoint** (`GET /api/v1/health/detailed`):
  - Database: Integrity, Groesse, WAL-Mode
  - Ollama: Erreichbar ja/nein
  - Providers: Circuit-Breaker-State pro Provider
  - Disk: /config und /media Nutzung (via psutil)
  - Memory: RSS/VMS Nutzung (via psutil)
  - Rueckgabe: 200 (healthy), 503 (degraded)
- [x] **Dependencies**: `prometheus_client`, `psutil` in `requirements.in`
- [ ] Grafana-Dashboard-Template — geplant

### S8: Container Safety — ✅ 95%

- [x] **Non-Root User im Dockerfile**:
  - `ARG PUID=1000` / `ARG PGID=1000`
  - `groupadd`/`useradd` mit konfigurierbaren IDs
  - `chown` auf /app und /config
  - `USER sublarr` vor EXPOSE
- [x] **Docker-Compose Hardening**:
  - PUID/PGID Build-Args
  - Resource-Limits: 2 CPU, 4G RAM (reservations: 0.5 CPU, 512M)
  - `security_opt: no-new-privileges:true`
  - `cap_drop: ALL` + `cap_add: CHOWN, DAC_OVERRIDE, SETGID, SETUID`
  - JSON-File Logging mit Rotation (10m, 3 files)
- [x] **README-Dokumentation**: PUID/PGID Erklaerung, Troubleshooting
- [ ] Trivy Container-Scanning in CI — geplant

---

## Architektur-Diagramm

```
                     ┌──────────────────┐
                     │   Flask Server   │
                     │   (server.py)    │
                     └────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼────────┐     │     ┌─────────▼────────┐
    │  Error Handler   │     │     │  Metrics Export   │
    │ (error_handler)  │     │     │   (metrics.py)    │
    │                  │     │     │                   │
    │ SublarrError     │     │     │ Prometheus:       │
    │  ├ Translation   │     │     │  CPU, Memory,     │
    │  ├ Database      │     │     │  Translation,     │
    │  └ Config        │     │     │  Provider,        │
    └──────────────────┘     │     │  CircuitBreaker   │
                              │     └───────────────────┘
                    ┌─────────▼─────────┐
                    │  Provider Manager  │
                    │ (__init__.py)      │
                    │                   │
                    │ ┌───────────────┐ │
                    │ │CircuitBreaker │ │
                    │ │ per Provider  │ │
                    │ └───────────────┘ │
                    └─────────┬─────────┘
              ┌───────┬───────┼───────┬───────┐
              │       │       │       │       │
           Tosho   Jimaku   OS    SubDL   (future)

    ┌──────────────────────────────────────────────┐
    │              Database Layer                   │
    │  ┌──────────┐  ┌─────────┐  ┌──────────────┐│
    │  │transaction│  │ backup  │  │ health_check ││
    │  │ _manager  │  │ _system │  │  + vacuum    ││
    │  └──────────┘  └─────────┘  └──────────────┘│
    └──────────────────────────────────────────────┘
```

---

## Neue Dateien (erstellt)

| Datei | Milestone | Beschreibung |
|---|---|---|
| `backend/error_handler.py` | S5 | Exception-Hierarchie, Flask Error-Handler |
| `backend/circuit_breaker.py` | S5 | Circuit Breaker Pattern |
| `backend/transaction_manager.py` | S6 | Transaction Context Manager |
| `backend/database_backup.py` | S6 | Backup mit Rotation und Verification |
| `backend/database_health.py` | S6 | Integrity-Check, Stats, Vacuum |
| `backend/metrics.py` | S7 | Prometheus Metrics Export |
| `tests/integration/test_translator_pipeline.py` | S3 | Translation Pipeline Tests |
| `tests/integration/test_provider_pipeline.py` | S3 | Provider + Circuit Breaker Tests |

## Geaenderte Dateien

| Datei | Milestones | Aenderungen |
|---|---|---|
| `backend/server.py` | S5, S6, S7 | Error-Handler, Backup-API, Metrics, Health, JSON-Logging |
| `backend/config.py` | S5, S6, S7 | Circuit Breaker, Backup, Log-Format Settings |
| `backend/providers/__init__.py` | S5 | Circuit Breaker Integration |
| `backend/providers/base.py` | S5 | ProviderTimeoutError |
| `backend/mypy.ini` | S2 | Strict Mode aktiviert |
| `backend/requirements.in` | S7 | prometheus_client, psutil |
| `backend/tests/conftest.py` | S3 | Neue Fixtures: mock_ollama, mock_provider_manager, create_test_subtitle |
| `Dockerfile` | S8 | Non-Root User (PUID/PGID) |
| `docker-compose.yml` | S8 | Resource-Limits, Security, Logging |
| `README.md` | S8 | PUID/PGID Dokumentation |

---

## Bekannte Limitierungen

- **Circuit Breaker State**: In-memory (geht bei Restart verloren). Fuer den Home-Lab-Einsatz akzeptabel.
- **Transaction-Migration**: `transaction_manager.py` existiert, aber nicht alle DB-Writes sind bereits migriert. Schrittweise Migration geplant.
- **Frontend E2E Tests**: Playwright-Tests sind geplant aber noch nicht implementiert.
- **Grafana-Dashboard**: Template fuer Prometheus-Metriken geplant.
- **Metriken-Instrumentierung**: `record_translation()` und `record_provider_search()` sind definiert, muessen in translator.py/providers noch aufgerufen werden.

---

## Vergleich mit Bazarr

| Feature | Bazarr | Sublarr v1.0 | Sublarr aktuell |
|---|---|---|---|
| **CI/CD** | ❌ Keine | ❌ Keine | ✅ GitHub Actions |
| **Code Quality Tools** | ❌ Keine | ❌ Keine | ✅ ruff, mypy strict, ESLint |
| **Test Coverage** | ⚠️ Begrenzt | ⚠️ Basis | ✅ 80%+ Ziel (Integration Tests) |
| **Integration Tests** | ❌ Keine | ❌ Keine | ✅ Translator, Provider, API |
| **Dependency Scanning** | ❌ Keine | ❌ Keine | ✅ pip-audit, npm audit, Dependabot |
| **Error Handling** | ⚠️ Basis | ⚠️ Basis | ✅ Zentralisiert (Codes, Hints) |
| **Circuit Breaker** | ❌ Keine | ❌ Keine | ✅ Pro Provider |
| **Database Backups** | ❌ Keine | ❌ Keine | ✅ Automatisch + API |
| **Monitoring** | ⚠️ Basis | ⚠️ Basis | ✅ Prometheus + Detail-Health |
| **Container Security** | ⚠️ Root User | ⚠️ Root User | ✅ Non-Root + Hardening |
| **Structured Logging** | ❌ Keine | ❌ Keine | ✅ JSON-Format (optional) |
| **Pre-commit Hooks** | ❌ Keine | ❌ Keine | ✅ ruff, mypy, eslint |
