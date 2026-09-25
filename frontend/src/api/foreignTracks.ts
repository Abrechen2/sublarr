/**
 * Foreign-track cleanup preview API (Task 9, track variant policy).
 *
 * Backend: `backend/routes/foreign_tracks_preview.py` — POST
 * `/api/v1/foreign-tracks/preview-file`. Read-only: resolves the effective
 * track variant policy for the given file (optionally scoped to a
 * series/movie override) and returns the same per-track keep/strip verdict
 * a real strip would produce, without touching the file.
 */
import { api } from './client'
import type { TrackVerdict } from '@/components/cleanup/TrackVerdictList'

export interface PreviewFileRequest {
  path: string
  // Mutually exclusive — the backend rejects both being set at once.
  series_id?: number
  movie_id?: number
}

export interface ResolvedPolicy {
  mode: 'all' | 'one_per_language'
  keep_forced: boolean
  keep_sdh: boolean
  sidecar_policy: 'keep_embedded' | 'drop_if_real_sidecar'
}

export interface PreviewFileResponse {
  path: string
  policy: ResolvedPolicy
  verdicts: TrackVerdict[]
}

export async function previewFile(payload: PreviewFileRequest): Promise<PreviewFileResponse> {
  const { data } = await api.post('/foreign-tracks/preview-file', payload)
  return data
}
