# Phase 8: i18n + Backup + Admin Polish - Research

**Researched:** 2026-02-15
**Domain:** Internationalization, Backup/Restore, Admin UX (Charts, Theming, Logs, Subtitle Tools)
**Confidence:** HIGH

## Summary

Phase 8 covers four distinct but complementary areas: (1) i18n via react-i18next for English/German UI, (2) full backup/restore as ZIP (config + DB) with upload/download in the Settings UI, (3) a statistics page with charts and time-range filtering, and (4) admin polish including dark/light theme toggle, log improvements, and subtitle processing tools.

The existing codebase provides strong foundations for all four areas. The backend already has `database_backup.py` with create/list/restore/rotate functionality and API endpoints in `routes/system.py`. Config export/import is already implemented in `routes/config.py`. The frontend already uses CSS custom properties (`--bg-primary`, `--accent`, etc.) throughout, making theme switching a matter of swapping variable values. The `daily_stats` table and `provider_stats` table already store the data needed for charts. The Logs page already has level filtering and search -- it needs download, rotation config, and polish.

**Primary recommendation:** Use react-i18next with static JSON imports (no HTTP backend needed for 2 languages), Recharts for statistics charts, CSS custom properties with Tailwind v4 `@custom-variant` for dark/light theming, and extend the existing backup infrastructure to produce ZIP archives containing both DB and config JSON.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| i18next | ^25.x | Core i18n framework | De facto standard, 30M+ weekly downloads |
| react-i18next | ^16.x | React bindings for i18next | Official React integration, hook-based API |
| i18next-browser-languageDetector | ^8.x | Auto-detect user language | Persists to localStorage, detects browser lang |
| recharts | ^3.7 | Charting (LineChart, AreaChart, BarChart, PieChart) | Most-used React chart library, SVG-based, declarative |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none needed) | - | i18next-http-backend | NOT needed -- only 2 languages, use static JSON imports |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| recharts | @nivo/line | Nivo is prettier but heavier; Recharts is simpler for dashboards with < 100 data points |
| recharts | chart.js + react-chartjs-2 | Canvas-based (better perf for huge datasets) but less React-idiomatic |
| react-i18next | FormatJS/react-intl | react-i18next is simpler, better for apps with few languages, more flexible |
| i18next-http-backend | Static JSON import | With only en/de, bundled JSON is simpler, no extra HTTP requests, instant load |

**Installation:**
```bash
cd frontend && npm install i18next react-i18next i18next-browser-languagedetector recharts
```

No new backend dependencies needed -- Python's `zipfile`, `io.BytesIO`, and `json` modules are all in the standard library.

## Architecture Patterns

### Frontend i18n File Structure
```
frontend/src/
  i18n/
    index.ts           # i18n init (import i18next, configure, export)
    locales/
      en/
        common.json    # Shared: nav, buttons, status labels
        dashboard.json # Dashboard-specific
        settings.json  # Settings-specific
        library.json   # Library, Wanted, SeriesDetail
        activity.json  # Activity, Queue, History, Blacklist
        logs.json      # Logs page
        statistics.json # Statistics page
        onboarding.json # Onboarding wizard
      de/
        common.json
        dashboard.json
        settings.json
        library.json
        activity.json
        logs.json
        statistics.json
        onboarding.json
```

### Theme System Structure
```
frontend/src/
  index.css            # Extend: add :root (light) + .dark {} variable sets
  hooks/
    useTheme.ts        # Theme toggle hook (localStorage + class toggle)
  components/
    shared/
      ThemeToggle.tsx   # Sun/Moon icon toggle component
```

### Backend Backup ZIP Structure
```
sublarr_backup_20260215_120000.zip
  manifest.json        # Version, timestamp, schema version, contents list
  config.json          # Safe config export (no raw secrets, masked)
  sublarr.db           # SQLite backup via backup API
```

### Statistics Page Structure
```
frontend/src/
  pages/
    Statistics.tsx      # New page with chart components
  components/
    charts/
      TranslationChart.tsx   # Daily translations over time (AreaChart)
      ProviderChart.tsx      # Provider usage breakdown (BarChart/PieChart)
      FormatChart.tsx        # ASS vs SRT distribution (PieChart)
      DownloadChart.tsx      # Downloads over time (LineChart)
```

