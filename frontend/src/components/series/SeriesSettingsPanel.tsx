import type React from 'react'
import type { SeriesDetail } from '@/lib/types'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Tooltip } from '@/components/shared/Tooltip'
import { useCreateOverride } from '@/pages/Settings/profilesOverrides/useProfilesOverrides'
import { useLanguageProfiles, useAssignProfile } from '@/hooks/useApi'
import { profilesScopeUrl, seriesDetailUrl } from '@/lib/routes'

interface SeriesSettingsPanelProps {
  readonly series: SeriesDetail
  readonly seriesId: number
  readonly showGlossary: boolean
  readonly hasFansubOverride: boolean
  readonly isExtracting: boolean
  readonly extractProgress: { current: number; total: number; filename: string } | null
  readonly onToggleGlossary: () => void
  readonly onToggleAbsoluteOrder: (enabled: boolean) => void
  readonly onSetCleanupForeignTracks: (value: boolean | null) => void
  readonly onRefreshAnidb: () => void
  readonly onExtract: () => void
  readonly onCleanup: () => void
  readonly onFansub: () => void
  readonly onExport: () => void
  readonly updatePending: boolean
  readonly refreshPending: boolean
}

const sectionLabelStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  marginBottom: '8px',
}

const buttonBaseStyle: React.CSSProperties = {
  fontSize: '11px',
  padding: '4px 10px',
  borderRadius: '4px',
  cursor: 'pointer',
}

