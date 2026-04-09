import { api } from './core'
import type { LibraryInfo, SeriesDetail, MovieDetail, EpisodeHistoryEntry, WantedSearchResponse } from '@/lib/types'

// ─── Library ─────────────────────────────────────────────────────────────────

export async function getLibrary(): Promise<LibraryInfo> {
  const { data } = await api.get('/library')
  return data
}

export async function getSeriesDetail(seriesId: number): Promise<SeriesDetail> {
  const { data } = await api.get(`/library/series/${seriesId}`)
  return data
}

export async function getMovieDetail(movieId: number): Promise<MovieDetail> {
  const { data } = await api.get(`/standalone/movies/${movieId}`)
  return data
}

// ─── Episode Search & History ─────────────────────────────────────────────────

export async function episodeSearch(episodeId: number): Promise<WantedSearchResponse> {
  const { data } = await api.post(`/episodes/${episodeId}/search`)
  return data
}

export async function episodeHistory(episodeId: number): Promise<{ entries: EpisodeHistoryEntry[] }> {
  const { data } = await api.get(`/episodes/${episodeId}/history`)
  return data
}

// ─── Interactive Search ───────────────────────────────────────────────────────

export interface InteractiveSearchResult {
  provider_name: string
  subtitle_id: string
  language: string
  format: string
  filename: string
  release_info: string
  score: number
  score_breakdown?: Record<string, number>
  hearing_impaired: boolean
  forced: boolean
  matches: string[]
  machine_translated?: boolean
  mt_confidence?: number  // 0-100
  uploader_trust_bonus?: number  // 0-20
  uploader_name?: string
}

export interface InteractiveSearchResponse {
  results: InteractiveSearchResult[]
  total: number
  item: { id: number; title: string; item_type: string }
}

export interface DownloadSpecificPayload {
  provider_name: string
  subtitle_id: string
  language: string
  translate: boolean
}

export interface DownloadSpecificResult {
  success: boolean
  path?: string
  format?: string
  translated?: boolean
  error?: string
}

export async function searchInteractive(itemId: number): Promise<InteractiveSearchResponse> {
  const { data } = await api.get(`/wanted/${itemId}/search-providers`)
  return data
}

export async function searchInteractiveEpisode(episodeId: number): Promise<InteractiveSearchResponse> {
  const { data } = await api.get(`/episodes/${episodeId}/search-providers`)
  return data
}

export async function downloadSpecific(itemId: number, payload: DownloadSpecificPayload): Promise<DownloadSpecificResult> {
  const { data } = await api.post(`/wanted/${itemId}/download-specific`, payload)
  return data
}

export async function downloadSpecificEpisode(episodeId: number, payload: DownloadSpecificPayload): Promise<DownloadSpecificResult> {
  const { data } = await api.post(`/episodes/${episodeId}/download-specific`, payload)
  return data
}

// ─── Subtitle Sidecar Management ─────────────────────────────────────────────

export async function listEpisodeTracks(epId: number): Promise<import('@/lib/types').EpisodeTracksResponse> {
  const { data } = await api.get(`/library/episodes/${epId}/tracks`)
  return data
}

export async function extractTrack(epId: number, index: number, language?: string): Promise<import('@/lib/types').ExtractTrackResult> {
  const body: Record<string, unknown> = {}
  if (language) body.language = language
  const { data } = await api.post(`/library/episodes/${epId}/tracks/${index}/extract`, body)
  return data
}

export async function trackAsSource(epId: number, index: number): Promise<import('@/lib/types').TrackAsSourceResult> {
  const { data } = await api.post(`/library/episodes/${epId}/tracks/${index}/use-as-source`)
  return data
}

export async function removeTrackFromContainer(
  epId: number,
  index: number,
  subtitleTrackIndex?: number,
): Promise<{ job_id: string; status: string }> {
  const body: Record<string, unknown> = {}
  if (subtitleTrackIndex !== undefined) body.subtitle_track_index = subtitleTrackIndex
  const { data } = await api.post(`/library/episodes/${epId}/tracks/${index}/remove-from-container`, body)
  return data
}

export async function getRemuxJob(jobId: string): Promise<{ job_id: string; status: string; result: Record<string, string> | null; error: string | null }> {
  const { data } = await api.get(`/remux/jobs/${jobId}`)
  return data
}

export async function restoreRemuxBackup(backupPath: string, videoPath: string): Promise<{ restored: string; backup_removed: string }> {
  const { data } = await api.post('/remux/backups/restore', { backup_path: backupPath, video_path: videoPath })
  return data
}

