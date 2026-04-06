# Settings Redesign — Plan 3: Field Treatment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the new UX patterns to every settings page: add inline hints to normal fields, add `advanced` badge + tooltip to power-user fields, replace free-text inputs with `<select>` dropdowns where the value set is known, and build the language pill selector for Sprachen & Profile.

**Architecture:** Pure frontend changes. Each task targets one settings page. The `FormGroup` `advanced` prop and `SettingsSection` `advancedCount` prop from Plan 1 are used throughout. No backend changes. All hint text is stored in i18n files (EN + DE).

**Prerequisite:** Plans 1 and 2 must be completed first.

**Tech Stack:** React 19, TypeScript, react-i18next (namespace `settings`), existing `settingsInputStyle` from `@/styles/settingsShared`

**Branch:** `feature/settings-redesign`

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/i18n/locales/en/settings.json` | Add hint text for every field on every page |
| `frontend/src/i18n/locales/de/settings.json` | Same in German |
| `frontend/src/pages/settings/GeneralSettings.tsx` | Hints, select fields, advanced props |
| `frontend/src/pages/settings/ConnectionsSettings.tsx` | Hints, advanced props |
| `frontend/src/pages/settings/SubtitlesSettings.tsx` | Language pill selector, hints, selects |
| `frontend/src/pages/settings/ScoringTab.tsx` | Hints, advanced props |
| `frontend/src/pages/settings/ProvidersSettings.tsx` | Hints, advanced props |
| `frontend/src/pages/settings/AutomationSettings.tsx` | Hints, selects, advanced props (Suche & Scan, Upgrades) |
| `frontend/src/pages/settings/AutomationPostProcessingPage.tsx` | Hints, selects, advanced props |
| `frontend/src/pages/settings/NotificationsSettings.tsx` | Hints, advanced props |
| `frontend/src/pages/settings/SystemSettings.tsx` | Hints, advanced props |
| `frontend/src/pages/settings/BackupTab.tsx` | Hints |
| `frontend/src/pages/settings/CleanupSettings.tsx` | Hints |

---

## Shared Pattern Reference

Before starting, internalize this pattern. Every task repeats it:

**Normal field (hint inline):**
```tsx
<FormGroup
  label={t('page.field_label')}
  hint={t('page.field_label_hint')}
  htmlFor="field-id"
>
  <input id="field-id" ... />
</FormGroup>
```

**Advanced field (hint as tooltip):**
```tsx
<FormGroup
  label={t('page.field_label')}
  hint={t('page.field_label_hint')}
  advanced
  htmlFor="field-id"
>
  <input id="field-id" ... />
</FormGroup>
```

**SettingsSection with advanced count:**
```tsx
<SettingsSection
  title={t('page.section_title')}
  advancedCount={3}
  advanced={
    <>
      <FormGroup label="..." hint="..." advanced> ... </FormGroup>
      <FormGroup label="..." hint="..." advanced> ... </FormGroup>
      <FormGroup label="..." hint="..." advanced> ... </FormGroup>
    </>
  }
>
  {/* normal fields */}
</SettingsSection>
```

**Select field (replaces text input):**
```tsx
<select
  value={config?.field_name ?? 'default'}
  onChange={(e) => save({ field_name: e.target.value })}
  style={{ ...settingsInputStyle, width: '200px' }}
>
  <option value="opt1">{t('page.opt1_label')}</option>
  <option value="opt2">{t('page.opt2_label')}</option>
