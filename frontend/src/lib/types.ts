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
  absolute_order?: boolean
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
  subtitle_type: 'full' | 'forced'
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

export interface ProviderHealthStats {
  total_searches: number
  successful_downloads: number
  failed_downloads: number
  success_rate: number
  avg_score: number
  consecutive_failures: number
  last_success_at: string | null
  last_failure_at: string | null
  avg_response_time_ms: number
  last_response_time_ms: number
  auto_disabled: boolean
  disabled_until: string
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
  stats: ProviderHealthStats
}

export interface ProviderStats {
  cache: Record<string, { total: number; active: number }>
  downloads: Record<string, { total: number; by_format: Record<string, number> }>
  performance: Record<string, ProviderHealthStats & { success_rate: number; auto_disabled: boolean }>
}

export interface LanguageProfile {
  id: number
  name: string
  source_language: string
  source_language_name: string
  target_languages: string[]
  target_language_names: string[]
  is_default: boolean
  translation_backend: string
  fallback_chain: string[]
  forced_preference: 'disabled' | 'separate' | 'auto'
}

// ─── Translation Backends ────────────────────────────────────────────────────

export interface TranslationBackendInfo {
  name: string
  display_name: string
  config_fields: BackendConfigField[]
  configured: boolean
  supports_glossary: boolean
  max_batch_size: number
}

export interface BackendConfigField {
  key: string
  label: string
  type: 'text' | 'password' | 'number'
  required: boolean
  default: string
  help?: string
}

export interface BackendConfig {
  [key: string]: string
}

export interface BackendHealthResult {
  healthy: boolean
  message: string
  usage?: Record<string, unknown>
}

export interface BackendStats {
  backend_name: string
  total_requests: number
  successful_translations: number
  failed_translations: number
  total_characters: number
  avg_response_time_ms: number
  last_response_time_ms: number
  last_success_at: string | null
  last_failure_at: string | null
  last_error: string
  consecutive_failures: number
}

// ─── Media Servers ──────────────────────────────────────────────────────────

export interface MediaServerType {
  name: string           // "jellyfin", "plex", "kodi"
  display_name: string   // "Jellyfin / Emby", "Plex", "Kodi"
  config_fields: BackendConfigField[]  // Reuse existing BackendConfigField interface
}

export interface MediaServerInstance {
  type: string           // "jellyfin", "plex", "kodi"
  name: string           // User-defined name, e.g. "Living Room Plex"
  enabled: boolean
  [key: string]: unknown // Dynamic config keys (url, api_key, token, username, password, path_mapping)
}

export interface MediaServerHealthResult {
  name: string
  type: string
  healthy: boolean
  message: string
}

export interface MediaServerTestResult {
  healthy: boolean
  message: string
}

// ─── Blacklist ──────────────────────────────────────────────────────────────

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

// ─── Whisper Types ──────────────────────────────────────────────────────────
export interface WhisperBackendInfo {
  name: string
  display_name: string
  config_fields: Array<{
    key: string
    label: string
    type: 'text' | 'password' | 'number'
    required: boolean
    default: string
    help: string
  }>
  configured: boolean
  supports_gpu: boolean
  supports_language_detection: boolean
}

export interface WhisperJob {
  id: string
  file_path: string
  language: string
  status: 'queued' | 'extracting' | 'loading' | 'transcribing' | 'saving' | 'completed' | 'failed' | 'cancelled'
  progress: number
  phase: string
  backend_name: string
  detected_language: string
  language_probability: number
  srt_content: string
  segment_count: number
  duration_seconds: number
  processing_time_ms: number
  error: string
  created_at: string
  started_at: string
  completed_at: string
}

export interface WhisperConfig {
  whisper_enabled: boolean
  whisper_backend: string
  max_concurrent_whisper: number
  whisper_fallback_min_score: number
}

export interface WhisperStats {
  total: number
  by_status: Record<string, number>
  avg_processing_time: number
}

export interface WhisperHealthResult {
  healthy: boolean
  message: string
}

// ─── Standalone Mode ──────────────────────────────────────────────────────

