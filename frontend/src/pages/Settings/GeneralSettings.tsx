import { Globe, HardDrive, FileText, Monitor } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal } from '@/lib/configUtils'

// ─── Shared input style ───────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
  fontFamily: 'var(--font-body)',
  width: '220px',
  outline: 'none',
}

// ─── Constants ────────────────────────────────────────────────────────────────

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
const LOG_FORMATS = ['text', 'json'] as const
const SCAN_ENGINES = ['auto', 'ffprobe', 'mediainfo'] as const

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'de', label: 'Deutsch' },
] as const

const LIBRARY_VIEWS = ['grid', 'list'] as const
const LIBRARY_SORTS = [
  { value: 'alpha', label: 'Alphabetical' },
  { value: 'date', label: 'Date Added' },
  { value: 'score', label: 'Score' },
] as const
const DATETIME_FORMATS = [
  { value: 'relative', label: 'Relative (2 hours ago)' },
  { value: 'absolute', label: 'Absolute (2026-03-21 14:00)' },
] as const

const HI_OPTIONS = [
  { value: 'include', label: 'Include (no preference)' },
  { value: 'prefer', label: 'Prefer HI (+30 score)' },
  { value: 'exclude', label: 'Exclude HI (−999 penalty)' },
  { value: 'only', label: 'Only HI (non-HI excluded)' },
] as const

const FORCED_OPTIONS = [
  { value: 'include', label: 'Include (no preference)' },
  { value: 'prefer', label: 'Prefer forced (+30 score)' },
  { value: 'exclude', label: 'Exclude forced (−999 penalty)' },
  { value: 'only', label: 'Only forced (non-forced excluded)' },
] as const

// ─── Component ────────────────────────────────────────────────────────────────