</select>
```

---

### Task 1: Add all hint i18n keys (EN + DE)

**Files:**
- Modify: `frontend/src/i18n/locales/en/settings.json`
- Modify: `frontend/src/i18n/locales/de/settings.json`

This is the largest single step. Add hint keys for every field on every settings page. Hints follow the naming convention `{page_key}.{field_key}_hint`.

- [ ] **Step 1: Add General page hints to EN settings.json**

Under `"general"` add:

```json
"port_hint": "TCP port the Sublarr server listens on. Requires restart to take effect.",
"api_key_hint": "Protects all API endpoints. Leave empty to disable authentication.",
"log_level_hint": "Controls server log verbosity. Use DEBUG only for troubleshooting — it generates large log files.",
"media_path_hint": "Root directory where your media library is stored. Used for path resolution when Sonarr/Radarr path mapping is not configured.",
"db_path_hint": "Path to the SQLite database file. Changing this requires manually moving the existing file.",
"scan_engine_hint": "Tool used to probe video file metadata. Auto selects the best available. Switch to mediainfo if ffprobe causes issues."
```

Under `"general"` add advanced hints:

```json
"log_format_hint": "json is useful for log aggregation tools (Loki, Splunk). text is human-readable.",
"cors_origins_hint": "Comma-separated list of allowed CORS origins for the API. Only needed when accessing Sublarr from a different domain.",
"db_pool_size_hint": "Maximum number of SQLite connections in the pool. Increase only if you see 'database is locked' errors under heavy load.",
"redis_url_hint": "Redis connection URL. Leave empty to use the built-in in-memory queue.",
"plugins_dir_hint": "Directory where Sublarr looks for installed plugins. Defaults to the config directory."
```

- [ ] **Step 2: Add Automation > Suche & Scan hints to EN settings.json**

Under `"wanted_tab"` add:

```json
"scan_interval_hint": "How often Sublarr scans the library for new media without subtitles. Set to 0 to disable scheduled scanning.",
"scan_on_startup_hint": "Immediately scan the entire library when Sublarr starts. Useful after adding new media.",
"search_interval_hint": "How often Sublarr searches providers for items in the Wanted list. Set to 0 to disable.",
"search_on_startup_hint": "Search providers for all Wanted items when Sublarr starts.",
"max_search_attempts_hint": "Stop automatically searching for a subtitle after this many failed attempts. The item stays in Wanted and can be searched manually at any time.",
"skip_srt_hint": "When no ASS subtitle is found, do not download an SRT fallback. Useful for anime where ASS formatting (signs, typesetting) is important.",
"anime_only_hint": "Restrict library scanning to Sonarr entries tagged as anime. Leave off unless you specifically want to exclude non-anime series.",
"anime_movies_hint": "Include Radarr entries tagged as anime in anime-only scans.",
"max_items_per_run_hint": "Limit how many Wanted items are processed per search cycle. Reduces provider load for large libraries.",
"backoff_base_hint": "Multiplier for wait time between retries. After each failed attempt the wait doubles. Higher values mean longer gaps before retrying.",
"backoff_cap_hint": "Maximum wait time in hours between retry attempts regardless of how many times the item has failed."
```

- [ ] **Step 3: Add Automation > Upgrades hints to EN settings.json**

Under `"automation"` add:

```json
"upgrade_enabled_hint": "Automatically replace subtitles with better-scoring ones when found.",
"prefer_ass_hint": "Prefer ASS format over SRT when upgrading. ASS supports styled text, useful for anime.",
"min_score_delta_hint": "Minimum score improvement required to replace an existing subtitle. Prevents unnecessary replacements for marginal improvements.",
"upgrade_window_hint": "Only upgrade subtitles downloaded within this many days. Older subtitles are kept even if a better one is found.",
"upgrade_scan_interval_hint": "How often to scan for upgrade opportunities. Independent of the main search interval."
```

- [ ] **Step 4: Add Provider hints to EN settings.json**

Under `"providers"` (or create if missing) add:

```json
"search_timeout_hint": "Maximum time in seconds to wait for a provider response before giving up.",
"cache_ttl_hint": "How long to cache provider search results. Cached results are returned instantly without hitting the provider.",
"rate_limit_enabled_hint": "Throttle requests to providers that have rate limits. Recommended to keep enabled.",
"max_concurrent_hint": "Maximum number of provider searches running simultaneously. Lower values reduce provider ban risk.",
"download_delay_hint": "Wait this many milliseconds between requests to the same provider. Helps avoid rate limiting.",
"max_file_size_hint": "Reject subtitle files larger than this size in kilobytes. Oversized files are usually corrupt or mis-labelled.",
"auto_prioritize_hint": "Automatically reorder providers based on historic success rate. Disable for manual control only.",
"circuit_breaker_hint": "Temporarily disable a provider after consecutive failures. It will recover automatically after the cooldown period.",
"dynamic_timeout_hint": "Increase timeout for slow providers based on their historic response time. Reduces timeouts for consistently slow providers."
```

- [ ] **Step 5: Add Subtitle > Format & Naming hints to EN settings.json**

Under `"subtitles"` (or create if missing) add:

```json
"hi_preference_hint": "Hearing Impaired subtitles contain sound descriptions like [door creaks]. Choose whether to prefer, include, exclude or require them.",
"forced_preference_hint": "Forced subtitles show only foreign-language dialogue. Choose whether to search for them alongside or instead of full subtitles.",
"use_embedded_hint": "Count embedded subtitle tracks inside video files as 'available'. If disabled, Sublarr always searches for sidecar files.",
"auto_extract_hint": "Automatically extract embedded subtitle tracks as sidecar files when a video is first scanned.",
"skip_srt_no_ass_hint": "When the best available subtitle is SRT but ASS is preferred, skip downloading it. The item stays in Wanted until ASS is found.",
"lang_code_format_hint": "Format used for subtitle language codes in filenames. Alpha-2 (de) is most compatible. Alpha-3 (deu) is required by some players.",
"suffix_separator_hint": "Character between the video filename and the language code. Default is a dot (Movie.de.srt).",
"hi_suffix_hint": "Suffix added to Hearing Impaired subtitle filenames. Default: .hi (Movie.de.hi.srt).",
"forced_suffix_hint": "Suffix added to Forced subtitle filenames. Default: .forced (Movie.de.forced.srt)."
```

- [ ] **Step 6: Add Post-Processing hints to EN settings.json**

Under `"post_processing"` (or create if missing) add:

```json
"enabled_hint": "Enable the post-processing pipeline. When disabled, no automatic fixes are applied after download.",
"auto_sync_hint": "Automatically synchronize subtitle timing to the video after download using the selected engine.",
"sync_engine_hint": "Synchronization tool to use. alass aligns by audio similarity, ffsubsync by speech detection. auto tries both.",
"common_fixes_hint": "Apply common subtitle fixes after download: remove duplicate lines, fix encoding issues, normalize formatting.",
"hi_removal_hint": "Automatically remove Hearing Impaired tags (sound descriptions) from downloaded subtitles.",
"credit_removal_hint": "Remove translator credit lines at the start or end of subtitle files.",
"post_command_hint": "Shell command executed after every successful subtitle download. Use %path% for the subtitle file path, %media% for the video path.",
"sync_threshold_hint": "Minimum confidence score for auto-sync to apply changes. Below this threshold the original timing is kept.",
"sync_fallback_engine_hint": "If the primary sync engine fails or produces low-confidence results, try this engine as fallback."
```

- [ ] **Step 7: Add all the same keys in German to DE settings.json**

For every key added above, add the German translation. Examples:

```json
"general": {
  "port_hint": "TCP-Port, auf dem der Sublarr-Server lauscht. Erfordert Neustart.",
  "api_key_hint": "Schützt alle API-Endpunkte. Leer lassen, um Authentifizierung zu deaktivieren.",
  "log_level_hint": "Steuert die Ausführlichkeit der Server-Logs. DEBUG nur zur Fehlersuche verwenden.",
  "media_path_hint": "Stammverzeichnis deiner Mediathek. Wird für Pfadauflösung verwendet wenn kein Pfad-Mapping konfiguriert ist.",
  "db_path_hint": "Pfad zur SQLite-Datenbankdatei. Bei Änderung muss die bestehende Datei manuell verschoben werden.",
  "scan_engine_hint": "Tool zum Auslesen von Video-Metadaten. Auto wählt das beste verfügbare. Wechsle zu mediainfo falls ffprobe Probleme verursacht."
},
"wanted_tab": {
  "scan_interval_hint": "Wie oft die Bibliothek nach Medien ohne Untertitel gescannt wird. 0 = deaktiviert.",
  "scan_on_startup_hint": "Beim Start sofort die gesamte Bibliothek scannen.",
  "search_interval_hint": "Wie oft Provider nach Einträgen in der Wanted-Liste durchsucht werden. 0 = deaktiviert.",
  "search_on_startup_hint": "Beim Start alle Wanted-Einträge bei Providern suchen.",
  "max_search_attempts_hint": "Nach dieser Anzahl Fehlversuchen nicht mehr automatisch suchen. Manuell jederzeit anstoßbar.",
  "skip_srt_hint": "Kein SRT herunterladen wenn kein ASS gefunden wurde. Sinnvoll für Anime.",
  "anime_only_hint": "Scan auf als Anime markierte Sonarr-Einträge beschränken.",
  "anime_movies_hint": "Radarr-Einträge mit Anime-Genre in Anime-Only-Scans einbeziehen.",
  "max_items_per_run_hint": "Maximale Anzahl Wanted-Einträge pro Suchzyklus. Reduziert Provider-Last bei großen Bibliotheken.",
  "backoff_base_hint": "Multiplikator für die Wartezeit zwischen Versuchen. Nach jedem Fehlschlag verdoppelt sich die Wartezeit.",
  "backoff_cap_hint": "Maximale Wartezeit in Stunden zwischen Versuchen."
}
```

Continue the same translation pattern for all other hint keys.

- [ ] **Step 8: Verify JSON validity**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors (TypeScript checks i18n type safety).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/i18n/locales/en/settings.json frontend/src/i18n/locales/de/settings.json
git commit -m "feat: add hint text i18n keys for all settings fields"
```

