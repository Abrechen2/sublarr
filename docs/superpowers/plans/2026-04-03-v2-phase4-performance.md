---
phase: 4
title: "Performance & Pool-Caching"
version_target: "0.39.0-beta"
created: 2026-04-03
status: planned
---

# Phase 4 — Performance & Pool-Caching

## Kontext: Was bereits existiert

Vor der Implementierung wurde das bestehende System vollständig analysiert. Mehrere Punkte aus
der ursprünglichen Aufgabenstellung sind bereits umgesetzt:

### Bereits vorhanden (NICHT neu implementieren)

**Zwei-Tier Provider Cache** — vollständig implementiert in `backend/providers/__init__.py`:
- Tier 1: Fast-Cache via `app.cache_backend` (Redis oder In-Memory) mit Key-Prefix `provider:combined:`
- Tier 2: Persistenter DB-Cache via `ProviderCache`-Tabelle (`db/models/providers.py`)
- Cache-Key-Generierung via `_make_cache_key(query, format_filter)`
- TTL über `provider_cache_ttl_minutes` in `config.py` (Default: 5 min)
- Cache-Invalidierung via `CacheRepository.invalidate_app_cache(prefix="provider:")`
- `ProviderCache` DB-Model mit Indexes auf `(provider_name, query_hash)` und `expires_at`
- `CacheBackend` ABC in `backend/cache/` mit `RedisCacheBackend` und `MemoryCacheBackend`

**Bestehende Indexes auf `wanted_items`**:
- `idx_wanted_status` auf `status`
- `idx_wanted_item_type` auf `item_type`
- `idx_wanted_file_path` auf `file_path`
- `idx_wanted_sonarr_series/episode`, `idx_wanted_radarr_movie`
- `idx_wanted_composite` auf `(status, item_type)`
- `idx_wanted_retry_after` auf `retry_after`

**Webhook-Delay** — bereits konfigurierbar via `webhook_delay_minutes` in `config.py`;
`time.sleep(delay)` in `routes/webhooks.py:44` ist intentional und durch Config gesteuert.

**`Metrics.CACHE_HITS_TOTAL`/`CACHE_MISSES_TOTAL`** — Prometheus Counter in `metrics.py`
definiert und mit `["backend"]`-Label initialisiert, aber **nie inkrementiert** aus dem
Provider-Cache-Pfad.

---

## Aufgabe 1: Provider-Cache-Metriken instrumentieren

### Problem

`Metrics.CACHE_HITS_TOTAL` und `Metrics.CACHE_MISSES_TOTAL` (definiert in `backend/metrics.py`)
werden zwar initialisiert, aber nirgendwo inkrementiert wenn der Provider-Cache in
`providers/__init__.py` einen Hit oder Miss erzeugt. Prometheus-Scraping zeigt dadurch
permanent `0` für beide Counter — kein Monitoring der Cache-Effizienz möglich.

### Dateien

```
backend/providers/__init__.py   # Cache-Hit/Miss-Aufrufe hinzufügen (2 Stellen)
backend/metrics.py              # PROVIDER_CACHE_HIT/MISS Counter hinzufügen (layer-Label)
```

### Implementierung

**`backend/metrics.py`** — Neue dedizierte Counter neben den bestehenden generischen
`CACHE_HITS_TOTAL`/`CACHE_MISSES_TOTAL` ergänzen. Die bestehenden Counter haben Label
`["backend"]` (redis/memory). Neue Counter bekommen `["layer"]`-Label (`fast`/`db`) damit
klar differenziert wird wo im Two-Tier-System der Treffer erfolgte:

```python
# In der Metrics-Klasse, nach CACHE_MISSES_TOTAL:
PROVIDER_CACHE_HITS_TOTAL = Counter(
    "sublarr_provider_cache_hits_total",
    "Provider search result cache hits",
    ["layer"],  # "fast" (Redis/memory), "db" (ProviderCache table)
)
PROVIDER_CACHE_MISSES_TOTAL = Counter(
    "sublarr_provider_cache_misses_total",
    "Provider search result cache misses",
    ["layer"],  # "fast", "db"
)
```

