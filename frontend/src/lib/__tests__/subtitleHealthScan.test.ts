import { describe, it, expect } from 'vitest'

import { seriesHealthScanToast } from '../subtitleHealthScan'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${JSON.stringify(opts)}` : key

const base = {
  series_id: 7,
  episodes_scanned: 3,
  episodes_skipped: 0,
  total_issues: 4,
  affected_episodes: 2,
}

describe('seriesHealthScanToast', () => {
  it('reports the issue totals of a finished scan', () => {
    expect(seriesHealthScanToast(base, t)).toEqual({
      message: 'subtitle_health.scan_series_done:{"count":4,"episodes":2}',
      kind: 'success',
    })
  })

  it('flags a scan that found no file on disk instead of a silent success', () => {
    const toast = seriesHealthScanToast(
      { ...base, episodes_scanned: 0, episodes_skipped: 5, total_issues: 0, affected_episodes: 0 },
      t,
    )
    expect(toast).toEqual({
      message: 'subtitle_health.scan_series_no_files:{"count":5}',
      kind: 'error',
    })
  })

  it('shows a failed scan as an error', () => {
    expect(seriesHealthScanToast({ ...base, error: 'Sonarr not configured' }, t).kind).toBe('error')
  })
})
