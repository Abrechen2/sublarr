# Code Quality Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behebe alle identifizierten Sicherheitslücken, kritischen Bugs und Code-Qualitätsprobleme aus dem Code-Review vom 2026-03-30 — ohne Task-Queue- und DI-Umbau.

**Architecture:** Vier unabhängige Phasen: Security/Critical Bugs → Backend-Qualität → Frontend-Qualität → Architektur. Jede Phase kann separat deployed werden. TDD wo sinnvoll; direkte Fixes für klare Bugs.

**Tech Stack:** Python 3.12 / Flask / SQLAlchemy / Alembic · React 19 / TypeScript / Vitest · ruff (backend lint) · ESLint + tsc (frontend)

---

## Phase 1 — Security & Critical Bugs

### Task 1.1: Doppelte Alembic-Revision-ID fixen

**Befund:** Zwei Migrations-Dateien haben `revision = "a1b2c3d4e5f6"`. `alembic upgrade head` schlägt bei Fresh-Installs fehl.

**Files:**
- Modify: `backend/db/migrations/versions/a1b2c3d4e5f6_add_ffprobe_cache_file_path_mtime_index.py`

- [ ] **Prüfe die Alembic-Chain:**
```bash
cd backend && python -m alembic history --verbose 2>&1 | head -40
```
Erwartung: Fehler oder zwei Einträge mit gleicher ID.

- [ ] **Weise der Index-Migration eine neue eindeutige ID zu.**

Ersetze in `a1b2c3d4e5f6_add_ffprobe_cache_file_path_mtime_index.py`:
```python
# ALT
revision = "a1b2c3d4e5f6"
down_revision = "c7d8e9f0a1b2"

# NEU
revision = "b2c3d4e5f6a7"
down_revision = "c7d8e9f0a1b2"
```

Benenne die Datei um:
```bash
mv backend/db/migrations/versions/a1b2c3d4e5f6_add_ffprobe_cache_file_path_mtime_index.py \
   backend/db/migrations/versions/b2c3d4e5f6a7_add_ffprobe_cache_file_path_mtime_index.py
```

- [ ] **Prüfe ob nachfolgende Migrationen `a1b2c3d4e5f6` als `down_revision` referenzieren:**
```bash
grep -r "a1b2c3d4e5f6" backend/db/migrations/versions/ | grep -v "add_anidb"
```
Für jeden Treffer: `down_revision = "a1b2c3d4e5f6"` → `"b2c3d4e5f6a7"` ersetzen (nur Migrationen die von der Index-Migration abhängen, nicht von der AniDB-Migration).

- [ ] **Verifiziere:**
```bash
cd backend && python -m alembic history 2>&1 | head -20
```
Erwartung: Keine Fehler, zwei verschiedene Revisions-IDs.

- [ ] **Commit:**
```bash
git add backend/db/migrations/versions/
git commit -m "fix: resolve duplicate alembic revision ID a1b2c3d4e5f6"
```

---

### Task 1.2: `/health` gibt immer HTTP 200 zurück

**Befund:** `healthy = True` wird nie aktualisiert. Ollama-Ausfall → immer 200.

**Files:**
- Modify: `backend/routes/system/health.py`

- [ ] **Schreibe zuerst den Test:**

In `backend/tests/test_health.py` (erstellen falls nicht vorhanden):
```python
def test_health_returns_503_when_ollama_unreachable(client, mocker):
    """Basic /health must return 503 when Ollama is down."""
    mocker.patch(
        "routes.system.health._health_check_ollama",
        return_value=({"ollama": "unreachable"}, False),
    )
    mocker.patch("routes.system.health._health_check_providers", return_value=({"providers": "healthy"}, None))
    mocker.patch("routes.system.health._health_check_sonarr", return_value=({"sonarr": "ok"}, None))
    mocker.patch("routes.system.health._health_check_radarr", return_value=({"radarr": "ok"}, None))
    mocker.patch("routes.system.health._health_check_media_servers", return_value=({"media_servers": "1/1 healthy"}, None))

    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
```

- [ ] **Führe Test aus — muss FEHLSCHLAGEN:**
```bash
cd backend && python -m pytest tests/test_health.py::test_health_returns_503_when_ollama_unreachable -v
```

- [ ] **Fixe den Loop in `health.py`, Zeile 166:**

```python
# ALT
for name, (part, _overall) in results_by_name.items():
    service_status.update(part)

# NEU
for name, (part, overall) in results_by_name.items():
    service_status.update(part)
    if overall is False:          # None = optional service, False = required
        healthy = False
```

- [ ] **Führe Test aus — muss BESTEHEN:**
```bash
cd backend && python -m pytest tests/test_health.py -v
```

- [ ] **Commit:**
```bash
git add backend/routes/system/health.py backend/tests/test_health.py
git commit -m "fix: health endpoint now returns 503 when required services are down"
```

---

### Task 1.3: `is_safe_path` Argumente vertauscht in `cleanup_sidecars`

**Befund:** `is_safe_path(media_path, sidecar)` — Argumente sind vertauscht. Check ist immer True → Security-Check wirkungslos.

**Files:**
- Modify: `backend/routes/wanted/providers.py` (Zeile ~281)

- [ ] **Test schreiben:**