---

### Task 2: Apply field treatment to GeneralSettings

**Files:**
- Modify: `frontend/src/pages/settings/GeneralSettings.tsx`

- [ ] **Step 1: Read the full file**

```bash
cat frontend/src/pages/settings/GeneralSettings.tsx
```

- [ ] **Step 2: Identify normal vs advanced fields**

Normal (always visible, hint inline):
- port, api_key, log_level, media_path, interface_language, default_library_view, default_library_sort, datetime_format, hi_preference, forced_preference

Advanced (collapsed, hint tooltip):
- log_format, scan_metadata_engine, scan_metadata_max_workers, ffmpeg_timeout

- [ ] **Step 3: Convert log_level to select**

Find the current log_level field. It should already be a select (LOG_LEVELS constant exists). If it uses a text input, convert:

```tsx
<select
  value={config?.log_level ?? 'INFO'}
  onChange={(e) => save({ log_level: e.target.value })}
  style={{ ...settingsInputStyle, width: '160px' }}
>
  {LOG_LEVELS.map((l) => (
    <option key={l} value={l}>{l}</option>
  ))}
</select>
```

- [ ] **Step 4: Convert scan_metadata_engine to select**

```tsx
<select
  value={config?.scan_metadata_engine ?? 'auto'}
  onChange={(e) => save({ scan_metadata_engine: e.target.value })}
  style={{ ...settingsInputStyle, width: '160px' }}
>
  {SCAN_ENGINES.map((e) => (
    <option key={e} value={e}>{e}</option>
  ))}
</select>
```

