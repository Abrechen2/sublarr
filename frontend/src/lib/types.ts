export interface Job {
  id: string
  file_path: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  source_format: string
  output_path: string
  stats: Record<string, unknown>
  error: string
  force: boolean
  arr_context: Record<string, unknown> | null
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
  profile_id: number | null
  profile_name: string
  missing_count: number
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

export interface EpisodeInfo {
  id: number
  season: number
  episode: number
  title: string
  has_file: boolean
  file_path: string
  subtitles: Record<string, string>  // lang -> "ass"|"srt"|""
  audio_languages: string[]
  monitored: boolean
}

export interface SeriesDetail {
  id: number
  title: string
  year: number
  path: string
  poster: string
  fanart: string
  overview: string
  status: string
  season_count: number
  episode_count: number
  episode_file_count: number
  tags: string[]
  profile_name: string
  target_languages: string[]
  target_language_names: string[]
  source_language: string
  source_language_name: string
  episodes: EpisodeInfo[]
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
  target_language: string
  status: 'wanted' | 'searching' | 'found' | 'failed' | 'ignored'
  last_search_at: string
  search_count: number
  error: string
  added_at: string
  updated_at: string
  upgrade_candidate: number
  current_score: number
  instance_name?: string
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
  upgradeable: number
  scan_running: boolean
  last_scan_at: string
}

export interface RetranslateStatus {
  current_hash: string
  outdated_count: number
  ollama_model: string
  target_language: string
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

export interface LanguageProfile {
  id: number
  name: string
  source_language: string
  source_language_name: string
  target_languages: string[]
  target_language_names: string[]
  is_default: boolean
}

export interface BlacklistEntry {
  id: number
  provider_name: string
  subtitle_id: string
  language: string
  file_path: string
  title: string
  reason: string
  added_at: string
}

export interface PaginatedBlacklist {
  data: BlacklistEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface HistoryEntry {
  id: number
  provider_name: string
  subtitle_id: string
  language: string
  format: string
  file_path: string
  score: number
  downloaded_at: string
}

export interface PaginatedHistory {
  data: HistoryEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface HistoryStats {
  total_downloads: number
  by_provider: Record<string, number>
  by_format: Record<string, number>
  by_language: Record<string, number>
  last_24h: number
  last_7d: number
}

export interface EpisodeHistoryEntry {
  action: 'download' | 'translate'
  provider_name: string
  format: string
  score: number
  date: string
  status: string
  error: string
}

export interface AppConfig {
  [key: string]: string | number | boolean
}