export interface WatchedFolder {
  id: number
  path: string
  label: string
  media_type: 'auto' | 'tv' | 'movie'
  enabled: boolean
  last_scan_at: string
  created_at: string
  updated_at: string
}

export interface StandaloneSeries {
  id: number
  title: string
  year: number | null
  folder_path: string
  tmdb_id: number | null
  tvdb_id: number | null
  anilist_id: number | null
  imdb_id: string
  poster_url: string
  is_anime: boolean
  episode_count: number
  season_count: number
  metadata_source: string
  wanted_count?: number  // from joined query
  created_at: string
  updated_at: string
}

export interface StandaloneMovie {
  id: number
  title: string
  year: number | null
  file_path: string
  tmdb_id: number | null
  imdb_id: string
  poster_url: string
  metadata_source: string
  wanted?: boolean  // from joined query
  created_at: string
  updated_at: string
}

export interface StandaloneStatus {
  enabled: boolean
  watcher_running: boolean
  folders_count: number
  scanner_scanning: boolean
}

export interface StandaloneScanResult {
  folders_scanned: number
  series_found: number
  movies_found: number
  wanted_added: number
  duration_seconds: number
}

// ─── Events & Hooks ──────────────────────────────────────────────────────

export interface EventCatalogItem {
  name: string
  label: string
  description: string
  payload_keys: string[]
}

export interface HookConfig {
  id: number
  name: string
  event_name: string
  hook_type: string
  enabled: boolean
  script_path: string
  timeout_seconds: number
  last_triggered_at: string
  last_status: string
  trigger_count: number
  created_at: string
  updated_at: string
}

export interface WebhookConfig {
  id: number
  name: string
  event_name: string
  url: string
  secret: string
  enabled: boolean
  retry_count: number
  timeout_seconds: number
  last_triggered_at: string
  last_status_code: number
  last_error: string
  consecutive_failures: number
  trigger_count: number
  created_at: string
  updated_at: string
}

export interface HookLog {
  id: number
  hook_id: number | null
  webhook_id: number | null
  event_name: string
  hook_type: string
  success: boolean
  exit_code: number | null
  status_code: number | null
  stdout: string
  stderr: string
  error: string
  duration_ms: number
  triggered_at: string
}

export interface HookTestResult {
  success: boolean
  exit_code?: number
  stdout?: string
  stderr?: string
  status_code?: number
  error?: string
  duration_ms: number
}

export interface ScoringWeights {
  episode: Record<string, number>
  movie: Record<string, number>
  defaults: {
    episode: Record<string, number>
    movie: Record<string, number>
  }
}

export interface ProviderModifiers {
  [provider_name: string]: number
}

// ─── Track Manifest (Phase 29) ───────────────────────────────────────────────

export interface Track {
  index: number
  sub_index: number
  codec_type: 'audio' | 'subtitle'
  codec: string
  language: string
  title: string
  forced: boolean
  default: boolean
}

export interface EpisodeTracksResponse {
  tracks: Track[]
  video_path: string
}

export interface ExtractTrackResult {
  output_path: string
  language: string
  format: string
  track: Track
}

export interface TrackAsSourceResult {
  content: string
  format: string
  language: string
  title: string
}

// ─── Statistics ──────────────────────────────────────────────────────────────

export interface StatisticsData {
  daily: DailyStat[]
  providers: Record<string, ProviderHealthStats>
  downloads_by_provider: Array<{ provider_name: string; count: number; avg_score: number }>
  backend_stats: Array<{ backend_name: string; total_requests: number; successful_translations: number; failed_translations: number; total_characters: number }>
  upgrades: Array<{ type: string; count: number }>
  by_format: Record<string, number>
  range: string
}

// ─── Backup ──────────────────────────────────────────────────────────────────

export interface FullBackupInfo {
  filename: string
  size_bytes: number
  created_at: string
  contents: string[]
}

export interface SubtitleToolResult {
  status: string
  [key: string]: unknown
}

export interface LogRotationConfig {
  max_size_mb: number
  backup_count: number
}

// ─── Scheduler Tasks ──────────────────────────────────────────────────────────

export interface SchedulerTask {
  name: string
  display_name: string
  running: boolean
  last_run: string | null
  next_run: string | null
  interval_hours: number | null
  enabled: boolean
}