### Pattern 1: i18n Initialization with Static Resources
**What:** Initialize i18next with bundled JSON, language detector, and React integration
**When to use:** Apps with small number of languages (2-5) where bundle size is negligible
**Example:**
```typescript
// Source: https://react.i18next.com/guides/quick-start
// frontend/src/i18n/index.ts
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Static imports -- no HTTP backend needed for 2 languages
import enCommon from './locales/en/common.json'
import enDashboard from './locales/en/dashboard.json'
import enSettings from './locales/en/settings.json'
import deCommon from './locales/de/common.json'
import deDashboard from './locales/de/dashboard.json'
import deSettings from './locales/de/settings.json'
// ... more namespaces

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: enCommon,
        dashboard: enDashboard,
        settings: enSettings,
      },
      de: {
        common: deCommon,
        dashboard: deDashboard,
        settings: deSettings,
      },
    },
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: ['common', 'dashboard', 'settings', 'library', 'activity', 'logs', 'statistics', 'onboarding'],
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'sublarr-language',
      caches: ['localStorage'],
    },
  })

export default i18n
```

### Pattern 2: useTranslation Hook in Components
**What:** Access translations via hook with specific namespace
**When to use:** Every component that has user-facing text
**Example:**
```typescript
// Source: https://react.i18next.com/latest/usetranslation-hook
import { useTranslation } from 'react-i18next'

function Dashboard() {
  const { t } = useTranslation('dashboard')
  // Uses 'dashboard' namespace, falls back to 'common' for shared keys
  return (
    <div>
      <h1>{t('title')}</h1>
      <StatCard label={t('stats.translated_today')} value={stats.today_translated} />
    </div>
  )
}
```

### Pattern 3: Language Switcher Component
**What:** Toggle between en/de with persistence
**When to use:** In sidebar footer or settings
**Example:**
```typescript
import { useTranslation } from 'react-i18next'

function LanguageSwitcher() {
  const { i18n } = useTranslation()

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'de' : 'en'
    i18n.changeLanguage(newLang)
    // Automatically persisted to localStorage by language detector
  }

  return (
    <button onClick={toggleLanguage}>
      {i18n.language === 'en' ? 'DE' : 'EN'}
    </button>
  )
}
```

### Pattern 4: Tailwind v4 Dark/Light Theme with CSS Variables
**What:** Toggle theme by swapping CSS custom property values via `.dark` class
**When to use:** Tailwind v4 apps with custom property-based design systems
**Example:**
```css
/* Source: https://tailwindcss.com/docs/dark-mode */
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));

:root {
  /* Light theme */
  --bg-primary: #f8fafc;
  --bg-surface: #ffffff;
  --bg-surface-hover: #f1f5f9;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --border: #e2e8f0;
  /* ... all existing variables with light values */
}

.dark {
  /* Dark theme (current values become dark-only) */
  --bg-primary: #171923;
  --bg-surface: #1e2130;
  --bg-surface-hover: #252838;
  --text-primary: #e2e5eb;
  --text-secondary: #7c8293;
  --border: #2a2e3b;
  /* ... existing values stay in .dark */
}
```

### Pattern 5: useTheme Hook
**What:** Manage theme state with localStorage persistence
**When to use:** App-wide theme management
**Example:**
```typescript
import { useState, useEffect } from 'react'

type Theme = 'dark' | 'light' | 'system'

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem('sublarr-theme') as Theme) || 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') {
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      root.classList.toggle('dark', isDark)
      localStorage.removeItem('sublarr-theme')
    } else {
      root.classList.toggle('dark', theme === 'dark')
      localStorage.setItem('sublarr-theme', theme)
    }
  }, [theme])

  return { theme, setTheme: setThemeState }
}
```

### Pattern 6: Recharts Statistics Chart
**What:** Time-series area chart with tooltips and responsive container
**When to use:** Displaying daily_stats data as charts
**Example:**
```typescript
// Source: https://recharts.org/en-US/api/AreaChart
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

function TranslationChart({ data }: { data: DailyStat[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={11} />
        <YAxis stroke="var(--text-muted)" fontSize={11} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}
        />
        <Area
          type="monotone"
          dataKey="translated"
          stroke="var(--accent)"
          fill="var(--accent-subtle)"
        />
        <Area
          type="monotone"
          dataKey="failed"
          stroke="var(--error)"
          fill="var(--error-bg)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
```

