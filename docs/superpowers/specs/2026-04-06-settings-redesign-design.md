# Settings UI Redesign — Implementation Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Completely restructure the Settings UI — consolidate duplicates, add contextual hints, introduce collapsible advanced sections, replace text fields with selects where possible, and reorganize settings into a logical information architecture.

**Branch:** `feature/settings-redesign`

---

## Design Decisions

### Navigation Pattern
- Persistent sidebar always visible (groups + pages)
- `/settings` landing page shows tile overview grid (like now) AND sidebar
- Clicking a tile OR a sidebar item navigates to the detail page
- The tile overview and sidebar co-exist: tiles give visual overview, sidebar gives direct access

### Field Treatment
- **Normal fields**: inline hint (small gray text, always visible, below label)
- **Advanced fields**: amber `Erweitert` badge + ⓘ tooltip icon (no inline hint to save space)
- **Advanced sections**: collapsed by default per section — "X erweiterte Einstellungen" toggle button
- **Input types**: Select/dropdown everywhere the value set is known; free text only for URLs, commands, custom names, numeric overrides
- **Language selection**: Primary language = single select dropdown; Additional languages = pill system with dropdown to add

### Feature Gates
- **Übersetzung (Translation)**: entire group only visible in sidebar and tiles when translation is enabled — same Beta gate as today

### Removed from Settings
- **Adjust Timing** (alass/ffsubsync tool UI) — action, not setting; stays in episode action menu only
- **HI Removal** (tool UI) — action, not setting; stays in episode action menu only
- Path fields for bundled tools (Docker bundles them; path override → advanced field only if needed)

---

## Information Architecture

### 8 Navigation Groups, 33 Pages

#### 1. Allgemein
| Page | Settings |
|------|---------|
| App & Oberfläche | port, api_key, interface_language, items_per_page, default_library_view, default_library_sort, datetime_format, log_level |
| Datenbank & Pfade | media_path, db_path, database_url, db_pool_*, redis_url, redis_cache_enabled, redis_queue_enabled, cors_origins, plugins_dir, plugin_hot_reload |

#### 2. Verbindungen
| Page | Settings | Notes |
|------|---------|-------|
| Sonarr & Radarr | sonarr_url, sonarr_api_key, sonarr_instances_json, radarr_url, radarr_api_key, radarr_instances_json, path_mapping | Multi-instance editor stays |
| Mediathek-Quellen | standalone_enabled, standalone_scan_interval_hours, standalone_debounce_seconds, standalone_skip_extras, tmdb_api_key, tvdb_api_key, tvdb_pin, metadata_cache_ttl_days | |
| Media-Server | jellyfin_url, jellyfin_api_key, media_servers_json | Jellyfin/Plex/Kodi |
| Metadaten | anidb_enabled, anidb_cache_ttl_days, anidb_custom_field_name, anidb_fallback_to_mapping, scan_metadata_engine, scan_metadata_max_workers, ffmpeg_timeout | **Moved from System** |

#### 3. Untertitel
| Page | Settings | Notes |
|------|---------|-------|
| Sprachen & Profile | hi_preference, forced_preference, language_profiles (CRUD) | Primary language = select per profile, additional = pills. Note: source_language/target_language are translation config — stay in Übersetzung > Backends |
| Scoring | score_threshold_per_language, scoring weights, scoring presets, release_group_prefer, release_group_exclude, release_group_prefer_bonus | |
| Format & Benennung | subtitle_language_code_format, subtitle_suffix_separator, subtitle_hi_suffix, subtitle_forced_suffix, use_embedded_subs, wanted_auto_extract, wanted_skip_srt_on_no_ass | |
| Bereinigung | cleanup rules CRUD, auto_cleanup_after_extract, auto_cleanup_keep_languages, auto_cleanup_keep_formats, subtitle_trash_retention_days, dedup, orphaned files | **Consolidated — tab in SubtitlesSettings removed** |
| Stream-Verwaltung | remux_trash_dir, remux_backup_retention_days, remux_use_reflink, remux_arr_pause_enabled, auto_nfo_export | **Moved from System** |

#### 4. Provider
| Page | Settings | Notes |
|------|---------|-------|
| Provider-Liste | provider_priorities, providers_enabled, providers_hidden, provider_auto_prioritize, marketplace | Priority drag-reorder stays |
| Zugangsdaten | opensubtitles_*, addic7ed_*, turkcealtyazi_*, jimaku_api_key, subdl_api_key, subsdump_*, anti_captcha_* | **All credentials in one place** |
| Cache & Limits | provider_cache_ttl_minutes, provider_search_timeout, provider_dynamic_timeout_*, provider_rate_limit_enabled, circuit_breaker_*, provider_auto_disable_cooldown_minutes, max_concurrent_provider_searches, download_delay_between_providers_ms, max_subtitle_file_size_kb | |
| Transkription | whisper settings (backend, concurrent jobs, fallback score) | **Moved from Translation — Whisper is a provider** |

