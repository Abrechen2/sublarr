# i18n Remaining Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alle verbliebenen hardcoded Strings in GeneralSettings, AutomationSettings, ScoringTab, BackupTab, AnidbTab, CacheTab und Trash.tsx durch `t()` ersetzen.

**Architecture:** Datei-für-Datei wie beim ersten Plan. Alle neuen Keys landen im `settings`-Namespace (außer Trash.tsx → `common`). Bestehende `t('settings.automation.*', fallback)`-Calls mit `useTranslation('common')` werden NICHT angefasst — nur neue hardcoded Strings werden migriert. Für Funktionen die bereits `useTranslation('common')` haben: zweite Instanz `const { t: tS } = useTranslation('settings')` hinzufügen.

**Tech Stack:** React 19, i18next, react-i18next, TypeScript — keine neuen Dependencies.

---

## Dateiübersicht

**Zu ändern (Locale-JSON):**
- `frontend/src/i18n/locales/de/settings.json` — neue Keys für alle Settings-Pages
- `frontend/src/i18n/locales/en/settings.json` — selbe Keys Englisch
- `frontend/src/i18n/locales/de/common.json` — `trash`-Block
- `frontend/src/i18n/locales/en/common.json` — `trash`-Block

**Zu ändern (TSX):**
- `frontend/src/pages/Settings/GeneralSettings.tsx`
- `frontend/src/pages/Settings/AutomationSettings.tsx`
- `frontend/src/pages/Settings/ScoringTab.tsx`
- `frontend/src/pages/Settings/BackupTab.tsx`
- `frontend/src/pages/Settings/AnidbTab.tsx`
- `frontend/src/pages/Settings/CacheTab.tsx`
- `frontend/src/pages/Trash.tsx`

---

### Task 1: GeneralSettings.tsx

**Files:**
- Modify: `frontend/src/pages/Settings/GeneralSettings.tsx`
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

> **Kontext:** Die Datei hat kein `useTranslation`. Alle Strings sind hardcoded Englisch. HI_OPTIONS, FORCED_OPTIONS, LIBRARY_SORTS und DATETIME_FORMATS sind Konstanten-Arrays auf Modulebene — deren Labels müssen in den Komponent verschoben werden um t() verwenden zu können.

- [ ] **Keys in settings.json DE hinzufügen**

Am Ende der Datei `frontend/src/i18n/locales/de/settings.json` (vor dem schließenden `}`), neues Objekt hinzufügen:

```json
"general_page": {
  "title": "Allgemein",
  "subtitle": "Oberfläche, Server und Protokoll-Einstellungen",
  "interface_section": "Oberfläche",
  "interface_desc": "Sprachpräferenzen für Untertitelsuche und Anzeige",
  "interface_prefs_section": "Darstellungs-Einstellungen",
  "interface_prefs_desc": "Seitennummerierung, Bibliothekslayout, Sortierung und Datumsformate.",
  "paths_section": "Pfade & Server",
  "paths_desc": "Medienbibliothek-Wurzelpfad, Server-Port und erweiterte Optionen",
  "logging_section": "Protokollierung",
  "logging_desc": "Protokoll-Ausführlichkeit und Dateiausgabe-Einstellungen",
  "source_language": "Quellsprache",
  "source_language_hint": "Sprache der Quell-Untertitel (z.B. en)",
  "target_language": "Zielsprache",
  "target_language_hint": "Sprache für die Untertitelsuche (z.B. de)",
  "hi_preference": "Hörgeschädigten-Präferenz",
  "hi_preference_hint": "Wie Untertitel mit HI-Tags bei der Anbietersuche behandelt werden",
  "hi_include": "Einschließen (kein Vorzug)",
  "hi_prefer": "Bevorzugen (+30 Score)",
  "hi_exclude": "Ausschließen (−999 Malus)",
  "hi_only": "Nur HI (andere ausgeschlossen)",
  "forced_preference": "Erzwungene Untertitel",
  "forced_preference_hint": "Wie erzwungene Untertitel (fremdsprachige Szenen) behandelt werden",
  "forced_include": "Einschließen (kein Vorzug)",
  "forced_prefer": "Bevorzugen (+30 Score)",
  "forced_exclude": "Ausschließen (−999 Malus)",
  "forced_only": "Nur erzwungene (andere ausgeschlossen)",
  "interface_language": "Oberflächensprache",
  "interface_language_hint": "Anzeigesprache der Benutzeroberfläche",
  "items_per_page": "Einträge pro Seite",
  "items_per_page_hint": "Anzahl der Einträge pro Seite in Bibliothekslisten",
  "default_library_view": "Standard-Bibliotheksansicht",
  "default_library_view_hint": "Standard-Ansichtsmodus für die Bibliothek (Raster oder Liste)",
  "default_library_sort": "Standard-Sortierung",
  "default_library_sort_hint": "Standard-Sortierreihenfolge für Bibliothekseinträge",
  "sort_alpha": "Alphabetisch",
  "sort_date": "Hinzugefügt",
  "sort_score": "Score",
  "datetime_format": "Datum-/Uhrzeitformat",
  "datetime_format_hint": "Wie Datum und Uhrzeit in der Oberfläche angezeigt werden",
  "datetime_relative": "Relativ (vor 2 Stunden)",
  "datetime_absolute": "Absolut (2026-03-21 14:00)",
  "metadata_engine": "Metadaten-Scan-Engine",
  "metadata_engine_hint": "Tool zum Lesen von Medienmetadaten. 'auto' bevorzugt mediainfo wenn verfügbar.",
  "translation_workers": "Übersetzungs-Worker",
  "translation_workers_hint": "Parallele Threads für Untertitel-Übersetzungsaufgaben",
  "metadata_workers": "Metadaten-Scan-Worker",
  "metadata_workers_hint": "Parallele Threads für Metadaten-Scans",
  "base_url": "Basis-URL",
  "base_url_hint": "Reverse-Proxy-Präfix wenn Sublarr unter einem Unterpfad läuft",
  "db_path": "Datenbankpfad",
  "db_path_hint": "SQLite-Datenbankdatei. Nur ändern wenn die DB verschoben wurde.",
  "media_path": "Medienpfad",
  "media_path_hint": "Wurzelpfad des Medienverzeichnisses. Alle Medienpfade müssen darunter liegen.",
  "port": "Port",
  "port_hint": "HTTP-Port auf dem Sublarr hört. Standard: 5765.",
  "log_level": "Protokoll-Level",
  "log_level_hint": "Steuert die Ausführlichkeit des Backend-Protokolls",
  "log_file": "Protokolldatei-Pfad",
  "log_file_hint": "Protokoll in diesen Dateipfad schreiben, z.B. /config/sublarr.log. Leer lassen zum Deaktivieren.",
  "log_format": "Protokollformat",
  "log_format_hint": "Ausgabeformat für Protokolleinträge. 'json' für Log-Aggregationstools."
}
```

- [ ] **Keys in settings.json EN hinzufügen**