### Pattern 7: Backend ZIP Backup Endpoint
**What:** Create ZIP with config + DB and send as downloadable file
**When to use:** Full backup endpoint
**Example:**
```python
import io
import json
import zipfile
from flask import send_file
from database_backup import DatabaseBackup

@bp.route("/backup/full", methods=["POST"])
def create_full_backup():
    """Create ZIP backup with config + DB."""
    from config import get_settings
    s = get_settings()

    # Create DB backup first
    db_backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    backup_info = db_backup.create_backup(label="manual")

    # Build ZIP in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Manifest
        manifest = {
            "version": "1.0.0",
            "created_at": backup_info["timestamp"],
            "schema_version": 1,
            "contents": ["manifest.json", "config.json", "sublarr.db"],
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        # Config (safe, no raw secrets)
        config_data = s.get_safe_config()
        zf.writestr("config.json", json.dumps(config_data, indent=2))

        # Database file
        zf.write(backup_info["path"], "sublarr.db")

    buffer.seek(0)
    filename = f"sublarr_backup_{backup_info['timestamp']}.zip"
    return send_file(
        buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=filename,
    )
```

### Anti-Patterns to Avoid
- **Hardcoded strings in JSX:** Every user-visible string must go through `t()`. Do not leave any hardcoded English text in components.
- **Giant single translation file:** Split by namespace (page or feature area) to keep files manageable and enable future lazy loading.
- **CSS-in-JS for theming:** The app already uses CSS custom properties inline -- do NOT introduce a CSS-in-JS solution. Keep using `var(--name)` pattern.
- **Dark mode via Tailwind dark: prefix everywhere:** Since the app uses inline `style={{ color: 'var(--text-primary)' }}`, the theme switch happens at the CSS variable level. Do NOT rewrite all components to use `className="dark:bg-black"`.
- **Storing full secrets in backup ZIP:** Config export must mask API keys like the existing `get_safe_config()` does. ZIP restore should only restore non-secret config values.
- **Recharts with huge datasets:** The daily_stats table stores 30 days by default. If adding longer ranges, limit to max ~365 data points. SVG-based charts degrade beyond 1000+ points.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Translation string management | Custom string lookup system | i18next with namespace JSON files | Pluralization, interpolation, fallback chains, language detection |
| Language persistence | Manual localStorage management | i18next-browser-languageDetector | Handles detection order, caching, fallback automatically |
| Charts/data visualization | Custom SVG/Canvas charting | Recharts | Tested, accessible, responsive, handles tooltips/legends/animations |
| ZIP archive creation | Manual file concatenation | Python zipfile module | Handles compression, CRC, file metadata correctly |
| ZIP file validation | Custom binary parsing | zipfile.is_zipfile() + ZipFile.testzip() | Catches corruption, bad headers, incomplete files |
| Theme persistence | Custom state management | useTheme hook + localStorage + CSS class toggle | Standard pattern, SSR-safe, handles system preference |
| Subtitle time adjustment | Custom time parsing/math | pysubs2 library (or manual SRT/ASS time parsing) | Handles all subtitle formats, time shift, style preservation |

**Key insight:** The i18n domain has decades of edge cases (pluralization rules differ by language, RTL support, number formatting, date formatting). i18next handles all of this. For only en/de, the complexity is low, but the library handles it correctly from the start.

## Common Pitfalls

### Pitfall 1: Missing Translation Keys in Production
**What goes wrong:** Strings show as raw keys like `dashboard.stats.translated_today` instead of actual text.
**Why it happens:** Developer adds a `t()` call but forgets to add the key to BOTH en and de JSON files.
**How to avoid:** Use i18next's `saveMissing` option in development mode that logs missing keys. Create a CI step or script that validates all namespaces have matching keys in en and de.
**Warning signs:** Console warnings about missing keys, raw key strings visible in UI.

### Pitfall 2: Theme Flash on Page Load
**What goes wrong:** Page briefly shows light theme then switches to dark (or vice versa).
**Why it happens:** JavaScript runs after initial CSS render. If dark class is set via useEffect, there's a flash.
**How to avoid:** Add an inline script in `index.html` (before React loads) that reads localStorage and sets the `dark` class on `<html>` immediately. This runs synchronously before paint.
**Warning signs:** Brief white flash on page load in dark mode.

