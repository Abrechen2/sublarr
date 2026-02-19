# Phase 15: API-Key Mgmt + Notifications + Cleanup - Research

**Researched:** 2026-02-19
**Domain:** API key management, notification templating, subtitle deduplication
**Confidence:** HIGH (well-understood problem domains within established codebase)

## Summary

Phase 15 covers three distinct functional areas that share the common theme of operational management: centralized API key management, enhanced notification templates with quiet hours, and subtitle file deduplication/cleanup. All three areas build upon well-established patterns in the existing codebase (SQLAlchemy ORM models, Flask Blueprint routes, React Settings tabs, Apprise notifications).

The codebase already has scattered API key management (individual fields in config.py), basic Apprise notifications (notifier.py with simple event toggles), and no deduplication system at all. The existing architecture -- SQLAlchemy models, repository pattern, Flask Blueprints, React query hooks -- provides clear extension points for all three feature areas.

**Primary recommendation:** Implement in three clear sub-phases: (1) API Key Management + Bazarr migration as a backend-focused sub-phase, (2) Notification Templates + Quiet Hours extending the existing notifier, (3) Deduplication Engine + Cleanup Dashboard as a filesystem-scanning sub-phase.

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | 3.1.0 | Blueprint routes for new API endpoints | Already the project web framework |
| SQLAlchemy | 2.0.46 | ORM models for new tables | Already the project ORM |
| Flask-Migrate/Alembic | 4.1.0/1.18.4 | Database migrations for new tables | Already handles schema evolution |
| Apprise | 1.9.2 | Notification delivery (80+ services) | Already integrated in notifier.py |
| Jinja2 | (bundled with Flask) | Notification template rendering | Already available, powerful templating |
| React 19 + TanStack Query 5 | 19.2/5.90 | Frontend UI for all three features | Already the project frontend stack |
| Zustand | 5.0.11 | Client-side state for complex UI (dedup selections) | Already in project for stores |
| hashlib (stdlib) | N/A | SHA-256 content hashing for deduplication | Python stdlib, no additional deps |
| Pydantic | 2.10.6 | Settings validation, export schema validation | Already the config framework |
| pysubs2 | 1.7.3 | Subtitle parsing for metadata comparison in dedup | Already in project |

### Supporting (new additions)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PyYAML | (already transitive dep) | Parsing Bazarr config.yaml for migration | Only for KEYS-05 Bazarr migration |
| zipfile (stdlib) | N/A | ZIP export of config + profiles + glossaries | KEYS-03 extended export |
| csv (stdlib) | N/A | CSV import of API keys | KEYS-04 import |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Jinja2 for templates | Simple str.format() | Jinja2 supports conditionals, loops, filters -- needed for advanced templates |
| hashlib SHA-256 | xxhash for speed | SHA-256 is good enough for subtitle files (small), no new dependency needed |
| Zustand for dedup state | React useState | Zustand better for complex multi-step selection state across components |

**Installation:**
No new packages required. All functionality uses existing dependencies.

## Architecture Patterns

### Recommended Project Structure (new files)
```
backend/
  db/
    models/
      notifications.py     # NotificationTemplate, NotificationHistory, QuietHours
      cleanup.py            # SubtitleHash, CleanupRule, CleanupHistory
    repositories/
      notifications.py      # NotificationRepository
      cleanup.py            # CleanupRepository
  routes/
    api_keys.py             # Blueprint for /api/v1/api-keys/*
    notifications_mgmt.py   # Blueprint for /api/v1/notifications/templates/*, /quiet-hours/*
    cleanup.py              # Blueprint for /api/v1/cleanup/*
  notifier.py               # Extend existing with template rendering + quiet hours
  bazarr_migrator.py        # Bazarr config.yaml + DB parser
  dedup_engine.py           # Content hashing + metadata comparison engine
  cleanup_scheduler.py      # Scheduled cleanup job runner

frontend/
  src/
    pages/Settings/
      ApiKeysTab.tsx         # Centralized API key management
      NotificationTemplatesTab.tsx  # Template editor + assignment
      CleanupTab.tsx         # Dedup + cleanup dashboard
    components/
      notifications/
        TemplateEditor.tsx   # Variable-aware template editor with preview
        TemplatePreview.tsx  # Live preview of template with sample data
        QuietHoursConfig.tsx # Time window picker
      cleanup/
        DedupGroupList.tsx   # Grouped duplicate display
        DiskSpaceWidget.tsx  # Disk usage analysis
        CleanupPreview.tsx   # Preview of what will be deleted
```