export async function listEpisodeSubtitles(epId: number): Promise<{ subtitles: import('@/lib/types').SidecarSubtitle[]; video_path: string }> {
  const { data } = await api.get(`/library/episodes/${epId}/subtitles`)
  return data
}

export async function listSeriesSubtitles(seriesId: number): Promise<{ subtitles: Record<string, import('@/lib/types').SidecarSubtitle[]> }> {
  const { data } = await api.get(`/library/series/${seriesId}/subtitles`)
  return data
}

export async function listMovieSubtitles(movieId: number): Promise<{ subtitles: import('@/lib/types').SidecarSubtitle[]; video_path: string }> {
  const { data } = await api.get(`/library/movies/${movieId}/subtitles`)
  return data
}

export async function deleteSubtitles(paths: string[], blacklist = false): Promise<{ deleted: string[]; failed: { path: string; error: string }[] }> {
  const { data } = await api.delete('/library/subtitles', { data: { paths, blacklist } })
  return data
}

export async function exportSubtitleNfo(path: string): Promise<{ status: string; nfo_path: string }> {
  const { data } = await api.post('/subtitles/export-nfo', null, { params: { path } })
  return data
}

export async function batchDeleteSeriesSubtitles(
  seriesId: number,
  filter: { languages?: string[]; formats?: string[] }
): Promise<{ deleted: number; failed: number }> {
  const { data } = await api.post(`/library/series/${seriesId}/subtitles/batch-delete`, filter)
  return data
}

export async function getSupportedLanguages(): Promise<{ code: string; name: string }[]> {
  const { data } = await api.get('/languages')
  return data
}

/** Returns a URL that triggers a browser download of a single subtitle file. */
export function getSubtitleDownloadUrl(path: string): string {
  return `/api/v1/subtitles/download?path=${encodeURIComponent(path)}`
}

/** Downloads all subtitle sidecar files for a series as a ZIP. */
export async function exportSeriesSubtitles(
  seriesId: number,
  lang?: string,
): Promise<void> {
  const params = lang ? `?lang=${encodeURIComponent(lang)}` : ""
  const { data, headers } = await api.get(
    `/series/${seriesId}/subtitles/export${params}`,
    { responseType: 'blob' },
  )
  const disposition: string = headers['content-disposition'] ?? ''
  const match = disposition.match(/filename[^;=\n]*=["']?([^"';\n]+)["']?/)
  const filename = match ? match[1].trim() : `series-${seriesId}-subtitles.zip`
  const url = URL.createObjectURL(data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function updateSeriesSettings(
  seriesId: number,
  settings: { absolute_order: boolean }
): Promise<{ success: boolean }> {
  const response = await api.put(`/library/series/${seriesId}/settings`, settings)
  return response.data
}

export async function batchExtractAllTracks(seriesId: number): Promise<{ status: string }> {
  const { data } = await api.post(`/library/series/${seriesId}/batch-extract-tracks`, {})
  return data
}

export async function exportSeriesNfo(seriesId: number): Promise<Blob> {
  const { data } = await api.post('/subtitles/export-nfo', { series_id: seriesId }, { responseType: 'blob' })
  return data
}

// ─── Fansub Preferences ──────────────────────────────────────────────────────

export async function getSeriesFansubPrefs(seriesId: number): Promise<import('@/lib/types').SeriesFansubPrefs> {
  const { data } = await api.get(`/series/${seriesId}/fansub-prefs`)
  return data
}

export async function setSeriesFansubPrefs(
  seriesId: number,
  prefs: { preferred_groups: string[]; excluded_groups: string[]; bonus: number },
): Promise<import('@/lib/types').SeriesFansubPrefs> {
  const { data } = await api.put(`/series/${seriesId}/fansub-prefs`, prefs)
  return data
}

export async function deleteSeriesFansubPrefs(seriesId: number): Promise<void> {
  await api.delete(`/series/${seriesId}/fansub-prefs`)
}

// ─── Series Audio Track Preference ────────────────────────────────────────

export async function getSeriesAudioPref(seriesId: number): Promise<import('@/lib/types').SeriesAudioPref> {
  const { data } = await api.get(`/series/${seriesId}/audio-track-pref`)
  return data
}

export async function setSeriesAudioPref(seriesId: number, trackIndex: number | null): Promise<import('@/lib/types').SeriesAudioPref> {
  const { data } = await api.put(`/series/${seriesId}/audio-track-pref`, { preferred_audio_track_index: trackIndex })
  return data
}