### Pitfall 3: CSS Variable Scope with Tailwind v4
**What goes wrong:** Dark mode variables don't apply, or apply inconsistently.
**Why it happens:** Tailwind v4 removed `darkMode` config. Must use `@custom-variant dark (&:where(.dark, .dark *))`.
**How to avoid:** Add the `@custom-variant` directive at the top of `index.css`, right after `@import "tailwindcss"`. Test with both themes.
**Warning signs:** `dark:` prefix classes not working, or working only on some elements.

### Pitfall 4: Backup Restore Corrupting Active Database
**What goes wrong:** Restore fails mid-operation, leaving DB in inconsistent state.
**Why it happens:** The existing `restore_backup()` already handles this with safety backup + rollback, but the ZIP restore adds an extra layer (extraction, validation).
**How to avoid:** Validate ZIP contents BEFORE starting restore. Check manifest schema version. Verify DB integrity on the extracted file before replacing the active DB. The existing `DatabaseBackup.restore_backup()` already creates a safety backup.
**Warning signs:** 500 errors after restore, missing data, schema mismatch.

### Pitfall 5: BytesIO Cursor Position After ZIP Write
**What goes wrong:** Flask sends an empty response (0 bytes) for backup download.
**Why it happens:** After writing to BytesIO with zipfile, the cursor is at the end. Must call `buffer.seek(0)` before `send_file()`.
**How to avoid:** Always call `buffer.seek(0)` after writing and before sending.
**Warning signs:** Downloaded ZIP file is 0 bytes or invalid.

### Pitfall 6: Translation Context for German Technical Terms
**What goes wrong:** German translations use overly formal or incorrect technical terms for subtitle/anime domain.
**Why it happens:** Generic translation without domain expertise.
**How to avoid:** Use established German terms from Sonarr/Radarr/Bazarr German translations. Keep anime terms untranslated (e.g., "Anime" stays "Anime"). Use "Untertitel" for subtitle, "Uebersetzung" for translation, etc.
**Warning signs:** Users switch back to English because German feels unnatural.

### Pitfall 7: Recharts Not Respecting CSS Variables
**What goes wrong:** Charts don't update colors when theme switches.
**Why it happens:** Recharts reads CSS variable values at render time. If theme changes, chart SVG elements may not update.
**How to avoid:** Use a key prop on the chart container that changes with theme, forcing re-render. Or pass computed colors from a hook.
**Warning signs:** Chart colors stuck on dark theme values in light mode.

## Code Examples

### i18n JSON Structure (English common.json)
```json
{
  "nav": {
    "dashboard": "Dashboard",
    "library": "Library",
    "wanted": "Wanted",
    "activity": "Activity",
    "queue": "Queue",
    "history": "History",
    "blacklist": "Blacklist",
    "settings": "Settings",
    "logs": "Logs",
    "statistics": "Statistics"
  },
  "nav_groups": {
    "content": "Content",
    "activity": "Activity",
    "system": "System"
  },
  "status": {
    "healthy": "Healthy",
    "unhealthy": "Unhealthy",
    "online": "Online",
    "offline": "Offline",
    "enabled": "Enabled",
    "disabled": "Disabled",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "queued": "Queued"
  },
  "actions": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "edit": "Edit",
    "add": "Add",
    "test": "Test",
    "download": "Download",
    "upload": "Upload",
    "refresh": "Refresh",
    "search": "Search",
    "export": "Export",
    "import": "Import",
    "confirm": "Confirm",
    "back": "Back"
  },
  "theme": {
    "dark": "Dark",
    "light": "Light",
    "system": "System"
  },
  "language": {
    "en": "English",
    "de": "Deutsch"
  }
}
```