In `backend/tests/test_security.py` oder neuer Datei:
```python
def test_cleanup_sidecars_rejects_path_outside_media(client, mocker, tmp_path):
    """cleanup_sidecars must reject sidecar paths outside media_path."""
    media = tmp_path / "media"
    media.mkdir()
    evil_sidecar = str(tmp_path / "secret.ass")  # outside media_path

    mocker.patch("routes.wanted.providers.get_settings").return_value.media_path = str(media)
    mocker.patch("routes.wanted.providers.get_wanted_items").return_value = {
        "items": [{"id": 1, "file_path": str(media / "ep1.mkv"), "target_language": "de"}]
    }

    resp = client.post(
        "/api/v1/wanted/cleanup-sidecars",
        json={"sidecars": [evil_sidecar]},
        headers={"X-Api-Key": "test"},
    )
    # Should skip or reject the evil_sidecar — not delete it
    assert resp.status_code in (200, 403)
```

- [ ] **Führe Test aus — muss FEHLSCHLAGEN.**

- [ ] **Fixe Argumente in `providers.py` Zeile ~281:**

```python
# ALT
if not is_safe_path(media_path, sidecar):

# NEU
if not is_safe_path(sidecar, media_path):
```

- [ ] **Tests:**
```bash
cd backend && python -m pytest tests/test_security.py -v
```

- [ ] **Commit:**
```bash
git add backend/routes/wanted/providers.py backend/tests/test_security.py
git commit -m "fix: correct reversed is_safe_path arguments in cleanup_sidecars"
```

---

### Task 1.4: `session_timeout_minutes` nie verwendet

**Befund:** `session.permanent = True` → 31-Tage-Session. `session_timeout_minutes` aus Config wird nie gelesen.

**Files:**
- Modify: `backend/ui_auth.py`

- [ ] **Fix in `ui_auth.py` — direkt nach `app.config["SESSION_COOKIE_SECURE"] = False`:**

```python
# NEU: nach den bestehenden session cookie config lines
from datetime import timedelta as _td
_timeout = getattr(get_settings(), "session_timeout_minutes", 0)
if _timeout and _timeout > 0:
    app.config["PERMANENT_SESSION_LIFETIME"] = _td(minutes=_timeout)
else:
    app.config["PERMANENT_SESSION_LIFETIME"] = _td(hours=8)  # sicherer Default statt 31 Tage
```

- [ ] **Test:**
```bash
cd backend && python -m pytest tests/ -k "auth" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/ui_auth.py
git commit -m "fix: enforce session_timeout_minutes; default to 8h instead of 31 days"
```

---

### Task 1.5: `is_safe_path` fehlt in `ocr/batch-extract`

**Befund:** `extract_ocr` und `preview_ocr` prüfen `is_safe_path`. `batch_extract` nicht — beliebige Pfade außerhalb `media_path` möglich.

**Files:**
- Modify: `backend/routes/ocr.py`

- [ ] **Finde die genaue Zeile:**
```bash
grep -n "video_path\|is_safe_path\|def batch_extract" backend/routes/ocr.py | head -20
```

- [ ] **Ergänze den Check direkt nach `video_path = map_path(video_path)`:**

```python
# Nach map_path(video_path):
if not is_safe_path(video_path, settings.media_path):
    return jsonify({"error": "Access denied: path outside media directory"}), 403
```

(Import `is_safe_path` ist bereits in der Datei — prüfen mit `grep "from security_utils" backend/routes/ocr.py`)

- [ ] **Test:**
```bash
cd backend && python -m pytest tests/ -k "ocr" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/routes/ocr.py
git commit -m "fix: add is_safe_path check to ocr batch-extract endpoint"
```

---

### Task 1.6: `db/models/__init__.py` fehlende Exporte

**Befund:** `SeriesSettings`, `FansubPreference`, `AnidbAbsoluteMapping`, `ChapterCache`, `TranslationMemory` nicht in `__all__`. Alembic `--autogenerate` erkennt sie nicht → würde DROP-Migrationen erzeugen.

**Files:**
- Modify: `backend/db/models/__init__.py`

- [ ] **Prüfe aktuellen Stand:**
```bash
grep -n "__all__\|SeriesSettings\|FansubPreference\|AnidbAbsoluteMapping\|ChapterCache\|TranslationMemory" backend/db/models/__init__.py
```

- [ ] **Ergänze fehlende Imports und `__all__`-Einträge:**

```python
# Imports ergänzen (sofern fehlend):
from db.models.core import SeriesSettings, FansubPreference, AnidbAbsoluteMapping, ChapterCache
from db.models.translation import TranslationMemory

# In __all__ ergänzen:
__all__ = [
    # ... bestehende ...
    "SeriesSettings",
    "FansubPreference",
    "AnidbAbsoluteMapping",
    "ChapterCache",
    "TranslationMemory",
]
```

- [ ] **Verifiziere Alembic-Erkennung:**
```bash
cd backend && python -c "from db.models import *; print('SeriesSettings:', SeriesSettings.__tablename__)"
```

- [ ] **Commit:**
```bash
git add backend/db/models/__init__.py
git commit -m "fix: add missing model exports to db/models/__init__.py for alembic autogenerate"
```

---

### Task 1.7: `post_download_command` mit `shell=True` — Command Injection

