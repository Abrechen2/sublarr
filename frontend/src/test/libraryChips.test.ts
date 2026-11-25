import { describe, expect, it } from 'vitest'
import { matchesSeriesChip } from '@/pages/libraryChips'
import type { SeriesInfo } from '@/types/library'

const series = (over: Partial<SeriesInfo>): SeriesInfo => ({
  id: 1, title: 'X', year: 2020, seasons: 1, episodes: 10, episodes_with_files: 10,
  path: '/x', poster: '', status: 'ended', profile_id: null, profile_name: 'Default',
  missing_count: 0, ...over,
})

describe('library quick filters (#50)', () => {
  it('anime keeps only series Sonarr classifies as anime', () => {
    expect(matchesSeriesChip(series({ status: 'continuing', seasons: 3 }), 'anime')).toBe(false)
    expect(matchesSeriesChip(series({ title: 'Anime Club' }), 'anime')).toBe(false)
    expect(matchesSeriesChip(series({ is_anime: true }), 'anime')).toBe(true)
  })

  it('low score reads upgrade candidates, not video-file coverage', () => {
    expect(matchesSeriesChip(series({ episodes_with_files: 2 }), 'low_score')).toBe(false)
    expect(matchesSeriesChip(series({ low_score_count: 3 }), 'low_score')).toBe(true)
  })

  it('missing and complete keep their meaning', () => {
    expect(matchesSeriesChip(series({ missing_count: 2 }), 'missing')).toBe(true)
    expect(matchesSeriesChip(series({}), 'complete')).toBe(true)
    expect(matchesSeriesChip(series({ episodes: 0 }), 'complete')).toBe(false)
  })
})
