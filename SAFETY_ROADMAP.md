# Safety Roadmap — Code Stability, Security & Best Practices

> **Fokus:** Interne Netzwerk-Nutzung (Home Lab)
> Keine externe Exposition, kein Reverse Proxy erforderlich.
> Prioritaet auf Code-Stabilitaet, Datenintegritaet und Wartbarkeit.

## Status-Uebersicht

### Phase 1: Foundation Safety (v1.0-beta) — TEILWEISE VORHANDEN

| Bereich | Status | Beschreibung |
|---|---|---|
| Basis-Authentifizierung | ✅ | Optional API-Key Auth (hmac.compare_digest) |
| Input Validation | ✅ | Pydantic Settings, Parameterized Queries |
| Path Traversal | ✅ | Path-Mapping, Media-Directory-Validation |
| SQL Injection | ✅ | Parameterized Queries, keine String-Interpolation |
| Secrets Management | ✅ | Secrets nie in Logs/Responses |
| Logging | ✅ | RotatingFileHandler, WebSocket-Logs |
| Error Handling | ⚠️ | Basis vorhanden, aber nicht zentralisiert |

### Phase 2: Code Quality & Testing (v0.2.0-beta → v0.5.0-beta) — IN PLANUNG

| Milestone | Status | Beschreibung | Geplante Version |
|---|---|---|---|
| S1 | 🔲 Geplant | CI/CD Pipeline (Tests, Linting, Type-Checking) | v0.2.0-beta |
| S2 | 🔲 Geplant | Code Quality Tools (ruff, mypy, Coverage) | v0.2.0-beta |
| S3 | 🔲 Geplant | Erweiterte Tests (Integration, E2E) | v0.3.0-beta |
| S4 | 🔲 Geplant | Dependency Management & Security Scanning | v0.3.0-beta |
| S5 | 🔲 Geplant | Error Handling & Resilience Patterns | v0.4.0-beta |
| S6 | 🔲 Geplant | Database Safety & Backup-System | v0.4.0-beta |
| S7 | 🔲 Geplant | Monitoring & Observability | v0.5.0-beta |
| S8 | 🔲 Geplant | Container Safety & Best Practices | v0.5.0-beta |

---

## Phase 1: Foundation Safety (v1.0-beta) — Details

### Bereits implementiert ✅

**Authentifizierung:**
- Optional API-Key-Auth mit `hmac.compare_digest` (timing-safe)
- Health-Endpoint ohne Auth
- Webhook-Endpoints mit eigener Auth

**Input Validation:**
- Pydantic Settings fuer Type-Safety
- Parameterized SQL-Queries (keine SQL-Injection)
- Path-Mapping fuer sichere Datei-Operationen

**Secrets Management:**
- Secrets nie in API-Responses (`get_safe_config()`)
- Secrets nie in Logs
- Environment-Variablen mit `SUBLARR_` Prefix

**Logging:**
- RotatingFileHandler (5MB, 3 Backups)
- WebSocket-Log-Emission
- Konfigurierbare Log-Levels

**Datenbank:**
- SQLite WAL-Mode fuer Concurrency
- Thread-Safe Database-Operations (`_db_lock`)
- Schema-Migrations

### Verbesserungsbedarf ⚠️

**Error Handling:**
- Kein zentraler Exception-Handler
- Fehler werden nicht strukturiert geloggt
- Keine Error-Tracking-Integration

**Path Validation:**
- Path-Mapping vorhanden, aber nicht ueberall konsistent
- Keine explizite Path-Traversal-Validierung in allen Endpoints

**Container Security:**
- Container laeuft als Root (nicht ideal)
- Keine Resource-Limits definiert
- Kein `.dockerignore`

---

## Phase 2: Code Quality & Testing

### Milestone S1: CI/CD Pipeline

**Ziel:** Automatisierte Tests, Linting und Type-Checking bei jedem Commit.

**Motivation:**
- Aktuell nur manuelle Tests moeglich
- Keine automatische Code-Quality-Checks
- Fehler werden erst spaet entdeckt

**Implementierung:**

