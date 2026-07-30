/** Wanted / search types. */

export interface WantedItem {
  id: number
  item_type: 'episode' | 'movie'
  sonarr_series_id: number | null
  sonarr_episode_id: number | null
  radarr_movie_id: number | null
  title: string
  season_episode: string
  file_path: string
  existing_sub: string
  embedded_languages: Array<{ lang: string; format: string }>
  missing_languages: string[]
  target_language: string
  status: 'wanted' | 'searching' | 'found' | 'failed' | 'ignored' | 'extracted' | 'provisional'
  last_search_at: string
  search_count: number
  error: string
  retry_after: string | null
  added_at: string
  updated_at: string
  upgrade_candidate: number
  current_score: number
  instance_name?: string
  subtitle_type: 'full' | 'forced'
}

export interface WantedGroup {
  /** Stable group identity — equals file_path. */
  key: string
  title: string
  season_episode: string
  file_path: string
  item_type: 'episode' | 'movie'
  instance_name?: string
  /** One WantedItem per target_language, sorted alphabetically (de < en). */
  languages: WantedItem[]
}

export interface PaginatedWanted {
  data: WantedItem[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface WantedSummary {
  total: number
  by_type: Record<string, number>
  by_status: Record<string, number>
  by_existing: Record<string, number>
  by_subtitle_type: Record<string, number>
  upgradeable: number
  scan_running: boolean
  last_scan_at: string
}

export interface SearchResult {
  provider: string
  subtitle_id: string
  language: string
  format: string
  filename: string
  release_info: string
  score: number
  score_breakdown?: Record<string, number>
  hearing_impaired: boolean
  matches: string[]
}

export interface WantedSearchResponse {
  wanted_id: number
  target_results: SearchResult[]
  source_results: SearchResult[]
}

export interface WantedBatchStatus {
  running: boolean
  total: number
  processed: number
  found: number
  failed: number
  skipped: number
  current_item: string | null
}

// ─── Filter Presets & Batch Actions ──────────────────────────────────────────

export type FilterOperator = 'eq' | 'neq' | 'contains' | 'starts' | 'gt' | 'lt' | 'in'
export type FilterScope = 'wanted' | 'library' | 'history'

export interface FilterCondition {
  field: string
  op: FilterOperator
  value: string | string[] | number | boolean
}

export interface FilterGroup {
  logic: 'AND' | 'OR'
  conditions: (FilterCondition | FilterGroup)[]
}

export interface FilterPreset {
  id: number
  name: string
  scope: FilterScope
  conditions: FilterGroup
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface SearchResultSeries {
  id: number
  title: string
}

export interface SearchResultEpisode {
  id: number
  series_id: number
  title: string
  season_episode: string
}

export interface SearchResultSubtitle {
  id: number
  file_path: string
  provider_name: string
  language: string
}

export interface GlobalSearchResults {
  query: string
  series: SearchResultSeries[]
  episodes: SearchResultEpisode[]
  subtitles: SearchResultSubtitle[]
}

export type BatchAction = 'ignore' | 'unignore' | 'blacklist' | 'export' | 'extract' | 'translate'

export interface BatchActionResult {
  success: boolean
  action: BatchAction
  affected: number
  item_ids: number[]
  warning?: string
}
