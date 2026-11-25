import type { SeriesInfo } from '@/types/library'

export type SeriesChip = 'all' | 'missing' | 'complete' | 'low_score' | 'anime'

/**
 * Whether a series passes a library quick filter.
 *
 * "low_score" and "anime" read the backend's data: open upgrade candidates
 * and Sonarr's anime classification. They used to guess from video-file
 * coverage and from "continuing or has seasons", which matched almost every
 * series (#50).
 */
export function matchesSeriesChip(series: SeriesInfo, chip: string): boolean {
  switch (chip) {
    case 'missing':
      return (series.missing_count ?? 0) > 0
    case 'complete':
      return series.missing_count === 0 && series.episodes > 0
    case 'low_score':
      return (series.low_score_count ?? 0) > 0
    case 'anime':
      return series.is_anime === true
    default:
      return true
  }
}
