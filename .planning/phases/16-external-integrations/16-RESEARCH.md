# Phase 16: External Integrations - Research

**Researched:** 2026-02-20
**Domain:** External tool migration, media-player compatibility, extended service health checks, export formats
**Confidence:** HIGH

## Summary

Phase 16 extends Sublarr integration ecosystem in four directions: (1) deepening the existing Bazarr migration from config-only import to full database reading with a detailed mapping report, (2) validating subtitle file naming/placement against Plex conventions, (3) enriching Sonarr/Radarr/Jellyfin/Emby health checks with API version, library access, and webhook status diagnostics, and (4) exporting Sublarr config and subtitle data in formats compatible with Bazarr, Plex, Kodi, and a generic JSON format.

The existing codebase already provides substantial infrastructure: bazarr_migrator.py handles config parsing and DB reading (profiles, blacklist, Sonarr/Radarr settings); sonarr_client.py, radarr_client.py, and jellyfin_client.py have basic health_check() methods; the mediaserver/ package has Plex, Kodi, and Jellyfin backends with health_check() and refresh_item(). The work is primarily about extending these existing modules with richer diagnostics, adding a compatibility checker for file naming, and building export serializers.

**Primary recommendation:** Extend existing client classes with extended diagnostic methods (extended_health_check()) rather than creating new modules, add a compat_checker.py for Plex/Kodi naming validation, and create an export_manager.py for multi-format export.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | 3.x | API endpoints for all integration routes | Already in stack, Blueprint pattern |
| SQLite3 (stdlib) | 3.x | Read Bazarr database (read-only mode) | Already used in bazarr_migrator.py |
| requests | 2.31+ | HTTP calls to Sonarr/Radarr/Jellyfin APIs | Already in stack for all client modules |
| plexapi | 4.15+ | Plex API calls for health check extension | Already optional dependency in mediaserver/plex.py |
| pysubs2 | 1.7+ | Parse subtitle files for export/validation | Already in stack for health_checker.py |
| PyYAML | 6.0+ | Parse Bazarr YAML config files | Already optional in bazarr_migrator.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | - | Generic JSON export format | All export operations |
| os.path (stdlib) | - | File path validation for Plex/Kodi conventions | Compat checker |
| re (stdlib) | - | Pattern matching for subtitle filename validation | Compat checker |
| zipfile (stdlib) | - | ZIP export packaging | Full export bundles |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Bazarr DB reader | ORM-based reader | Overkill; Bazarr DB is read-only, simple queries suffice |
| Custom file validator | jsonschema | Schema validation is for JSON, not file naming patterns |
| plexapi for Plex checks | Raw HTTP requests | plexapi already in stack, provides typed access to libraries |

**Installation:**
No new dependencies needed. All required libraries are already in the stack.

## Architecture Patterns

### Recommended Project Structure
```
backend/
  bazarr_migrator.py         # EXTEND: add DB-reader mapping report, deeper table extraction
  compat_checker.py          # NEW: Plex/Kodi subtitle naming/placement validator
  export_manager.py          # NEW: multi-format export (Bazarr, Plex, Kodi, JSON)
  sonarr_client.py           # EXTEND: extended_health_check() method
  radarr_client.py           # EXTEND: extended_health_check() method
  jellyfin_client.py         # EXTEND: extended_health_check() method
  mediaserver/plex.py        # EXTEND: extended_health_check() method
  mediaserver/kodi.py        # EXTEND: extended_health_check() method
  routes/
    integrations.py          # NEW: Blueprint for all Phase 16 endpoints
frontend/
  src/
    pages/Settings/
      IntegrationsTab.tsx     # NEW: Migration, compat check, export UI
```

### Pattern 1: Extended Health Check Protocol
**What:** Each external service client gets an extended_health_check() method that returns a structured diagnostic report beyond basic reachability.
**When to use:** INTG-03, INTG-04 requirements.
**Example:**
```python
def extended_health_check(self) -> dict:
    result = {
        "connection": {"healthy": False, "message": ""},
        "api_version": {"version": "", "branch": "", "app_name": ""},
        "library_access": {"series_count": 0, "accessible": False},
        "webhook_status": {"configured": False, "sublarr_webhooks": []},
        "health_issues": [],
    }
    # 1. Connection + version via /system/status
    status = self._get("/system/status")
    if status is None:
        result["connection"]["message"] = f"Cannot connect at {self.url}"
        return result
    result["connection"] = {"healthy": True, "message": "OK"}
    result["api_version"] = {
        "version": status.get("version", ""),
        "branch": status.get("branch", ""),
        "app_name": status.get("appName", ""),
    }
    # 2. Library access via /series or /movie
    # 3. Webhook status via /notification
    # 4. Health issues via /health
    return result
```