**`backend/providers/__init__.py`** — In `search_subtitles()` (die Methode mit dem Two-Tier
Cache, ab ca. Zeile 782) an vier Stellen Metriken einbauen. Import oben in der Datei
hinzufügen: `from metrics import Metrics`. Alle Metric-Calls in `try/except Exception` wrappen
(Metrics dürfen nie einen Provider-Call blockieren):

```python
# Tier 1 Hit (ca. Zeile 796, nach "cached_data = json.loads(fast_cached)"):
try:
    Metrics.PROVIDER_CACHE_HITS_TOTAL.labels(layer="fast").inc()
except Exception:
    pass

# Tier 1 Miss (nach dem try/except-Block für Tier 1, vor Tier 2):
# Kein expliziter Miss-Counter für Tier 1 nötig — nur wenn Tier 2 auch Miss ist.

# Tier 2 Hit (ca. Zeile 813, nach "cached_data = json.loads(cached_json)"):
try:
    Metrics.PROVIDER_CACHE_HITS_TOTAL.labels(layer="db").inc()
except Exception:
    pass

# Kompletter Miss (nach den beiden Cache-Checks, kurz vor dem parallelen Executor,
# ca. nach Zeile 824):
try:
    Metrics.PROVIDER_CACHE_MISSES_TOTAL.labels(layer="fast").inc()
    Metrics.PROVIDER_CACHE_MISSES_TOTAL.labels(layer="db").inc()
except Exception:
    pass
```

Hinweis: Der Cache-Backfill (Tier 2 -> Tier 1) bei einem DB-Hit benötigt keinen separaten
Counter; der `layer="db"` Hit-Counter reicht.

### Verifikation

```bash
cd backend && python -c "
from metrics import Metrics
Metrics.PROVIDER_CACHE_HITS_TOTAL.labels(layer='fast').inc()
Metrics.PROVIDER_CACHE_HITS_TOTAL.labels(layer='db').inc()
Metrics.PROVIDER_CACHE_MISSES_TOTAL.labels(layer='fast').inc()
Metrics.PROVIDER_CACHE_MISSES_TOTAL.labels(layer='db').inc()
print('Metrics OK')
"
cd backend && ruff check providers/__init__.py metrics.py
```

### Akzeptanzkriterium

`GET /api/v1/metrics` gibt `sublarr_provider_cache_hits_total` und
`sublarr_provider_cache_misses_total` mit `layer`-Label zurück. Nach einem Provider-Search
(der auf Cache trifft) steigt der entsprechende Counter.

---

## Aufgabe 2: N+1 Query Audit & Befunde

### Analyseergebnisse

Nach vollständiger Analyse der Repositories und Scanner-Logik:

**Kein klassisches N+1 in Repositories gefunden.** `WantedRepository`, `CacheRepository`,
`HistoryRepository` nutzen SQLAlchemy mit Bulk-Queries (`.in_()`, `select()` + Filter).

**Echter Fund: `get_wanted_item(item_id)` im Such-Loop.**

In `backend/services/wanted_scanner_core.py` (Zeile ~952) wird für jeden der `eligible`-Items
`process_wanted_item(item["id"])` via ThreadPoolExecutor aufgerufen. In
`backend/wanted_search/process.py` (Zeile 213) steht:

```python
item = get_wanted_item(item_id)  # Einzelner DB-Fetch pro Thread
```

Das ist kein klassisches N+1 (es ist in separaten Threads), aber es sind N einzelne
SELECT-Calls statt eines Bulk-Fetches. Da `wanted_items` bereits via `get_wanted_items()` in
`search_all_wanted()` vollständig geladen werden (Zeile ~857), ist das ein Duplicate-Fetch.

**Echter Fund: Cleanup-Loop mit `os.path.exists()` ohne Batch-Optimierung.**

In `wanted_scanner_core.py` `_cleanup_stale_wanted()` (ab Zeile 793) iteriert über alle
`get_wanted_items_for_cleanup()`-Items und ruft für jedes `os.path.exists(path)` auf. Das ist
keine DB-N+1, aber potenziell ein I/O-N+1 bei großen Libraries (tausende Items).

### Dateien

```
backend/wanted_search/process.py          # item-Dict statt item_id übergeben (optional)
backend/services/wanted_scanner_core.py   # Kommentar zum Cleanup-Loop ergänzen
```

### Implementierung