**Befund:** Benutzerkontrollierter String aus DB wird mit `shell=True` ausgeführt.

**Files:**
- Modify: `backend/post_download.py`

- [ ] **Lese die aktuelle Implementierung:**
```bash
grep -n "subprocess\|shell\|expanded\|shlex" backend/post_download.py
```

- [ ] **Ersetze `shell=True` durch geparsten Argv-Aufruf:**

```python
import shlex

# ALT
subprocess.run(expanded, shell=True, timeout=60, check=False)

# NEU
try:
    argv = shlex.split(expanded)
except ValueError as e:
    logger.warning("post_download_command: invalid shell syntax, skipping: %s", e)
    return
subprocess.run(argv, shell=False, timeout=60, check=False)  # noqa: S603
```

- [ ] **Test:**
```bash
cd backend && python -m pytest tests/ -k "post_download" -v --tb=short
```

Existieren keine Tests: Manuell prüfen dass ein Befehl mit Leerzeichen korrekt geparst wird:
```python
import shlex; print(shlex.split("echo 'hello world'"))  # ['echo', 'hello world']
```

- [ ] **Commit:**
```bash
git add backend/post_download.py
git commit -m "fix: replace shell=True with shlex.split to prevent command injection in post_download_command"
```

---

### Task 1.8: `allowed_ip_ranges` Setting — enforzen oder entfernen

**Befund:** Setting existiert und erscheint im UI, wird aber nie ausgewertet. Nutzer glauben IP-Filtering sei aktiv.

**Files:**
- Modify: `backend/auth.py` (before_request Hook)
- Modify: `backend/config.py` (Docstring Klarstellung)

- [ ] **Ergänze IP-Check in `init_auth()` before_request:**

```python
import ipaddress as _ipaddress

def _check_ip_allowlist():
    """Returns 403 if request IP is not in allowed_ip_ranges (when configured)."""
    allowed = getattr(get_settings(), "allowed_ip_ranges", "").strip()
    if not allowed:
        return None  # empty = allow all
    try:
        networks = [_ipaddress.ip_network(r.strip(), strict=False) for r in allowed.split(",") if r.strip()]
    except ValueError:
        logger.warning("allowed_ip_ranges contains invalid CIDR — skipping check")
        return None
    client_ip = _ipaddress.ip_address(request.remote_addr)
    if not any(client_ip in net for net in networks):
        return jsonify({"error": "Forbidden"}), 403
    return None
```

In `init_auth()` → `before_request` Hook:
```python
@app.before_request
def check_api_key():
    ip_block = _check_ip_allowlist()
    if ip_block:
        return ip_block
    # ... bestehende Logik
```

- [ ] **Test:**
```bash
cd backend && python -m pytest tests/ -k "ip_range or allowed_ip" -v --tb=short
```

Falls kein Test existiert, schreibe einen:
```python
def test_allowed_ip_ranges_blocks_unlisted_ip(client, mocker):
    mocker.patch("auth.get_settings").return_value.allowed_ip_ranges = "10.0.0.0/8"
    mocker.patch("auth.request").remote_addr = "192.168.1.1"
    # ... test returns 403
```

- [ ] **Commit:**
```bash
git add backend/auth.py
git commit -m "fix: enforce allowed_ip_ranges setting for IP-based access control"
```

---

### Task 1.9: Plugin-Install ohne SSRF-Schutz

**Befund:** `validate_service_url()` existiert, wird in `marketplace.py` nie aufgerufen. Nur Scheme-Check.

**Files:**
- Modify: `backend/services/marketplace.py`

- [ ] **Ergänze `validate_service_url` in beiden Install-Pfaden:**

```bash
grep -n "def _install_from_zip\|def install_plugin_from_zip\|validate_service_url\|zip_url\|registry_url" backend/services/marketplace.py | head -20
```

In `_install_from_zip()` und `install_plugin_from_zip()` nach dem Scheme-Check:
```python
from security_utils import validate_service_url

# Nach dem HTTPS-Check:
validate_service_url(zip_url)  # raises ValueError on SSRF targets
```

Gleiches für `fetch_registry()` mit `self.registry_url`.

- [ ] **Test:**
```bash
cd backend && python -m pytest tests/ -k "marketplace or plugin" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/services/marketplace.py
git commit -m "fix: apply validate_service_url to plugin zip install and registry fetch"
```

---

### Task 1.10: Webhook-Auth auch ohne API-Key erzwingen

**Befund:** Webhook-Endpoints erlauben alle Requests wenn kein API-Key konfiguriert.

**Files:**
- Modify: `backend/routes/webhooks.py`

- [ ] **Prüfe das Muster in allen drei Webhooks:**
```bash
grep -n "api_key\|hmac\|return\b" backend/routes/webhooks.py | head -30
```

- [ ] **Alle drei Webhook-Handler müssen bei fehlendem API-Key 401 zurückgeben:**

```python
# ALT (Muster in allen drei Handlers):
_api_key = getattr(_s, "api_key", None)
if _api_key:
    _provided = request.headers.get("X-Api-Key", "")
    if not hmac.compare_digest(_provided, _api_key):
        return jsonify({"error": "Unauthorized"}), 401

# NEU:
_api_key = getattr(_s, "api_key", None) or ""
_provided = request.headers.get("X-Api-Key", "")
if not _api_key or not hmac.compare_digest(_provided, _api_key):
    return jsonify({"error": "Unauthorized"}), 401
```