### Pattern 1: Centralized API Key Registry
**What:** Instead of scattered API key fields in config, maintain a registry that maps service names to their key fields, providing unified CRUD, masking, and validation.
**When to use:** KEYS-01, KEYS-02 -- centralizing the existing config-based keys.
**Example:**
```python
# backend/routes/api_keys.py
API_KEY_REGISTRY = {
    "sublarr": {"keys": ["api_key"], "test_fn": None},
    "sonarr": {"keys": ["sonarr_api_key"], "test_fn": "sonarr_client.test_connection"},
    "radarr": {"keys": ["radarr_api_key"], "test_fn": "radarr_client.test_connection"},
    "opensubtitles": {"keys": ["opensubtitles_api_key", "opensubtitles_username", "opensubtitles_password"], "test_fn": "providers.test_provider"},
    "jimaku": {"keys": ["jimaku_api_key"], "test_fn": "providers.test_provider"},
    "subdl": {"keys": ["subdl_api_key"], "test_fn": "providers.test_provider"},
    "jellyfin": {"keys": ["jellyfin_api_key"], "test_fn": "mediaserver.test_connection"},
    "tmdb": {"keys": ["tmdb_api_key"], "test_fn": None},
    "tvdb": {"keys": ["tvdb_api_key"], "test_fn": None},
    "deepl": {"keys": ["deepl_api_key"], "test_fn": "translation.deepl_backend.test_connection"},
}
```

### Pattern 2: Notification Template System with Jinja2
**What:** Notification templates stored in DB, rendered via Jinja2 with event-specific variables, previewed before saving.
**When to use:** NOTF-01, NOTF-02 -- template creation and assignment.
**Example:**
```python
from jinja2 import Environment, BaseLoader, select_autoescape
import jinja2

_jinja_env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape([]),
    undefined=jinja2.Undefined,
)

def render_notification_template(template_str, variables):
    tmpl = _jinja_env.from_string(template_str)
    return tmpl.render(**variables)
```

### Pattern 3: Content-Hash Deduplication
**What:** SHA-256 hash of normalized subtitle content to identify exact and near-duplicates.
**When to use:** DEDU-01 -- building the deduplication engine.
**Example:**
```python
import hashlib

def compute_subtitle_hash(file_path):
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    normalized = content.strip().replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

### Pattern 4: Quiet Hours with Timezone Support
**What:** Time window checking against configurable quiet periods with exception lists for critical events.
**When to use:** NOTF-04 -- quiet hours implementation.
**Example:**
```python
from datetime import datetime, time