**Kurzfristig (diese Phase):** In `backend/wanted_search/process.py` den `get_wanted_item`-Call
mit einem Hinweis-Kommentar versehen, dass der Caller die Item-Daten bereits hält:

```python
# NOTE: item_id-only API ist absichtlich — der Caller (ThreadPoolExecutor) übergibt
# nur die ID damit jeder Thread seinen eigenen DB-Session-Scope bekommt.
# Trade-off: N einzelne SELECTs statt 1 Bulk-Fetch. Akzeptiert, solange
# wanted_search_max_items_per_run < 200 bleibt (typisch: 50).
item = get_wanted_item(item_id)
```

In `backend/services/wanted_scanner_core.py` `_cleanup_stale_wanted()` (Zeile ~793) einen
Hinweis-Kommentar ergänzen:

```python
# NOTE: os.path.exists() wird für jedes Item einzeln aufgerufen (I/O-Loop).
# Bei sehr großen Libraries (>5000 Items) kann dies spürbar sein.
# Optimization path: batch via ThreadPoolExecutor mit max_workers=8 falls nötig.
for item in items:
```

**Diese Phase liefert:** Dokumentation der Analyse-Ergebnisse + Kommentare an den relevanten
Stellen. Kein Refactoring der Thread-Architektur in dieser Phase (Risiko zu hoch, kein
messbarer Gewinn bei typischen Library-Größen).

### Verifikation

```bash
cd backend && ruff check services/wanted_scanner_core.py wanted_search/process.py
# Manuelle Review: Grep zeigt keine neuen N+1-Patterns
grep -n "get_wanted_item\|for.*in.*items" backend/wanted_search/process.py backend/services/wanted_scanner_core.py
```

### Akzeptanzkriterium

Kommentare sind gesetzt. `ruff check` sauber. Keine neuen DB-Queries in Loops eingeführt.

---

## Aufgabe 3: Fehlende DB-Indexes

### Analyse

Nach vollständiger Prüfung aller Index-Definitionen in `db/models/core.py` und
`db/models/providers.py` fehlen zwei Indexes die regelmäßig abgefragt werden:

**`wanted_items.last_search_at`** — Wird in `wanted_scanner_core.py` (Zeile ~882) im Backoff-
Filter via `item.get("last_search_at")` verarbeitet (Python-seitig nach dem Fetch). Der
relevante Query-Filter passiert in `get_wanted_items(status="wanted")` — kein direkter
`last_search_at`-Filter in SQL. **Befund: Index hier wenig Nutzen, da Status-Filter
`idx_wanted_status` bereits greift und `last_search_at` nur in Python gefiltert wird.**

**`subtitle_downloads.language`** — Kein Index auf `language`. Wird bei Provider-History-
Lookups und Cache-Stats genutzt. Bei großen Download-Historien (>10.000 Einträge) relevant.

**Echter Bedarf: Composite Index auf `wanted_items(status, retry_after)`** — Der
`get_wanted_items(status="wanted")` Call mit anschließendem Python-seitigen `retry_after`-
Filter könnte profitieren. Aktuell: `idx_wanted_composite` auf `(status, item_type)` und
`idx_wanted_retry_after` auf `retry_after` separat. Ein Composite `(status, retry_after)` würde
die Kandidaten-Selektion für den Search-Loop direkt in SQL lösen.

### Dateien

```
backend/db/models/core.py                                           # Index-Definition ergänzen
backend/db/models/providers.py                                      # Index-Definition ergänzen
backend/db/migrations/versions/a1b2c3d4e5f6_add_performance_indexes.py  # Neue Migration
```

### Implementierung

**`backend/db/models/core.py`** — In `WantedItem.__table_args__` ergänzen:

```python
Index("idx_wanted_status_retry_after", "status", "retry_after"),
```

**`backend/db/models/providers.py`** — In `SubtitleDownload.__table_args__` ergänzen:

```python
Index("idx_subtitle_downloads_language", "language"),
```

**`backend/db/migrations/versions/a1b2c3d4e5f6_add_performance_indexes.py`**:

```python
"""Add performance indexes for wanted_items and subtitle_downloads

Revision ID: a1b2c3d4e5f6
Revises: e4f5a6b7c8d9
Create Date: 2026-04-03

Adds composite index on wanted_items(status, retry_after) for the
scan-loop candidate filter, and language index on subtitle_downloads
for provider history lookups.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.create_index(
            "idx_wanted_status_retry_after",
            ["status", "retry_after"],
        )
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.create_index(
            "idx_subtitle_downloads_language",
            ["language"],
        )


def downgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_index("idx_wanted_status_retry_after")
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.drop_index("idx_subtitle_downloads_language")
```

**Wichtig — Revision Chain:** `down_revision = "e4f5a6b7c8d9"` (= `make_glossary_series_id_nullable.py`,
der aktuelle Head der Migration-Chain). Vor dem Commit verifizieren mit:
```bash
cd backend && python -m alembic history --verbose | head -10
```

### Verifikation

```bash
cd backend && python -m alembic upgrade head
cd backend && python -c "
from sqlalchemy import inspect, create_engine
import os
db_path = 'dev/sublarr.db'  # lokaler Dev-Pfad
if os.path.exists(db_path):
    engine = create_engine(f'sqlite:///{db_path}')
    insp = inspect(engine)
    wi = [i['name'] for i in insp.get_indexes('wanted_items')]
    sd = [i['name'] for i in insp.get_indexes('subtitle_downloads')]
    assert 'idx_wanted_status_retry_after' in wi, f'Missing index, have: {wi}'
    assert 'idx_subtitle_downloads_language' in sd, f'Missing index, have: {sd}'
    print('Indexes verified OK')
"
cd backend && python -m alembic downgrade -1 && python -m alembic upgrade head
```

### Akzeptanzkriterium

`alembic upgrade head` läuft fehlerfrei. `alembic downgrade -1` + `upgrade head` auch.
Beide neuen Indexes sind in der DB vorhanden.

---

## Aufgabe 4: Konfigurierbares Gestdown-Retry-Delay

### Problem

`backend/providers/gestdown.py` Zeile 355:

```python
if resp.status_code == 423:
    # Locked/retry -- wait 1s and retry once
    logger.debug("Gestdown: HTTP 423 (locked), retrying after 1s")
    time.sleep(1)
    resp = self.session.get(url)
```

Das `time.sleep(1)` ist hardcodiert. Bei Batch-Suchen über viele Episoden (z. B. komplette
Serien-Scans) multipliziert sich das: 20 Episoden mit je einem 423 = 20 Sekunden blockierter
Thread. Das Delay soll über `config.py` steuerbar sein.

### Dateien

```
backend/config.py              # Neues Feld gestdown_retry_delay_s
backend/providers/gestdown.py  # time.sleep(1) -> settings-Wert
```

### Implementierung

**`backend/config.py`** — In der `SublarrSettings`-Klasse, sinnvoll neben den anderen Provider-
Timeout-Feldern (Suche nach `download_delay_between_providers_ms` als Orientierung):

```python
gestdown_retry_delay_s: float = 1.0
"""Wartezeit in Sekunden vor dem Retry nach HTTP 423 (Locked) von Gestdown.
Niedrigere Werte beschleunigen Batch-Scans; 0.0 deaktiviert das Warten.
Env: SUBLARR_GESTDOWN_RETRY_DELAY_S"""
```

Das Feld muss auch in der `to_dict()`-Methode von `SublarrSettings` eingetragen werden
(Abschnitt wo andere Provider-spezifische Felder stehen, z. B. `download_delay_between_providers_ms`).
Prüfe ob `gestdown_retry_delay_s` bereits in `to_dict()` fehlt und ergänze es.

**`backend/providers/gestdown.py`** — Den hardcodierten Sleep ersetzen:

```python
if resp.status_code == 423:
    retry_delay = getattr(self.settings, "gestdown_retry_delay_s", 1.0)
    logger.debug("Gestdown: HTTP 423 (locked), retrying after %.1fs", retry_delay)
    if retry_delay > 0:
        time.sleep(retry_delay)
    resp = self.session.get(url)
```

`getattr` mit Default-Wert verwenden (wie im Codebase-Konventions-Pattern für Optional settings:
`getattr(self.settings, "field", default)` — nie direkten Attribute-Zugriff).

### Verifikation