### Pattern 2: Migration Preview-then-Apply
**What:** Two-step migration: first generate a detailed mapping report (preview), then apply only after user confirmation.
**When to use:** INTG-01 (Bazarr migration extension).

### Pattern 3: Compatibility Checker as Pure Function Module
**What:** A stateless module with pure functions that validate subtitle file paths against media player conventions.
**When to use:** INTG-02 (Plex compatibility check).

### Pattern 4: Export Manager with Format Strategies
**What:** An export manager using strategy pattern for different output formats (Bazarr, Plex, Kodi, Generic JSON).
**When to use:** INTG-05 (export formats).

### Anti-Patterns to Avoid
- **Mutating Bazarr DB during read:** MUST be opened read-only (file:path?mode=ro).
- **Hardcoding language code mappings:** Use existing _LANGUAGE_TAGS from config.py.
- **Putting all logic in routes:** Keep business logic in dedicated modules.
- **Breaking existing health_check() signatures:** Add extended_health_check() as NEW method.

## Do Not Hand-Roll

| Problem | Do Not Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ISO 639 language code validation | Custom regex | _LANGUAGE_TAGS from config.py | Already exists |
| Plex API interaction | Raw HTTP | plexapi library | Already in stack |
| Bazarr YAML parsing | Custom parser | PyYAML yaml.safe_load() | Already used |
| SQLite read-only access | Custom wrapper | sqlite3.connect(file:path?mode=ro, uri=True) | Already pattern |
| ZIP archive creation | Custom binary | zipfile stdlib | Already used |
| Subtitle file parsing | Custom parsers | pysubs2 library | Already in stack |

**Key insight:** This phase extends existing infrastructure. Every external service already has a client class with basic health checking. The Bazarr migrator already reads databases and configs. New work is depth (richer diagnostics, more tables) and breadth (export formats, compat checking).

## Common Pitfalls

### Pitfall 1: Bazarr Database Schema Versioning
**What goes wrong:** Bazarr has evolved its schema. Older databases may lack tables or have different column names.
**Why it happens:** Bazarr uses Alembic migrations, tables/columns vary by version.
**How to avoid:** Check table existence before querying. Use SELECT name FROM sqlite_master WHERE type=table. Follow existing pattern that catches OperationalError.
**Warning signs:** Migration fails silently or returns empty data.

### Pitfall 2: Plex Subtitle Format Case Sensitivity
**What goes wrong:** Plex is case-sensitive on Linux for language codes. .EN.srt may not work.
**Why it happens:** Plex scanner is case-sensitive on Linux, case-insensitive on macOS/Windows.
**How to avoid:** Warn about uppercase language codes, recommend lowercase.
**Warning signs:** Subtitles work on macOS but not Docker Linux.

### Pitfall 3: Sonarr/Radarr API Version Differences
**What goes wrong:** /api/v3/notification may differ between versions. Sonarr v4 changes some endpoints.
**Why it happens:** Rapid *arr ecosystem evolution.
**How to avoid:** Wrap each sub-query in try/except. Mark webhook_status as unknown on failure.
**Warning signs:** Extended health check crashes on older instances.

### Pitfall 4: Jellyfin vs Emby API Divergence
**What goes wrong:** /System/Info exists on both but returns different fields.
**Why it happens:** Independent development since fork.
**How to avoid:** Handle missing fields with .get() defaults.
**Warning signs:** Health check works on Jellyfin but fails on Emby.

### Pitfall 5: Export Format Lock-In
**What goes wrong:** Bazarr export may not match current Bazarr config format exactly.
**Why it happens:** Bazarr config is an internal implementation detail, not a public API.
**How to avoid:** Label as Bazarr-compatible. Recommend generic JSON as primary portable format.
**Warning signs:** Import into Bazarr and settings do not apply.

### Pitfall 6: Path Mapping in Compat Checker
**What goes wrong:** Compat checker validates Docker-internal paths, but Plex sees different paths.
**Why it happens:** Docker volume mappings.
**How to avoid:** Validate naming conventions and relative positioning, NOT absolute paths.
**Warning signs:** Compat checker says valid but Plex does not see subtitle.

