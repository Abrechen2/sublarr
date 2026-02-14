export interface Job {
  id: string
  file_path: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  source_format: string
  output_path: string
  stats: Record<string, unknown>
  error: string
  force: boolean
  bazarr_context: Record<string, unknown> | null
  created_at: string
  completed_at: string
}

export interface PaginatedJobs {
  data: Job[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy'
  version: string
  services: Record<string, string>
}

export interface Stats {
  total_translated: number
  total_failed: number
  total_skipped: number
  today_translated: number
  by_format: Record<string, number>
  by_source: Record<string, number>
  daily: DailyStat[]
  upgrades: Record<string, number>
  bazarr_synced: number
  quality_warnings: number
  pending_jobs: number
  uptime_seconds: number
  batch_running: boolean
}

export interface DailyStat {
  date: string
  translated: number
  failed: number
  skipped: number
}

export interface BatchState {
  running: boolean
  total: number
  processed: number
  succeeded: number
  failed: number
  skipped: number
  current_file: string | null
  errors: Array<{ file: string; error: string }>
}

export interface BazarrStatus {
  configured: boolean
  reachable?: boolean
  message: string
  wanted_anime_count?: number
  translations_synced?: number
}

export interface WantedEpisode {
  series_title: string
  episode_number: string
  episode_title: string
  sonarr_series_id: number
  sonarr_episode_id: number
  path: string
  missing_subtitles: string[]
}

export interface LibraryInfo {
  series: SeriesInfo[]
  movies: MovieInfo[]
}

export interface SeriesInfo {
  id: number
  title: string
  year: number
  seasons: number
  episodes: number
  episodes_with_files: number
  path: string
  poster: string
  status: string
}

export interface MovieInfo {
  id: number
  title: string
  year: number
  has_file: boolean
  path: string
  poster: string
  status: string
}

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
  missing_languages: string[]
  status: 'wanted' | 'searching' | 'found' | 'failed' | 'ignored'
  last_search_at: string
  search_count: number
  error: string
  added_at: string
  updated_at: string
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

export interface ProviderConfigField {
  key: string
  label: string
  type: 'text' | 'password'
  required: boolean
}

export interface ProviderInfo {
  name: string
  enabled: boolean
  initialized: boolean
  healthy: boolean
  message: string
  priority: number
  downloads: number
  config_fields: ProviderConfigField[]
}

export interface ProviderStats {
  cache: Record<string, { total: number; active: number }>
  downloads: Record<string, { total: number; by_format: Record<string, number> }>
}

export interface AppConfig {
  [key: string]: string | number | boolean
}