```bash
cd backend && python -c "
from config import SublarrSettings
s = SublarrSettings()
val = getattr(s, 'gestdown_retry_delay_s', 'MISSING')
assert val == 1.0, f'Expected 1.0, got {val}'
print(f'gestdown_retry_delay_s = {val} OK')
"
cd backend && ruff check providers/gestdown.py config.py
```

### Akzeptanzkriterium

`SUBLARR_GESTDOWN_RETRY_DELAY_S=0.5` in `.env` gesetzt -> `get_settings().gestdown_retry_delay_s`
gibt `0.5` zurück. `SUBLARR_GESTDOWN_RETRY_DELAY_S=0` -> kein Sleep bei 423.
`ruff check` sauber.

---

## Aufgabe 5: Webhook Blocking Sleep dokumentieren

### Kontext

`backend/routes/webhooks.py` Zeile 44:

```python
if delay > 0:
    logger.info("Webhook pipeline: waiting %d minutes...", s.webhook_delay_minutes)
    time.sleep(delay)
```

Das ist ein **blockierender Sleep im Background-Thread** (`_webhook_auto_pipeline` wird via
`threading.Thread(target=...).start()` aufgerufen). Das ist funktional korrekt — der Thread
läuft im Hintergrund, der HTTP-Response wurde bereits zurückgegeben. Kein Bug.

Der langfristige Pfad (async Job-Queue via RQ) ist architektonisch sauber aber nicht
zwingend in dieser Phase.

### Dateien

```
backend/routes/webhooks.py  # Kommentar ergänzen
```

### Implementierung

Den bestehenden Sleep-Block mit einem erklärenden Kommentar versehen:

```python
# Step 1: Configurable delay (blocking sleep is safe here — this runs in a
# dedicated background thread, HTTP response was already returned to the caller).
# Long-term path: replace with RQ job so delay survives server restarts and
# is visible in the job queue UI. See app.job_queue for the existing RQ setup.
if delay > 0:
    logger.info("Webhook pipeline: waiting %d minutes...", s.webhook_delay_minutes)
    time.sleep(delay)
```

### Verifikation

```bash
cd backend && ruff check routes/webhooks.py
grep -n "Long-term path\|background thread" backend/routes/webhooks.py
```

### Akzeptanzkriterium

Kommentar ist gesetzt. `ruff check` sauber. Keine funktionale Änderung.

---

## Ausführungsreihenfolge

Aufgaben 1, 3, 4, 5 sind unabhängig und können in beliebiger Reihenfolge ausgeführt werden.
Aufgabe 2 (N+1 Audit) ist rein dokumentarisch und kann parallel dazu laufen.

**Empfohlene Reihenfolge:**
1. Aufgabe 4 (Gestdown config) — kleinste Änderung, sofortiger Nutzen
2. Aufgabe 5 (Webhook Kommentar) — reine Dokumentation
3. Aufgabe 1 (Cache Metriken) — höchster Monitoring-Wert
4. Aufgabe 3 (DB Indexes + Migration) — braucht Alembic-Sorgfalt, zuletzt
5. Aufgabe 2 (N+1 Kommentare) — inline mit anderen Änderungen

## Pre-Commit Checkliste

```bash
# Backend ruff (immer auf gesamtes backend/ Verzeichnis):
cd backend && ruff check . && ruff format --check .

# Backend Tests (mit Standard-Ignores):
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"

# Alembic Migration Round-Trip:
cd backend && python -m alembic upgrade head
cd backend && python -m alembic downgrade -1
cd backend && python -m alembic upgrade head
```

## Commit-Vorschlag

```
perf: add provider cache metrics, DB indexes, configurable gestdown retry

- Increment sublarr_provider_cache_hits/misses_total from two-tier cache path
  in ProviderManager.search_subtitles() with layer=fast/db label
- Add composite index wanted_items(status, retry_after) for scan-loop filter
- Add index subtitle_downloads(language) for provider history queries
- Alembic migration a1b2c3d4e5f6 (down_revision: e4f5a6b7c8d9)
- Replace hardcoded time.sleep(1) in gestdown.py 423-handler with
  configurable gestdown_retry_delay_s (default: 1.0, env: SUBLARR_GESTDOWN_RETRY_DELAY_S)
- Document webhook background thread sleep and async handover path
- N+1 audit: no structural N+1 found; document findings with inline comments
```