export function SeriesSettingsPanel({
  series,
  seriesId,
  showGlossary,
  hasFansubOverride,
  isExtracting,
  extractProgress,
  onToggleGlossary,
  onToggleAbsoluteOrder,
  onSetCleanupForeignTracks,
  onRefreshAnidb,
  onExtract,
  onCleanup,
  onFansub,
  onExport,
  updatePending,
  refreshPending,
}: SeriesSettingsPanelProps) {
  const { t } = useTranslation('library')
  const { t: tSettings } = useTranslation('settings')
  const navigate = useNavigate()
  const createOverride = useCreateOverride('series')
  const { data: profilesData } = useLanguageProfiles()
  const assignProfile = useAssignProfile()
  const profiles = profilesData ?? []

  const handleSubtitleSettings = async () => {
    await createOverride.mutateAsync(seriesId)
    navigate(profilesScopeUrl({ type: 'series', id: seriesId }, { from: seriesDetailUrl(seriesId) }))
  }

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        marginBottom: '16px',
      }}
    >
      {/* Language section */}
      <div>
        <div style={sectionLabelStyle}>{t('series_settings_panel.section_language')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          <select
            aria-label={tSettings('profiles_overrides.action.select_profile', 'Select profile…')}
            data-testid="series-profile-select"
            disabled={assignProfile.isPending}
            value={series.profile_id ?? ''}
            onChange={(e) => {
              const id = Number(e.target.value)
              if (!isNaN(id) && id > 0) {
                assignProfile.mutate({ type: 'series', arrId: seriesId, profileId: id })
              }
            }}
            style={{
              padding: '3px 8px',
              borderRadius: '4px',
              fontSize: '11px',
              backgroundColor: 'var(--accent-bg)',
              color: 'var(--accent)',
              border: '1px solid var(--accent)',
              fontWeight: 600,
              cursor: assignProfile.isPending ? 'default' : 'pointer',
              opacity: assignProfile.isPending ? 0.6 : 1,
            }}
          >
            {profiles.length === 0 && (
              <option value="">{series.profile_name || 'Default'}</option>
            )}
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.is_default ? ' ★' : ''}
              </option>
            ))}
          </select>
          {series.target_language_names?.map((name: string) => (
            <span
              key={name}
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              {name}
            </span>
          ))}
          {series.source_language_name && (
            <span
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-muted)',
                fontStyle: 'italic',
              }}
            >
              src: {series.source_language_name}
            </span>
          )}
        </div>
      </div>

      {/* Subtitles section */}
      <div>
        <div style={sectionLabelStyle}>{t('series_settings_panel.section_subtitles')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          {/* Glossary toggle */}
          <button
            onClick={onToggleGlossary}
            style={{
              ...buttonBaseStyle,
              backgroundColor: showGlossary ? 'var(--accent-bg)' : 'var(--bg-elevated)',
              color: showGlossary ? 'var(--accent)' : 'var(--text-secondary)',
              border: showGlossary ? '1px solid var(--accent)' : '1px solid var(--border)',
            }}
          >
            📖 Glossary
          </button>

          {/* Absolute order toggle — field is `absolute_order` on SeriesDetail */}
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              cursor: updatePending ? 'default' : 'pointer',
              opacity: updatePending ? 0.6 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={series.absolute_order ?? false}
              disabled={updatePending}
              onChange={(e) => onToggleAbsoluteOrder(e.target.checked)}
            />
            Absolute Order
          </label>

          {/* AniDB refresh — only shown when absolute order is enabled */}
          {series.absolute_order && (
            <button
              onClick={onRefreshAnidb}
              disabled={refreshPending}
              style={{
                ...buttonBaseStyle,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                opacity: refreshPending ? 0.6 : 1,
                cursor: refreshPending ? 'default' : 'pointer',
              }}
            >
              🔄 AniDB Refresh
            </button>
          )}

          {/* Foreign-track cleanup override — three-state (inherit / always / never).
              0.71.1 follow-up #1. Reads cleanup_foreign_tracks_override + _effective
              from SeriesDetail and PATCHes /api/v1/series/<id>/settings. */}
          <Tooltip
            content={t('series_settings_panel.tooltip_cleanup_foreign_tracks', {
              defaultValue:
                'After extraction: strip non-target-language subtitle streams from the MKV. ' +
                '"Inherit" follows the global default in Settings.',
            })}
          >
            <label
              htmlFor="cleanup-foreign-tracks-select"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '11px',
                color: 'var(--text-secondary)',
                cursor: updatePending ? 'default' : 'pointer',
                opacity: updatePending ? 0.6 : 1,
              }}
            >
              <span>
                {t('series_settings_panel.cleanup_foreign_tracks_label', {
                  defaultValue: 'Cleanup foreign tracks:',
                })}
              </span>
              <select
                id="cleanup-foreign-tracks-select"
                aria-label="Cleanup foreign tracks"
                disabled={updatePending}
                value={
                  series.cleanup_foreign_tracks_override === true
                    ? 'true'
                    : series.cleanup_foreign_tracks_override === false
                      ? 'false'
                      : 'null'
                }
                onChange={(e) => {
                  const next = e.target.value
                  if (next === 'true') onSetCleanupForeignTracks(true)
                  else if (next === 'false') onSetCleanupForeignTracks(false)
                  else onSetCleanupForeignTracks(null)
                }}
                style={{
                  fontSize: '11px',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-secondary)',
                }}
              >
                <option value="null">
                  {t('series_settings_panel.cleanup_inherit', {
                    defaultValue: 'Inherit',
                  })}
                  {series.cleanup_foreign_tracks_effective !== undefined
                    ? ` (${series.cleanup_foreign_tracks_effective ? 'on' : 'off'})`
                    : ''}
                </option>
                <option value="true">
                  {t('series_settings_panel.cleanup_always', { defaultValue: 'Always' })}
                </option>
                <option value="false">
                  {t('series_settings_panel.cleanup_never', { defaultValue: 'Never' })}
                </option>
              </select>
            </label>
          </Tooltip>
        </div>
      </div>

      {/* Tools section */}
      <div>
        <div style={sectionLabelStyle}>{t('series_settings_panel.section_tools')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          {/* Untertitel exportieren */}
          <Tooltip content={t('series_settings_panel.tooltip_export_zip')}>
            <button
              onClick={onExport}
              style={{
                ...buttonBaseStyle,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
            >
              📦 Untertitel exportieren
            </button>
          </Tooltip>

          {/* Embedded extrahieren */}
          <Tooltip content={t('series_settings_panel.tooltip_extract_embedded')}>
            <button
              onClick={onExtract}
              disabled={isExtracting}
              style={{
                ...buttonBaseStyle,
                backgroundColor: isExtracting ? 'var(--accent-bg)' : 'var(--bg-elevated)',
                color: isExtracting ? 'var(--accent)' : 'var(--text-secondary)',
                border: isExtracting ? '1px solid var(--accent-dim)' : '1px solid var(--border)',
                opacity: isExtracting ? 0.6 : 1,
                cursor: isExtracting ? 'default' : 'pointer',
              }}
            >
              {isExtracting
                ? `Extrahiere… ${extractProgress ? `${extractProgress.current}/${extractProgress.total}` : ''}`
                : '🎵 Embedded extrahieren'
              }
            </button>
          </Tooltip>

          {/* Sidecar bereinigen */}
          <Tooltip content={t('series_settings_panel.tooltip_cleanup')}>
            <button
              onClick={onCleanup}
              style={{
                ...buttonBaseStyle,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
            >
              🧹 Sidecar bereinigen
            </button>
          </Tooltip>

          {/* Fansub-Override */}
          <Tooltip content={t('series_settings_panel.tooltip_fansub')}>
            <button
              onClick={onFansub}
              style={{
                ...buttonBaseStyle,
                backgroundColor: hasFansubOverride ? 'var(--accent-bg)' : 'var(--bg-elevated)',
                color: hasFansubOverride ? 'var(--accent)' : 'var(--text-secondary)',
                border: hasFansubOverride ? '1px solid var(--accent)' : '1px solid var(--border)',
                fontWeight: hasFansubOverride ? 600 : 400,
                cursor: 'pointer',
              }}
            >
              🎭 Fansub-Override{hasFansubOverride ? ' ✓' : ''}
            </button>
          </Tooltip>
        </div>
      </div>

      {/* Subtitle settings link — navigates to Profiles & Overrides scoped to this series */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
        <button
          type="button"
          onClick={() => { void handleSubtitleSettings() }}
          disabled={createOverride.isPending}
          data-testid="series-subtitle-settings-link"
          style={{
            ...buttonBaseStyle,
            backgroundColor: 'var(--bg-elevated)',
            color: 'var(--accent)',
            border: '1px solid var(--accent-dim)',
            opacity: createOverride.isPending ? 0.6 : 1,
            cursor: createOverride.isPending ? 'default' : 'pointer',
          }}
        >
          {tSettings('profiles_overrides.action.subtitle_settings', 'Subtitle settings →')}
        </button>
      </div>
    </div>
  )
}