- [ ] **Step 5: Add hint props to all FormGroup calls**

For each `<FormGroup label={...}>`, add the corresponding `hint={t('general.{field}_hint')}`. For advanced fields also add `advanced`.

Example — normal field:
```tsx
<FormGroup
  label={t('general_page.log_level')}
  hint={t('general.log_level_hint')}
  htmlFor="log-level"
>
  <select id="log-level" ...>...</select>
</FormGroup>
```

Example — advanced field:
```tsx
<FormGroup
  label={t('general_page.log_format')}
  hint={t('general.log_format_hint')}
  advanced
  htmlFor="log-format"
>
  <select id="log-format" ...>...</select>
</FormGroup>
```

- [ ] **Step 6: Wrap advanced fields in SettingsSection advanced prop**

For each section that has advanced fields, move them into the `advanced` prop of `<SettingsSection>` and set `advancedCount`:

```tsx
<SettingsSection
  title={t('general_page.section_server')}
  icon={...}
  advancedCount={2}
  advanced={
    <>
      <FormGroup label={t('general_page.log_format')} hint={t('general.log_format_hint')} advanced>
        ...
      </FormGroup>
      <FormGroup label={t('general_page.scan_engine')} hint={t('general.scan_engine_hint')} advanced>
        ...
      </FormGroup>
    </>
  }
>
  {/* normal fields */}
  <FormGroup label={t('general_page.log_level')} hint={t('general.log_level_hint')} htmlFor="log-level">
    ...
  </FormGroup>
</SettingsSection>
```