```json
"general_page": {
  "title": "General",
  "subtitle": "Interface, server, and logging configuration",
  "interface_section": "Interface",
  "interface_desc": "Language preferences for subtitle search and display",
  "interface_prefs_section": "Interface Preferences",
  "interface_prefs_desc": "Pagination, library layout, sorting, and date display defaults.",
  "paths_section": "Paths & Server",
  "paths_desc": "Media library root, server port, and advanced server options",
  "logging_section": "Logging",
  "logging_desc": "Log verbosity and file output settings",
  "source_language": "Source Language",
  "source_language_hint": "Language of the source subtitles (e.g. en)",
  "target_language": "Target Language",
  "target_language_hint": "Language to search subtitles in (e.g. de)",
  "hi_preference": "Hearing Impaired Preference",
  "hi_preference_hint": "How subtitles with HI tags are treated during provider search",
  "hi_include": "Include (no preference)",
  "hi_prefer": "Prefer HI (+30 score)",
  "hi_exclude": "Exclude HI (−999 penalty)",
  "hi_only": "Only HI (non-HI excluded)",
  "forced_preference": "Forced Subtitle Preference",
  "forced_preference_hint": "How forced subtitles (foreign-language scenes) are handled",
  "forced_include": "Include (no preference)",
  "forced_prefer": "Prefer forced (+30 score)",
  "forced_exclude": "Exclude forced (−999 penalty)",
  "forced_only": "Only forced (non-forced excluded)",
  "interface_language": "Interface Language",
  "interface_language_hint": "UI display language",
  "items_per_page": "Items per Page",
  "items_per_page_hint": "Number of items shown per page in library lists",
  "default_library_view": "Default Library View",
  "default_library_view_hint": "Default view mode for the library (grid or list)",
  "default_library_sort": "Default Library Sort",
  "default_library_sort_hint": "Default sort order for library listings",
  "sort_alpha": "Alphabetical",
  "sort_date": "Date Added",
  "sort_score": "Score",
  "datetime_format": "Date/Time Format",
  "datetime_format_hint": "How dates and times are displayed throughout the UI",
  "datetime_relative": "Relative (2 hours ago)",
  "datetime_absolute": "Absolute (2026-03-21 14:00)",
  "metadata_engine": "Metadata Scan Engine",
  "metadata_engine_hint": "Tool used to read media metadata. 'auto' prefers mediainfo when available.",
  "translation_workers": "Translation Workers",
  "translation_workers_hint": "Parallel threads for subtitle translation jobs",
  "metadata_workers": "Metadata Scan Workers",
  "metadata_workers_hint": "Parallel threads for metadata scanning",
  "base_url": "Base URL",
  "base_url_hint": "Reverse-proxy prefix if Sublarr is served at a sub-path",
  "db_path": "Database Path",
  "db_path_hint": "SQLite database file. Only change if the DB has been moved.",
  "media_path": "Media Path",
  "media_path_hint": "Root path of the media directory. All media paths must be below this.",
  "port": "Port",
  "port_hint": "HTTP port Sublarr listens on. Default: 5765.",
  "log_level": "Log Level",
  "log_level_hint": "Controls the verbosity of backend logging",
  "log_file": "Log File Path",
  "log_file_hint": "Write logs to this file path, e.g. /config/sublarr.log. Leave empty to disable.",
  "log_format": "Log Format",
  "log_format_hint": "Output format for log entries. Use 'json' for log aggregation tools."
}
```

- [ ] **useTranslation in GeneralSettings.tsx importieren und hook hinzufügen**

Zeile 1 von `frontend/src/pages/Settings/GeneralSettings.tsx`:
```tsx
import { useTranslation } from 'react-i18next'
import { Globe, HardDrive, FileText, Monitor } from 'lucide-react'
```

In `GeneralSettings()` nach `const { mutate: updateConfig, isPending } = useUpdateConfig()`:
```tsx
  const { t } = useTranslation('settings')
```

- [ ] **LIBRARY_SORTS und DATETIME_FORMATS als computed arrays in die Komponente verschieben**

Die Konstanten auf Modulebene `LIBRARY_SORTS` und `DATETIME_FORMATS` enthalten englische Labels die übersetzt werden müssen. Die Arrays auf Modulebene bleiben als Werte-Arrays:

```tsx
// Bestehende Konstanten auf Modulebene BLEIBEN:
const LIBRARY_VIEWS = ['grid', 'list'] as const
const LIBRARY_SORTS_KEYS = ['alpha', 'date', 'score'] as const
const DATETIME_FORMAT_KEYS = ['relative', 'absolute'] as const
// (LIBRARY_SORTS und DATETIME_FORMATS Arrays entfernen oder umbenennen)
```

Innerhalb der `GeneralSettings()`-Funktion, nach dem `t`-Hook:
```tsx
  const librarySorts = [
    { value: 'alpha', label: t('general_page.sort_alpha') },
    { value: 'date',  label: t('general_page.sort_date') },
    { value: 'score', label: t('general_page.sort_score') },
  ]
  const datetimeFormats = [
    { value: 'relative', label: t('general_page.datetime_relative') },
    { value: 'absolute', label: t('general_page.datetime_absolute') },
  ]
  const hiOptions = [
    { value: 'include', label: t('general_page.hi_include') },
    { value: 'prefer',  label: t('general_page.hi_prefer') },
    { value: 'exclude', label: t('general_page.hi_exclude') },
    { value: 'only',    label: t('general_page.hi_only') },
  ]
  const forcedOptions = [
    { value: 'include', label: t('general_page.forced_include') },
    { value: 'prefer',  label: t('general_page.forced_prefer') },
    { value: 'exclude', label: t('general_page.forced_exclude') },
    { value: 'only',    label: t('general_page.forced_only') },
  ]
```

In den `select`-Elementen die `HI_OPTIONS`, `FORCED_OPTIONS`, `LIBRARY_SORTS`, `DATETIME_FORMATS` verwenden: durch die neuen lokalen Variablen `hiOptions`, `forcedOptions`, `librarySorts`, `datetimeFormats` ersetzen.

- [ ] **Hardcoded Strings in GeneralSettings.tsx ersetzen**

`SettingsDetailLayout` (Zeilen 58-60 und 80-82):
```tsx
// Skeleton:
<SettingsDetailLayout title={t('general_page.title')} subtitle={t('general_page.subtitle')}>
// Haupt-Render:
<SettingsDetailLayout title={t('general_page.title')} subtitle={t('general_page.subtitle')}>
```

`SettingsSection` Titel/Descriptions:
```tsx
// Interface section (Zeile 87-90):
title={t('general_page.interface_section')}
description={t('general_page.interface_desc')}

// Interface Preferences section (Zeile 176-179):
title={t('general_page.interface_prefs_section')}
description={t('general_page.interface_prefs_desc')}

// Paths & Server section (Zeile 292-295):
title={t('general_page.paths_section')}
description={t('general_page.paths_desc')}

// Logging section (Zeile 437-440):
title={t('general_page.logging_section')}
description={t('general_page.logging_desc')}
```

`FormGroup` labels und hints (alle ersetzen):
```tsx
// Source Language:
label={t('general_page.source_language')}
hint={t('general_page.source_language_hint')}

// Target Language:
label={t('general_page.target_language')}
hint={t('general_page.target_language_hint')}

// Hearing Impaired Preference:
label={t('general_page.hi_preference')}
hint={t('general_page.hi_preference_hint')}

// Forced Subtitle Preference:
label={t('general_page.forced_preference')}
hint={t('general_page.forced_preference_hint')}

// Interface Language:
label={t('general_page.interface_language')}
hint={t('general_page.interface_language_hint')}

// Items per Page:
label={t('general_page.items_per_page')}
hint={t('general_page.items_per_page_hint')}

// Default Library View:
label={t('general_page.default_library_view')}
hint={t('general_page.default_library_view_hint')}

// Default Library Sort:
label={t('general_page.default_library_sort')}
hint={t('general_page.default_library_sort_hint')}

// Date/Time Format:
label={t('general_page.datetime_format')}
hint={t('general_page.datetime_format_hint')}

// Metadata Scan Engine (in advanced):
label={t('general_page.metadata_engine')}
hint={t('general_page.metadata_engine_hint')}

// Translation Workers:
label={t('general_page.translation_workers')}
hint={t('general_page.translation_workers_hint')}

// Metadata Scan Workers:
label={t('general_page.metadata_workers')}
hint={t('general_page.metadata_workers_hint')}

// Base URL:
label={t('general_page.base_url')}
hint={t('general_page.base_url_hint')}

// Database Path:
label={t('general_page.db_path')}
hint={t('general_page.db_path_hint')}

// Media Path:
label={t('general_page.media_path')}
hint={t('general_page.media_path_hint')}

// Port:
label={t('general_page.port')}
hint={t('general_page.port_hint')}

// Log Level:
label={t('general_page.log_level')}
hint={t('general_page.log_level_hint')}

// Log File Path:
label={t('general_page.log_file')}
hint={t('general_page.log_file_hint')}

// Log Format:
label={t('general_page.log_format')}
hint={t('general_page.log_format_hint')}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Settings/GeneralSettings.tsx \
  frontend/src/i18n/locales/de/settings.json \
  frontend/src/i18n/locales/en/settings.json
git commit -m "feat: i18n GeneralSettings"
```