export interface TasksResponse {
  tasks: SchedulerTask[]
}

// ─── Subtitle Editor ──────────────────────────────────────────────────────────

export interface SubtitleContent {
  format: 'ass' | 'srt'
  content: string
  encoding: string
  size_bytes: number
  total_lines: number
  last_modified: number
}

export interface SubtitleSaveResult {
  status: string
  backup_path: string
  new_mtime: number
}

export interface SubtitleBackup {
  content: string
  encoding: string
  backup_path: string
}

export interface SubtitleValidation {
  valid: boolean
  error?: string
  event_count?: number
  style_count?: number
  warnings: string[]
}

export interface SubtitleCue {
  start: number    // seconds
  end: number      // seconds
  text: string
  style: string
  quality_score?: number  // 0-100, present when .quality.json sidecar exists
}

export interface SubtitleParseResult {
  cues: SubtitleCue[]
  total_duration: number
  cue_count: number
  format: string
  styles: Record<string, string> | null  // style_name -> "dialog"|"signs"|"songs"
  has_quality_scores?: boolean  // true when at least one cue has a quality_score
}

// ─── Health Check & Quality ─────────────────────────────────────────────────

export interface HealthIssue {
  check: string
  severity: 'error' | 'warning' | 'info'
  message: string
  line: number | null
  auto_fixable: boolean
  fix: string | null
}

export interface HealthCheckResult {
  file_path: string
  checks_run: number
  issues: HealthIssue[]
  score: number
  checked_at: string
}

export interface HealthCheckBatchResult {
  results: HealthCheckResult[]
  summary: {
    total: number
    avg_score: number
    total_issues: number
  }
}

export interface HealthFixResult {
  status: string
  fixes_applied: string[]
  counts: Record<string, number>
  new_score: number
  remaining_issues: number
}

export interface QualityTrend {
  date: string
  avg_score: number
  issues_count: number
  files_checked: number
}

// ─── Comparison ─────────────────────────────────────────────────────────────

export interface ComparisonPanel {
  path: string
  content: string
  format: 'ass' | 'srt'
  encoding: string
  total_lines: number
}

export interface ComparisonResponse {
  panels: ComparisonPanel[]
}

// ─── Sync ───────────────────────────────────────────────────────────────────

export interface SyncPreviewEvent {
  index: number
  before_start: string
  before_end: string
  after_start: string
  after_end: string
  text: string
}

export interface SyncResult {
  status: string
  operation: string
  events: number
}

export interface SyncPreviewResult {
  preview: SyncPreviewEvent[]
  operation: string
  total_events: number
}


// ─── Phase 22: Auto-Sync ─────────────────────────────────────────────────────

export interface AutoSyncResult {
  status: string
  file_path: string
  engine: string
  backup_path?: string
  message?: string
}

export interface AutoSyncBulkResult {
  status: string
  total_items: number
  message: string
}

export interface SyncBatchProgress {
  current: number
  total: number
  file_path: string
  completed: number
  failed: number
  error?: string
}

export interface SyncBatchComplete {
  completed: number
  failed: number
  total: number
}

// ─── Phase 12: Batch Operations + Smart-Filter ────────────────────────────

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

export type BatchAction = 'ignore' | 'unignore' | 'blacklist' | 'export'

export interface BatchActionResult {
  success: boolean
  action: BatchAction
  affected: number
  item_ids: number[]
  warning?: string
}

// ─── API Key Management ──────────────────────────────────────────────────────

export interface ApiKeyService {
  service: string
  keys: { name: string; status: 'configured' | 'missing'; masked_value: string }[]
  testable: boolean
}

export interface ApiKeyExportData {
  config: Record<string, string>
  profiles: unknown[]
  glossary: unknown[]
}

export interface BazarrMigrationPreview {
  config_entries: { key: string; value: string; current_value: string }[]
  profiles: unknown[]
  blacklist_count: number
  warnings: string[]
}

// ─── Notification Templates ──────────────────────────────────────────────────