- [ ] **Step 7: TypeScript + lint check**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 8: Visual check**

Navigate to /settings/general. Verify:
- All normal fields show hint text below the label ✓
- Advanced section toggle shows count ("2 advanced settings") ✓
- Clicking toggle reveals advanced fields with badge and no inline hint ✓
- Hovering ⓘ icon shows tooltip ✓

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/settings/GeneralSettings.tsx
git commit -m "feat: apply hints, selects, and advanced fields to GeneralSettings"
```

---

### Task 3: Apply field treatment to Automation > Suche & Scan and Upgrades

**Files:**
- Modify: `frontend/src/pages/settings/AutomationSettings.tsx`

- [ ] **Step 1: Read the current AutomationSettings top sections**

```bash
sed -n '1,400p' frontend/src/pages/settings/AutomationSettings.tsx
```

- [ ] **Step 2: Identify advanced fields for Suche & Scan**

Normal: scan_interval, scan_on_startup, search_interval, search_on_startup, max_search_attempts, skip_srt_on_no_ass
Advanced: anime_only, anime_movies_only, max_items_per_run, adaptive_backoff_base, adaptive_backoff_cap, scan_ignore_patterns, scan_min_file_size_mb, scan_ignore_languages

- [ ] **Step 3: Add hints and advanced props**

Follow the same pattern as Task 2 — add `hint` to every FormGroup, add `advanced` to advanced fields, move advanced fields into `SettingsSection advanced` prop, set `advancedCount`.

For the Upgrades section:
- Normal: upgrade_enabled, prefer_ass, min_score_delta, upgrade_window
- Advanced: upgrade_scan_interval_hours

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/AutomationSettings.tsx
git commit -m "feat: apply hints and advanced fields to Automation Suche & Scan + Upgrades"
```

---

### Task 4: Apply field treatment to Automation > Post-Processing

**Files:**
- Modify: `frontend/src/pages/settings/AutomationPostProcessingPage.tsx`

- [ ] **Step 1: Identify normal vs advanced fields**

Normal: post_processing_enabled, auto_sync_after_download, auto_sync_engine (select), auto_process_common_fixes, auto_process_hi_removal, auto_process_credit_removal, post_download_command

Advanced: auto_process_sync_threshold, auto_process_sync_fallback_engine

- [ ] **Step 2: Convert auto_sync_engine to select**

```tsx
const SYNC_ENGINES = ['auto', 'alass', 'ffsubsync'] as const

<select
  value={config?.auto_sync_engine ?? 'auto'}
  onChange={(e) => save({ auto_sync_engine: e.target.value })}
  style={{ ...settingsInputStyle, width: '160px' }}
>
  {SYNC_ENGINES.map((e) => (
    <option key={e} value={e}>{e}</option>
  ))}
</select>
```

- [ ] **Step 3: Convert auto_process_sync_fallback_engine to select**

Same SYNC_ENGINES array, same pattern.

- [ ] **Step 4: Add hints and advanced props following the shared pattern**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/AutomationPostProcessingPage.tsx
git commit -m "feat: apply hints, selects, and advanced fields to Post-Processing page"
```

---

### Task 5: Apply field treatment to Providers

**Files:**
- Modify: `frontend/src/pages/settings/ProvidersSettings.tsx`

- [ ] **Step 1: Read ProvidersSettings**

```bash
cat frontend/src/pages/settings/ProvidersSettings.tsx
```

- [ ] **Step 2: Identify normal vs advanced fields**

Normal: provider priority list, provider enable/disable toggles, search_timeout, cache_ttl, rate_limit_enabled, max_concurrent_provider_searches

Advanced: provider_dynamic_timeout_*, circuit_breaker_*, provider_auto_disable_cooldown_minutes, download_delay_between_providers_ms, max_subtitle_file_size_kb

- [ ] **Step 3: Add hints and advanced props**

Follow the shared pattern. The provider list and marketplace tabs remain unchanged — apply hints only to the configuration fields.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/ProvidersSettings.tsx
git commit -m "feat: apply hints and advanced fields to ProvidersSettings"
```

