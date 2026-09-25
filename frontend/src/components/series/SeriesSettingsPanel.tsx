import type React from 'react'
import { useState } from 'react'
import type { SeriesDetail } from '@/lib/types'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Tooltip } from '@/components/shared/Tooltip'
import { useLanguageProfiles, useAssignProfile } from '@/hooks/useApi'
import {
  getResolvedSeriesSettings,
  patchSeriesTrackVariantOverride,
  seriesOverrideValue,
  type TrackVariantOverridePayload,
} from '@/api/seriesSettings'
import { previewFile } from '@/api/foreignTracks'
import { TrackVerdictList } from '@/components/cleanup/TrackVerdictList'

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
  readonly onScanHealth: () => void
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
  onScanHealth,
  updatePending,
  refreshPending,
}: SeriesSettingsPanelProps) {
  const { t } = useTranslation('library')
  const { data: profilesData } = useLanguageProfiles()
  const assignProfile = useAssignProfile()
  const profiles = profilesData ?? []

  // ─── Track variant policy overrides (1.15.0) ───────────────────────────
  // Resolved through the profiles-overrides API (Global -> Profile ->
  // Series inheritance), NOT part of SeriesDetail — see api/seriesSettings.ts.
  const queryClient = useQueryClient()
  const resolvedQueryKey = ['series-track-variant-resolved', seriesId]
  const resolvedQuery = useQuery({
    queryKey: resolvedQueryKey,
    queryFn: () => getResolvedSeriesSettings(seriesId),
  })
  const patchOverride = useMutation({
    mutationFn: (payload: TrackVariantOverridePayload) =>
      patchSeriesTrackVariantOverride(seriesId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: resolvedQueryKey })
    },
  })

  const modeOverride = seriesOverrideValue(resolvedQuery.data, 'cleanup_track_variant_mode') as
    | 'all'
    | 'one_per_language'
    | null
  const keepForcedOverride = seriesOverrideValue(resolvedQuery.data, 'cleanup_keep_forced') as
    | boolean
    | null
  const keepSdhOverride = seriesOverrideValue(resolvedQuery.data, 'cleanup_keep_sdh') as
    | boolean
    | null
  const sidecarPolicyOverride = seriesOverrideValue(resolvedQuery.data, 'cleanup_sidecar_policy') as
    | 'keep_embedded'
    | 'drop_if_real_sidecar'
    | null
  const modeEffective = resolvedQuery.data?.settings.cleanup_track_variant_mode?.effective as
    | 'all'
    | 'one_per_language'
    | undefined
  // Policy B (keep_forced / keep_sdh / sidecar_policy) only takes effect in
  // "one_per_language" mode — mirrors the global settings page ruling.
  const policyBActive = modeEffective === 'one_per_language'

  const variantLabel = (mode: 'all' | 'one_per_language' | undefined) =>
    mode === 'one_per_language'
      ? t('series_settings_panel.variant_one', { defaultValue: 'One main track per language' })
      : t('series_settings_panel.variant_all', { defaultValue: 'Keep all variants' })

  // Preview: per-episode keep/strip verdict for the effective policy.
  const episodesWithFile = series.episodes.filter((ep) => ep.has_file && ep.file_path)
  const [previewEpisodeId, setPreviewEpisodeId] = useState<number | null>(
    episodesWithFile[0]?.id ?? null,
  )
  const previewMutation = useMutation({
    mutationFn: (path: string) => previewFile({ path, series_id: seriesId }),
  })
  const handlePreview = () => {
    const ep = episodesWithFile.find((e) => e.id === previewEpisodeId)
    if (!ep) return
    previewMutation.mutate(ep.file_path)
  }

  return (
    <div
      className="bg-surface border border-border rounded-md p-4 flex flex-col gap-4 mb-4"
    >
      {/* Language section */}
      <div>
        <div style={sectionLabelStyle}>{t('series_settings_panel.section_language')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          <select
            aria-label={t('series_settings_panel.select_profile_aria', 'Select language profile')}
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
              <option value="">{series.profile_name || t('series_settings_panel.default_profile')}</option>
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
              {t('series_settings_panel.source_label')} {series.source_language_name}
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
            📖 {t('series_settings_panel.glossary')}
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
            {t('series_settings_panel.absolute_order')}
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
              🔄 {t('series_settings_panel.anidb_refresh')}
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
                aria-label={t('series_settings_panel.cleanup_foreign_tracks_aria')}
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
                className="text-[11px] py-0.5 px-1.5 rounded border border-border bg-elevated text-secondary"
              >
                <option value="null">
                  {t('series_settings_panel.cleanup_inherit', {
                    defaultValue: 'Inherit',
                  })}
                  {series.cleanup_foreign_tracks_effective !== undefined
                    ? ` (${series.cleanup_foreign_tracks_effective ? t('series_settings_panel.on') : t('series_settings_panel.off')})`
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

        {/* Track variant policy overrides (1.15.0) — profiles-overrides API.
            "Inherit" (null) falls back through Profile -> Global. */}
        <div
          className="flex flex-wrap gap-2 items-center mt-2 pt-2"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <label className="flex items-center gap-1.5 text-[11px] text-secondary">
            <span>
              {t('series_settings_panel.track_variant_mode_label', {
                defaultValue: 'Variants per language:',
              })}
            </span>
            <select
              aria-label={t('series_settings_panel.track_variant_mode_aria', {
                defaultValue: 'Variants per language override',
              })}
              disabled={patchOverride.isPending}
              value={modeOverride ?? 'null'}
              onChange={(e) => {
                const next = e.target.value
                patchOverride.mutate({
                  cleanup_track_variant_mode:
                    next === 'null' ? null : (next as 'all' | 'one_per_language'),
                })
              }}
              className="text-[11px] px-1.5 py-0.5 rounded border border-border bg-elevated text-secondary"
            >
              <option value="null">
                {t('series_settings_panel.cleanup_inherit', { defaultValue: 'Inherit' })}
                {modeEffective !== undefined ? ` (${variantLabel(modeEffective)})` : ''}
              </option>
              <option value="all">{variantLabel('all')}</option>
              <option value="one_per_language">{variantLabel('one_per_language')}</option>
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-secondary">
            <span>
              {t('series_settings_panel.keep_forced_label', { defaultValue: 'Keep forced:' })}
            </span>
            <select
              aria-label={t('series_settings_panel.keep_forced_aria', {
                defaultValue: 'Keep forced override',
              })}
              disabled={patchOverride.isPending || !policyBActive}
              title={
                policyBActive
                  ? undefined
                  : t('series_settings_panel.variant_only_hint', {
                      defaultValue: 'Only applies with "One main track per language".',
                    })
              }
              value={
                keepForcedOverride === true ? 'true' : keepForcedOverride === false ? 'false' : 'null'
              }
              onChange={(e) => {
                const next = e.target.value
                patchOverride.mutate({
                  cleanup_keep_forced: next === 'null' ? null : next === 'true',
                })
              }}
              className="text-[11px] px-1.5 py-0.5 rounded border border-border bg-elevated text-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="null">
                {t('series_settings_panel.cleanup_inherit', { defaultValue: 'Inherit' })}
              </option>
              <option value="true">
                {t('series_settings_panel.cleanup_always', { defaultValue: 'Always' })}
              </option>
              <option value="false">
                {t('series_settings_panel.cleanup_never', { defaultValue: 'Never' })}
              </option>
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-secondary">
            <span>{t('series_settings_panel.keep_sdh_label', { defaultValue: 'Keep SDH:' })}</span>
            <select
              aria-label={t('series_settings_panel.keep_sdh_aria', {
                defaultValue: 'Keep SDH override',
              })}
              disabled={patchOverride.isPending || !policyBActive}
              title={
                policyBActive
                  ? undefined
                  : t('series_settings_panel.variant_only_hint', {
                      defaultValue: 'Only applies with "One main track per language".',
                    })
              }
              value={keepSdhOverride === true ? 'true' : keepSdhOverride === false ? 'false' : 'null'}
              onChange={(e) => {
                const next = e.target.value
                patchOverride.mutate({
                  cleanup_keep_sdh: next === 'null' ? null : next === 'true',
                })
              }}
              className="text-[11px] px-1.5 py-0.5 rounded border border-border bg-elevated text-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="null">
                {t('series_settings_panel.cleanup_inherit', { defaultValue: 'Inherit' })}
              </option>
              <option value="true">
                {t('series_settings_panel.cleanup_always', { defaultValue: 'Always' })}
              </option>
              <option value="false">
                {t('series_settings_panel.cleanup_never', { defaultValue: 'Never' })}
              </option>
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-secondary">
            <span>
              {t('series_settings_panel.sidecar_policy_label', {
                defaultValue: 'When a real subtitle sits next to it:',
              })}
            </span>
            <select
              aria-label={t('series_settings_panel.sidecar_policy_aria', {
                defaultValue: 'Sidecar policy override',
              })}
              disabled={patchOverride.isPending || !policyBActive}
              title={
                policyBActive
                  ? undefined
                  : t('series_settings_panel.variant_only_hint', {
                      defaultValue: 'Only applies with "One main track per language".',
                    })
              }
              value={sidecarPolicyOverride ?? 'null'}
              onChange={(e) => {
                const next = e.target.value
                patchOverride.mutate({
                  cleanup_sidecar_policy:
                    next === 'null' ? null : (next as 'keep_embedded' | 'drop_if_real_sidecar'),
                })
              }}
              className="text-[11px] px-1.5 py-0.5 rounded border border-border bg-elevated text-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="null">
                {t('series_settings_panel.cleanup_inherit', { defaultValue: 'Inherit' })}
              </option>
              <option value="keep_embedded">
                {t('series_settings_panel.sidecar_keep', { defaultValue: 'Keep the embedded track' })}
              </option>
              <option value="drop_if_real_sidecar">
                {t('series_settings_panel.sidecar_drop', {
                  defaultValue: 'Remove the embedded main track',
                })}
              </option>
            </select>
          </label>

          {episodesWithFile.length > 0 && (
            <label className="flex items-center gap-1.5 text-[11px] text-secondary">
              <select
                aria-label={t('series_settings_panel.preview_episode_select_aria', {
                  defaultValue: 'Choose an episode to preview',
                })}
                value={previewEpisodeId ?? ''}
                onChange={(e) => setPreviewEpisodeId(Number(e.target.value))}
                className="text-[11px] px-1.5 py-0.5 rounded border border-border bg-elevated text-secondary"
              >
                {episodesWithFile.map((ep) => (
                  <option key={ep.id} value={ep.id}>
                    S{String(ep.season).padStart(2, '0')}E{String(ep.episode).padStart(2, '0')}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handlePreview}
                disabled={previewMutation.isPending}
                className="text-[11px] px-2.5 py-1 rounded border border-border bg-elevated text-secondary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {previewMutation.isPending
                  ? t('series_settings_panel.preview_loading', { defaultValue: 'Loading preview…' })
                  : t('series_settings_panel.preview_episode_button', {
                      defaultValue: 'Preview one episode',
                    })}
              </button>
            </label>
          )}
        </div>

        {previewMutation.isError && (
          <div className="text-[11px] mt-1 text-error">
            {t('series_settings_panel.preview_failed', { defaultValue: 'Preview failed' })}
          </div>
        )}
        {previewMutation.data && (
          <div className="mt-2 pl-1">
            <TrackVerdictList verdicts={previewMutation.data.verdicts} />
          </div>
        )}
      </div>

      {/* Tools section */}
      <div>
        <div style={sectionLabelStyle}>{t('series_settings_panel.section_tools')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          {/* Untertitel exportieren */}
          <Tooltip content={t('series_settings_panel.tooltip_export_zip')}>
            <button
              onClick={onExport}
              className="text-[11px] px-2.5 py-1 rounded bg-elevated text-secondary border border-border cursor-pointer"
            >
              📦 {t('series_settings_panel.export_subtitles')}
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
                ? `${t('series_settings_panel.extracting')} ${extractProgress ? `${extractProgress.current}/${extractProgress.total}` : ''}`
                : `🎵 ${t('series_settings_panel.extract_embedded')}`
              }
            </button>
          </Tooltip>

          {/* Sidecar bereinigen */}
          <Tooltip content={t('series_settings_panel.tooltip_cleanup')}>
            <button
              onClick={onCleanup}
              className="text-[11px] px-2.5 py-1 rounded bg-elevated text-secondary border border-border cursor-pointer"
            >
              🧹 {t('series_settings_panel.cleanup_sidecar')}
            </button>
          </Tooltip>

          {/* Untertitel-Gesundheit prüfen (ganze Serie) */}
          <button
            onClick={onScanHealth}
            className="text-[11px] px-2.5 py-1 rounded bg-elevated text-secondary border border-border cursor-pointer"
          >
            🩺 {t('subtitle_health.scan_series')}
          </button>

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
              🎭 {t('series_settings_panel.fansub_override')}{hasFansubOverride ? ' ✓' : ''}
            </button>
          </Tooltip>
        </div>
      </div>

    </div>
  )
}