Gleiches Pattern für Jellyfin-Webhook (Zeile ~429).

- [ ] **Test:**
```bash
cd backend && python -m pytest tests/ -k "webhook" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/routes/webhooks.py
git commit -m "fix: reject webhook requests when no API key is configured"
```

---

## Phase 2 — Backend Code-Qualität

### Task 2.1: `StatisticsRepository` — Raw SQL aus Route extrahieren

**Befund:** `routes/system/statistics.py` enthält 6 Raw-SQL-Statements direkt im Handler.

**Files:**
- Create: `backend/db/repositories/statistics.py`
- Modify: `backend/routes/system/statistics.py`
- Create: `backend/tests/db/test_statistics_repository.py`

- [ ] **Erstelle `backend/db/repositories/statistics.py`:**

```python
"""Repository for statistics queries."""
from __future__ import annotations

from sqlalchemy import text

from db.repositories.base import BaseRepository


class StatisticsRepository(BaseRepository):
    def get_daily_stats(self, days: int = 30) -> list[dict]:
        rows = self.session.execute(
            text(
                "SELECT date, translated, failed, skipped "
                "FROM daily_stats ORDER BY date DESC LIMIT :days"
            ),
            {"days": days},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_downloads_by_provider(self, days: int = 30) -> list[dict]:
        rows = self.session.execute(
            text(
                "SELECT provider, COUNT(*) as count "
                "FROM subtitle_downloads "
                "WHERE downloaded_at > date('now', :offset) "
                "GROUP BY provider ORDER BY count DESC"
            ),
            {"offset": f"-{days} days"},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_translation_backend_stats(self, days: int = 30) -> list[dict]:
        rows = self.session.execute(
            text(
                "SELECT backend, COUNT(*) as count, "
                "AVG(duration_seconds) as avg_duration "
                "FROM translation_backend_stats "
                "WHERE created_at > date('now', :offset) "
                "GROUP BY backend"
            ),
            {"offset": f"-{days} days"},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    # Weitere Query-Methoden aus statistics.py hierher migrieren
```

- [ ] **Erstelle Facade-Shim `backend/db/statistics.py`:**

```python
from db.repositories.statistics import StatisticsRepository

_repo: StatisticsRepository | None = None

def _get_repo() -> StatisticsRepository:
    global _repo
    if _repo is None:
        _repo = StatisticsRepository()
    return _repo

def get_daily_stats(days: int = 30) -> list[dict]:
    return _get_repo().get_daily_stats(days)

def get_downloads_by_provider(days: int = 30) -> list[dict]:
    return _get_repo().get_downloads_by_provider(days)

def get_translation_backend_stats(days: int = 30) -> list[dict]:
    return _get_repo().get_translation_backend_stats(days)
```

- [ ] **Migriere `routes/system/statistics.py`:** Alle `db.engine.connect()` / `text(...)` Aufrufe durch Facade-Calls ersetzen.

- [ ] **Tests:**
```bash
cd backend && python -m pytest tests/ -k "statistics" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/db/repositories/statistics.py backend/db/statistics.py backend/routes/system/statistics.py
git commit -m "refactor: extract statistics queries into StatisticsRepository"
```

---

### Task 2.2: Raw DB Access in `routes/subtitles.py` fixen

**Befund:** `_trash_sidecar()` öffnet eigene DB-Connection via `db.engine.connect()` statt Repository zu nutzen. Filesystem- und DB-Aktion nicht atomisch.

**Files:**
- Modify: `backend/routes/subtitles.py`
- Modify: `backend/db/repositories/library.py`

- [ ] **Ergänze `delete_download_record(file_path)` in `LibraryRepository`:**

```python
def delete_download_record(self, file_path: str) -> None:
    from db.models.providers import SubtitleDownload
    self.session.query(SubtitleDownload).filter_by(file_path=file_path).delete()
    self.session.commit()
```

- [ ] **Ersetze direkten DB-Zugriff in `_trash_sidecar()`:**

```python
# ALT: db.engine.connect() mit text(...)
# NEU:
from db.library import delete_download_record
delete_download_record(file_path)
```

- [ ] **Tests:**
```bash
cd backend && python -m pytest tests/ -k "subtitle" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/routes/subtitles.py backend/db/repositories/library.py backend/db/library.py
git commit -m "refactor: replace direct db.engine access in _trash_sidecar with repository call"
```

---

### Task 2.3: Episode "Find-or-Create Wanted Item" Service extrahieren

**Befund:** 30-Zeilen-Block 3× kopiert in `routes/library/episodes.py`.

**Files:**
- Create: `backend/services/episode_wanted.py`
- Modify: `backend/routes/library/episodes.py`

- [ ] **Erstelle `backend/services/episode_wanted.py`:**