def is_quiet_hours(quiet_config):
    if not quiet_config.get("enabled"):
        return False
    now = datetime.now().time()
    start = time.fromisoformat(quiet_config["start_time"])
    end = time.fromisoformat(quiet_config["end_time"])
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end
```

### Anti-Patterns to Avoid
- **Storing API keys in new tables:** Keep using config_entries for API keys (single source of truth). The key management UI is a view layer over existing config, not a new storage layer.
- **Template rendering without sandboxing:** Never use eval() or allow arbitrary Python in templates. Jinja2 with BaseLoader and no filesystem access is safe. Consider SandboxedEnvironment for extra safety.
- **Full file reads for deduplication:** Read in chunks (64KB blocks) for hashing large files. Subtitle files are small, but establish the pattern correctly.
- **Deleting files without confirmation:** Always require explicit user confirmation before any file deletion. Preview first, delete second.
- **Ignoring timezone in quiet hours:** Store times as local time strings and evaluate against the server local time. Document that quiet hours use server timezone.

## Do Not Hand-Roll

| Problem | Do Not Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template rendering | Custom string replacement | Jinja2 (already in Flask) | Supports conditionals, loops, filters, auto-escaping |
| Notification delivery | Custom HTTP clients | Apprise (already integrated) | Supports 80+ services, handles auth/formatting |
| YAML parsing | Custom parser | PyYAML (transitive dep) | Handles all YAML edge cases |
| ZIP file creation | Manual byte manipulation | zipfile (stdlib) | Handles compression, paths, encoding correctly |
| Content hashing | Custom checksum | hashlib SHA-256 (stdlib) | Cryptographically strong, fast for small files |
| Subtitle parsing | Custom ASS/SRT parser | pysubs2 (already in project) | Handles all subtitle format edge cases |
| Scheduled cleanup | Custom threading | Existing scheduler pattern in app.py | Already established for wanted_scanner |

**Key insight:** All three feature areas are primarily integration work, not novel algorithm design. The existing codebase patterns (repository, blueprint, query hooks) should be followed precisely.

## Common Pitfalls

### Pitfall 1: API Key Rotation Breaking Active Connections
**What goes wrong:** Rotating an API key while Sonarr/provider connections are cached causes auth failures.
**Why it happens:** Singleton client instances cache the old key.
**How to avoid:** Call invalidate_client() / invalidate_manager() after any key rotation (same pattern as update_config route already does).
**Warning signs:** 401 errors after key change until container restart.

### Pitfall 2: Bazarr Config Format Changes Between Versions
**What goes wrong:** Bazarr changed from config.ini to config.yaml in v1.4. Migration tool fails on one format.
**Why it happens:** Assuming a single config format.
**How to avoid:** Detect format by file extension and attempt both parsers. Support .ini (configparser) and .yaml (PyYAML).
**Warning signs:** Migration tool crashes on older Bazarr installs.

### Pitfall 3: Jinja2 Template Injection via User Input
**What goes wrong:** User-crafted templates could potentially access Flask internals.
**Why it happens:** Using Environment with FileSystemLoader or not restricting template features.
**How to avoid:** Use SandboxedEnvironment from jinja2.sandbox for user-provided templates. Never use FileSystemLoader. Restrict available globals/filters.
**Warning signs:** Templates that access config, request, or other Flask objects.

### Pitfall 4: Quiet Hours Timezone Confusion
**What goes wrong:** Quiet hours trigger at wrong times for users in different timezones.
**Why it happens:** Storing times as naive datetime without timezone context.
**How to avoid:** Store quiet hours as local time strings ("22:00"-"07:00") and evaluate against the server local time. Document that quiet hours use server timezone.
**Warning signs:** Notifications during configured quiet hours.

### Pitfall 5: Deduplication Deleting the Only Copy
**What goes wrong:** All copies in a duplicate group are deleted, leaving no subtitle.
**Why it happens:** No "keep at least one" guard in batch delete.
**How to avoid:** Always require the user to select which copy to KEEP, not which to delete. The UI should show a "keep" radio button per group, and the backend should refuse to delete all files in a group.
**Warning signs:** Missing subtitles after cleanup.

### Pitfall 6: Large Filesystem Scans Blocking the Event Loop
**What goes wrong:** Dedup scan of thousands of files blocks the Flask thread.
**Why it happens:** Running scan synchronously in the request handler.
**How to avoid:** Run scans in a background thread (ThreadPoolExecutor) with progress updates via WebSocket, same pattern as batch translation.
**Warning signs:** UI timeout during "Scan for duplicates" action.

### Pitfall 7: Export/Import of Keys Leaking Secrets
**What goes wrong:** ZIP export includes plaintext API keys.
**Why it happens:** Not filtering sensitive fields in export.
**How to avoid:** The existing get_safe_config() masks secrets. For the new extended export (KEYS-03), maintain this masking in config sections and handle key-specific exports with explicit user consent only.
**Warning signs:** API keys appearing in downloaded ZIP files.

## Code Examples

### New Database Models for Notifications

```python
# backend/db/models/notifications.py
from typing import Optional
from sqlalchemy import Index, Integer, Text, String
from sqlalchemy.orm import Mapped, mapped_column
from extensions import db

class NotificationTemplate(db.Model):
    __tablename__ = "notification_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    event_type: Mapped[Optional[str]] = mapped_column(String(50))
    service_name: Mapped[Optional[str]] = mapped_column(String(50))
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