- [ ] **GitHub Actions CI-Pipeline** (`.github/workflows/ci.yml`):
  - Backend Tests: `pytest` mit Coverage
  - Frontend Tests: `vitest` mit Coverage
  - Python Linting: `ruff check`
  - TypeScript Linting: `eslint`
  - Python Type-Checking: `mypy`
  - TypeScript Type-Checking: `tsc --noEmit`
  - Test auf Python 3.11, 3.12
  - Test auf Node 20, 21
  - Matrix-Build fuer Multi-Version-Support

- [ ] **Pre-commit Hooks** (`.pre-commit-config.yaml`):
  - Ruff (Python Linting + Formatting)
  - Black (Python Formatting, Fallback)
  - isort (Import-Sorting)
  - mypy (Type-Checking, optional)
  - ESLint (Frontend Linting)
  - Prettier (Frontend Formatting)
  - Git-Secrets-Check (keine Secrets in Commits)

- [ ] **Code Coverage:**
  - Coverage-Ziel: 80%+ fuer Backend, 70%+ fuer Frontend
  - Coverage-Reports in CI
  - Coverage-Badges in README
  - Coverage-Diff bei PRs

**Neue Dateien:** 2 (`.github/workflows/ci.yml`, `.pre-commit-config.yaml`) | **Geschaetzte Zeilen:** +200

**Abhaengigkeiten:** Keine

---

### Milestone S2: Code Quality Tools

**Ziel:** Statische Code-Analyse, Type-Checking und Code-Metriken.

**Motivation:**
- Code-Quality wird nicht automatisch ueberprueft
- Type-Safety nicht vollstaendig
- Code-Duplikate und Dead Code nicht erkannt

**Implementierung:**

- [ ] **Python Code Quality:**
  - `ruff` Integration (Linting + Formatting, sehr schnell)
  - `mypy` Integration (Type-Checking, strict mode)
  - `pylint` oder `flake8` (optional, als zusaetzliche Checks)
  - `vulture` (Dead Code Detection)
  - `bandit` (Security-Scanning)

- [ ] **TypeScript Code Quality:**
  - ESLint erweitern (mehr Rules)
  - TypeScript strict mode aktivieren
  - `ts-prune` (Dead Code Detection)

- [ ] **Code-Metriken:**
  - Cyclomatic Complexity Tracking
  - Code-Duplikat-Erkennung
  - Maintainability-Index

- [ ] **CI-Integration:**
  - Alle Tools in CI-Pipeline
  - Fail bei kritischen Issues
  - Warnungen bei nicht-kritischen Issues

**Neue Dateien:** 3 (`ruff.toml`, `mypy.ini`, `bandit.yml`) | **Geschaetzte Zeilen:** +150

**Abhaengigkeiten:** Milestone S1 (CI-Pipeline)

---

### Milestone S3: Erweiterte Tests

**Ziel:** Integration-Tests, E2E-Tests und Performance-Tests.

**Motivation:**
- Aktuell nur Unit-Tests vorhanden
- Keine Integration-Tests fuer API-Endpoints
- Keine E2E-Tests fuer User-Flows
- Keine Performance-Tests

**Implementierung:**

- [ ] **Backend Integration Tests:**
  - API-Endpoint-Tests (alle `/api/v1/` Endpoints)
  - Database-Operation-Tests
  - Provider-Integration-Tests (mit Mock-Responses)
  - Webhook-Tests (Sonarr/Radarr)
  - Translation-Pipeline-Tests

- [ ] **Frontend E2E Tests:**
  - Playwright oder Cypress Integration
  - Kritische User-Flows:
    - Onboarding-Wizard
    - Wanted-Search + Download
    - Settings-Konfiguration
    - Language-Profile-Erstellung
  - Cross-Browser-Tests (Chrome, Firefox)

- [ ] **Performance Tests:**
  - Load-Tests fuer API (locust oder pytest-benchmark)
  - Database-Performance-Tests
  - Frontend-Performance (Lighthouse CI)

- [ ] **Test-Utilities:**
  - Test-Fixtures (Dummy-Daten)
  - Mock-Provider-Responses
  - Test-Database-Setup/Teardown

**Neue Dateien:** 5 (Integration-Tests, E2E-Tests, Performance-Tests, Fixtures) | **Geschaetzte Zeilen:** +3000