### i18n JSON Structure (German common.json)
```json
{
  "nav": {
    "dashboard": "Dashboard",
    "library": "Bibliothek",
    "wanted": "Gesucht",
    "activity": "Aktivitaet",
    "queue": "Warteschlange",
    "history": "Verlauf",
    "blacklist": "Sperrliste",
    "settings": "Einstellungen",
    "logs": "Protokolle",
    "statistics": "Statistiken"
  },
  "nav_groups": {
    "content": "Inhalte",
    "activity": "Aktivitaet",
    "system": "System"
  },
  "status": {
    "healthy": "Gesund",
    "unhealthy": "Fehlerhaft",
    "online": "Online",
    "offline": "Offline",
    "enabled": "Aktiviert",
    "disabled": "Deaktiviert",
    "running": "Laeuft",
    "completed": "Abgeschlossen",
    "failed": "Fehlgeschlagen",
    "queued": "Wartend"
  },
  "actions": {
    "save": "Speichern",
    "cancel": "Abbrechen",
    "delete": "Loeschen",
    "edit": "Bearbeiten",
    "add": "Hinzufuegen",
    "test": "Testen",
    "download": "Herunterladen",
    "upload": "Hochladen",
    "refresh": "Aktualisieren",
    "search": "Suchen",
    "export": "Exportieren",
    "import": "Importieren",
    "confirm": "Bestaetigen",
    "back": "Zurueck"
  },
  "theme": {
    "dark": "Dunkel",
    "light": "Hell",
    "system": "System"
  },
  "language": {
    "en": "English",
    "de": "Deutsch"
  }
}
```

### Theme Toggle Inline Script (index.html)
```html
<!-- Add BEFORE React bundle loads to prevent flash -->
<script>
  (function() {
    var theme = localStorage.getItem('sublarr-theme');
    if (theme === 'light') {
      document.documentElement.classList.remove('dark');
    } else if (theme === 'dark' || !theme) {
      document.documentElement.classList.add('dark');
    } else {
      // system
      if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.classList.add('dark');
      }
    }
  })();
</script>
```

### Light Theme CSS Variables
```css
/* These go in :root {} (light is default when .dark is absent) */
:root {
  --bg-primary: #f0f2f5;
  --bg-surface: #ffffff;
  --bg-surface-hover: #f5f7fa;
  --bg-elevated: #ffffff;
  --border: #e2e5eb;
  --border-hover: #d0d4dc;
  --text-primary: #1a1d26;
  --text-secondary: #5c6370;
  --text-muted: #9ca3b0;
  --accent: #0f9bb5;
  --accent-hover: #0d8aa1;
  --accent-dim: #0a7089;
  --accent-subtle: rgba(15, 155, 181, 0.08);
  --accent-bg: rgba(15, 155, 181, 0.12);
  --success: #22a55b;
  --success-bg: rgba(34, 165, 91, 0.1);
  --error: #e5334b;
  --error-bg: rgba(229, 51, 75, 0.1);
  --warning: #d48a08;
  --warning-bg: rgba(212, 138, 8, 0.1);
}

.dark {
  /* Current values move here */
  --bg-primary: #171923;
  --bg-surface: #1e2130;
  --bg-surface-hover: #252838;
  --bg-elevated: #2a2e3d;
  --border: #2a2e3b;
  --border-hover: #363b4d;
  --text-primary: #e2e5eb;
  --text-secondary: #7c8293;
  --text-muted: #4a5068;
  --accent: #1DB8D4;
  --accent-hover: #19a5bf;
  --accent-dim: #116d7e;
  --accent-subtle: rgba(29, 184, 212, 0.08);
  --accent-bg: rgba(29, 184, 212, 0.12);
  --success: #2ed573;
  --success-bg: rgba(46, 213, 115, 0.1);
  --error: #f43f5e;
  --error-bg: rgba(244, 63, 94, 0.1);
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.1);
}
```

### Backend Statistics Endpoint (Enhanced)
```python
@bp.route("/statistics", methods=["GET"])
def get_statistics():
    """Get comprehensive statistics with time range filter.

    Query params: range (7d, 30d, 90d, 365d), format (json, csv)
    """
    from db.jobs import get_stats_summary
    from db.providers import get_provider_stats, get_provider_health_history

    range_param = request.args.get("range", "30d")
    days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}.get(range_param, 30)

    # Extended stats query with date range
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()

    # Provider stats
    provider_stats = get_provider_stats()

    # Download history stats
    with _db_lock:
        download_rows = db.execute(
            """SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
               FROM subtitle_downloads
               GROUP BY provider_name"""
        ).fetchall()

    return jsonify({
        "daily": [dict(r) for r in rows],
        "providers": provider_stats,
        "downloads_by_provider": [dict(r) for r in download_rows],
        "range": range_param,
    })
```