class NotificationHistory(db.Model):
    __tablename__ = "notification_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[Optional[int]] = mapped_column(Integer)
    service_urls: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sent")
    error: Mapped[Optional[str]] = mapped_column(Text, default="")
    sent_at: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        Index("idx_notif_history_event", "event_type"),
        Index("idx_notif_history_sent", "sent_at"),
    )

class QuietHoursConfig(db.Model):
    __tablename__ = "quiet_hours"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    days_of_week: Mapped[str] = mapped_column(Text, nullable=False, default="[0,1,2,3,4,5,6]")
    exception_events: Mapped[str] = mapped_column(Text, nullable=False, default='["error"]')
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
```

### New Database Models for Deduplication

```python
# backend/db/models/cleanup.py
from typing import Optional
from sqlalchemy import Index, Integer, Text, String
from sqlalchemy.orm import Mapped, mapped_column
from extensions import db

class SubtitleHash(db.Model):
    __tablename__ = "subtitle_hashes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(10))
    line_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_scanned: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        Index("idx_subtitle_hash", "content_hash"),
        Index("idx_subtitle_hash_path", "file_path"),
    )

class CleanupRule(db.Model):
    __tablename__ = "cleanup_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_run_at: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

class CleanupHistory(db.Model):
    __tablename__ = "cleanup_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[Optional[int]] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_freed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    performed_at: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        Index("idx_cleanup_history_date", "performed_at"),
    )
```

### Bazarr Migration Parser

```python
import yaml
import configparser

def parse_bazarr_config(file_path):
    with open(file_path, "r") as f:
        content = f.read()
    try:
        config = yaml.safe_load(content)
        if isinstance(config, dict):
            return _normalize_yaml_config(config)
    except yaml.YAMLError:
        pass
    parser = configparser.ConfigParser()
    parser.read_string(content)
    return _normalize_ini_config(parser)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Individual API key fields in Settings tabs | Centralized key management page | This phase | Single place to manage all credentials |
| Simple event toggles for notifications | Template-based notifications with variables | This phase | Rich, customizable notification content |
| No duplicate detection | Content-hash based deduplication | This phase | Prevents wasted disk space from duplicate subs |
| Bazarr as separate tool | Migration path from Bazarr to Sublarr | This phase | Easier adoption for existing Bazarr users |
| No quiet hours | Configurable notification suppression windows | This phase | No more middle-of-night notification spam |

**Existing infrastructure to build on:**
- notifier.py -- basic Apprise integration (extend, do not replace)
- config.py -- Settings class with all API key fields (view layer for KEYS-01/02)
- get_safe_config() -- already masks secrets (reuse for export)
- routes/config.py -- existing export/import endpoints (extend for ZIP)
- events/catalog.py -- EVENT_CATALOG with payload_keys (use for template variables)
- routes/tools.py -- existing subtitle file operations (reuse validation patterns)

## Bazarr Migration Research

### Config Format (MEDIUM confidence)
- Bazarr >= 1.4: config.yaml (YAML format via Dynaconf)
- Bazarr < 1.4: config.ini (INI format via ConfigParser)
- Database: SQLite at db/bazarr.db

### Key Tables to Migrate From
- table_settings_general -- General settings
- table_settings_sonarr -- Sonarr connection (ip, port, base_url, ssl, apikey)
- table_settings_radarr -- Radarr connection
- table_blacklist -- Blacklisted subtitles (timestamp, provider, subtitle_id)
- table_languages_profiles -- Language profile definitions

### Migration Strategy
1. Accept Bazarr config directory path
2. Detect config format (YAML vs INI)
3. Parse config and extract mappable settings
4. Read bazarr.db for language profiles and blacklist
5. Present preview of what will be imported
6. User confirms, then write to Sublarr config_entries + DB tables

## Notification Architecture Details

### Current State
- notifier.py: Singleton Apprise instance, event type toggles (download, upgrade, batch_complete, error)
- send_notification(title, body, event_type): Simple title+body, no templating
- Frontend: Simple toggle switches in Notifications tab

### Target State
- Template storage in DB with Jinja2 syntax
- Per-event-type template assignment
- Per-service template assignment (different template for Discord vs Pushover)
- Variable catalog derived from EVENT_CATALOG payload_keys
- Live preview with sample data
- Quiet hours with day-of-week and exception event support
- Notification history with re-send capability