---

### Task 6: Build LanguagePillSelector component and apply to Subtitles > Sprachen & Profile

**Files:**
- Create: `frontend/src/components/settings/LanguagePillSelector.tsx`
- Modify: `frontend/src/pages/settings/SubtitlesSettings.tsx` (or LanguageProfilesTab)

This is the most visual change: language selection changes from a text field to a pill system with a dropdown to add languages.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/LanguagePillSelector.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n'
import { LanguagePillSelector } from '../LanguagePillSelector'

const LANGUAGES = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: 'Japanese' },
]

describe('LanguagePillSelector', () => {
  it('renders current selections as pills', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <LanguagePillSelector
          value={['de', 'en']}
          options={LANGUAGES}
          onChange={vi.fn()}
        />
      </I18nextProvider>
    )
    expect(screen.getByText('Deutsch')).toBeInTheDocument()
    expect(screen.getByText('English')).toBeInTheDocument()
  })

  it('calls onChange with new value when a language is removed', () => {
    const onChange = vi.fn()
    render(
      <I18nextProvider i18n={i18n}>
        <LanguagePillSelector
          value={['de', 'en']}
          options={LANGUAGES}
          onChange={onChange}
        />
      </I18nextProvider>
    )
    fireEvent.click(screen.getAllByLabelText('Remove')[0])
    expect(onChange).toHaveBeenCalledWith(['en'])
  })

  it('calls onChange with added value when a language is selected from dropdown', () => {
    const onChange = vi.fn()
    render(
      <I18nextProvider i18n={i18n}>
        <LanguagePillSelector
          value={['de']}
          options={LANGUAGES}
          onChange={onChange}
        />
      </I18nextProvider>
    )
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'ja' } })
    expect(onChange).toHaveBeenCalledWith(['de', 'ja'])
  })

  it('does not show already-selected languages in the dropdown', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <LanguagePillSelector
          value={['de', 'en']}
          options={LANGUAGES}
          onChange={vi.fn()}
        />
      </I18nextProvider>
    )
    const select = screen.getByRole('combobox')
    expect(select).not.toHaveTextContent('Deutsch')
    expect(select).not.toHaveTextContent('English')
    expect(select).toHaveTextContent('Japanese')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/components/settings/__tests__/LanguagePillSelector.test.tsx
```

Expected: FAIL — `LanguagePillSelector` does not exist.

- [ ] **Step 3: Create LanguagePillSelector**

Create `frontend/src/components/settings/LanguagePillSelector.tsx`:

```tsx
import { X } from 'lucide-react'
import { settingsInputStyle } from '@/styles/settingsShared'

interface LanguageOption {
  value: string
  label: string
}

interface Props {
  value: string[]
  options: LanguageOption[]
  onChange: (newValue: string[]) => void
  placeholder?: string
}