```python
"""Service: resolve or create a WantedItem for a given Sonarr episode."""
from __future__ import annotations

import logging
import os

from db.wanted import upsert_wanted_item, get_wanted_item_by_file_path

logger = logging.getLogger(__name__)


def get_or_create_wanted_for_episode(
    episode: dict,
    series: dict,
    settings,
) -> dict | None:
    """Return existing or newly-created WantedItem dict for *episode*.

    Returns None when the episode has no valid file path.
    """
    file_path = episode.get("episodeFile", {}).get("path", "")
    if not file_path or not os.path.exists(file_path):
        return None

    existing = get_wanted_item_by_file_path(file_path)
    if existing:
        return existing

    item = upsert_wanted_item(
        file_path=file_path,
        sonarr_series_id=series.get("id"),
        sonarr_episode_id=episode.get("id"),
        title=episode.get("title", ""),
        # weitere Felder aus dem bestehenden upsert-Block übernehmen
    )
    return item
```

- [ ] **Ersetze alle drei Kopien in `episodes.py` durch Aufruf des Service.**

- [ ] **Tests:**
```bash
cd backend && python -m pytest tests/ -k "episode" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/services/episode_wanted.py backend/routes/library/episodes.py
git commit -m "refactor: extract episode find-or-create logic into episode_wanted service"
```

---

### Task 2.4: `_retranslate_item` in eigenen Service auslagern

**Befund:** Business-Logik (Path-Validation, Job-Creation, Thread-Spawn) in Route-Hilfsfunktion.

**Files:**
- Create: `backend/services/retranslation.py`
- Modify: `backend/routes/wanted/providers.py`

- [ ] **Erstelle `backend/services/retranslation.py`** mit der Logik aus `_retranslate_item`:

```python
"""Service: re-queue a wanted item for translation."""
from __future__ import annotations
import logging
import os
import threading

logger = logging.getLogger(__name__)


def retranslate_item(item_id: int) -> str | None:
    """Create a translation job for *item_id*. Returns job_id or None on error."""
    from db.wanted import get_wanted_item
    from db.jobs import create_job
    from security_utils import is_safe_path
    from config import get_settings

    settings = get_settings()
    item = get_wanted_item(item_id)
    if not item:
        return None

    file_path = item.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        logger.warning("retranslate_item: file not found for item %s", item_id)
        return None
    if not is_safe_path(file_path, settings.media_path):
        logger.warning("retranslate_item: path traversal rejected for item %s", item_id)
        return None

    # Sidecar-Cleanup + Job-Erstellung wie bisher, aus Route-Helper hierher verschoben
    job_id = create_job(...)  # bestehende Logik
    threading.Thread(target=..., daemon=True).start()
    return job_id
```

- [ ] **Route ruft nur noch `retranslate_item(item_id)` auf.**

- [ ] **Tests:**
```bash
cd backend && python -m pytest tests/ -k "retranslate" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/services/retranslation.py backend/routes/wanted/providers.py
git commit -m "refactor: extract _retranslate_item business logic into retranslation service"
```

---

### Task 2.5: `cleanup_sidecars` Performance-Fixes

**Befund:** N+1 Queries (`get_wanted_item` für jede ID) + unboundetes `per_page=10000`.

**Files:**
- Modify: `backend/routes/wanted/providers.py`

- [ ] **N+1 Fix — ersetze List-Comprehension durch Batch-Fetch:**

```python
# ALT
items = [get_wanted_item(iid) for iid in item_ids]

# NEU
from db.wanted import get_wanted_items_by_ids
items = get_wanted_items_by_ids(item_ids)
```

- [ ] **Unboundete Page-Size einschränken:**

```python
# ALT
result = get_wanted_items(status="extracted", per_page=10000)

# NEU — in Batches verarbeiten
PAGE = 200
page = 1
all_items = []
while True:
    result = get_wanted_items(status="extracted", page=page, per_page=PAGE)
    all_items.extend(result.get("items", []))
    if len(result.get("items", [])) < PAGE:
        break
    page += 1
```

- [ ] **Tests:**
```bash
cd backend && python -m pytest tests/ -k "cleanup_sidecar or wanted" -v --tb=short
```

- [ ] **Commit:**
```bash
git add backend/routes/wanted/providers.py
git commit -m "perf: fix N+1 queries and unbounded per_page in cleanup_sidecars"
```

---

### Task 2.6: Silent Exception Swallowing durch Logging ersetzen

**Befund:** Mehrere `except Exception: pass` in `config.py` und anderen Stellen.

**Files:**
- Modify: `backend/routes/config.py`

- [ ] **Finde alle stummen Exceptions:**
```bash
grep -n "except Exception:\s*$\|except Exception as.*:\s*$" backend/routes/config.py
```

- [ ] **Ersetze `pass` durch `logger.warning`:**

```python
# ALT
except Exception:
    pass

# NEU
except Exception as exc:
    logger.warning("Media server reload failed after config update: %s", exc)
```

Gleiches Muster für Scheduler-Restart-Block.

- [ ] **Selbe Prüfung für andere betroffene Dateien:**
```bash
grep -rn "except Exception.*:\s*$" backend/routes/ | grep -v "#"
```

- [ ] **Tests:**
```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py
```

- [ ] **Commit:**
```bash
git add backend/routes/config.py
git commit -m "fix: replace silent except Exception: pass with logger.warning"
```

---

## Phase 3 — Frontend Code-Qualität

### Task 3.1: Gemeinsamer `settingsInputStyle` statt 13 Kopien

**Befund:** Fast-identisches `inputStyle`-Objekt in 13 Settings-Dateien definiert.