export function GeneralSettings() {
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) {
    return (
      <SettingsDetailLayout
        title="General"
        subtitle="Interface, server, and logging configuration"
      >
        <div
          data-testid="general-settings-skeleton"
          className="animate-pulse space-y-4"
          aria-busy="true"
        >
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-32 rounded-lg"
              style={{ background: 'var(--bg-surface)' }}
            />
          ))}
        </div>
      </SettingsDetailLayout>
    )
  }

  return (
    <SettingsDetailLayout
      title="General"
      subtitle="Interface, server, and logging configuration"
    >
      <div data-testid="general-settings" className="space-y-4">

        {/* ── Interface ────────────────────────────────────────────────── */}
        <div data-testid="section-interface">
          <SettingsSection
            title="Interface"
            description="Language preferences for subtitle search and display"
            icon={<Globe size={16} style={{ color: 'var(--accent)' }} />}
          >
            <FormGroup
              label="Source Language"
              hint="Language of the source subtitles (e.g. en)"
              htmlFor="source-language"
              data-testid="form-group-source-language"
            >
              <input
                id="source-language"
                type="text"
                data-testid="input-source-language"
                style={inputStyle}
                value={strVal(config, 'source_language', 'en')}
                onChange={(e) => save({ source_language: e.target.value })}
                disabled={isPending}
                placeholder="en"
              />
            </FormGroup>

            <FormGroup
              label="Target Language"
              hint="Language to search subtitles in (e.g. de)"
              htmlFor="target-language"
              data-testid="form-group-target-language"
            >
              <input
                id="target-language"
                type="text"
                data-testid="input-target-language"
                style={inputStyle}
                value={strVal(config, 'target_language', 'de')}
                onChange={(e) => save({ target_language: e.target.value })}
                disabled={isPending}
                placeholder="de"
              />
            </FormGroup>

            <FormGroup
              label="Hearing Impaired Preference"
              hint="How subtitles with HI tags are treated during provider search"
              htmlFor="hi-preference"
              data-testid="form-group-hi-preference"
            >
              <select
                id="hi-preference"
                data-testid="select-hi-preference"
                style={inputStyle}
                value={strVal(config, 'hi_preference', 'include')}
                onChange={(e) => save({ hi_preference: e.target.value })}
                disabled={isPending}
              >
                {HI_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FormGroup>

            <FormGroup
              label="Forced Subtitle Preference"
              hint="How forced subtitles (foreign-language scenes) are handled"
              htmlFor="forced-preference"
              data-testid="form-group-forced-preference"
            >
              <select
                id="forced-preference"
                data-testid="select-forced-preference"
                style={inputStyle}
                value={strVal(config, 'forced_preference', 'include')}
                onChange={(e) => save({ forced_preference: e.target.value })}
                disabled={isPending}
              >
                {FORCED_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FormGroup>
          </SettingsSection>
        </div>

        {/* ── Interface Preferences ─────────────────────────────────────── */}
        <div data-testid="section-interface-preferences">
          <SettingsSection
            title="Interface Preferences"
            description="Pagination, library layout, sorting, and date display defaults."
            icon={<Monitor size={16} style={{ color: 'var(--accent)' }} />}
          >
            <FormGroup
              label="Interface Language"
              hint="UI display language"
              htmlFor="interface-language"
              data-testid="form-group-interface-language"
            >
              <select
                id="interface-language"
                data-testid="select-interface-language"
                style={inputStyle}
                value={strVal(config, 'interface_language', 'en')}
                onChange={(e) => save({ interface_language: e.target.value })}
                disabled={isPending}
              >
                {LANGUAGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FormGroup>

            <FormGroup
              label="Items per Page"
              hint="Number of items shown per page in library lists"
              htmlFor="items-per-page"
              data-testid="form-group-items-per-page"
            >
              <input
                id="items-per-page"
                type="number"
                data-testid="input-items-per-page"
                style={{ ...inputStyle, maxWidth: '120px' }}
                value={Number(strVal(config, 'items_per_page', '25'))}
                onChange={(e) => save({ items_per_page: Number(e.target.value) })}
                disabled={isPending}
                min={10}
                max={200}
              />
            </FormGroup>

            <FormGroup
              label="Default Library View"
              hint="Default view mode for the library (grid or list)"
              htmlFor="default-library-view"
              data-testid="form-group-default-library-view"
            >
              <select
                id="default-library-view"
                data-testid="select-default-library-view"
                style={inputStyle}
                value={strVal(config, 'default_library_view', 'grid')}
                onChange={(e) => save({ default_library_view: e.target.value })}
                disabled={isPending}
              >
                {LIBRARY_VIEWS.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </FormGroup>

            <FormGroup
              label="Default Library Sort"
              hint="Default sort order for library listings"
              htmlFor="default-library-sort"
              data-testid="form-group-default-library-sort"
            >
              <select
                id="default-library-sort"
                data-testid="select-default-library-sort"
                style={inputStyle}
                value={strVal(config, 'default_library_sort', 'alpha')}
                onChange={(e) => save({ default_library_sort: e.target.value })}
                disabled={isPending}
              >
                {LIBRARY_SORTS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FormGroup>

            <FormGroup
              label="Date/Time Format"
              hint="How dates and times are displayed throughout the UI"
              htmlFor="datetime-format"
              data-testid="form-group-datetime-format"
            >
              <select
                id="datetime-format"
                data-testid="select-datetime-format"
                style={inputStyle}
                value={strVal(config, 'datetime_format', 'relative')}
                onChange={(e) => save({ datetime_format: e.target.value })}
                disabled={isPending}
              >
                {DATETIME_FORMATS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FormGroup>
          </SettingsSection>
        </div>

        {/* ── Paths & Server ────────────────────────────────────────────── */}
        <div data-testid="section-paths">
          <SettingsSection
            title="Paths & Server"
            description="Media library root, server port, and advanced server options"
            icon={<HardDrive size={16} style={{ color: 'var(--accent)' }} />}
            advanced={
              <>
                <FormGroup
                  label="Metadata Scan Engine"
                  hint="Tool used to read media metadata. 'auto' prefers mediainfo when available."
                  htmlFor="scan-metadata-engine"
                  data-testid="form-group-scan-metadata-engine"
                >
                  <select
                    id="scan-metadata-engine"
                    data-testid="select-scan-metadata-engine"
                    style={{ ...inputStyle, maxWidth: '160px' }}
                    value={strVal(config, 'scan_metadata_engine', 'auto')}
                    onChange={(e) => save({ scan_metadata_engine: e.target.value })}
                    disabled={isPending}
                  >
                    {SCAN_ENGINES.map((e) => (
                      <option key={e} value={e}>
                        {e}
                      </option>
                    ))}
                  </select>
                </FormGroup>

                <FormGroup
                  label="Translation Workers"
                  hint="Parallel threads for subtitle translation jobs"
                  htmlFor="translation-max-workers"
                  data-testid="form-group-translation-max-workers"
                >
                  <input
                    id="translation-max-workers"
                    type="number"
                    data-testid="input-translation-max-workers"
                    style={{ ...inputStyle, maxWidth: '120px' }}
                    value={strVal(config, 'translation_max_workers', '2')}
                    onChange={(e) => save({ translation_max_workers: Number(e.target.value) })}
                    disabled={isPending}
                    min={1}
                    max={32}
                  />
                </FormGroup>

                <FormGroup
                  label="Metadata Scan Workers"
                  hint="Parallel threads for metadata scanning"
                  htmlFor="scan-metadata-max-workers"
                  data-testid="form-group-scan-metadata-max-workers"
                >
                  <input
                    id="scan-metadata-max-workers"
                    type="number"
                    data-testid="input-scan-metadata-max-workers"
                    style={{ ...inputStyle, maxWidth: '120px' }}
                    value={strVal(config, 'scan_metadata_max_workers', '2')}
                    onChange={(e) => save({ scan_metadata_max_workers: Number(e.target.value) })}
                    disabled={isPending}
                    min={1}
                    max={32}
                  />
                </FormGroup>

                <FormGroup
                  label="Base URL"
                  hint="Reverse-proxy prefix if Sublarr is served at a sub-path"
                  htmlFor="base-url"
                  data-testid="form-group-base-url"
                >
                  <input
                    id="base-url"
                    type="text"
                    data-testid="input-base-url"
                    style={inputStyle}
                    value={strVal(config, 'base_url', '')}
                    onChange={(e) => save({ base_url: e.target.value })}
                    disabled={isPending}
                    placeholder="/"
                  />
                </FormGroup>

                <FormGroup
                  label="Database Path"
                  hint="SQLite database file. Only change if the DB has been moved."
                  htmlFor="db-path"
                  data-testid="form-group-db-path"
                >
                  <input
                    id="db-path"
                    type="text"
                    data-testid="input-db-path"
                    style={inputStyle}
                    value={strVal(config, 'db_path', '/config/sublarr.db')}
                    onChange={(e) => save({ db_path: e.target.value })}
                    disabled={isPending}
                    placeholder="/config/sublarr.db"
                  />
                </FormGroup>
              </>
            }
          >
            <FormGroup
              label="Media Path"
              hint="Root path of the media directory. All media paths must be below this."
              htmlFor="media-path"
              data-testid="form-group-media-path"
            >
              <input
                id="media-path"
                type="text"
                data-testid="input-media-path"
                style={inputStyle}
                value={strVal(config, 'media_path', '/media')}
                onChange={(e) => save({ media_path: e.target.value })}
                disabled={isPending}
                placeholder="/media"
              />
            </FormGroup>

            <FormGroup
              label="Port"
              hint="HTTP port Sublarr listens on. Default: 5765."
              htmlFor="port"
              data-testid="form-group-port"
            >
              <input
                id="port"
                type="number"
                data-testid="input-port"
                style={{ ...inputStyle, maxWidth: '120px' }}
                value={strVal(config, 'port', '5765')}
                onChange={(e) => save({ port: Number(e.target.value) })}
                disabled={isPending}
                min={1}
                max={65535}
              />
            </FormGroup>
          </SettingsSection>
        </div>

        {/* ── Logging ───────────────────────────────────────────────────── */}
        <div data-testid="section-logging">
          <SettingsSection
            title="Logging"
            description="Log verbosity and file output settings"
            icon={<FileText size={16} style={{ color: 'var(--accent)' }} />}
          >
            <FormGroup
              label="Log Level"
              hint="Controls the verbosity of backend logging"
              htmlFor="log-level"
              data-testid="form-group-log-level"
            >
              <select
                id="log-level"
                data-testid="select-log-level"
                style={{ ...inputStyle, maxWidth: '160px' }}
                value={strVal(config, 'log_level', 'INFO')}
                onChange={(e) => save({ log_level: e.target.value })}
                disabled={isPending}
              >
                {LOG_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </FormGroup>

            <FormGroup
              label="Log File Path"
              hint="Write logs to this file path, e.g. /config/sublarr.log. Leave empty to disable."
              htmlFor="log-file"
              data-testid="form-group-log-file"
            >
              <input
                id="log-file"
                type="text"
                data-testid="input-log-file"
                style={inputStyle}
                value={strVal(config, 'log_file', '')}
                onChange={(e) => save({ log_file: e.target.value })}
                disabled={isPending}
                placeholder="/config/sublarr.log"
              />
            </FormGroup>

            <FormGroup
              label="Log Format"
              hint="Output format for log entries. Use 'json' for log aggregation tools."
              htmlFor="log-format"
              data-testid="form-group-log-format"
            >
              <select
                id="log-format"
                data-testid="select-log-format"
                style={{ ...inputStyle, maxWidth: '160px' }}
                value={strVal(config, 'log_format', 'text')}
                onChange={(e) => save({ log_format: e.target.value })}
                disabled={isPending}
              >
                {LOG_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </FormGroup>
          </SettingsSection>
        </div>

      </div>
    </SettingsDetailLayout>
  )
}