---

### Task 2: AutomationSettings.tsx — SearchScanContent + UpgradeRulesContent

**Files:**
- Modify: `frontend/src/pages/Settings/AutomationSettings.tsx` (Zeilen 41-397)
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

> **Kontext:** `SearchScanContent()` (Zeile 41) und `UpgradeRulesContent()` (Zeile 295) haben bereits `const { t } = useTranslation('common')`. Diese NICHT ändern. Eine zweite Instanz `const { t: tS } = useTranslation('settings')` hinzufügen für neue Keys.
> 
> `SearchScanContent` hat zwei hardcoded deutsche Subheadings (Zeilen 64 und 110), zwei deutsche FormGroups (Zeilen 67-88), und sieben englische FormGroups (Zeilen 150-288).
> `UpgradeRulesContent` hat zwei englische FormGroups (Zeilen 365-394).

- [ ] **Keys in settings.json DE hinzufügen**

```json
"automation_page": {
  "subheading_library_scan": "Bibliotheks-Scan",
  "subheading_subtitle_search": "Untertitel-Suche",
  "scan_interval": "Scan-Intervall (Stunden)",
  "scan_interval_hint": "Wie oft (in Stunden) Sublarr die Bibliothek auf neue Dateien scannt. 0 = nur event-gesteuert.",
  "scan_on_startup": "Scan beim Start",
  "scan_on_startup_hint": "Bibliothek beim Start von Sublarr automatisch scannen.",
  "max_items_per_run": "Max. Elemente pro Lauf",
  "max_items_per_run_hint": "Maximale Anzahl von gesuchten Elementen in einem einzigen Suchlauf.",
  "max_search_attempts": "Max. Suchversuche",
  "max_search_attempts_hint": "Wie oft Sublarr eine fehlgeschlagene Untertitelsuche wiederholt bevor es aufgibt.",
  "auto_extract": "Eingebettete automatisch extrahieren",
  "auto_extract_hint": "Eingebettete Untertitel während Wanted-Scans automatisch extrahieren.",
  "anime_series_only": "Nur Anime-Serien",
  "anime_series_only_hint": "Nur Untertitel für Anime-Serien suchen (Live-Action überspringen).",
  "anime_movies_only": "Nur Anime-Filme",
  "anime_movies_only_hint": "Nur Untertitel für Anime-Filme suchen.",
  "skip_srt_no_ass": "SRT überspringen wenn kein ASS gefunden",
  "skip_srt_no_ass_hint": "SRT-Downloads überspringen wenn keine ASS-Untertitel für die Episode gefunden wurden.",
  "adaptive_backoff": "Adaptives Backoff",
  "adaptive_backoff_hint": "Wiederholungsverzögerung exponentiell erhöhen für wiederholt fehlschlagende Elemente.",
  "backoff_base": "Backoff-Basis (Stunden)",
  "backoff_base_hint": "Anfängliche Wiederholungsverzögerung in Stunden wenn Backoff aktiv ist.",
  "backoff_cap": "Backoff-Obergrenze (Stunden)",
  "backoff_cap_hint": "Maximale Wiederholungsverzögerung in Stunden. Verzögerung überschreitet diesen Wert nicht.",
  "upgrade_window": "Upgrade-Fenster (Tage)",
  "upgrade_window_hint": "Nur Untertitel upgraden die innerhalb dieser Anzahl von Tagen heruntergeladen wurden.",
  "prefer_ass": "ASS gegenüber SRT bevorzugen",
  "prefer_ass_hint": "Immer von SRT auf ASS upgraden wenn ein besserer ASS-Untertitel verfügbar ist."
}
```

- [ ] **Keys in settings.json EN hinzufügen**

```json
"automation_page": {
  "subheading_library_scan": "Library Scan",
  "subheading_subtitle_search": "Subtitle Search",
  "scan_interval": "Scan Interval (hours)",
  "scan_interval_hint": "How often (in hours) Sublarr scans the library for new files. 0 = event-driven only.",
  "scan_on_startup": "Scan on Startup",
  "scan_on_startup_hint": "Automatically scan the library when Sublarr starts.",
  "max_items_per_run": "Max Items per Run",
  "max_items_per_run_hint": "Maximum number of wanted items processed in a single search run.",
  "max_search_attempts": "Max Search Attempts",
  "max_search_attempts_hint": "How many times Sublarr retries a failed subtitle search before giving up.",
  "auto_extract": "Auto-Extract Embedded",
  "auto_extract_hint": "Automatically extract embedded subtitles during wanted scans.",
  "anime_series_only": "Anime Series Only",
  "anime_series_only_hint": "Only search subtitles for anime series (skip live-action).",
  "anime_movies_only": "Anime Movies Only",
  "anime_movies_only_hint": "Only search subtitles for anime movies.",
  "skip_srt_no_ass": "Skip SRT When No ASS Found",
  "skip_srt_no_ass_hint": "Skip SRT subtitle downloads if no ASS subtitle was found for the episode.",
  "adaptive_backoff": "Adaptive Backoff",
  "adaptive_backoff_hint": "Increase retry delay exponentially for items that repeatedly fail.",
  "backoff_base": "Backoff Base (hours)",
  "backoff_base_hint": "Initial retry delay in hours when backoff is active.",
  "backoff_cap": "Backoff Cap (hours)",
  "backoff_cap_hint": "Maximum retry delay in hours. Delay will not exceed this value.",
  "upgrade_window": "Upgrade Window (days)",
  "upgrade_window_hint": "Only upgrade subtitles downloaded within this many days.",
  "prefer_ass": "Prefer ASS over SRT",
  "prefer_ass_hint": "Always upgrade from SRT to ASS format when a better ASS subtitle is available."
}
```

- [ ] **Zweite useTranslation-Instanz in SearchScanContent() hinzufügen**

In `SearchScanContent()` (Zeile 41), direkt nach der bestehenden Zeile `const { t } = useTranslation('common')`:
```tsx
  const { t: tS } = useTranslation('settings')
```

- [ ] **Hardcoded Strings in SearchScanContent() ersetzen**

Zeile 64 (Subheading `Bibliotheks-Scan`):
```tsx
{tS('automation_page.subheading_library_scan')}
```

Zeile 68-69 (FormGroup):
```tsx
label={tS('automation_page.scan_interval')}
hint={tS('automation_page.scan_interval_hint')}
```

Zeile 87-88 (FormGroup):
```tsx
label={tS('automation_page.scan_on_startup')}
hint={tS('automation_page.scan_on_startup_hint')}
```

Zeile 110 (Subheading `Untertitel-Suche`):
```tsx
{tS('automation_page.subheading_subtitle_search')}
```

Zeilen 151-152 (FormGroup):
```tsx
label={tS('automation_page.max_items_per_run')}
hint={tS('automation_page.max_items_per_run_hint')}
```

Zeilen 170-171:
```tsx
label={tS('automation_page.max_search_attempts')}
hint={tS('automation_page.max_search_attempts_hint')}
```

Zeilen 189-190:
```tsx
label={tS('automation_page.auto_extract')}
hint={tS('automation_page.auto_extract_hint')}
```

Zeilen 201-202:
```tsx
label={tS('automation_page.anime_series_only')}
hint={tS('automation_page.anime_series_only_hint')}
```

Zeilen 213-214:
```tsx
label={tS('automation_page.anime_movies_only')}
hint={tS('automation_page.anime_movies_only_hint')}
```

Zeilen 224-226:
```tsx
label={tS('automation_page.skip_srt_no_ass')}
hint={tS('automation_page.skip_srt_no_ass_hint')}
```

Zeilen 237-238:
```tsx
label={tS('automation_page.adaptive_backoff')}
hint={tS('automation_page.adaptive_backoff_hint')}
```