**Files:**
- Create: `frontend/src/styles/settingsShared.ts`
- Modify: alle 13 betroffenen Settings-Seiten

- [ ] **Erstelle `frontend/src/styles/settingsShared.ts`:**

```typescript
import type React from 'react'

export const settingsInputStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
}
```

- [ ] **Finde alle betroffenen Dateien:**
```bash
grep -rl "const inputStyle" frontend/src/
```

- [ ] **Ersetze in jeder Datei:**
```typescript
// ALT: lokale Definition entfernen
const inputStyle: React.CSSProperties = { ... }

// NEU: Import ergänzen
import { settingsInputStyle } from '@/styles/settingsShared'
// Verwendungen: inputStyle → settingsInputStyle
```

- [ ] **TypeScript-Check:**
```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit:**
```bash
git add frontend/src/styles/settingsShared.ts frontend/src/pages/Settings/
git commit -m "refactor: consolidate duplicate inputStyle into shared settingsShared.ts"
```

---

### Task 3.2: `Stats` Type erweitern — `as any` entfernen

**Befund:** `HeroStats.tsx` und `AutomationBanner.tsx` casten `stats as any` weil Felder fehlen.

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/dashboard/HeroStats.tsx`
- Modify: `frontend/src/components/dashboard/AutomationBanner.tsx`

- [ ] **Ergänze fehlende Felder in `Stats` Interface (`types.ts`):**

```typescript
export interface Stats {
  // ... bestehende Felder ...
  total_subtitles?: number
  downloads_today?: number
  average_score?: number
  low_score_count?: number
  success_rate?: number
}
```

- [ ] **Ersetze `as any` in `HeroStats.tsx`:**

```typescript
// ALT
const extStats = stats as any
const totalSubs = extStats?.total_subtitles ?? 0

// NEU
const totalSubs = stats?.total_subtitles ?? 0
```

Gleiches in `AutomationBanner.tsx`.

- [ ] **TypeScript-Check:**
```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit:**
```bash
git add frontend/src/lib/types.ts frontend/src/components/dashboard/
git commit -m "fix: extend Stats type with missing fields, remove as any casts"
```

---

### Task 3.3: Duplizierte Konstanten und Hilfsfunktionen zusammenführen

**Befund:** `LOW_SCORE_THRESHOLD`, `deriveSubtitlePath` und `strVal`/`numVal`-Helpers dupliziert.

**Files:**
- Modify: `frontend/src/components/series/seriesUtils.ts`
- Create: `frontend/src/lib/configUtils.ts`
- Modify: `frontend/src/pages/Wanted.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx`
- Modify: `frontend/src/pages/Settings/SecurityTab.tsx`
- Modify: `frontend/src/pages/Settings/GeneralSettings.tsx`

- [ ] **`LOW_SCORE_THRESHOLD` in `seriesUtils.ts` ergänzen:**
```typescript
export const LOW_SCORE_THRESHOLD = 60
```
Dann in `SeriesDetail.tsx` und `SeasonSummaryBar.tsx`: lokale Definition entfernen, Import ergänzen.

- [ ] **`deriveSubtitlePath` in `Wanted.tsx` entfernen**, stattdessen aus `seriesUtils.ts` importieren.

- [ ] **`frontend/src/lib/configUtils.ts` erstellen:**
```typescript
import type { AppConfig } from './types'

export function strVal(config: AppConfig | null | undefined, key: string, fallback = ''): string {
  if (!config) return fallback
  const v = (config as Record<string, unknown>)[key]
  return typeof v === 'string' ? v : fallback
}

export function numVal(config: AppConfig | null | undefined, key: string, fallback = 0): number {
  if (!config) return fallback
  const v = (config as Record<string, unknown>)[key]
  return typeof v === 'number' ? v : fallback
}
```
Lokale Kopien in `SecurityTab.tsx` und `GeneralSettings.tsx` entfernen, Import ergänzen.

- [ ] **TypeScript-Check + Tests:**
```bash
cd frontend && npx tsc --noEmit && npm run test -- --run
```

- [ ] **Commit:**
```bash
git add frontend/src/
git commit -m "refactor: deduplicate LOW_SCORE_THRESHOLD, deriveSubtitlePath, strVal/numVal helpers"
```

---

### Task 3.4: `useDebounce` Hook + Duplikate entfernen

**Befund:** Manuelles `setTimeout`-Debounce-Pattern in `Wanted.tsx` und `GlobalSearchModal.tsx` kopiert.

**Files:**
- Create: `frontend/src/hooks/useDebounce.ts`
- Modify: `frontend/src/pages/Wanted.tsx`
- Modify: `frontend/src/components/shared/GlobalSearchModal.tsx`

- [ ] **Erstelle `frontend/src/hooks/useDebounce.ts`** (bereits in TypeScript Patterns dokumentiert):

```typescript
import { useState, useEffect } from 'react'

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(handler)
  }, [value, delay])

  return debouncedValue
}
```

- [ ] **Ersetze manuellen Debounce in `Wanted.tsx`:**
```typescript
// ALT:
useEffect(() => {
  const timer = setTimeout(() => setDebouncedQuery(query), 300)
  return () => clearTimeout(timer)
}, [query])