### Subtitle Processing Tools Backend
```python
@bp.route("/tools/adjust-timing", methods=["POST"])
def adjust_subtitle_timing():
    """Shift subtitle timing by milliseconds."""
    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    offset_ms = data.get("offset_ms", 0)
    # Parse SRT/ASS, shift all timestamps, write back
    # ... implementation uses regex for SRT timestamps or pysubs2

@bp.route("/tools/remove-hi", methods=["POST"])
def remove_hi_tags():
    """Remove hearing-impaired tags from subtitle file."""
    from hi_remover import remove_hi_markers
    # Already implemented in hi_remover.py
    # Wrap as API endpoint

@bp.route("/tools/common-fixes", methods=["POST"])
def apply_common_fixes():
    """Apply common subtitle fixes: encoding, line breaks, whitespace."""
    from ass_utils import fix_line_breaks
    # Leverage existing fix_line_breaks + additional fixes
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| tailwind.config.js `darkMode: 'class'` | `@custom-variant dark` in CSS | Tailwind v4 (Jan 2025) | Config file replaced by CSS directive |
| i18next-http-backend for lazy loading | Static imports for small apps | Always valid | No HTTP overhead for 2 languages |
| recharts v2 API | recharts v3 API | May 2024 | Minor API changes, better performance |
| Custom chart rendering | Recharts declarative components | N/A | Standard practice for React dashboards |

**Deprecated/outdated:**
- `tailwind.config.js` `darkMode` option: Replaced by `@custom-variant` in Tailwind v4
- `react-i18next` class-based HOC (`withTranslation`): Still works but hooks (`useTranslation`) are preferred
- `recharts` v2 `<Sector>` customization: API changed in v3

## Existing Codebase Assets (Critical for Planning)

The following already exists and should be EXTENDED, not rebuilt:

### Backend
| Asset | Location | What It Does | What Needs Adding |
|-------|----------|--------------|-------------------|
| `DatabaseBackup` class | `backend/database_backup.py` | Create/verify/list/restore/rotate SQLite backups | ZIP wrapping (config + DB together) |
| Backup API endpoints | `backend/routes/system.py` lines 224-290 | POST create, GET list, POST restore | ZIP download endpoint, ZIP upload endpoint |
| Config export/import | `backend/routes/config.py` lines 138-204 | JSON config export (safe) and import | Integrate into ZIP backup |
| Stats summary | `backend/db/jobs.py` lines 201-250 | Daily stats with 30-day history | Extend range parameter, add provider stats |
| Provider stats | `backend/db/providers.py` | Per-provider success/failure/score tracking | Expose as statistics endpoint |
| Log endpoint | `backend/routes/system.py` lines 305-331 | Read log file with level filter | Add download, rotation config |
| HI removal | `backend/hi_remover.py` | Remove hearing-impaired markers | Wrap as API tool endpoint |
| ASS utilities | `backend/ass_utils.py` | Tag handling, line break fixes | Wrap as API tool endpoints |
| Backup scheduler | `backend/database_backup.py` lines 244-297 | Timer-based daily backup | Config for schedule in Settings UI |

### Frontend
| Asset | Location | What It Does | What Needs Adding |
|-------|----------|--------------|-------------------|
| CSS custom properties | `frontend/src/index.css` | All colors as variables | Add light theme values, move current to `.dark` |
| Settings page tabs | `frontend/src/pages/Settings.tsx` | 16 tabs with collapsible cards | Add "Backup" tab, "Appearance" tab |
| Logs page | `frontend/src/pages/Logs.tsx` | Level filter, search, auto-scroll | Download button, rotation config |
| Dashboard stats | `frontend/src/pages/Dashboard.tsx` | StatCards, Quick Actions, Recent Activity | Link to new Statistics page |
| Sidebar nav | `frontend/src/components/layout/Sidebar.tsx` | 3 groups with nav items | Add "Statistics" nav item |
| useApi hooks | `frontend/src/hooks/useApi.ts` | All API hooks | Add backup/statistics hooks |
| Types | `frontend/src/lib/types.ts` | DailyStat, Stats, etc. | Add BackupInfo, StatisticsData types |
| useExportConfig/useImportConfig | `frontend/src/hooks/useApi.ts` lines 453-466 | Config export/import hooks | Extend for ZIP backup |

### Database Tables with Statistics Data
| Table | Key Fields | Use for Statistics |
|-------|-----------|-------------------|
| `daily_stats` | date, translated, failed, skipped, by_format_json, by_source_json | Translation charts |
| `provider_stats` | provider_name, total_searches, successful_downloads, failed_downloads, avg_score | Provider usage charts |
| `subtitle_downloads` | provider_name, language, format, score, downloaded_at | Download history charts |
| `translation_backend_stats` | backend_name, total_requests, successful/failed, total_characters | Backend usage charts |
| `upgrade_history` | old_format, new_format, provider_name, upgraded_at | Upgrade charts |

## Open Questions

1. **Subtitle time adjustment library**
   - What we know: Python's `pysubs2` library can parse/modify SRT and ASS timing. The app already has regex-based ASS parsing in `ass_utils.py`.
   - What's unclear: Whether to add `pysubs2` as a dependency or build minimal time-shift logic using existing regex patterns.
   - Recommendation: For ADMN-04 (subtitle tools), use the existing `ass_utils.py` patterns for ASS files and simple regex for SRT timestamp shifting. Avoid adding `pysubs2` unless more complex operations are needed. Keep the tools minimal: time shift, HI removal, encoding fix.

2. **Statistics data retention**
   - What we know: `daily_stats` currently stores up to 30 days (query LIMIT 30). `provider_stats` is cumulative (single row per provider).
   - What's unclear: Whether longer ranges (90d, 365d) require schema changes or just removing the LIMIT.
   - Recommendation: The `daily_stats` table already stores rows per day indefinitely. The 30-day LIMIT is only in the query. For longer ranges, simply increase the LIMIT parameter. Add a cleanup job to prune stats older than 1 year.

3. **Backup secret handling**
   - What we know: `get_safe_config()` masks secrets. ZIP restore should use the same `import_config()` logic that skips secrets.
   - What's unclear: Should the ZIP include a way to optionally include secrets (encrypted)?
   - Recommendation: Keep it simple. ZIP backup uses `get_safe_config()` (no secrets). Users must re-enter API keys after restore. This is the safe default. Document this clearly in the UI.

4. **CSV/JSON export for statistics**
   - What we know: ADMN-01 requires export capability.
   - What's unclear: Export format preference.
   - Recommendation: Support both JSON and CSV export from the statistics endpoint via query parameter. CSV is useful for spreadsheet users, JSON for programmatic access.

## Sources

### Primary (HIGH confidence)
- Tailwind CSS v4 Dark Mode docs: https://tailwindcss.com/docs/dark-mode -- verified `@custom-variant` syntax
- react-i18next Quick Start: https://react.i18next.com/guides/quick-start -- initialization pattern
- react-i18next useTranslation hook: https://react.i18next.com/latest/usetranslation-hook -- namespace usage
- Recharts GitHub: https://github.com/recharts/recharts -- v3.7 API, component list
- Existing codebase: `database_backup.py`, `routes/system.py`, `routes/config.py`, `db/__init__.py` -- verified all existing infrastructure

### Secondary (MEDIUM confidence)
- i18next-browser-languageDetector npm: https://www.npmjs.com/package/i18next-browser-languagedetector -- detection order and localStorage configuration
- Recharts npm: https://www.npmjs.com/package/recharts -- version 3.7.0 confirmed
- react-i18next npm: https://www.npmjs.com/package/react-i18next -- version 16.0.1 confirmed
- i18next npm: https://www.npmjs.com/package/i18next -- version 25.8.7 confirmed

### Tertiary (LOW confidence)
- Light theme color values: Custom design based on *arr-suite patterns, may need visual tuning during implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - well-established libraries, verified current versions
- Architecture (i18n): HIGH - standard react-i18next patterns, verified with official docs
- Architecture (backup): HIGH - extending existing DatabaseBackup class, Python stdlib zipfile
- Architecture (theming): HIGH - Tailwind v4 docs verified, CSS variable approach matches existing codebase
- Architecture (charts): HIGH - Recharts is standard, data already exists in DB
- Architecture (subtitle tools): MEDIUM - tools are simple wrappers, but exact feature scope for ADMN-04 is broad
- Pitfalls: HIGH - based on common i18n/theming issues, verified with community reports

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days - all technologies are stable)