Zeilen 251-252:
```tsx
label={tS('automation_page.backoff_base')}
hint={tS('automation_page.backoff_base_hint')}
```

Zeilen 270-271:
```tsx
label={tS('automation_page.backoff_cap')}
hint={tS('automation_page.backoff_cap_hint')}
```

- [ ] **Zweite useTranslation-Instanz in UpgradeRulesContent() hinzufügen**

In `UpgradeRulesContent()` (Zeile 295), nach `const { t } = useTranslation('common')`:
```tsx
  const { t: tS } = useTranslation('settings')
```

- [ ] **Hardcoded Strings in UpgradeRulesContent() ersetzen**

Zeilen 366-367:
```tsx
label={tS('automation_page.upgrade_window')}
hint={tS('automation_page.upgrade_window_hint')}
```

Zeilen 385-386:
```tsx
label={tS('automation_page.prefer_ass')}
hint={tS('automation_page.prefer_ass_hint')}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Settings/AutomationSettings.tsx \
  frontend/src/i18n/locales/de/settings.json \
  frontend/src/i18n/locales/en/settings.json
git commit -m "feat: i18n AutomationSettings SearchScan + UpgradeRules"
```

---

### Task 3: AutomationSettings.tsx — ProcessingPipeline + Webhook + Cleanup + Section titles

**Files:**
- Modify: `frontend/src/pages/Settings/AutomationSettings.tsx` (Zeilen 401-870)
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

> **Kontext:** `ProcessingPipelineContent()` (Zeile 401) hat `useTranslation('common')` → zweite Instanz hinzufügen.
> `WebhookContent()` (Zeile 614) hat KEIN useTranslation → direkt `useTranslation('settings')` hinzufügen.
> `CleanupContent()` (Zeile 684) hat KEIN useTranslation → direkt `useTranslation('settings')` hinzufügen.
> `AutomationSettings()` (Zeile 771) hat `useTranslation('common')` → zweite Instanz hinzufügen für Section-Titles "Webhook" und "Subtitle Cleanup".

- [ ] **Keys in settings.json DE hinzufügen (in den bestehenden `automation_page` Block aus Task 2)**

```json
"auto_common_fixes": "Auto Common Fixes",
"auto_common_fixes_hint": "Häufige Untertitel-Formatierungskorrekturen automatisch nach dem Download anwenden.",
"auto_hi_removal": "Auto HI-Entfernung",
"auto_hi_removal_hint": "Hörgeschädigten-Tags aus Untertiteln automatisch nach dem Download entfernen.",
"auto_credit_removal": "Auto Abspann-Entfernung",
"auto_credit_removal_hint": "Abspann-Zeilen (Übersetzernotizen, Gruppenhinweise) automatisch aus Untertiteln entfernen.",
"sync_threshold": "Auto-Sync Score-Schwellenwert",
"sync_threshold_hint": "Minimaler Untertitel-Score um Auto-Sync nach dem Download auszulösen.",
"sync_fallback_engine": "Sync Fallback-Engine",
"sync_fallback_engine_hint": "Synchronisations-Engine wenn der primäre Sync-Versuch fehlschlägt. ffsubsync ist audiobasiert; alass ist KI-basiert.",
"nfo_export": "NFO-Sidecar exportieren",
"nfo_export_hint": "Eine NFO-Metadaten-Sidecar-Datei neben jeden heruntergeladenen Untertitel schreiben.",
"jellyfin_translate": "Bei Jellyfin-Wiedergabe übersetzen",
"jellyfin_translate_hint": "Untertitel automatisch übersetzen wenn Jellyfin die Wiedergabe einer neuen Episode startet.",
"streaming_enabled": "Streaming aktiviert",
"streaming_enabled_hint": "Subtitle-Streaming-Modus aktivieren (experimentell). Erlaubt Live-Übertragung von Untertiteln an kompatible Player.",
"post_processing_enabled": "Post-Processing aktiviert",
"post_processing_enabled_hint": "Führt nach jedem erfolgreichen Subtitle-Download den konfigurierten Shell-Befehl aus.",
"post_download_command": "Post-Download-Befehl",
"post_download_command_hint": "Shell-Befehl nach Subtitle-Download. Variablen: {subtitle_path}, {path}, {language}, {provider}, {score}, {media_type}, {video_path}",
"webhook_section": "Webhook",
"webhook_section_desc": "Steuert was automatisch passiert wenn Sonarr/Radarr eine Download-Benachrichtigung sendet.",
"webhook_delay": "Webhook-Verzögerung (Minuten)",
"webhook_delay_hint": "Wartezeit in Minuten nach einem Sonarr/Radarr-Webhook bevor gesucht wird. Gibt der Datei Zeit zu erscheinen.",
"webhook_auto_scan": "Auto-Scan bei Webhook",
"webhook_auto_scan_hint": "Bibliotheks-Scan automatisch auslösen wenn ein Sonarr/Radarr-Webhook empfangen wird.",
"webhook_auto_search": "Auto-Suche bei Webhook",
"webhook_auto_search_hint": "Untertitelsuche automatisch auslösen wenn ein Download-Webhook empfangen wird.",
"webhook_auto_translate": "Auto-Übersetzen bei Webhook",
"webhook_auto_translate_hint": "Untertitel automatisch übersetzen die über eine webhook-ausgelöste Suche gefunden wurden.",
"cleanup_section": "Untertitel-Bereinigung",
"cleanup_section_desc": "Steuert welche Untertitel bei der Bereinigung behalten werden und wie lange gelöschte Dateien aufbewahrt werden.",
"keep_languages": "Sprachen behalten",
"keep_languages_hint": "Kommagetrennte Sprachcodes die bei der Duplikat-Bereinigung behalten werden (z.B. de,en).",
"keep_formats": "Formate behalten",
"keep_formats_hint": "Kommagetrennte Untertitel-Formate die bei der Bereinigung behalten werden (z.B. ass,srt).",
"trash_retention": "Papierkorb-Aufbewahrung (Tage)",
"trash_retention_hint": "Gelöschte Untertitel für diese Anzahl von Tagen im Papierkorb behalten bevor sie endgültig gelöscht werden."
```

- [ ] **Keys in settings.json EN hinzufügen (in `automation_page` Block)**

```json
"auto_common_fixes": "Auto Common Fixes",
"auto_common_fixes_hint": "Apply common subtitle formatting fixes automatically after download.",
"auto_hi_removal": "Auto HI Removal",
"auto_hi_removal_hint": "Remove hearing-impaired tags from subtitles automatically after download.",
"auto_credit_removal": "Auto Credit Removal",
"auto_credit_removal_hint": "Remove credit lines (translator notes, group ads) from subtitles automatically.",
"sync_threshold": "Auto-Sync Score Threshold",
"sync_threshold_hint": "Minimum subtitle score required to trigger auto-sync after download.",
"sync_fallback_engine": "Sync Fallback Engine",
"sync_fallback_engine_hint": "Synchronisation engine used when the primary sync attempt fails. ffsubsync is audio-based; alass is AI-based.",
"nfo_export": "Export NFO Sidecar",
"nfo_export_hint": "Write an NFO metadata sidecar file alongside each downloaded subtitle.",
"jellyfin_translate": "Translate on Jellyfin Playback",
"jellyfin_translate_hint": "Automatically translate subtitles when Jellyfin starts playback of a new episode.",
"streaming_enabled": "Streaming Enabled",
"streaming_enabled_hint": "Enable subtitle streaming mode (experimental). Allows live transmission of subtitles to compatible players.",
"post_processing_enabled": "Post-Processing Enabled",
"post_processing_enabled_hint": "Runs the configured shell command after every successful subtitle download.",
"post_download_command": "Post-Download Command",
"post_download_command_hint": "Shell command after subtitle download. Variables: {subtitle_path}, {path}, {language}, {provider}, {score}, {media_type}, {video_path}",
"webhook_section": "Webhook",
"webhook_section_desc": "Control what happens automatically when Sonarr/Radarr sends a download notification.",
"webhook_delay": "Webhook Delay (minutes)",
"webhook_delay_hint": "Wait this many minutes after a Sonarr/Radarr webhook before searching. Allows time for the file to appear.",
"webhook_auto_scan": "Auto-Scan on Webhook",
"webhook_auto_scan_hint": "Trigger a library scan automatically when a Sonarr/Radarr webhook is received.",
"webhook_auto_search": "Auto-Search on Webhook",
"webhook_auto_search_hint": "Trigger a subtitle search automatically when a download webhook is received.",
"webhook_auto_translate": "Auto-Translate on Webhook",
"webhook_auto_translate_hint": "Automatically translate subtitles found via a webhook-triggered search.",
"cleanup_section": "Subtitle Cleanup",
"cleanup_section_desc": "Control which subtitles are kept during cleanup and how long deleted files are retained.",
"keep_languages": "Keep Languages",
"keep_languages_hint": "Comma-separated language codes to keep when cleaning up duplicates (e.g. de,en).",
"keep_formats": "Keep Formats",
"keep_formats_hint": "Comma-separated subtitle formats to keep during cleanup (e.g. ass,srt).",
"trash_retention": "Trash Retention (days)",
"trash_retention_hint": "Keep deleted subtitles in trash for this many days before permanent removal."
```

