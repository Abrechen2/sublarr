import { HardDrive, FileText, Monitor } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal } from '@/lib/configUtils'
import { settingsInputStyle, LANGUAGE_OPTIONS } from '@/styles/settingsShared'

// Reference migration for Settings Template B (FormLayout). This is the
// first page converted onto the new scaffold — it defines the
// section-id / titleKey / testid conventions that subsequent FormLayout
// migrations copy. See frontend/src/components/settings/layouts/README.md
// for the five locked conventions this file exemplifies.

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '220px', outline: 'none' }

// ─── Constants ────────────────────────────────────────────────────────────────

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
const LOG_FORMATS = ['text', 'json'] as const
const LIBRARY_VIEWS = ['grid', 'list'] as const

// Section definitions — order matches scroll order; titleKey resolves via
// useTranslation('settings'). Locking these as a single constant keeps the
// TOC metadata + SettingsSection headers in sync (same keys everywhere).
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'interface-preferences', titleKey: 'general_page.interface_prefs_section' },
  { id: 'paths',                 titleKey: 'general_page.paths_section' },
  { id: 'logging',               titleKey: 'general_page.logging_section' },
]

// ─── Component ────────────────────────────────────────────────────────────────

export function GeneralSettings() {
  const { data: config, isLoading } = useConfig()
  const { mutate: updateConfig, isPending } = useUpdateConfig()
  const { t } = useTranslation('settings')

  const librarySorts = [
    { value: 'alpha', label: t('general_page.sort_alpha') },
    { value: 'date',  label: t('general_page.sort_date') },
    { value: 'score', label: t('general_page.sort_score') },
  ]
  const datetimeFormats = [
    { value: 'relative', label: t('general_page.datetime_relative') },
    { value: 'absolute', label: t('general_page.datetime_absolute') },
  ]

  const save = (patch: Record<string, unknown>) => updateConfig(patch)

  if (isLoading) {
    return (
      <SettingsDetailLayout
        title={t('general_page.title')}
        subtitle={t('general_page.subtitle')}
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
      title={t('general_page.title')}
      subtitle={t('general_page.subtitle')}
    >
      <div data-testid="general-settings">
        <FormLayout sections={SECTIONS}>

          {/* ── Interface Preferences ─────────────────────────────────── */}
          <section
            id="interface-preferences"
            data-testid="settings.general.section-interface-preferences"
          >
            <SettingsSection
              title={t('general_page.interface_prefs_section')}
              description={t('general_page.interface_prefs_desc')}
              icon={<Monitor size={16} style={{ color: 'var(--accent)' }} />}
            >
              <FormGroup
                label={t('general_page.interface_language')}
                hint={t('general_page.interface_language_hint')}
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
                label={t('general_page.items_per_page')}
                hint={t('general_page.items_per_page_hint')}
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
                label={t('general_page.default_library_view')}
                hint={t('general_page.default_library_view_hint')}
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
                label={t('general_page.default_library_sort')}
                hint={t('general_page.default_library_sort_hint')}
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
                  {librarySorts.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </FormGroup>

              <FormGroup
                label={t('general_page.datetime_format')}
                hint={t('general_page.datetime_format_hint')}
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
                  {datetimeFormats.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </FormGroup>
            </SettingsSection>
          </section>

          {/* ── Paths & Server ────────────────────────────────────────── */}
          <section id="paths" data-testid="settings.general.section-paths">
            <SettingsSection
              title={t('general_page.paths_section')}
              description={t('general_page.paths_desc')}
              icon={<HardDrive size={16} style={{ color: 'var(--accent)' }} />}
              advanced={
                <>
                  <FormGroup
                    label={t('general_page.base_url')}
                    hint={t('general_page.base_url_hint')}
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
                    label={t('general_page.db_path')}
                    hint={t('general_page.db_path_hint')}
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
                label={t('general_page.media_path')}
                hint={t('general_page.media_path_hint')}
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
                label={t('general_page.port')}
                hint={t('general_page.port_hint')}
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
          </section>

          {/* ── Logging ───────────────────────────────────────────────── */}
          <section id="logging" data-testid="settings.general.section-logging">
            <SettingsSection
              title={t('general_page.logging_section')}
              description={t('general_page.logging_desc')}
              icon={<FileText size={16} style={{ color: 'var(--accent)' }} />}
            >
              <FormGroup
                label={t('general_page.log_level')}
                hint={t('general_page.log_level_hint')}
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
                label={t('general_page.log_file')}
                hint={t('general_page.log_file_hint')}
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
                label={t('general_page.log_format')}
                hint={t('general_page.log_format_hint')}
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
          </section>

        </FormLayout>
      </div>
    </SettingsDetailLayout>
  )
}