#### 5. Automatisierung
| Page | Settings | Notes |
|------|---------|-------|
| Suche & Scan | wanted_scan_interval_hours, wanted_scan_on_startup, wanted_anime_only, wanted_anime_movies_only, wanted_search_interval_hours, wanted_search_on_startup, wanted_search_max_items_per_run, wanted_max_search_attempts, wanted_adaptive_backoff_*, scan_ignore_patterns, scan_min_file_size_mb, scan_ignore_languages | |
| Upgrades | upgrade_enabled, upgrade_min_score_delta, upgrade_window_days, upgrade_prefer_ass, upgrade_scan_interval_hours | |
| Webhooks & Trigger | webhook_delay_minutes, webhook_auto_scan, webhook_auto_search, webhook_auto_translate, jellyfin_play_translate_enabled | Sonarr/Radarr event → action mapping |
| Post-Processing | auto_sync_after_download, auto_sync_engine (select), auto_process_common_fixes, auto_process_hi_removal, auto_process_credit_removal, auto_process_sync_threshold, auto_process_sync_fallback_engine, post_processing_enabled, post_download_command | **No path fields for tools. Adjust Timing + HI Removal tool UIs removed from settings — they live in episode actions only.** |

#### 6. Übersetzung *(only visible when translation is enabled — Beta gate)*
| Page | Settings |
|------|---------|
| Backends | source_language, target_language (translation source/target — different from subtitle search language), ollama_url, ollama_model, batch_size, request_timeout, temperature, max_retries, backoff_base, translation_max_workers |
| Prompt-Presets | prompt_template, presets CRUD |
| Glossar | glossary_enabled, glossary_max_terms, translation_series_glossary_auto, global glossary CRUD |
| Qualität & Kontext | translation quality thresholds, translation_use_episode_context, translation_context_episodes |

#### 7. Benachrichtigungen
| Page | Settings |
|------|---------|
| Kanäle & Events | notification_urls_json, notify_on_download, notify_on_upgrade, notify_on_batch_complete, notify_on_error, notify_manual_actions |
| Stille Stunden | quiet_hours_enabled, quiet_hours_start, quiet_hours_end, quiet_hours_timezone |
| Vorlagen & Verlauf | notification templates CRUD, notification history |

#### 8. System
| Page | Settings | Notes |
|------|---------|-------|
| Sicherheit | session_timeout_minutes, max_login_attempts, lockout_duration_minutes, allowed_ip_ranges, UI auth toggle, password change | |
| Backup | backup_dir, backup_retention_*, backup_auto_enabled, backup_auto_interval_hours, backup_auto_on_startup, backup_notify_on_failure, manual backup/restore | |
| Protokoll | log viewer, log_file, log_format, log rotation, support bundle export | |
| Hooks & Webhooks | shell hooks CRUD, outgoing webhooks CRUD, event catalog, execution log | **Consolidated from HooksPage + WebhooksPage** |
| Integrationen | Bazarr migration wizard, config export, player compat check, health diagnostics | |

---

## Consolidations & Removals

| What | From | To | Action |
|------|------|----|--------|
| AniDB settings | System | Verbindungen > Metadaten | Move |
| Remux settings | System | Untertitel > Stream-Verwaltung | Move |
| Whisper settings | Übersetzung | Provider > Transkription | Move |
| Cleanup tab | SubtitlesSettings (tab) | — | Remove (Bereinigung standalone page stays) |
| HooksPage + WebhooksPage | Two separate routes | System > Hooks & Webhooks | Consolidate |
| All provider credentials | Scattered across pages | Provider > Zugangsdaten | Consolidate |
| Post-Processing section | AutomationSettings (section 4) | Automatisierung > Post-Processing (own page) | Extract |
| Adjust Timing tool UI | Settings | Episode action menu only | Remove from settings |
| HI Removal tool UI | Settings | Episode action menu only | Remove from settings |
| LegacySettings.tsx | Active in codebase | — | Delete (dead code) |

---

## Field Input Type Rules

| Field Type | Input |
|-----------|-------|
| Language selection (primary) | `<select>` with all supported languages |
| Language selection (additional) | Pill system + `<select>` to add |
| Engine/backend selection (alass/ffsubsync/auto, scan engine, etc.) | `<select>` |
| Preference (HI, Forced, sort order, view mode) | `<select>` |
| Enable/disable boolean | Toggle switch |
| Numeric threshold/interval | `<input type="number">` with unit label |
| URL field | `<input type="url">` with validate button |
| API key / credential | `<input type="password">` with show/test button |
| Command / shell script | `<input type="text">` or `<textarea>` |
| Free name / custom label | `<input type="text">` |
| Path override (advanced only) | `<input type="text">` under Erweitert collapse |

---

## Advanced Field Classification (Examples)

Fields that should be **Erweitert** (collapsed by default):

**Suche & Scan:**
- wanted_anime_only, wanted_anime_movies_only
- wanted_adaptive_backoff_base, wanted_adaptive_backoff_cap
- wanted_search_max_items_per_run
- scan_ignore_patterns, scan_min_file_size_mb, scan_ignore_languages