- [ ] **ProcessingPipelineContent() anpassen**

Nach `const { t } = useTranslation('common')` in `ProcessingPipelineContent()`:
```tsx
  const { t: tS } = useTranslation('settings')
```

Ersetze alle hardcoded FormGroup labels/hints in ProcessingPipelineContent (Zeilen 457-607):
```tsx
// Zeilen 458-459:
label={tS('automation_page.auto_common_fixes')}
hint={tS('automation_page.auto_common_fixes_hint')}

// Zeilen 470-471:
label={tS('automation_page.auto_hi_removal')}
hint={tS('automation_page.auto_hi_removal_hint')}

// Zeilen 482-483:
label={tS('automation_page.auto_credit_removal')}
hint={tS('automation_page.auto_credit_removal_hint')}

// Zeilen 494-495:
label={tS('automation_page.sync_threshold')}
hint={tS('automation_page.sync_threshold_hint')}

// Zeilen 514-515:
label={tS('automation_page.sync_fallback_engine')}
hint={tS('automation_page.sync_fallback_engine_hint')}

// Zeilen 537-538:
label={tS('automation_page.nfo_export')}
hint={tS('automation_page.nfo_export_hint')}

// Zeilen 549-550:
label={tS('automation_page.jellyfin_translate')}
hint={tS('automation_page.jellyfin_translate_hint')}

// Zeilen 561-562 (war deutsch hardcoded):
label={tS('automation_page.streaming_enabled')}
hint={tS('automation_page.streaming_enabled_hint')}

// Zeilen 573-574 (war deutsch hardcoded):
label={tS('automation_page.post_processing_enabled')}
hint={tS('automation_page.post_processing_enabled_hint')}

// Zeilen 585-586 (war deutsch hardcoded):
label={tS('automation_page.post_download_command')}
hint={tS('automation_page.post_download_command_hint')}
```

Auch den placeholder in der textarea (Zeile 604):
```tsx
placeholder={tS('automation_page.post_processing_enabled')}
```
→ Nein, der Placeholder `"z.B. curl -s http://localhost:7878/api/refreshMonitor"` ist ein technisches Beispiel und kann als-ist bleiben.

- [ ] **WebhookContent() anpassen (hat kein useTranslation)**

In `WebhookContent()` (Zeile 614), erste Zeile des Funktionskörpers:
```tsx
  const { t } = useTranslation('settings')
```

Import am Anfang der Datei ist bereits vorhanden (`useTranslation` ist schon importiert).

Ersetze alle hardcoded FormGroup labels/hints in WebhookContent:
```tsx
// Zeilen 625-626:
label={t('automation_page.webhook_delay')}
hint={t('automation_page.webhook_delay_hint')}

// Zeilen 644-645:
label={t('automation_page.webhook_auto_scan')}
hint={t('automation_page.webhook_auto_scan_hint')}

// Zeilen 656-657:
label={t('automation_page.webhook_auto_search')}
hint={t('automation_page.webhook_auto_search_hint')}

// Zeilen 668-669:
label={t('automation_page.webhook_auto_translate')}
hint={t('automation_page.webhook_auto_translate_hint')}
```

- [ ] **CleanupContent() anpassen (hat kein useTranslation)**

In `CleanupContent()` (Zeile 684), erste Zeile des Funktionskörpers:
```tsx
  const { t } = useTranslation('settings')
```

Ersetze alle hardcoded FormGroup labels/hints:
```tsx
// Zeilen 695-696:
label={t('automation_page.keep_languages')}
hint={t('automation_page.keep_languages_hint')}

// Zeilen 713-714:
label={t('automation_page.keep_formats')}
hint={t('automation_page.keep_formats_hint')}

// Zeilen 731-732:
label={t('automation_page.trash_retention')}
hint={t('automation_page.trash_retention_hint')}
```

- [ ] **AutomationSettings() Section-Titles anpassen**

In `AutomationSettings()` (Zeile 771), nach `const { t } = useTranslation('common')`:
```tsx
  const { t: tS } = useTranslation('settings')
```

Webhook section (Zeile 813-815):
```tsx
title={tS('automation_page.webhook_section')}
description={tS('automation_page.webhook_section_desc')}
```

Subtitle Cleanup section (Zeile 838-839):
```tsx
title={tS('automation_page.cleanup_section')}
description={tS('automation_page.cleanup_section_desc')}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Settings/AutomationSettings.tsx \
  frontend/src/i18n/locales/de/settings.json \
  frontend/src/i18n/locales/en/settings.json
git commit -m "feat: i18n AutomationSettings Pipeline + Webhook + Cleanup"
```

---

### Task 4: ScoringTab.tsx

**Files:**
- Modify: `frontend/src/pages/Settings/ScoringTab.tsx`
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

> **Kontext:** `ScoringTab()` hat kein `useTranslation`. Die `WEIGHT_LABELS` und `WEIGHT_HINTS` Objekte auf Modulebene sind technische Labels (Word Count, Season Match usw.) — diese bleiben als englische Konstanten. Zu übersetzen sind: SettingsSection Titel/Descriptions, die 2 Key-FormGroups "Prefer ASS/SSA" und "Penalize MT", sowie die 4 Release-Group- und MT-FormGroups im sichtbaren Bereich.

- [ ] **Keys in settings.json DE hinzufügen**

```json
"scoring_tab": {
  "presets_title": "Schnellstart: Preset anwenden",
  "presets_desc": "Ein Klick um ein abgestimmtes Scoring-Profil anzuwenden. Deine aktuellen Gewichtungen werden ersetzt.",
  "what_matters_title": "Was am meisten zählt",
  "what_matters_desc": "Die wirkungsvollsten Einstellungen für Untertitel-Qualität. Diese zuerst ändern.",
  "prefer_ass": "ASS/SSA-Format bevorzugen",
  "prefer_ass_hint": "Gibt ASS- und SSA-Untertiteln gegenüber einfachem SRT einen +30 Score-Bonus. Empfohlen für Anime.",
  "penalize_mt": "Maschinell übersetzte Untertitel bestrafen",
  "penalize_mt_hint": "Wendet einen −30 Score-Malus auf Untertitel an die als maschinell übersetzt markiert sind.",
  "release_group_title": "Release-Gruppen-Präferenzen",
  "release_group_desc": "Untertitel von bestimmten Gruppen bevorzugen (Score-Bonus) oder unerwünschte Gruppen blockieren.",
  "preferred_groups": "Bevorzugte Gruppen",
  "blocked_groups": "Blockierte Gruppen",
  "blocked_groups_hint": "Kommagetrennte Gruppen die vollständig aus allen Ergebnissen ausgeschlossen werden.",
  "prefer_bonus": "Bevorzugungsbonus (Score-Punkte)",
  "prefer_bonus_hint": "Zusätzliche Score-Punkte für Untertitel einer bevorzugten Gruppe.",
  "mt_penalty": "MT Score-Malus",
  "mt_penalty_hint": "Malus für maschinell übersetzte Untertitel (−50 bis 0; 0 = deaktiviert).",
  "mt_threshold": "MT Konfidenz-Schwellenwert",
  "mt_threshold_hint": "Minimale Konfidenz % (0–100) um einen Untertitel als maschinell übersetzt zu markieren."
}
```

