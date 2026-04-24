import { api } from './client'

/** Payload for PATCH /api/v1/series/<id>/settings (scheduler overrides). */
export interface SeriesOverridePayload {
  priority_override?: string | null
  min_attempts_per_day?: number
  // 0.71.1: tri-state — true (force), false (skip), null (inherit global default).
  cleanup_foreign_tracks?: boolean | null
}

export interface SeriesOverrideResponse {
  sonarr_series_id: number
  priority_override: string | null
  min_attempts_per_day: number
  cleanup_foreign_tracks: boolean | null
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