**Abhaengigkeiten:** Milestone S1 (CI-Pipeline)

---

### Milestone S4: Dependency Management & Security Scanning

**Ziel:** Sichere Dependencies, automatische Updates und Vulnerability-Scanning.

**Motivation:**
- Dependencies nicht gepinnt (Security-Risiko)
- Keine automatische Vulnerability-Erkennung
- Manuelle Updates erforderlich

**Implementierung:**

- [ ] **Dependency Pinning:**
  - `requirements.txt` → `requirements.in` + `requirements.txt` (via pip-tools)
  - `package.json` → `package-lock.json` bereits vorhanden ✅
  - Dependency-Versions explizit festlegen
  - Changelog-Tracking fuer Dependency-Updates

- [ ] **Security Scanning:**
  - `pip-audit` oder `safety` fuer Python
  - `npm audit` fuer Frontend (bereits in package.json)
  - `trivy` fuer Container-Scanning
  - Automatische Scans in CI

- [ ] **Dependabot Integration:**
  - `.github/dependabot.yml` konfigurieren
  - Automatische PRs fuer Security-Updates
  - Automatische PRs fuer Dependency-Updates (optional)

- [ ] **License Compliance:**
  - `liccheck` fuer Python (License-Checking)
  - `license-checker` fuer Frontend
  - License-Whitelist definieren
  - License-Report generieren

**Neue Dateien:** 3 (`requirements.in`, `.github/dependabot.yml`, `LICENSE_WHITELIST.txt`) | **Geschaetzte Zeilen:** +100

**Abhaengigkeiten:** Keine

---

### Milestone S5: Error Handling & Resilience Patterns

**Ziel:** Zentrales Error-Handling, Retry-Mechanismen und Circuit Breaker.

**Motivation:**
- Fehler werden nicht konsistent behandelt
- Keine Retry-Mechanismen fuer externe APIs
- Keine Circuit Breaker fuer Provider-Calls
- Fehler-Messages nicht benutzerfreundlich

**Implementierung:**

- [ ] **Zentrales Error-Handling:**
  - Global Exception Handler in Flask
  - Custom Exception-Klassen (`SublarrError`, `ProviderError`, etc.)
  - Strukturierte Error-Responses (JSON-Format)
  - Error-Logging mit Context (Request-ID, User-Action)

- [ ] **Retry-Mechanismen:**
  - Retry-Decorator fuer kritische Operationen
  - Exponential Backoff (bereits teilweise vorhanden)
  - Max-Retry-Limits konfigurierbar
  - Retry-Statistiken tracken

- [ ] **Circuit Breaker Pattern:**
  - Circuit Breaker fuer Provider-Calls
  - Auto-Recovery nach Cooldown
  - Fallback-Strategien (naechster Provider)
  - Circuit-Breaker-Status in UI

- [ ] **Graceful Degradation:**
  - Wenn Provider fehlschlaegt → naechster Provider
  - Wenn Ollama fehlschlaegt → Fehler-Message, kein Crash
  - Wenn Database-Lock → Retry mit Timeout

- [ ] **Error-Reporting:**
  - Benutzerfreundliche Error-Messages
  - Error-Codes fuer bekannte Fehler
  - Troubleshooting-Hints in Error-Responses
  - Error-History in Database

**Neue Dateien:** 3 (`error_handler.py`, `retry_utils.py`, `circuit_breaker.py`) | **Geschaetzte Zeilen:** +800

**Abhaengigkeiten:** Keine

---

### Milestone S6: Database Safety & Backup-System

**Ziel:** Datenintegritaet, automatische Backups und Recovery-Mechanismen.

**Motivation:**
- Keine automatischen Backups
- Keine Transaction-Management
- Keine Database-Health-Checks
- Datenverlust bei Fehlern moeglich

**Implementierung:**

- [ ] **Transaction Management:**
  - Context Manager fuer Database-Transactions
  - Auto-Rollback bei Fehlern
  - Transaction-Isolation-Level konfigurierbar
  - Deadlock-Detection und -Recovery

- [ ] **Database Backups:**
  - Automatische taegliche Backups (SQLite-Dump)
  - Backup-Rotation (letzte 7 Tage, dann woechentlich)
  - Backup-Verifizierung (Integrity-Check)
  - Backup-Notification (bei Fehlern)
  - Manueller Backup-Trigger via API

