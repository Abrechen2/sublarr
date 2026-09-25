import { api } from './client'

/** Payload for PATCH /api/v1/series/<id>/settings (scheduler overrides). */
export interface SeriesOverridePayload {
  priority_override?: string | null
  min_attempts_per_day?: number
  // 0.71.1: tri-state — true (force), false (skip), null (inherit global default).
  cleanup_foreign_tracks?: boolean | null
  // null (inherit: ASS preferred, SRT fallback) | "require_ass" (never fall back to SRT)
  subtitle_format_requirement?: string | null
}

export interface SeriesOverrideResponse {
  sonarr_series_id: number
  priority_override: string | null
  min_attempts_per_day: number
  cleanup_foreign_tracks: boolean | null
  subtitle_format_requirement: string | null
}

/**
 * Persist per-series scheduler overrides (priority tier + minimum attempts).
 *
 * Backend: `backend/routes/series_settings_overrides.py` — PATCH endpoint
 * validates priority_override ∈ {premium, standard, backlog, null} and
 * min_attempts_per_day ∈ [0, 50].
 */
export async function updateSeriesSettings(
  seriesId: number,
  payload: SeriesOverridePayload,
): Promise<SeriesOverrideResponse> {
  const { data } = await api.patch(`/series/${seriesId}/settings`, payload)
  return data
}

// ─── Track variant policy overrides (Task 9) ───────────────────────────────
//
// The four fields below live in `series_settings` too, but are NOT part of
// the tri-state `/series/<id>/settings` route above — they go through the
// profiles-overrides API (`backend/routes/profiles_overrides.py`, prefix
// `/api/v1/profiles-overrides`, NOT `/profiles/overrides`) so they inherit
// through Global -> LanguageProfile -> Series like every other field in
// `INHERITABLE_FIELDS` (`backend/services/inheritance_resolver.py`).

/** PATCH body for /profiles-overrides/series/<id> and /movie/<id>. `null` clears
 * the override and falls back to inheritance (profile, then global default). */
export interface TrackVariantOverridePayload {
  cleanup_track_variant_mode?: 'all' | 'one_per_language' | null
  cleanup_keep_forced?: boolean | null
  cleanup_keep_sdh?: boolean | null
  cleanup_sidecar_policy?: 'keep_embedded' | 'drop_if_real_sidecar' | null
}

export async function patchSeriesTrackVariantOverride(
  seriesId: number,
  payload: TrackVariantOverridePayload,
): Promise<{ ok: boolean }> {
  const { data } = await api.patch(`/profiles-overrides/series/${seriesId}`, payload)
  return data
}

export async function patchMovieTrackVariantOverride(
  movieId: number,
  payload: TrackVariantOverridePayload,
): Promise<{ ok: boolean }> {
  const { data } = await api.patch(`/profiles-overrides/movie/${movieId}`, payload)
  return data
}

export interface ResolvedChainStep {
  scope: 'global' | 'profile' | 'series' | 'movie'
  value: unknown
  label: string
}

export interface ResolvedSetting {
  effective: unknown
  source: 'global' | 'profile' | 'series' | 'movie'
  chain: ResolvedChainStep[]
}

export interface ResolvedSettingsResponse {
  scope: { type: string; id: number | null; name: string }
  settings: Record<string, ResolvedSetting>
}

export async function getResolvedSeriesSettings(seriesId: number): Promise<ResolvedSettingsResponse> {
  const { data } = await api.get(`/profiles-overrides/resolved/series/${seriesId}`)
  return data
}

export async function getResolvedMovieSettings(movieId: number): Promise<ResolvedSettingsResponse> {
  const { data } = await api.get(`/profiles-overrides/resolved/movie/${movieId}`)
  return data
}

/** Look up the raw override value (null = inherit) for one field from a
 * resolved-settings response's chain — the effective value alone can't tell
 * inherited from explicitly-set-to-the-same-value. */
export function seriesOverrideValue(
  resolved: ResolvedSettingsResponse | undefined,
  field: string,
): unknown {
  const chain = resolved?.settings[field]?.chain ?? []
  return chain.find((step) => step.scope === 'series')?.value ?? null
}
