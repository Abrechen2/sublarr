/**
 * TrackPolicyOverrides — the four track-variant-policy override selects
 * (mode, keep-forced, keep-SDH, sidecar policy), shared between the series
 * settings panel and the movie subtitle-settings card (owner-approved spec
 * 2026-09-25: series AND movies get the same overrides).
 *
 * Resolved/patched through the profiles-overrides API (Global -> Profile ->
 * Series/Movie inheritance) — NOT part of SeriesDetail/MovieDetail, see
 * api/seriesSettings.ts. "Inherit" always sends `null`.
 *
 * keep_forced / keep_sdh / sidecar_policy only take effect in
 * "one_per_language" mode, so they're disabled (with a hint) whenever the
 * *effective* mode resolves to "all" — mirrors the ruling on the global
 * Subtitle Automation settings page.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  getResolvedSeriesSettings,
  getResolvedMovieSettings,
  patchSeriesTrackVariantOverride,
  patchMovieTrackVariantOverride,
  seriesOverrideValue,
  type TrackVariantOverridePayload,
} from '@/api/seriesSettings'

export interface TrackPolicyOverridesProps {
  scope: 'series' | 'movie'
  id: number
}

const SELECT_CLASS =
  'text-[11px] px-1.5 py-0.5 rounded border border-border bg-elevated text-secondary'
const SELECT_CLASS_DISABLEABLE = `${SELECT_CLASS} disabled:opacity-50 disabled:cursor-not-allowed`

export function TrackPolicyOverrides({ scope, id }: TrackPolicyOverridesProps) {
  const { t } = useTranslation('library')
  const queryClient = useQueryClient()
  const resolvedQueryKey = ['track-policy-resolved', scope, id]

  const resolvedQuery = useQuery({
    queryKey: resolvedQueryKey,
    queryFn: () =>
      scope === 'series' ? getResolvedSeriesSettings(id) : getResolvedMovieSettings(id),
  })
  const patchOverride = useMutation({
    mutationFn: (payload: TrackVariantOverridePayload) =>
      scope === 'series'
        ? patchSeriesTrackVariantOverride(id, payload)
        : patchMovieTrackVariantOverride(id, payload),
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
  // "one_per_language" mode.
  const policyBActive = modeEffective === 'one_per_language'
  const policyBTitle = policyBActive
    ? undefined
    : t('series_settings_panel.variant_only_hint', {
        defaultValue: 'Only applies with "One main track per language".',
      })

  const variantLabel = (mode: 'all' | 'one_per_language' | undefined) =>
    mode === 'one_per_language'
      ? t('series_settings_panel.variant_one', { defaultValue: 'One main track per language' })
      : t('series_settings_panel.variant_all', { defaultValue: 'Keep all variants' })

  return (
    <div className="flex flex-wrap gap-2 items-center">
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
          className={SELECT_CLASS}
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
        <span>{t('series_settings_panel.keep_forced_label', { defaultValue: 'Keep forced:' })}</span>
        <select
          aria-label={t('series_settings_panel.keep_forced_aria', {
            defaultValue: 'Keep forced override',
          })}
          disabled={patchOverride.isPending || !policyBActive}
          title={policyBTitle}
          value={keepForcedOverride === true ? 'true' : keepForcedOverride === false ? 'false' : 'null'}
          onChange={(e) => {
            const next = e.target.value
            patchOverride.mutate({
              cleanup_keep_forced: next === 'null' ? null : next === 'true',
            })
          }}
          className={SELECT_CLASS_DISABLEABLE}
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
          title={policyBTitle}
          value={keepSdhOverride === true ? 'true' : keepSdhOverride === false ? 'false' : 'null'}
          onChange={(e) => {
            const next = e.target.value
            patchOverride.mutate({
              cleanup_keep_sdh: next === 'null' ? null : next === 'true',
            })
          }}
          className={SELECT_CLASS_DISABLEABLE}
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
          title={policyBTitle}
          value={sidecarPolicyOverride ?? 'null'}
          onChange={(e) => {
            const next = e.target.value
            patchOverride.mutate({
              cleanup_sidecar_policy:
                next === 'null' ? null : (next as 'keep_embedded' | 'drop_if_real_sidecar'),
            })
          }}
          className={SELECT_CLASS_DISABLEABLE}
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
    </div>
  )
}