- [ ] **Keys in settings.json EN hinzufügen**

```json
"scoring_tab": {
  "presets_title": "Quick Start: Apply a Preset",
  "presets_desc": "One click to apply a tuned scoring profile. Your current weights will be replaced.",
  "what_matters_title": "What Matters Most",
  "what_matters_desc": "The most impactful settings for subtitle quality. Change these first.",
  "prefer_ass": "Prefer ASS/SSA format",
  "prefer_ass_hint": "Gives a +30 score bonus to ASS and SSA subtitles over plain SRT. Recommended for anime.",
  "penalize_mt": "Penalize machine-translated subtitles",
  "penalize_mt_hint": "Applies a −30 score penalty to subtitles flagged as machine-translated.",
  "release_group_title": "Release Group Preferences",
  "release_group_desc": "Prefer subtitles from specific groups (score bonus) or block groups you dislike.",
  "preferred_groups": "Preferred Groups",
  "blocked_groups": "Blocked Groups",
  "blocked_groups_hint": "Comma-separated groups to exclude from all results entirely.",
  "prefer_bonus": "Prefer Bonus (score pts)",
  "prefer_bonus_hint": "Extra score points for subtitles matching a preferred group.",
  "mt_penalty": "MT Score Penalty",
  "mt_penalty_hint": "Penalty applied to machine-translated subtitles (−50 to 0; 0 = disabled).",
  "mt_threshold": "MT Confidence Threshold",
  "mt_threshold_hint": "Minimum confidence % (0–100) to flag a subtitle as machine-translated."
}
```

- [ ] **useTranslation in ScoringTab() hinzufügen**

`useTranslation` ist bereits importiert (Zeile 22 — prüfen). Falls nicht, hinzufügen:
```tsx
import { useTranslation } from 'react-i18next'
```

In `ScoringTab()` (Zeile 114), nach den `useState`-Hooks als erste Zeile:
```tsx
  const { t } = useTranslation('settings')
```

- [ ] **Hardcoded Strings ersetzen**

Presets SettingsSection (Zeile 291-293):
```tsx
title={t('scoring_tab.presets_title')}
description={t('scoring_tab.presets_desc')}
```

What Matters SettingsSection (Zeile 334-336):
```tsx
title={t('scoring_tab.what_matters_title')}
description={t('scoring_tab.what_matters_desc')}
```

FormGroup Prefer ASS (Zeilen 339-341):
```tsx
label={t('scoring_tab.prefer_ass')}
hint={t('scoring_tab.prefer_ass_hint')}
```

FormGroup Penalize MT (Zeilen 351-352):
```tsx
label={t('scoring_tab.penalize_mt')}
hint={t('scoring_tab.penalize_mt_hint')}
```

Release Group SettingsSection (Zeilen 364-366):
```tsx
title={t('scoring_tab.release_group_title')}
description={t('scoring_tab.release_group_desc')}
```

FormGroup Preferred Groups (Zeile 386):
```tsx
label={t('scoring_tab.preferred_groups')}
```

> Hinweis: Zeile 387 hat einen dynamischen hint mit `${rgBonus}` — diesen NICHT übersetzen (komplexe Interpolation, low-value).

FormGroup Blocked Groups (Zeilen 402-403):
```tsx
label={t('scoring_tab.blocked_groups')}
hint={t('scoring_tab.blocked_groups_hint')}
```

FormGroup Prefer Bonus (Zeilen 419-420):
```tsx
label={t('scoring_tab.prefer_bonus')}
hint={t('scoring_tab.prefer_bonus_hint')}
```

FormGroup MT Score Penalty (Zeilen 651-652):
```tsx
label={t('scoring_tab.mt_penalty')}
hint={t('scoring_tab.mt_penalty_hint')}
```

FormGroup MT Confidence Threshold (Zeilen 673-674):
```tsx
label={t('scoring_tab.mt_threshold')}
hint={t('scoring_tab.mt_threshold_hint')}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Settings/ScoringTab.tsx \
  frontend/src/i18n/locales/de/settings.json \
  frontend/src/i18n/locales/en/settings.json
git commit -m "feat: i18n ScoringTab"
```

---

### Task 5: BackupTab.tsx

**Files:**
- Modify: `frontend/src/pages/Settings/BackupTab.tsx`
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

> **Kontext:** Kein useTranslation vorhanden. Hardcoded englische h3-Titel, Button-Texte, SettingRow-Labels/Descriptions.

- [ ] **Keys in settings.json DE hinzufügen**

```json
"backup_tab": {
  "create_title": "Vollständiges Backup erstellen",
  "create_desc": "Erstellt ein ZIP-Archiv mit Datenbank und Konfiguration.",
  "creating": "Erstelle...",
  "create_button": "Backup erstellen",
  "existing_title": "Vorhandene Backups",
  "no_backups": "Keine Backups gefunden. Oben eines erstellen.",
  "download": "Download",
  "restore_title": "Aus Datei wiederherstellen",
  "restore_warning": "API-Schlüssel müssen nach der Wiederherstellung neu eingegeben werden.",
  "select_zip": "ZIP-Datei auswählen",
  "restore_button": "Wiederherstellen",
  "retention_title": "Aufbewahrungsrichtlinie",
  "retention_desc": "Der integrierte Scheduler läuft täglich und bereinigt Backups entsprechend der unten angegebenen Aufbewahrungsanzahl.",
  "backup_dir": "Backup-Verzeichnis",
  "backup_dir_desc": "Absoluter Pfad für Backup-Speicher",
  "daily_backups": "Tägliche Backups",
  "daily_backups_desc": "Anzahl der täglich zu behaltenden Backups",
  "weekly_backups": "Wöchentliche Backups",
  "weekly_backups_desc": "Anzahl der wöchentlich zu behaltenden Backups",
  "monthly_backups": "Monatliche Backups",
  "monthly_backups_desc": "Anzahl der monatlich zu behaltenden Backups"
}
```

- [ ] **Keys in settings.json EN hinzufügen**

```json
"backup_tab": {
  "create_title": "Create Full Backup",
  "create_desc": "Creates a ZIP archive containing the database and configuration.",
  "creating": "Creating...",
  "create_button": "Create Backup",
  "existing_title": "Existing Backups",
  "no_backups": "No backups found. Create one above.",
  "download": "Download",
  "restore_title": "Restore from File",
  "restore_warning": "API keys will need to be re-entered after restore.",
  "select_zip": "Select ZIP File",
  "restore_button": "Restore",
  "retention_title": "Retention Policy",
  "retention_desc": "The built-in scheduler runs daily and prunes backups according to the retention counts below.",
  "backup_dir": "Backup Directory",
  "backup_dir_desc": "Absolute path for backup storage",
  "daily_backups": "Daily Backups",
  "daily_backups_desc": "Number of daily backups to keep",
  "weekly_backups": "Weekly Backups",
  "weekly_backups_desc": "Number of weekly backups to keep",
  "monthly_backups": "Monthly Backups",
  "monthly_backups_desc": "Number of monthly backups to keep"
}
```

- [ ] **useTranslation in BackupTab.tsx importieren und verwenden**

Am Anfang der Datei nach den bestehenden Imports:
```tsx
import { useTranslation } from 'react-i18next'
```

In `BackupTab()`, erste Zeile nach `const { data: backupsData, isLoading } = useFullBackups()`:
```tsx
  const { t } = useTranslation('settings')
```

- [ ] **Hardcoded Strings ersetzen**