## Code Examples

### Plex Subtitle Naming Convention
```
Source: https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/
Movie: Movie_Name (Year).[lang_code].ext
TV: Show_Name SxxEyy.[lang_code].ext
Forced: filename.[lang_code].forced.ext
SDH: filename.[lang_code].sdh.ext (server v1.20.3.3401+)
Language codes: ISO 639-1 (en, de, fr) or ISO 639-2/B (eng, deu, fra)
Placement: same directory as video, or in Subtitles/Subs subfolder (v1.41.0+)
Supported formats: srt, smi, ssa, ass, vtt (full compatibility)
```

### Kodi Subtitle Naming Convention
```
Source: https://kodi.wiki/view/Subtitles
Pattern: <movie_name>.<language>.<ext>
Language: ISO 639-1, ISO 639-2, BCP 47 (- replaced by _), or English name
BCP 47 support: Kodi 22+
Placement: same directory as video file
```

### Sonarr/Radarr System Status Response Fields
```
/api/v3/system/status returns:
  appName, instanceName, version, buildTime, isDebug, isProduction,
  isAdmin, osName, osVersion, isDocker, mode, branch, authentication,
  sqliteVersion, migrationVersion, urlBase, runtimeVersion, startTime

/api/v3/health returns: list of {type, message, wikiUrl}
/api/v3/notification returns: list with name, implementation, enable, fields[]
```

### Jellyfin System Info Response Fields
```
/System/Info/Public returns:
  ServerName, Version, ProductName, OperatingSystem, Id,
  StartupWizardCompleted, LocalAddress

/System/Info (authenticated) adds:
  OperatingSystemDisplayName, HasPendingRestart, IsShuttingDown,
  SupportsLibraryMonitor, HasUpdateAvailable, SystemArchitecture
```

### Existing Bazarr Migrator Patterns (already implemented)
```
parse_bazarr_config(file_content, filename) -> normalized dict
migrate_bazarr_db(db_path) -> profiles, blacklist, sonarr/radarr config
preview_migration(config_data, db_data) -> human-readable preview
apply_migration(config_data, db_data) -> import counts + warnings
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bazarr config-only import | Bazarr DB + config with mapping report | Phase 16 | Full preview before committing |
| Basic health_check() | Extended diagnostics | Phase 16 | Richer troubleshooting |
| No Plex naming validation | Automated compat check | Phase 16 | Catches naming issues early |
| No export capability | Multi-format export | Phase 16 | Migration TO other tools |
| Plex subs in video folder only | Subtitles/Subs subfolder | Plex v1.41.0 | Check both locations |
| Kodi ISO 639-1/2 only | BCP 47 tag support | Kodi 22 | Accept BCP 47 |

## Open Questions

1. **Bazarr table_history depth** -- Column names vary by version. Use PRAGMA table_info() at runtime.
2. **Sonarr v3 vs v4 notification endpoint** -- Degrade gracefully if endpoint fails.
3. **Bazarr export format fidelity** -- Label as compatible, recommend generic JSON as primary.
4. **Emby-specific API paths** -- Use well-established endpoints only, degrade gracefully.

## Sources

### Primary (HIGH confidence)
- Existing codebase: bazarr_migrator.py, sonarr_client.py, radarr_client.py, jellyfin_client.py
- Existing codebase: mediaserver/plex.py, mediaserver/kodi.py, routes/system.py, routes/mediaservers.py
- Plex Subtitle Docs: https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/

### Secondary (MEDIUM confidence)
- Sonarr API: https://sonarr.tv/docs/api/
- Radarr API: https://radarr.video/docs/api/
- Bazarr GitHub: https://github.com/morpheus65535/bazarr
- Jellyfin API: https://jmshrv.com/posts/jellyfin-api/
- Kodi Subtitles: https://kodi.wiki/view/Subtitles

### Tertiary (LOW confidence)
- Bazarr DB schema from GitHub issues. Verify with PRAGMA table_info() on actual DB.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in codebase
- Architecture: HIGH - Extending existing patterns
- Pitfalls: HIGH - Based on code review and official docs
- Bazarr DB schema: MEDIUM - From GitHub issues, use dynamic column discovery
- Sonarr/Radarr extended API: MEDIUM - Basic endpoints verified, notification endpoint needs runtime verification

**Research date:** 2026-02-20
**Valid until:** 2026-04-20 (60 days)