export function LanguagePillSelector({ value, options, onChange, placeholder = '— Add language —' }: Props) {
  const available = options.filter((o) => !value.includes(o.value))

  const remove = (lang: string) => onChange(value.filter((v) => v !== lang))

  const add = (lang: string) => {
    if (lang && !value.includes(lang)) onChange([...value, lang])
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {/* Pills */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          minHeight: '36px',
          padding: '6px 8px',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          alignItems: 'center',
        }}
      >
        {value.map((lang) => {
          const opt = options.find((o) => o.value === lang)
          return (
            <span
              key={lang}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                background: 'var(--accent-bg)',
                border: '1px solid var(--accent-dim)',
                borderRadius: '4px',
                padding: '3px 8px',
                fontSize: '12px',
                color: 'var(--accent)',
              }}
            >
              {opt?.label ?? lang}
              <button
                type="button"
                aria-label="Remove"
                onClick={() => remove(lang)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: 0,
                  marginLeft: '2px',
                }}
              >
                <X size={11} />
              </button>
            </span>
          )
        })}
        {value.length === 0 && (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>—</span>
        )}
      </div>

      {/* Add dropdown */}
      {available.length > 0 && (
        <select
          value=""
          onChange={(e) => { add(e.target.value); e.target.value = '' }}
          style={{ ...settingsInputStyle, width: '220px', fontSize: '12px' }}
        >
          <option value="">{placeholder}</option>
          {available.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/components/settings/__tests__/LanguagePillSelector.test.tsx
```

Expected: 4 tests PASS.

- [ ] **Step 5: Find where language selection currently lives**

```bash
grep -n "target_language\|source_language\|language_profile\|LanguageSelect" frontend/src/pages/settings/SubtitlesSettings.tsx frontend/src/pages/settings/*.tsx 2>/dev/null | head -30
```

This tells you which file currently renders language selection.

- [ ] **Step 6: Apply LanguagePillSelector to additional languages field**

In the file where additional/secondary languages are configured (likely `LanguageProfilesTab.tsx`), replace the current input with:

```tsx
import { LanguagePillSelector } from '@/components/settings/LanguagePillSelector'

// Where additional languages are currently a text input or multi-select:
<FormGroup
  label={t('subtitles.additional_languages')}
  hint={t('subtitles.additional_languages_hint')}
>
  <LanguagePillSelector
    value={profile.additional_languages ?? []}
    options={LANGUAGE_OPTIONS}
    onChange={(langs) => updateProfile({ additional_languages: langs })}
    placeholder={t('subtitles.add_language_placeholder')}
  />
</FormGroup>
```

Where `LANGUAGE_OPTIONS` is the full list of supported languages (import or define inline if not already present):

```tsx
const LANGUAGE_OPTIONS = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
  { value: 'fr', label: 'Français' },
  { value: 'ja', label: 'Japanese' },
  { value: 'es', label: 'Español' },
  { value: 'it', label: 'Italiano' },
  { value: 'pt', label: 'Português' },
  { value: 'nl', label: 'Nederlands' },
  { value: 'pl', label: 'Polski' },
  { value: 'ru', label: 'Русский' },
  { value: 'ko', label: '한국어' },
  { value: 'zh', label: '中文' },
  { value: 'ar', label: 'العربية' },
  { value: 'tr', label: 'Türkçe' },
  { value: 'sv', label: 'Svenska' },
  { value: 'da', label: 'Dansk' },
  { value: 'fi', label: 'Suomi' },
  { value: 'no', label: 'Norsk' },
  { value: 'cs', label: 'Čeština' },
  { value: 'hu', label: 'Magyar' },
] as const
```

- [ ] **Step 7: Convert primary language field to select**

Where the primary/target language is currently a text input, replace with:

```tsx
<FormGroup
  label={t('subtitles.primary_language')}
  hint={t('subtitles.primary_language_hint')}
  htmlFor="primary-lang"
>
  <select
    id="primary-lang"
    value={config?.target_language ?? 'de'}
    onChange={(e) => save({ target_language: e.target.value })}
    style={{ ...settingsInputStyle, width: '220px' }}
  >
    {LANGUAGE_OPTIONS.map((o) => (
      <option key={o.value} value={o.value}>{o.label}</option>
    ))}
  </select>
</FormGroup>
```

- [ ] **Step 8: Add i18n keys for language selector**

Add to EN settings.json:
```json
"subtitles": {
  "primary_language": "Primary Language",
  "primary_language_hint": "The main subtitle language. Sublarr always searches for this first and uses it as default for all new media.",
  "additional_languages": "Additional Languages",
  "additional_languages_hint": "More languages to search for alongside the primary. Searched after the primary language.",
  "add_language_placeholder": "— Add language —"
}
```

Add to DE settings.json:
```json
"subtitles": {
  "primary_language": "Hauptsprache",
  "primary_language_hint": "Die wichtigste Untertitelsprache. Sublarr sucht immer zuerst nach dieser und verwendet sie als Standard für alle neuen Medien.",
  "additional_languages": "Weitere Sprachen",
  "additional_languages_hint": "Weitere Sprachen die parallel zur Hauptsprache gesucht werden.",
  "add_language_placeholder": "— Sprache hinzufügen —"
}
```

- [ ] **Step 9: TypeScript + lint check**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 10: Visual check**

Navigate to the language profile settings. Verify:
- Primary language is a dropdown ✓
- Additional languages shows pills with × buttons ✓
- Adding from dropdown adds a pill ✓
- Already-selected languages don't appear in the dropdown ✓

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/settings/LanguagePillSelector.tsx frontend/src/components/settings/__tests__/LanguagePillSelector.test.tsx frontend/src/pages/settings/SubtitlesSettings.tsx frontend/src/pages/settings/LanguageProfilesTab.tsx
git commit -m "feat: add LanguagePillSelector, apply to language profile settings"
```

---

### Task 7: Apply field treatment to remaining pages

For each remaining page, follow the same pattern: read the file, identify normal vs advanced fields, add hints, convert applicable fields to selects. One commit per page.

**Files and advanced field classification:**

#### ConnectionsSettings
Normal: sonarr_url, sonarr_api_key, radarr_url, radarr_api_key, jellyfin_url, jellyfin_api_key, standalone_enabled, tmdb_api_key, tvdb_api_key
Advanced: sonarr_instances_json (multi-instance), radarr_instances_json, path_mapping, standalone_scan_interval_hours, standalone_debounce_seconds, standalone_skip_extras, tvdb_pin, metadata_cache_ttl_days, ffmpeg_timeout, scan_metadata_max_workers

- [ ] **Step 1: Apply to ConnectionsSettings**

```bash
cd frontend && npm run test -- --run
git add frontend/src/pages/settings/ConnectionsSettings.tsx frontend/src/pages/settings/connections/
git commit -m "feat: apply hints and advanced fields to ConnectionsSettings"
```

#### ScoringTab
Normal: score_threshold_per_language (per-language select), scoring presets
Advanced: all individual scoring weight sliders/inputs (provider_bonus, hi_penalty, format_bonus, etc.)

- [ ] **Step 2: Apply to ScoringTab**

```bash
git add frontend/src/pages/settings/ScoringTab.tsx frontend/src/pages/settings/ScoringTabContent.tsx
git commit -m "feat: apply hints and advanced fields to ScoringTab"
```

#### NotificationsSettings
Normal: notification_urls_json, notify_on_download, notify_on_upgrade, notify_on_batch_complete, notify_on_error, notify_manual_actions
Advanced: quiet_hours_*, disk_warning_threshold_percent, backup_notify_on_failure

- [ ] **Step 3: Apply to NotificationsSettings**

```bash
git add frontend/src/pages/settings/NotificationsSettings.tsx
git commit -m "feat: apply hints and advanced fields to NotificationsSettings"
```

#### SystemSettings (Security + Backup sections)
Normal: UI auth toggle, current/new password, max_login_attempts, backup on-demand
Advanced: lockout_duration_minutes, allowed_ip_ranges, session_timeout_minutes, backup_auto_interval_hours, backup_retention_days

- [ ] **Step 4: Apply to SystemSettings**

```bash
git add frontend/src/pages/settings/SystemSettings.tsx frontend/src/pages/settings/SecurityTab.tsx frontend/src/pages/settings/BackupTab.tsx
git commit -m "feat: apply hints and advanced fields to SystemSettings, SecurityTab, BackupTab"
```

---

### Task 8: Final checks

- [ ] **Step 1: Run full frontend test suite**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests pass.

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Lint check**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 4: Full visual walkthrough**

Start the dev server and visit every settings page. Verify:
- Every page shows hints on normal fields ✓
- Every page has "X advanced settings" toggle where applicable ✓
- No page has a text input where a select is more appropriate ✓
- Language profile page shows pill selector ✓
- Toggling advanced shows amber badges + ⓘ tooltips ✓

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete Plan 3 — all settings pages have hints, selects, and advanced badges"
```