**Provider > Cache & Limits:**
- provider_dynamic_timeout_*, circuit_breaker_*, provider_auto_disable_cooldown_minutes
- download_delay_between_providers_ms, max_subtitle_file_size_kb, gestdown_retry_delay_s

**Subtitles > Format & Benennung:**
- subtitle_language_code_format, subtitle_suffix_separator, subtitle_hi_suffix, subtitle_forced_suffix
- scan_yield_ms

**Post-Processing:**
- auto_process_sync_threshold, auto_process_sync_fallback_engine

**Allgemein > Datenbank & Pfade:**
- db_pool_*, cors_origins, plugins_dir, plugin_hot_reload, redis_*

**Verbindungen > Mediathek-Quellen:**
- standalone_debounce_seconds, standalone_skip_extras, metadata_cache_ttl_days

---

## Component Patterns

### SettingsSection
```
<SettingsSection title="Bibliotheks-Scan">
  {/* normal fields */}
  <AdvancedCollapse count={2}>
    {/* advanced fields */}
  </AdvancedCollapse>
</SettingsSection>
```

### FormGroup (normal field)
```
<FormGroup label="Scan-Intervall" hint="Wie oft die Bibliothek automatisch gescannt wird. 0 = deaktiviert.">
  <input type="number" /> <span>Stunden</span>
</FormGroup>
```

### FormGroup (advanced field)
```
<FormGroup label="Adaptiver Backoff — Basis" advanced hint="Wartezeit-Multiplikator nach Fehlschlägen.">
  {/* hint shown as tooltip ⓘ, not inline */}
  <input type="number" />
</FormGroup>
```

### AdvancedCollapse
- Renders a `▶ X erweiterte Einstellungen` button at the bottom of a section
- Click toggles collapsed state, persisted in localStorage per section key
- Content styled with `background: var(--bg-primary)` to visually separate from section body

---

## Routing Changes

### New routes:
```
/settings/connections/metadata        (new — AniDB + scan engine)
/settings/subtitles/stream-management (new — Remux, was /settings/system)
/settings/providers/transcription     (new — Whisper, was in Translation)
/settings/automation/post-processing  (new — extracted from AutomationSettings)
/settings/system/hooks                (consolidated — was /settings/hooks + /settings/webhooks)
```

### Removed routes:
```
/settings/hooks        → merged into /settings/system/hooks
/settings/webhooks     → merged into /settings/system/hooks
/settings/cleanup      → stays as /settings/subtitles/cleanup (moved into Untertitel group)
```

### Unchanged routes (content moves, URL stays):
```
/settings/general       → Allgemein > App & Oberfläche
/settings/connections   → first page of Verbindungen group
/settings/subtitles     → first page of Untertitel group
/settings/providers     → first page of Provider group
/settings/automation    → Automatisierung > Suche & Scan
/settings/translation   → Übersetzung > Backends (feature-gated)
/settings/notifications → Benachrichtigungen > Kanäle & Events
/settings/system        → System > Sicherheit
/settings/about         → stays
```

---

## Files to Create / Modify

### New page files (frontend/src/pages/settings/):
- `ConnectionsMetadataPage.tsx` — AniDB + scan engine (split from SystemSettings)
- `SubtitlesStreamManagementPage.tsx` — Remux (split from SystemSettings)
- `ProvidersTranscriptionPage.tsx` — Whisper (split from TranslationSettings)
- `AutomationPostProcessingPage.tsx` — Post-processing pipeline (split from AutomationSettings)
- `SystemHooksPage.tsx` — Consolidated HooksPage + WebhooksPage

### Modified page files:
- `index.tsx` — updated route definitions
- `GeneralSettings.tsx` — split into App & Oberfläche + Datenbank & Pfade tabs
- `ConnectionsSettings.tsx` — add Metadaten page, remove AniDB
- `SubtitlesSettings.tsx` — remove Cleanup tab, add Stream-Verwaltung page
- `ProvidersSettings.tsx` — consolidate all credentials into Zugangsdaten tab, add Transkription
- `AutomationSettings.tsx` — remove Post-Processing section (becomes own page), remove Cleanup advanced section
- `TranslationSettings.tsx` — remove Whisper tab
- `SystemSettings.tsx` — remove AniDB, Remux, Hooks/Webhooks, add links to new locations
- `SettingsOverview.tsx` — update tile grid to match new 8 groups + show translation tile conditionally
- `LegacySettings.tsx` — **DELETE**

### New shared components (frontend/src/components/settings/):
- `AdvancedCollapse.tsx` — collapsible section for advanced fields, persists state in localStorage
- `FormGroup` (modify existing) — add `advanced?: boolean` prop: when true, render hint as tooltip ⓘ instead of inline

### i18n:
- `frontend/src/i18n/locales/en/settings.json` — add hint text for every field
- `frontend/src/i18n/locales/de/settings.json` — German hint text for every field

---

## Out of Scope
- Backend config.py changes — all fields already exist
- New settings/features — this is purely restructuring + UX improvement
- Mobile/responsive layout changes
- Settings search functionality — already exists, update index only