// NEU:
import { useDebounce } from '@/hooks/useDebounce'
const debouncedQuery = useDebounce(query, 300)
// setDebouncedQuery State komplett entfernen
```

Gleiches in `GlobalSearchModal.tsx`.

- [ ] **Barrel-Export in `hooks/index.ts` oder `hooks/useApi.ts` ergänzen** (je nach Konvention im Projekt prüfen):
```bash
grep -n "useDebounce\|export.*from" frontend/src/hooks/useApi.ts | head -5
```

- [ ] **Tests:**
```bash
cd frontend && npm run test -- --run
```

- [ ] **Commit:**
```bash
git add frontend/src/hooks/useDebounce.ts frontend/src/pages/Wanted.tsx frontend/src/components/shared/GlobalSearchModal.tsx
git commit -m "refactor: extract useDebounce hook, remove duplicate setTimeout debounce patterns"
```

---

### Task 3.5: `window.location.reload()` bei 401 → React Router Navigate

**Befund:** Hard-Reload bei 401 verliert ungespeicherte Änderungen im Subtitle-Editor. `beforeunload`-Guard feuert nicht bei programmatischem Reload.

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Lese aktuellen Interceptor:**
```bash
grep -n "401\|reload\|navigate" frontend/src/api/client.ts | head -15
```

- [ ] **Ersetze `window.location.reload()` durch Router-Navigation:**

```typescript
// ALT (ca. Zeile 115):
window.location.reload()

// NEU:
// Option A: wenn React Router zugänglich ist (RouterProvider-Kontext):
import { router } from '@/router'  // oder wie auch immer der Router exportiert wird
router.navigate('/login')

