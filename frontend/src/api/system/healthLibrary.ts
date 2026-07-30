/** Library health overview — GET /api/v1/health/library (Health page). */
import { api } from '../core'

export interface HealthSeriesRow {
  title: string
  item_type: string
  missing: number
  problems: number
}

export interface HealthProblemRow {
  id: number
  title: string
  season_episode: string
  item_type: string
  target_language: string
  status: string
  failure_kind: string | null
  error: string
  search_count: number
  updated_at: string | null
}

export interface HealthProviderRow {
  provider: string
  breaker_state: string
  breaker_failures: number
  searches: number
  hit_rate: number | null
  failed_downloads: number
  auto_disabled: boolean
  degraded: boolean
}

export interface LibraryHealth {
  totals: {
    wanted: number
    problems: number
    unmatched: number
    series_affected: number
    providers_degraded: number
  }
  series: HealthSeriesRow[]
  problems: HealthProblemRow[]
  providers: HealthProviderRow[]
}

export async function getLibraryHealth(): Promise<LibraryHealth> {
  const { data } = await api.get('/health/library')
  return data
}
