/** Payload of the `subtitle_health_complete` WebSocket event (series scan summary). */
export interface SeriesHealthScanComplete {
  series_id: number
  error?: string
  episodes_scanned: number
  episodes_skipped?: number
  total_issues: number
  affected_episodes: number
}

type TFn = (key: string, opts?: Record<string, unknown>) => string

/** Toast text and kind for a finished series health scan. */
export function seriesHealthScanToast(
  d: SeriesHealthScanComplete,
  t: TFn,
): { message: string; kind: 'success' | 'error' } {
  if (d.error) return { message: t('subtitle_health.scan_series_failed'), kind: 'error' }
  const skipped = d.episodes_skipped ?? 0
  if (d.episodes_scanned === 0 && skipped > 0) {
    // Usually a path mapping that does not match: no video file was found on disk.
    return { message: t('subtitle_health.scan_series_no_files', { count: skipped }), kind: 'error' }
  }
  return {
    message: t('subtitle_health.scan_series_done', {
      count: d.total_issues,
      episodes: d.affected_episodes,
    }),
    kind: 'success',
  }
}