Ersetze alle hardcoded Strings in BackupTab.tsx:
```tsx
// h3 Create Full Backup (Zeile 90):
{t('backup_tab.create_title')}

// p Creates a ZIP... (Zeile 93):
{t('backup_tab.create_desc')}

// Button text (Zeile 106):
{createBackup.isPending ? t('backup_tab.creating') : t('backup_tab.create_button')}

// h3 Existing Backups (Zeile 113):
{t('backup_tab.existing_title')}

// No backups found (Zeile 122):
{t('backup_tab.no_backups')}

// Download link text (Zeile 152):
{t('backup_tab.download')}

// h3 Restore from File (Zeile 163):
{t('backup_tab.restore_title')}

// API keys warning (Zeile 168):
{t('backup_tab.restore_warning')}

// Select ZIP File button (Zeile 178):
{t('backup_tab.select_zip')}

// Restore button (Zeile 203):
{restoreBackup.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
{t('backup_tab.restore_button')}

// h3 Retention Policy (Zeile 216):
{t('backup_tab.retention_title')}

// p scheduler runs daily (Zeile 218):
{t('backup_tab.retention_desc')}

// SettingRow Backup Directory (Zeile 221):
label={t('backup_tab.backup_dir')}
description={t('backup_tab.backup_dir_desc')}

// SettingRow Daily Backups (Zeile 237):
label={t('backup_tab.daily_backups')}
description={t('backup_tab.daily_backups_desc')}

// SettingRow Weekly Backups (Zeile 253):
label={t('backup_tab.weekly_backups')}
description={t('backup_tab.weekly_backups_desc')}

// SettingRow Monthly Backups (Zeile 269):
label={t('backup_tab.monthly_backups')}
description={t('backup_tab.monthly_backups_desc')}
```

> Hinweis: Die toast-Strings in `handleCreate` und `handleRestoreFromFile` (Zeilen 65, 67, 75-76, 78-79) sind Backend-Messages, nicht UI-Labels — diese können englisch bleiben.

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Settings/BackupTab.tsx \
  frontend/src/i18n/locales/de/settings.json \
  frontend/src/i18n/locales/en/settings.json
git commit -m "feat: i18n BackupTab"
```

---

### Task 6: AnidbTab.tsx + CacheTab.tsx

**Files:**
- Modify: `frontend/src/pages/Settings/AnidbTab.tsx`
- Modify: `frontend/src/pages/Settings/CacheTab.tsx`
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

- [ ] **Keys in settings.json DE hinzufügen**

```json
"anidb_tab": {
  "enable": "AniDB aktivieren",
  "enable_desc": "AniDB für Anime-Metadaten-Lookups verwenden",
  "cache_ttl": "Cache-TTL (Tage)",
  "cache_ttl_desc": "Tage für die AniDB-Antworten gecacht werden",
  "custom_field": "Benutzerdefinierter Feldname",
  "custom_field_desc": "Benutzerdefinierter Metadaten-Feldname für AniDB-ID",
  "fallback_mapping": "Fallback auf Mapping",
  "fallback_mapping_desc": "AniDB-zu-Sonarr-Mapping verwenden wenn direkte Suche fehlschlägt"
},
"cache_tab": {
  "ffprobe_label": "ffprobe-Cache",
  "ffprobe_cleanup_btn": "Veraltete Einträge bereinigen",
  "vacuum_label": "Datenbank-Vacuum",
  "vacuum_desc": "Ungenutzten Speicher freigeben und die SQLite-Datenbank defragmentieren.",
  "vacuum_confirm_title": "Datenbank-VACUUM ausführen?",
  "vacuum_confirm_desc": "Dies kann bei großen Datenbanken einen Moment dauern. Die App bleibt verfügbar.",
  "vacuum_cancel": "Abbrechen",
  "vacuum_run": "VACUUM ausführen"
}
```

- [ ] **Keys in settings.json EN hinzufügen**

```json
"anidb_tab": {
  "enable": "Enable AniDB",
  "enable_desc": "Use AniDB for anime metadata lookups",
  "cache_ttl": "Cache TTL (days)",
  "cache_ttl_desc": "Days to cache AniDB responses",
  "custom_field": "Custom Field Name",
  "custom_field_desc": "Custom metadata field name for AniDB ID",
  "fallback_mapping": "Fallback to Mapping",
  "fallback_mapping_desc": "Use AniDB-to-Sonarr mapping when direct lookup fails"
},
"cache_tab": {
  "ffprobe_label": "ffprobe cache",
  "ffprobe_cleanup_btn": "Clean up stale entries",
  "vacuum_label": "Database vacuum",
  "vacuum_desc": "Reclaim unused space and defragment the SQLite database.",
  "vacuum_confirm_title": "Run database VACUUM?",
  "vacuum_confirm_desc": "This may take a moment on large databases. The app remains available.",
  "vacuum_cancel": "Cancel",
  "vacuum_run": "Run VACUUM"
}
```

- [ ] **useTranslation in AnidbTab.tsx hinzufügen**

Import am Anfang der Datei hinzufügen:
```tsx
import { useTranslation } from 'react-i18next'
```

In `AnidbTab()`, erste Zeile nach dem `useConfig()` Hook:
```tsx
  const { t } = useTranslation('settings')
```

Alle 4 SettingRow label/description Props ersetzen:
```tsx
// Zeile 49-50:
label={t('anidb_tab.enable')}
description={t('anidb_tab.enable_desc')}

// Zeile 60-61:
label={t('anidb_tab.cache_ttl')}
description={t('anidb_tab.cache_ttl_desc')}

// Zeile 80-81:
label={t('anidb_tab.custom_field')}
description={t('anidb_tab.custom_field_desc')}

// Zeile 100-101:
label={t('anidb_tab.fallback_mapping')}
description={t('anidb_tab.fallback_mapping_desc')}
```

- [ ] **useTranslation in CacheTab.tsx hinzufügen**

Import am Anfang der Datei hinzufügen:
```tsx
import { useTranslation } from 'react-i18next'
```

In `CacheTab()`, erste Zeile nach dem `useState`:
```tsx
  const { t } = useTranslation('settings')
```

Alle Strings ersetzen:
```tsx
// SettingRow ffprobe (Zeile 17-18):
label={t('cache_tab.ffprobe_label')}
description={`${stats?.count ?? '…'} entries cached`}
// (description bleibt englisch — dynamischer Wert mit Zahl)

// Button Text (Zeile 34):
{cleanup.isPending && <Loader2 size={13} className="animate-spin" />}
{t('cache_tab.ffprobe_cleanup_btn')}

// SettingRow vacuum (Zeile 39-41):
label={t('cache_tab.vacuum_label')}
description={t('cache_tab.vacuum_desc')}

// Button Run VACUUM (Zeile 56):
{vacuum.isPending && <Loader2 size={13} className="animate-spin" />}
{t('cache_tab.vacuum_run')}

// Dialog h3 (Zeile 73):
{t('cache_tab.vacuum_confirm_title')}

// Dialog p (Zeile 75-76):
{t('cache_tab.vacuum_confirm_desc')}

// Cancel button (Zeile 85):
{t('cache_tab.vacuum_cancel')}

// Confirm button (Zeile 93):
{t('cache_tab.vacuum_run')}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add \
  frontend/src/pages/Settings/AnidbTab.tsx \
  frontend/src/pages/Settings/CacheTab.tsx \
  frontend/src/i18n/locales/de/settings.json \
  frontend/src/i18n/locales/en/settings.json