export interface NotificationTemplate {
  id: number
  name: string
  title_template: string
  body_template: string
  event_type: string | null
  service_name: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface NotificationHistoryEntry {
  id: number
  event_type: string
  title: string
  body: string
  template_id: number | null
  status: string
  error: string
  sent_at: string
}

export interface QuietHoursConfig {
  id: number
  name: string
  start_time: string
  end_time: string
  days_of_week: number[]
  exception_events: string[]
  enabled: boolean
}

export interface TemplateVariable {
  name: string
  description: string
  sample_value: string
}

export interface NotificationFilter {
  include_events: string[]
  exclude_events: string[]
  content_filters: { field: string; operator: string; value: string }[]
}

// ─── Cleanup System ─────────────────────────────────────────────────────────

export interface SubtitleHashEntry {
  file_path: string
  content_hash: string
  file_size: number
  format: string
  language: string | null
  line_count: number | null
  last_scanned: string
}

export interface DuplicateGroup {
  content_hash: string
  files: SubtitleHashEntry[]
}

export interface CleanupRule {
  id: number
  name: string
  rule_type: 'dedup' | 'orphaned' | 'old_backups'
  config_json: Record<string, unknown>
  enabled: boolean
  last_run_at: string | null
  created_at: string
}

export interface CleanupHistoryEntry {
  id: number
  rule_id: number | null
  action_type: string
  files_processed: number
  files_deleted: number
  bytes_freed: number
  performed_at: string
}

export interface DiskSpaceStats {
  total_files: number
  total_size_bytes: number
  by_format: { format: string; count: number; size_bytes: number }[]
  duplicate_files: number
  duplicate_size_bytes: number
  potential_savings_bytes: number
  trends: { date: string; bytes_freed: number }[]
}

export interface ScanStatus {
  status: 'idle' | 'scanning'
  progress: number
  total: number
  scan_id: string | null
}

export interface CleanupPreviewData {
  files: { path: string; size_bytes: number; action: string }[]
  total_size_bytes: number
  total_files: number
}

export interface OrphanedFile {
  file_path: string
  file_size: number
  format: string
  language: string | null
  last_modified: string
}

// ─── External Integrations ──────────────────────────────────────────────────

export interface ExtendedHealthCheck {
  connection: { healthy: boolean; message: string }
  api_version?: { version: string; branch: string; app_name: string }
  server_info?: {
    server_name?: string
    friendly_name?: string
    version: string
    product_name?: string
    platform?: string
    os?: string
    name?: string
    jsonrpc_version?: string
  }
  library_access: {
    series_count?: number
    movie_count?: number
    library_count?: number
    section_count?: number
    video_sources_count?: number
    accessible: boolean
    libraries?: Array<{ name: string; collectionType?: string }>
    sections?: Array<{ title: string; type: string }>
    video_sources?: Array<{ label: string }>
  }
  webhook_status?: {
    configured: boolean
    sublarr_webhooks: Array<{ name: string }>
  }
  health_issues: Array<{ type: string; message: string }>
}

export interface ExtendedHealthAllResponse {
  sonarr: Array<{ name: string } & ExtendedHealthCheck>
  radarr: Array<{ name: string } & ExtendedHealthCheck>
  jellyfin: ExtendedHealthCheck | null
  media_servers: Array<{ name: string; type: string } & ExtendedHealthCheck>
}

export interface BazarrMappingReport {
  tables_found: string[]
  table_details: Record<string, {
    row_count: number
    columns: string[]
    sample_row: Record<string, unknown> | null
  }>
  migration_summary: {
    profiles_count: number
    blacklist_count: number
    shows_count: number
    movies_count: number
    history_count: number
    has_sonarr_config: boolean
    has_radarr_config: boolean
  }
  compatibility: {
    bazarr_version: string | null
    schema_version: string | null
  }
  warnings: string[]
}

export interface CompatCheckResult {
  compatible: boolean
  issues: string[]
  warnings: string[]
  recommendations: string[]
}

export interface CompatBatchResult {
  results: Array<{ path: string } & CompatCheckResult>
  summary: { total: number; compatible: number; incompatible: number }
}

export interface ExportResult {
  format: string
  data: unknown
  filename: string
  content_type: string
  warnings: string[]
}