- [ ] **Database Health-Checks:**
  - Integrity-Check (`PRAGMA integrity_check`)
  - Vacuum-Optimierung (automatisch)
  - Database-Size-Monitoring
  - Connection-Pool-Health

- [ ] **Data Validation:**
  - Database-Constraints erweitern
  - Foreign-Key-Constraints (bereits teilweise vorhanden)
  - Check-Constraints fuer Datenvalidierung
  - Unique-Constraints wo noetig

- [ ] **Recovery-Mechanismen:**
  - Backup-Restore via API
  - Point-in-Time-Recovery (wenn moeglich)
  - Database-Repair-Tools

**Neue Dateien:** 3 (`database_backup.py`, `database_health.py`, `transaction_manager.py`) | **Geschaetzte Zeilen:** +1000

**Abhaengigkeiten:** Keine

---

### Milestone S7: Monitoring & Observability

**Ziel:** Metriken, Logging-Verbesserungen und Health-Monitoring.

**Motivation:**
- Keine Performance-Metriken
- Keine Business-Metriken
- Logs nicht strukturiert (JSON)
- Keine Alerting-Mechanismen

**Implementierung:**

- [ ] **Structured Logging:**
  - JSON-Log-Format (optional, konfigurierbar)
  - Log-Context (Request-ID, User-Action, etc.)
  - Log-Level-Filterung verbessern
  - Log-Aggregation (optional, ELK/Loki)

- [ ] **Metrics Export:**
  - Prometheus Metrics Export (`/metrics` Endpoint)
  - System-Metriken (CPU, Memory, Disk)
  - Business-Metriken (Uebersetzungen/Tag, Erfolgsrate)
  - Provider-Performance-Metriken
  - Database-Metriken

- [ ] **Health-Monitoring:**
  - Erweiterter Health-Endpoint (`/api/v1/health/detailed`)
  - Health-Checks fuer:
    - Database-Connectivity
    - Provider-Availability
    - Ollama-Status
    - Disk-Space
    - Memory-Usage
  - Health-Status-Badge in UI

- [ ] **Alerting (optional):**
  - Alert bei kritischen Fehlern
  - Alert bei Database-Problemen
  - Alert bei Provider-Ausfaellen
  - Integration mit Notification-System (Apprise)

**Neue Dateien:** 2 (`metrics.py`, `health_monitor.py`) | **Geschaetzte Zeilen:** +600

**Abhaengigkeiten:** Keine

---

### Milestone S8: Container Safety & Best Practices

**Ziel:** Sichere Container-Konfiguration und Best Practices.

**Motivation:**
- Container laeuft als Root (Security-Risiko)
- Keine Resource-Limits
- Kein `.dockerignore`
- Container nicht optimiert

**Implementierung:**

- [ ] **Non-Root User:**
  - Dedicated User im Container (`sublarr` User)
  - User-ID/GROUP-ID konfigurierbar (via Env-Vars)
  - File-Permissions korrekt setzen
  - Volume-Mounts mit korrekten Permissions

- [ ] **Resource Limits:**
  - CPU-Limits (konfigurierbar)
  - Memory-Limits (konfigurierbar)
  - Disk-Quotas (optional)
  - Resource-Monitoring

- [ ] **Container-Optimierung:**
  - `.dockerignore` erstellen (node_modules, .git, etc.)
  - Multi-Stage-Build optimieren (kleinere Images)
  - Layer-Caching verbessern
  - Image-Size reduzieren

- [ ] **Container-Scanning:**
  - Trivy-Scan in CI
  - Vulnerability-Reports
  - Automatische Scans bei Builds

- [ ] **Security Best Practices:**
  - Read-Only Root-Filesystem (wo moeglich)
  - Minimal Base-Image (python:3.11-slim bereits gut)
  - Secrets nie im Image
  - Health-Check verbessern

**Neue Dateien:** 2 (`.dockerignore`, `Dockerfile.security`) | **Geschaetzte Zeilen:** +200

**Abhaengigkeiten:** Keine

---

## Vergleich mit Bazarr

