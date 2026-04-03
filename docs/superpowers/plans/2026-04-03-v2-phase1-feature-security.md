---
phase: 1
title: "Feature Completeness & Security Fixes"
version_target: "0.39.0-beta"
created: 2026-04-03
status: planned
---

# Phase 1 — Feature Completeness & Security Fixes

**Spec:** `docs/superpowers/specs/2026-04-03-code-quality-v2-analysis.md`
**Basis:** v0.38.1-beta

## Vorbefunde aus Code-Analyse

Vor dem Planen wurden alle betroffenen Dateien gelesen. Die Lage weicht an zwei Stellen vom Spec ab:

| Finding | Status |
|---------|--------|
| `post_processing_enabled` — Backend-Guard | **Bereits implementiert** in `download_manager.py` (Z. 345) und `post_download.py` (Z. 44). Tests vorhanden. |
| `media.py` — `is_safe_path()` | **Bereits vorhanden** in `stream_media()` (Z. 74). Kein Gap. |
| `post_processing_enabled` — UI-Toggle | **Fehlt vollständig.** Kein Toggle + kein Command-Input in `AutomationSettings.tsx`. |
| `post_download_command` — UI-Input | **Fehlt vollständig.** Feld in config.py (Z. 200), aber kein Frontend-Pendant. |
| Rate Limiting | **Nur Login** hat `@limiter.limit`. Import, Change-Password, Setup, Provider-Search fehlen. |
| `auth_ui.py` Privilege-Check | `change_password` prüft Session manuell (OK). `toggle` prüft Session oder API Key (OK). Kein Gap. |

## Erfolgskriterien

- `POST /api/v1/config` mit `{"post_processing_enabled": true, "post_download_command": "echo {path}"}` → beide Felder persistiert und via `GET /api/v1/config` zurückgegeben
- Settings > Automation > Processing Pipeline zeigt Toggle + Textarea für Post-Processing
- `POST /api/v1/config/import` mehr als 5x/min → 429
- `POST /api/v1/auth/change-password` mehr als 5x/min → 429
- `POST /api/v1/auth/setup` mehr als 5x/min → 429
- `POST /api/v1/providers/search` mehr als 20x/min → 429
- Ruff + pytest grün

---

## Task 1 — UI: Post-Processing Toggle + Command Input

**Datei:** `frontend/src/pages/Settings/AutomationSettings.tsx`

**Parallelisierbar mit:** Task 2 (unabhängige Dateien)

### Was fehlt

Die `ProcessingPipelineContent`-Komponente (ab Z. 401) hat bereits Toggle-Felder für Auto-Translate, Auto-Sync, Auto-Cleanup usw., aber kein Feld für `post_processing_enabled` und kein Input für `post_download_command`.

### Implementierung

Am **Ende** der `ProcessingPipelineContent`-Funktion (vor dem schließenden `</div>`) zwei neue `FormGroup`-Blöcke einfügen — nach dem letzten vorhandenen FormGroup-Block (Z. ca. 545, nach `jellyfin_play_translate_enabled`):

```tsx
<FormGroup
  label="Post-Processing aktiviert"
  hint="Führt nach jedem erfolgreichen Subtitle-Download den konfigurierten Shell-Befehl aus."
  data-testid="form-group-post-processing-enabled"
>
  <Toggle
    checked={boolVal(config, 'post_processing_enabled', false)}
    onChange={(v) => save({ post_processing_enabled: v })}
    disabled={updateConfig.isPending}
  />
</FormGroup>

<FormGroup
  label="Post-Download-Befehl"
  hint="Shell-Befehl nach Subtitle-Download. Variablen: {subtitle_path}, {path}, {language}, {provider}, {score}, {media_type}, {video_path}"
  htmlFor="post-download-command"
  data-testid="form-group-post-download-command"
>
  <textarea
    id="post-download-command"
    data-testid="input-post-download-command"
    style={{
      ...settingsInputStyle,
      width: '100%',
      minHeight: '60px',
      resize: 'vertical',
      fontFamily: 'monospace',
      fontSize: '12px',
    }}
    value={strVal(config, 'post_download_command', '')}
    onChange={(e) => save({ post_download_command: e.target.value })}
    disabled={updateConfig.isPending}
    placeholder="z.B. curl -s http://localhost:7878/api/refreshMonitor"
    spellCheck={false}
  />
</FormGroup>
```

**Hinweise:**
- `boolVal` und `strVal` sind bereits importiert (Z. 18).
- `settingsInputStyle` ist bereits importiert (Z. 20); `inputStyle` ist ein lokales const darüber, aber für die Textarea direkt `settingsInputStyle` verwenden.
- `Toggle` ist bereits importiert (Z. 16).
- Kein neuer Import nötig.
- Die beiden Felder gehören ans Ende von `ProcessingPipelineContent`, da Post-Processing ein nachgelagerter Schritt nach den anderen Pipeline-Optionen ist.
- Die `FormGroup` mit `post_processing_enabled` MUSS vor `post_download_command` kommen (Toggle steuert ob der Command ausgeführt wird).

### Verifikation

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Manuell: Settings > Automation > Processing Pipeline → nach unten scrollen → Toggle "Post-Processing aktiviert" sichtbar, Textarea "Post-Download-Befehl" sichtbar. Toggle toggeln + Wert eingeben → `GET /api/v1/config` zeigt aktualisierte Werte.

### Abnahme

- Toggle für `post_processing_enabled` ist in der UI vorhanden und speichert via `useUpdateConfig`
- Textarea für `post_download_command` ist in der UI vorhanden und speichert via `useUpdateConfig`
- `npx tsc --noEmit` ohne Fehler
- Keine anderen Felder in `AutomationSettings.tsx` wurden verändert