// Option B: falls kein direkter Router-Zugriff:
window.location.href = '/login'  // löst beforeunload aus, kein full reload
```

Prüfe zuerst wie der Router in `App.tsx` konfiguriert ist:
```bash
grep -n "createBrowserRouter\|RouterProvider\|BrowserRouter" frontend/src/App.tsx | head -5
```

- [ ] **Tests:**
```bash
cd frontend && npm run test -- --run
```

- [ ] **Commit:**
```bash
git add frontend/src/api/client.ts
git commit -m "fix: replace window.location.reload() on 401 with navigation to preserve unsaved state"
```

---

### Task 3.6: `window.confirm` durch Modals ersetzen

**Befund:** `window.confirm()` in SubtitleEditor, TranslationTab — inaccessible, nicht styled.

**Files:**
- Modify: `frontend/src/components/editor/SubtitleEditor.tsx`
- Modify: `frontend/src/pages/Settings/TranslationTab.tsx`

- [ ] **Prüfe ob ein generisches Confirm-Modal bereits existiert:**
```bash
grep -rn "ConfirmModal\|ConfirmDialog\|useConfirm" frontend/src/components/ | head -10
```

Falls ja: dieses nutzen. Falls nein: kleines `ConfirmModal`-Component erstellen:

```typescript
// frontend/src/components/shared/ConfirmModal.tsx
interface Props {
  open: boolean
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({ open, title, message, onConfirm, onCancel }: Props) {
  if (!open) return null
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="confirm-title" className="modal-overlay">
      <div className="modal-content">
        <h2 id="confirm-title">{title}</h2>
        <p>{message}</p>
        <div className="modal-actions">
          <button onClick={onCancel}>Cancel</button>
          <button onClick={onConfirm} className="btn-danger">Confirm</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Ersetze `window.confirm` in `SubtitleEditor.tsx` und `TranslationTab.tsx`** durch State + ConfirmModal.

- [ ] **Commit:**
```bash
git add frontend/src/components/shared/ConfirmModal.tsx frontend/src/components/editor/SubtitleEditor.tsx frontend/src/pages/Settings/TranslationTab.tsx
git commit -m "fix: replace window.confirm with accessible ConfirmModal component"
```

---

### Task 3.7: `SeriesDetail` — 9.999 Wanted Items Client-seitig filtern fixen

**Befund:** `useWantedItems(1, 9999, ...)` lädt alle Items um client-seitig nach `sonarr_series_id` zu filtern.

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx`
- Modify: `frontend/src/api/client.ts` (ggf. neuer Parameter)
- Modify: `frontend/src/hooks/useWantedApi.ts`

- [ ] **Prüfe ob Backend bereits series-ID-Filterung unterstützt:**
```bash
grep -n "series_id\|sonarr_series_id" backend/routes/wanted/search.py | head -10
grep -n "series_id" frontend/src/api/client.ts | head -10
```

- [ ] **Falls Backend-Filter fehlt:** Ergänze Query-Parameter in `GET /api/v1/wanted`:
```python
# backend/routes/wanted/search.py — im Filter-Handling:
if sonarr_series_id := request.args.get("sonarr_series_id", type=int):
    query = query.filter(WantedItem.sonarr_series_id == sonarr_series_id)
```

- [ ] **Frontend-Client ergänzen:**
```typescript
// client.ts: getWantedItems Signatur erweitern
export async function getWantedItems(
  page = 1,
  perPage = 50,
  type?: string,
  status?: string,
  language?: string,
  fetchAll?: boolean,
  sonarrSeriesId?: number,  // NEU
)
```

- [ ] **`SeriesDetail.tsx` anpassen:**
```typescript
// ALT
const { data: wantedData } = useWantedItems(1, 9999, 'episode', undefined, undefined, true)
// + client-seitiger filter

// NEU
const { data: wantedData } = useWantedItems(1, 200, 'episode', undefined, undefined, false, seriesId)
```

- [ ] **Tests:**
```bash
cd frontend && npm run test -- --run
cd backend && python -m pytest tests/ -k "wanted" -v --tb=short
```

- [ ] **Commit:**
```bash
git commit -m "perf: filter wanted items by series_id server-side instead of fetching 9999 client-side"
```

---

### Task 3.8: `TranslationTab.tsx` aufsplitten (1.980 Zeilen)

**Befund:** 12 Komponenten in einer Datei — verletzt 800-Zeilen-Guideline stark.

**Files:**
- Create: `frontend/src/pages/Settings/translation/BackendCard.tsx`
- Create: `frontend/src/pages/Settings/translation/OllamaPullSection.tsx`
- Create: `frontend/src/pages/Settings/translation/TemplatePickerModal.tsx`
- Create: `frontend/src/pages/Settings/translation/GlobalGlossaryPanel.tsx`
- Create: `frontend/src/pages/Settings/translation/TranslationMemorySection.tsx`
- Create: `frontend/src/pages/Settings/translation/PromptPresetsTab.tsx`
- Create: `frontend/src/pages/Settings/translation/AutoSyncSection.tsx`
- Modify: `frontend/src/pages/Settings/TranslationTab.tsx` (nur noch Re-Exports + wenig Logik)

- [ ] **Prüfe welche Komponenten bereits lazy-importiert werden:**
```bash
grep -n "lazy\|import(" frontend/src/pages/Settings/TranslationSettings.tsx | head -20
```

- [ ] **Für jede lazy-importierte Komponente:** Extrahiere den Code aus `TranslationTab.tsx` in die entsprechende Datei. Die Lazy-Imports in `TranslationSettings.tsx` bleiben unverändert — nur die Quelle wechselt.

- [ ] **Reihenfolge:** Eine Komponente pro Commit. Mit der größten/einfachsten beginnen. Zwischen jedem Schritt TypeScript-Check:
```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit je Komponente:**
```bash
git commit -m "refactor: extract BackendCard into translation/BackendCard.tsx"
# ... wiederholen für jede Komponente
```

---

## Phase 4 — Architektur (Monat 2)

### Task 4.1: Services-Layer strukturieren

**Befund:** `translator.py`, `wanted_scanner.py`, `wanted_search.py` sind effektiv Services, leben aber auf Top-Level.

**Files:**
- Move: `backend/translator.py` → `backend/services/translator.py`
- Move: `backend/wanted_scanner.py` → `backend/services/wanted_scanner.py`
- Move: `backend/wanted_search.py` → `backend/services/wanted_search.py`

**Hinweis:** Das sind rein strukturelle Verschiebungen. Alle Import-Pfade müssen aktualisiert werden.

- [ ] **Pro Datei:** `git mv` + alle Imports fixen + Tests grün halten:
```bash
git mv backend/translator.py backend/services/translator.py
grep -rn "from translator import\|import translator" backend/ | grep -v services/
# Alle gefundenen Imports anpassen
cd backend && python -m pytest --tb=short -q  # Muss grün bleiben
git commit -m "refactor: move translator.py into services/"
```
Gleich für `wanted_scanner.py` und `wanted_search.py`.

---

### Task 4.2: Timestamps → SQLAlchemy `DateTime` Migration

**Befund:** Alle Timestamps als `Text` — SQLite-spezifische Queries, kein PostgreSQL-Support.

**Hinweis:** Das ist das umfangreichste Refactoring. Erfordert:
1. Alembic-Migration (ALTER COLUMN oder neue Tabelle + Datenmigration)
2. Alle ORM-Model-Definitionen anpassen
3. Alle Query-Stellen auf native Datetime-Vergleiche umstellen

- [ ] **Migration erstellen:**
```bash
cd backend && python -m alembic revision --autogenerate -m "migrate_timestamps_to_datetime"
# Manuelle Überprüfung der generierten Migration obligatorisch
```

- [ ] **Models anpassen:** `Mapped[str]` + `Text` → `Mapped[datetime]` + `DateTime(timezone=True)` für alle Timestamp-Felder.

- [ ] **Alle Query-Stellen fixen:** `date('now', ...)` SQLite-Strings → `datetime.now(UTC) - timedelta(days=n)`.

- [ ] **Vollständiger Test-Run:**
```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py
```

- [ ] **Commit:**
```bash
git commit -m "feat: migrate all timestamp columns from Text to DateTime(timezone=True)"
```

---

## Ausführungsreihenfolge und Priorität

| Phase | Tasks | Zeitschätzung | Voraussetzung |
|-------|-------|---------------|---------------|
| **Phase 1** | 1.1–1.10 | ~3h | Keine |
| **Phase 2** | 2.1–2.6 | ~1 Tag | Phase 1 abgeschlossen |
| **Phase 3** | 3.1–3.8 | ~2 Tage | Unabhängig von Phase 2 |
| **Phase 4** | 4.1–4.2 | ~2–3 Tage | Phase 2 abgeschlossen |

Phase 1 und Phase 3 können **parallel** bearbeitet werden (Backend vs. Frontend).

## Pre-PR Checks (nach jeder Phase)

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