### Template Variable Sources
From events/catalog.py, each event type has defined payload_keys:
- subtitle_downloaded: provider_name, language, format, score, series_title, season, episode, movie_title
- translation_complete: job_id, source_language, target_language, backend_name, duration_ms, series_title, movie_title
- translation_failed: job_id, source_language, target_language, backend_name, error, series_title, movie_title
- batch_complete: total, succeeded, failed, skipped, duration_ms
- upgrade_complete: title, old_format, new_format, old_score, new_score, provider_name
- All other events from catalog

### Rendering Flow
```
Event fires -> Check quiet hours -> Find matching template -> Render Jinja2 -> Send via Apprise -> Log to history
```

## Deduplication Architecture Details

### Scan Process
1. Walk media_path recursively, find all .srt, .ass, .ssa files
2. For each file: compute SHA-256 of normalized content, extract metadata
3. Store in subtitle_hashes table
4. Group by content_hash -- groups with 2+ entries are duplicates
5. Present groups in UI with file paths, sizes, dates

### Metadata Comparison (beyond exact hash match)
- **Exact duplicates:** Identical content hash
- **Near duplicates:** Same media file basename, same language, different content
- **Orphaned subtitles:** Subtitle files where the parent media file no longer exists

### Disk Space Analysis
- Sum file sizes by format (ASS vs SRT)
- Identify space that would be freed by removing duplicates
- Track trends over time (from cleanup_history table)

## Open Questions

1. **Bazarr database schema version detection**
   - What we know: Bazarr has migrated schemas over versions, tables may vary
   - What is unclear: Exact schema version detection mechanism
   - Recommendation: Try to read known tables with try/except, report missing tables as warnings

2. **Notification template inheritance**
   - What we know: NOTF-02 wants per-service and per-event assignment
   - What is unclear: Should there be a default template that specific assignments override?
   - Recommendation: Implement a fallback chain: specific (service+event) -> event-only -> default

3. **Cleanup scheduling interval**
   - What we know: DEDU-04 wants configurable scheduled cleanup
   - What is unclear: What default interval makes sense
   - Recommendation: Default to weekly, configurable from 1 day to 30 days

## Sources

### Primary (HIGH confidence)
- Codebase analysis: backend/notifier.py, backend/config.py, backend/auth.py, backend/events/catalog.py
- Codebase analysis: backend/db/models/core.py, backend/db/repositories/base.py, backend/routes/config.py
- Codebase analysis: frontend/src/pages/Settings/index.tsx, frontend/src/api/client.ts
- Apprise PyPI: https://pypi.org/project/apprise/ (v1.9.2, already in requirements.txt)
- Python hashlib documentation (stdlib, SHA-256)
- Jinja2 documentation (bundled with Flask 3.1.0)

### Secondary (MEDIUM confidence)
- Bazarr Wiki Settings: https://wiki.bazarr.media/Additional-Configuration/Settings/
- Bazarr GitHub config.py: https://github.com/morpheus65535/bazarr/blob/master/bazarr/app/config.py
- Bazarr PostgreSQL migration docs: https://wiki.bazarr.media/Additional-Configuration/PostgreSQL-Database/
- DietPi Bazarr config.yaml issue: https://github.com/MichaIng/DietPi/issues/7185

### Tertiary (LOW confidence)
- Bazarr internal DB schema (inferred from migration issues and PR #126, not directly verified)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in project, no new dependencies needed
- Architecture: HIGH - Clear extension of established patterns (models, repos, blueprints, React tabs)
- API Key Management: HIGH - Straightforward view layer over existing config system
- Notification Templates: HIGH - Jinja2 is well-understood, Apprise already integrated
- Quiet Hours: HIGH - Simple time comparison logic, well-defined requirements
- Bazarr Migration: MEDIUM - Config format confirmed but DB schema details from indirect sources
- Deduplication: HIGH - Standard SHA-256 hashing, straightforward filesystem scanning
- Pitfalls: HIGH - Based on direct codebase analysis of existing invalidation patterns

**Research date:** 2026-02-19
**Valid until:** 2026-03-19 (stable domain, no fast-moving dependencies)