---

## Task 2 — Rate Limiting auf kritische Routes ausrollen

**Dateien:**
- `backend/routes/config.py`
- `backend/routes/auth_ui.py`
- `backend/routes/providers.py`

**Parallelisierbar mit:** Task 1 (unabhängige Dateien)

### Ist-Zustand

Einziger `@limiter.limit`-Decorator im gesamten Projekt: `login()` in `auth_ui.py` (Z. 90).

Das `limiter`-Objekt aus `extensions.py` ist in `auth_ui.py` bereits importiert. In `config.py` und `providers.py` fehlt der Import noch.

### Implementierung

#### 2a — `backend/routes/config.py`

Import am Anfang der Datei ergänzen (nach den bestehenden Imports):

```python
from extensions import limiter
```

Decorator auf `import_config()` (Z. 422) setzen:

```python
@bp.route("/config/import", methods=["POST"])
@limiter.limit("5 per minute")
def import_config():
```

Decorator auf `export_config()` (Z. 395) setzen:

```python
@bp.route("/config/export", methods=["GET"])
@limiter.limit("30 per minute")
def export_config():
```

**Begründung Limits:**
- Import: 5/min — Konfigurationsimport ist ein seltener, potentiell destruktiver Vorgang. Brute-Force-Angriff über Config-Import (z.B. zum Überschreiben der API-Key-Konfiguration) wird gedrosselt.
- Export: 30/min — Weniger kritisch, aber ohne Limit wäre es ein unbegrenztes Datenleck-Risiko bei kompromittiertem Zugang.

#### 2b — `backend/routes/auth_ui.py`

`change_password` (Z. 116) und `setup` (Z. 60) bekommen Limits.
`limiter` ist bereits importiert (Z. 16).

```python
@auth_ui_bp.post("/setup")
@limiter.limit("5 per minute")
def setup():
```

```python
@auth_ui_bp.post("/change-password")
@limiter.limit("5 per minute; 20 per hour")
def change_password():
```

**Begründung:**
- Setup: Läuft nur einmal, aber ohne Limit ist First-Run-Setup angreifbar (Credential-Stuffing).
- Change-Password: Zusätzlich ein Stunden-Limit, da Brute-Force auf aktuelle Passwörter zeitlich verzögert stattfinden kann.

#### 2c — `backend/routes/providers.py`

Import am Anfang ergänzen:

```python
from extensions import limiter
```

`search_providers()` (Z. 213) bekommt ein Limit:

```python
@bp.route("/providers/search", methods=["POST"])
@limiter.limit("20 per minute")
def search_providers():
```

**Begründung:** Provider-Search triggert externe API-Calls zu allen aktiven Providern. Ohne Limit ist Sublarr für API-Abuse gegenüber Providern anfällig (könnte den Account sperren). 20/min ist großzügig genug für normale Nutzung, blockt aber automatisierte Angriffe.

### Reihenfolge der Decorators

Flask-Limiter muss **nach** dem `@bp.route`/`@auth_ui_bp.post`-Decorator, aber **vor** anderen Decorators wie `@cached_get` stehen. Beispiel:

```python
@bp.route("/config/import", methods=["POST"])
@limiter.limit("5 per minute")
def import_config():
```

Für `export_config`: Bereits kein weiterer Decorator vorhanden. Für `get_config` (mit `@cached_get`) wird **kein** Limit gesetzt — read-only und gecacht.

### Verifikation

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest backend/tests/test_config.py backend/tests/test_media_stream.py -v --tb=short 2>/dev/null || python -m pytest tests/test_config.py -v --tb=short
```

Smoke-Test (erfordert laufenden Dev-Server):

```bash
# Config-Import: 6x rapid fire → 6. Request muss 429 sein
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:5765/api/v1/config/import \
    -H "X-Api-Key: $(cat backend/dev.key 2>/dev/null || echo test)" \
    -H "Content-Type: application/json" \
    -d '{}'
done
```

### Abnahme

- `config.py`: `limiter` importiert, `import_config` hat `@limiter.limit("5 per minute")`, `export_config` hat `@limiter.limit("30 per minute")`
- `auth_ui.py`: `setup` hat `@limiter.limit("5 per minute")`, `change_password` hat `@limiter.limit("5 per minute; 20 per hour")`
- `providers.py`: `limiter` importiert, `search_providers` hat `@limiter.limit("20 per minute")`
- Ruff ohne neue Violations
- Bestehende Tests weiterhin grün

---

## Ausführungsreihenfolge

```
Task 1 (UI-Toggle)     ──┐
                          ├── parallel ──► Commit: "feat: add post-processing UI + rate limiting"
Task 2 (Rate Limiting) ──┘
```

Beide Tasks sind vollständig unabhängig (verschiedene Dateien, verschiedene Schichten). Können parallel ausgeführt und in einem Commit zusammengefasst werden.

---

## Nicht in Phase 1 enthalten (aufgrund Code-Analyse-Update)

| Item | Begründung |
|------|------------|
| `is_safe_path()` in `media.py` | Bereits vorhanden in `stream_media()`. Test `test_stream_rejects_path_traversal` grün. |
| `auth_ui.py` Privilege-Review | `change_password` und `toggle` prüfen Session/API-Key korrekt. Kein Code-Change nötig. |
| Backend-Guard für `post_processing_enabled` | Bereits in `download_manager.py` Z. 345 und `post_download.py` Z. 44 implementiert. |

---

## Pre-Commit-Checkliste

```bash
# Backend
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"

# Frontend
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```