git commit -m "feat: i18n AnidbTab + CacheTab"
```

---

### Task 7: Trash.tsx

**Files:**
- Modify: `frontend/src/pages/Trash.tsx`
- Modify: `frontend/src/i18n/locales/de/common.json`
- Modify: `frontend/src/i18n/locales/en/common.json`

> **Kontext:** Kein useTranslation. Alle Strings sind deutsch hardcoded (außer "Restore" Button-Text der gemischt ist). Da Trash eine Page ist, wird der `common` Namespace verwendet.

- [ ] **Keys in common.json DE hinzufügen**

Am Ende der Datei (vor dem schließenden `}`), neues Objekt hinzufügen:

```json
"trash": {
  "page_title": "Papierkorb",
  "loading": "Wird geladen…",
  "empty": "Papierkorb ist leer",
  "mkv_restore_title": "Video-Backup wiederherstellen",
  "mkv_restore_desc": "Die remuxte Video-Datei wird durch die Sicherung ersetzt (atomarer Tausch).",
  "mkv_no_video": "Original-Video nicht mehr auf Disk gefunden — Pfad kann nicht aufgelöst werden.",
  "delete_sidecars_label": "Passende Sidecar-Batches ebenfalls löschen",
  "cancel": "Abbrechen",
  "restore": "Wiederherstellen",
  "unknown_series": "Unbekannte Serie",
  "file_singular": "Datei",
  "file_plural": "Dateien",
  "deleted_on": "gelöscht",
  "expires": "läuft ab",
  "restore_btn": "Wiederherstellen",
  "delete_btn": "Löschen",
  "delete_confirm": "Endgültig löschen",
  "show_files": "{{count}} Dateien anzeigen ▼",
  "hide_files": "Dateien ausblenden ▲",
  "subtitle_sidecars": "Untertitel-Sidecars",
  "video_backups": "Video-Backups (Remux)",
  "original_not_found": "Original nicht gefunden",
  "expires_label": "läuft ab"
}
```

- [ ] **Keys in common.json EN hinzufügen**

```json
"trash": {
  "page_title": "Trash",
  "loading": "Loading…",
  "empty": "Trash is empty",
  "mkv_restore_title": "Restore Video Backup",
  "mkv_restore_desc": "The remuxed video file will be replaced by the backup (atomic swap).",
  "mkv_no_video": "Original video no longer found on disk — path cannot be resolved.",
  "delete_sidecars_label": "Also delete matching sidecar batches",
  "cancel": "Cancel",
  "restore": "Restore",
  "unknown_series": "Unknown Series",
  "file_singular": "file",
  "file_plural": "files",
  "deleted_on": "deleted",
  "expires": "expires",
  "restore_btn": "Restore",
  "delete_btn": "Delete",
  "delete_confirm": "Delete permanently",
  "show_files": "Show {{count}} files ▼",
  "hide_files": "Hide files ▲",
  "subtitle_sidecars": "Subtitle Sidecars",
  "video_backups": "Video Backups (Remux)",
  "original_not_found": "Original not found",
  "expires_label": "expires"
}
```

- [ ] **useTranslation in Trash.tsx importieren**

Am Anfang der Datei nach den bestehenden Imports:
```tsx
import { useTranslation } from 'react-i18next'
```

- [ ] **useTranslation hook in jede betroffene Funktion hinzufügen**

In `MkvRestoreModal()` (Zeile 36), erste Zeile des Funktionskörpers:
```tsx
  const { t } = useTranslation('common')
```

In `SidecarBatchCard()` (Zeile 125), erste Zeile:
```tsx
  const { t } = useTranslation('common')
```

In `MkvBackupCard()` (Zeile 227), erste Zeile:
```tsx
  const { t } = useTranslation('common')
```

In `TrashPage()` (Zeile 271), erste Zeile:
```tsx
  const { t } = useTranslation('common')
```

- [ ] **Hardcoded Strings in MkvRestoreModal() ersetzen**

```tsx
// Zeile 57 — h2:
{t('trash.mkv_restore_title')}

// Zeile 64 — p:
{t('trash.mkv_restore_desc')}

// Zeile 86 — Warnung kein Video:
{t('trash.mkv_no_video')}

// Zeile 97 — Checkbox-Label:
{t('trash.delete_sidecars_label')}

// Zeile 105 — Cancel button:
{t('trash.cancel')}

// Zeile 115 — Restore button (war "Wiederherstellen"):
{restore.isPending ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
{t('trash.restore')}
```

- [ ] **Hardcoded Strings in SidecarBatchCard() ersetzen**

```tsx
// Zeile 139 — "Unbekannte Serie":
{batch.series_name || t('trash.unknown_series')}

// Zeile 150 — Datei-Zähler:
{batch.file_count} {batch.file_count === 1 ? t('trash.file_singular') : t('trash.file_plural')} · {formatBytes(batch.size_bytes)} · {t('trash.deleted_on')} {formatDate(batch.created_at)}

// Zeile 154 — expires:
{t('trash.expires')} {formatDate(batch.expires_at)}

// Zeile 165 — title="Wiederherstellen":
title={t('trash.restore_btn')}

// Zeile 168 — Button text "Restore" (war englisch trotz deutschem title):
{restore.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
{t('trash.restore_btn')}

// Zeile 179 — "Löschen":
{remove.isPending ? <Loader2 size={12} className="animate-spin" /> : t('trash.delete_btn')}

// Zeile 194 — title="Endgültig löschen":
title={t('trash.delete_confirm')}

// Zeile 208 — show/hide files:
{expanded ? t('trash.hide_files') : t('trash.show_files', { count: batch.files.length })}
```

- [ ] **Hardcoded Strings in MkvBackupCard() ersetzen**

```tsx
// Zeile 241 — "läuft ab":
{backup.expires_at ? ` · ${t('trash.expires_label')} ${formatDate(backup.expires_at)}` : ''}

// Zeile 249 — "Original nicht gefunden":
{t('trash.original_not_found')}

// Zeile 259 — Restore button text (war "Restore" englisch):
{t('trash.restore')}
```

- [ ] **Hardcoded Strings in TrashPage() ersetzen**

```tsx
// Zeile 283 — h1 "Papierkorb":
{t('trash.page_title')}

// Zeile 288 — loading / summary:
{isLoading
  ? t('trash.loading')
  : `${sidecarCount} Sidecar-${sidecarCount === 1 ? 'Batch' : 'Batches'} · ${mkvCount} MKV-${mkvCount === 1 ? 'Backup' : 'Backups'} · ${formatBytes(totalSize)} gesamt`}
```

> Hinweis: Der Summary-String mit "Sidecar-Batch/Batches", "MKV-Backup/Backups" und "gesamt" verwendet englische Fachbegriffe (Sidecar, MKV, Batch) die als Produktnamen/Technikbegriffe üblicherweise nicht lokalisiert werden. Er bleibt daher bewusst als-ist außer dem `t('trash.loading')`.

```tsx
// Zeile 305-307 — empty state p:
{t('trash.empty')}

// Zeile 317 — h2 "Untertitel-Sidecars":
{t('trash.subtitle_sidecars')}

// Zeile 337 — h2 "Video-Backups (Remux)":
{t('trash.video_backups')}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Trash.tsx \
  frontend/src/i18n/locales/de/common.json \
  frontend/src/i18n/locales/en/common.json
git commit -m "feat: i18n Trash page"
```

---

### Task 8: Lint + TypeCheck + Tests + Push

**Files:** Keine Änderungen — Verifikation

- [ ] **ESLint ausführen**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run lint
```

Erwartete Ausgabe: Nur Warnings (keine Errors). Falls Errors: beheben, commit mit `fix: i18n lint fixes`.

- [ ] **TypeScript-Check ausführen**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit
```

Erwartete Ausgabe: Keine Ausgabe (= kein Fehler).

- [ ] **Frontend-Tests ausführen**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run
```

Erwartete Ausgabe: Alle Tests grün.

Falls GeneralSettings-Tests fehlschlagen weil sie hardcoded English-Strings erwarten: Test-Expectations auf Translation-Keys aktualisieren (analog zu SystemSettings.test.tsx Änderung aus dem vorherigen Plan).

- [ ] **Commit falls Fixes nötig**

```bash
git add -A && git commit -m "fix: i18n lint/test fixes"
```

- [ ] **Branch pushen**

```bash
cd D:/Sublarr_Projekt/Sublarr && git push
```

- [ ] **Ergebnis prüfen**

```bash
git log --oneline origin/feat/i18n-complete | head -10
```
