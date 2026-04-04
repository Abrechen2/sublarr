# Cleanup Rules Page — Design Spec

**Date:** 2026-04-04  
**Status:** Approved  
**Scope:** Dedicated Cleanup Rules settings page replacing the existing CleanupTab

---

## 1. Overview

Replace the existing `CleanupTab` (Settings → Cleanup tab) with a dedicated first-class Settings page — accessible as its own tile in the Settings grid alongside General, About, etc.

The page provides a full cleanup workflow UI: rule list sidebar + detail view, replacing the current scattered approach (comma-separated text fields in config, non-functional rule CRUD, separate scan buttons).

**Out of scope:** NFO files (`.nfo`) are system-wide excluded from all cleanup operations — this is hardcoded, not configurable.

---

## 2. Navigation & Layout

### Settings Grid

Add a `Cleanup` tile to the Settings overview grid. Clicking navigates to `/settings/cleanup`.

### Page Layout

```
┌─────────────────────────────────────────────────────┐
│  Topbar: Settings / Cleanup                         │
├──────────────┬──────────────────────────────────────┤
│              │  [DiskSpace Widget]                  │
│  Sidebar     │                                      │
│  ─────────   │  [Rule Detail View]                  │
│  Rule list   │    - Header (name, icon, actions)    │
│  + New Rule  │    - Last run bar                    │
│              │    - Config sections                  │
│              │    - Preview box                     │
│              ├──────────────────────────────────────┤
│              │  [History] (collapsible)             │
└──────────────┴──────────────────────────────────────┘
```

**Sidebar (260px fixed):**
- Section label "Regeln" + "+ Neu" button
- Each rule shown as a card: type icon, name, enabled dot, type badge, schedule badge
- Active rule highlighted with accent border

**Main area:**
- DiskSpace widget at top (moved from old CleanupTab)
- Rule detail view when a rule is selected
- Deduplication section (interactive hash-based scan — kept separate, not a rule type)
- History table (collapsible, paginated, at bottom)

---

## 3. Rule Types

Four rule types, selectable when creating a new rule:

| Type | Key | Description | Config fields |
|------|-----|-------------|---------------|
| Sprach-Filter | `language_filter` | Deletes sidecar files in non-allowed languages | `keep_languages: string[]` |
| Format-Upgrade | `format_upgrade` | Deletes SRT when ASS exists for the same episode | `keep_format: "ass" \| "srt" \| "any"` |
| Verwaiste Dateien | `orphan_files` | Deletes subtitle sidecars with no matching video on disk | _(no extra config)_ |
| DB-Bereinigung | `orphan_db` | Removes DB subtitle entries whose file no longer exists on disk | _(no extra config)_ |

Every rule additionally has:
- `name: string` — user-defined label
- `enabled: boolean` — toggle on/off
- `schedule: "manual" | "daily" | "weekly" | "after_scan"` — when the rule runs automatically

---

## 4. Rule Detail UI

### Header
- Type icon (32×32 rounded, type-colored background) + rule name + description
- Action buttons: **Vorschau** (ghost), **Jetzt ausführen** (accent), **Löschen** (danger)
- Inline name editing (click to edit)

### Last Run Bar
- Green dot + "Letzter Lauf erfolgreich" + stats (files deleted, MB freed) + timestamp
- Red dot + error message if last run failed
- Hidden if rule has never run

### Config Sections (per rule type)

**Language Filter — "Erlaubte Sprachen"**
- Tag-style picker: each language shown as a removable pill with flag emoji + ISO code
- "+ Sprache hinzufügen" opens a searchable dropdown of languages
- Hint text: "NFO-Dateien (.nfo) werden nie angefasst."

**Format Upgrade — "Format-Präferenz"**
- Three clickable cards: "Beide behalten" / "ASS bevorzugen" / "SRT bevorzugen"
- Selected card gets accent border + accent text

**Schedule — "Zeitplan" (all rule types)**
- Chip selector: Manuell / Täglich 03:00 / Wöchentlich / Nach jedem Scan
- Selected chip gets accent styling

### Preview Box
- Triggered by "Vorschau" button, result cached until next click
- Shows: total sidecar files found, files that would be deleted, MB to free, NFO files excluded (always 0 deleted)
- Displayed inline below config sections

---

## 5. Deduplication Section

Kept as a standalone section (not a rule type) because it requires interactive group selection — the user must choose which duplicate to keep per group.

- "Scan starten" button + progress bar
- `DedupGroupList` component (unchanged from current implementation)
- `CleanupPreview` modal before confirming deletion

---

## 6. Backend Changes

### DB Model: `cleanup_rules`

Extend existing model — add `schedule` column, make `config_json` structured:

```python
# New columns
schedule: str = "manual"  # "manual" | "daily" | "weekly" | "after_scan"

# config_json structure per type
# language_filter:  {"keep_languages": ["de", "en"]}
# format_upgrade:   {"keep_format": "ass"}
# orphan_files:     {}
# orphan_db:        {}
```

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/cleanup/rules` | List all rules (extend existing) |
| `POST` | `/api/v1/cleanup/rules` | Create rule (extend existing) |
| `PATCH` | `/api/v1/cleanup/rules/{id}` | Update rule config/schedule/enabled |
| `DELETE` | `/api/v1/cleanup/rules/{id}` | Delete rule (existing) |
| `POST` | `/api/v1/cleanup/rules/{id}/preview` | Dry-run: returns files that would be deleted |
| `POST` | `/api/v1/cleanup/rules/{id}/run` | Execute rule immediately (existing, extend) |

### Scheduler Integration

`cleanup_scheduler.py` checks `schedule` field on all enabled rules and runs them at the configured interval. After-scan trigger hooks into the existing post-scan event.

### Config.py

`auto_cleanup_keep_languages` and `auto_cleanup_keep_formats` remain in `config.py` as fallback defaults for the batch-extract flow (`auto_cleanup_after_extract`). They are no longer exposed in the UI — the Rules page writes directly to `config_json` in the DB.

---

## 7. Migration

- Existing cleanup rules in DB: `schedule` defaults to `"manual"`, `config_json` defaults to `{}`
- The old CleanupTab component is removed; its hooks/API calls are reused in the new page
- Alembic migration adds `schedule` column to `cleanup_rules` table

---

## 8. What Is Never Touched

- `.nfo` files — hardcoded exclusion in all cleanup executors
- Video files (`.mkv`, `.mp4`, `.avi`, etc.)
- Any file not matching known subtitle extensions (`.ass`, `.ssa`, `.srt`, `.vtt`, `.sub`)
