import { Globe, HardDrive, FileText, Languages } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FeatureAddon } from '@/components/settings/FeatureAddon'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

// ─── Config value helpers ─────────────────────────────────────────────────────

function strVal(config: unknown, key: string, fallback = ''): string {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  return v !== undefined && v !== null ? String(v) : fallback
}

function boolVal(config: unknown, key: string, fallback = false): boolean {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  if (v === undefined || v === null) return fallback
  return v === true || v === 'true' || v === 1
}

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

        {/* ── Paths & Server ────────────────────────────────────────────── */}
        <div data-testid="section-paths">
          <SettingsSection
            title="Paths & Server"
            description="Media library root, server port, and advanced server options"
            icon={<HardDrive size={16} style={{ color: 'var(--accent)' }} />}
            advanced={
              <>
                <FormGroup
                  label="Workers"
                  hint="Number of worker threads for the backend server"
                  htmlFor="workers"
                  data-testid="form-group-workers"
                >
                  <input
                    id="workers"
                    type="number"
                    data-testid="input-workers"
                    style={{ ...inputStyle, maxWidth: '120px' }}
                    value={strVal(config, 'workers', '4')}
                    onChange={(e) => save({ workers: Number(e.target.value) })}
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
              label="Log to File"
              hint="Write log output to a file in addition to stdout"
              data-testid="form-group-log-to-file"
            >
              <Toggle
                checked={boolVal(config, 'log_to_file', false)}
                onChange={(v) => save({ log_to_file: v })}
                disabled={isPending}
              />
            </FormGroup>
          </SettingsSection>
        </div>

        {/* ── Translation feature addon ─────────────────────────────────── */}
        <div data-testid="section-translation-addon">
          <FeatureAddon
            icon={Languages}
            title="Translation"
            description="Enable AI-powered subtitle translation between languages"
            isEnabled={boolVal(config, 'translation_enabled', false)}
            onToggle={(v) => save({ translation_enabled: v })}
          />
        </div>
      </div>
    </SettingsDetailLayout>
  )
}