| Feature | Bazarr | Sublarr v1.0 | Sublarr nach Safety-Roadmap |
|---|---|---|---|
| **CI/CD** | ❌ Keine | ❌ Keine | ✅ GitHub Actions |
| **Code Quality Tools** | ❌ Keine | ❌ Keine | ✅ ruff, mypy, ESLint |
| **Test Coverage** | ⚠️ Begrenzt | ⚠️ Basis | ✅ 80%+ Ziel |
| **Integration Tests** | ❌ Keine | ❌ Keine | ✅ Vollstaendig |
| **E2E Tests** | ❌ Keine | ❌ Keine | ✅ Playwright/Cypress |
| **Dependency Scanning** | ❌ Keine | ❌ Keine | ✅ pip-audit, npm audit |
| **Error Handling** | ⚠️ Basis | ⚠️ Basis | ✅ Zentralisiert |
| **Circuit Breaker** | ❌ Keine | ❌ Keine | ✅ Ja |
| **Database Backups** | ❌ Keine | ❌ Keine | ✅ Automatisch |
| **Monitoring** | ⚠️ Basis | ⚠️ Basis | ✅ Prometheus + Grafana |
| **Container Security** | ⚠️ Root User | ⚠️ Root User | ✅ Non-Root User |
| **Structured Logging** | ❌ Keine | ❌ Keine | ✅ JSON-Format |
| **Pre-commit Hooks** | ❌ Keine | ❌ Keine | ✅ Vollstaendig |

---

## Implementierungsreihenfolge

**Wave 1 (Foundation):** Milestone S1 + S2 + S4
- CI/CD, Code Quality, Dependency Management
- Hoechste Prioritaet, Basis fuer alles Weitere

**Wave 2 (Testing):** Milestone S3
- Erweiterte Tests
- Qualitaetssicherung

**Wave 3 (Resilience):** Milestone S5 + S6
- Error Handling, Database Safety
- Stabilitaet und Datenintegritaet

**Wave 4 (Observability):** Milestone S7 + S8
- Monitoring, Container Safety
- Production-Ready-Verbesserungen

---

## Geschaetzter Aufwand

| Milestone | Status | Schwerpunkt | Geschaetzte Zeilen |
|---|---|---|---|
| S1 CI/CD Pipeline | 🔲 | DevOps | +200 |
| S2 Code Quality Tools | 🔲 | Tooling | +150 |
| S3 Erweiterte Tests | 🔲 | Testing | +3000 |
| S4 Dependency Management | 🔲 | Security | +100 |
| S5 Error Handling | 🔲 | Backend | +800 |
| S6 Database Safety | 🔲 | Backend | +1000 |
| S7 Monitoring | 🔲 | Backend | +600 |
| S8 Container Safety | 🔲 | DevOps | +200 |
| **Gesamt** | **🔲** | | **~6050** |

---

## Priorisierung

**Kritisch (vor v0.2.0-beta):**
- S1: CI/CD Pipeline (Basis fuer alles)
- S2: Code Quality Tools (Code-Qualitaet sicherstellen)
- S4: Dependency Management (Security)

**Wichtig (vor v0.3.0-beta):**
- S3: Erweiterte Tests (Qualitaetssicherung)
- S5: Error Handling (Stabilitaet)

**Wertvoll (vor v0.5.0-beta):**
- S6: Database Safety (Datenintegritaet)
- S7: Monitoring (Observability)
- S8: Container Safety (Production-Ready)

---

## Best Practices fuer interne Nutzung

**Nicht erforderlich (externe Exposition):**
- ❌ CORS-Konfiguration (nicht kritisch)
- ❌ Rate Limiting fuer API (nicht kritisch)
- ❌ Security Headers (HSTS, CSP) - weniger kritisch
- ❌ Reverse Proxy Security - nicht relevant

**Wichtig (auch intern):**
- ✅ Input Validation (Path Traversal, SQL Injection)
- ✅ Error Handling (Stabilitaet)
- ✅ Database Safety (Datenintegritaet)
- ✅ Code Quality (Wartbarkeit)
- ✅ Testing (Zuverlaessigkeit)
- ✅ Monitoring (Probleme frueh erkennen)
