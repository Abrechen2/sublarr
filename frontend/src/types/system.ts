/** System-level types â€” blacklist, history, standalone, statistics, backup, scheduler, subtitle tools, health, sync, cleanup, integrations, notifications, diff, player, support. */

import type { ProviderHealthStats } from './providers'

// â”€â”€â”€ Blacklist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface BlacklistEntry {
  id: number
  provider_name: string
  subtitle_id: string
  language: string
  file_path: string
  title: string
  reason: string
  added_at: string
  /** Plan B3 â€” optional SHA-256 or OpenSubtitles hash for provider-agnostic retry suppression */
  file_hash?: string | null
}

export interface PaginatedBlacklist {
  data: BlacklistEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

// â”€â”€â”€ History â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/** Advisory LLM quality verdict for a downloaded subtitle (experimental). */
export interface AIQualityInfo {
  verdict: 'green' | 'yellow' | 'red' | string
  scores?: Record<string, number>
  reasons?: string[]
  model?: string
  sampled_cues?: number
  created_at?: string | null
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
  has_decision_log?: boolean
  ai_quality?: AIQualityInfo | null
}

// ─── Decision Log ─────────────────────────────────────────────────────────────

export interface DecisionLogProvider {
  name: string
  status: 'ok' | 'skipped' | 'timeout' | 'rate_limited' | 'error'
  reason?: string
  detail?: string
  hits?: number
  elapsed_ms?: number
}

export interface DecisionLogRejectedSample {
  provider: string
  filename: string
  language: string
  format: string
  score: number
  release_info: string
}

export interface DecisionLogFilterStage {
  stage: string
  removed: number
  remaining: number
  rejected?: DecisionLogRejectedSample[]
  wanted?: string | string[]
  threshold?: number
  rule?: string[]
}

export interface DecisionLogDownloadAttempt {
  provider: string
  subtitle_id: string
  status: string
  detail?: string
}

export interface DecisionLogSearch {
  step: string
  languages: string[]
  format: string
  min_score: number
  cache_hit: boolean
  providers: DecisionLogProvider[]
  results_total: number
  filters: DecisionLogFilterStage[]
  results_final: number
  download_attempts: DecisionLogDownloadAttempt[]
  unfinished_providers?: string[]
  early_exit?: { provider: string; score: number }
}

export interface DecisionLogFinal {
  status?: string
  provider?: string
  subtitle_id?: string
  language?: string
  format?: string
  score?: number
  score_breakdown?: Record<string, number>
  filename?: string
  release_info?: string
  step?: string
  reason?: string
  error?: string
  output_path?: string
}

export interface DecisionLog {
  version: number
  started_at: string
  finished_at: string
  item: {
    wanted_id?: number
    title?: string
    season_episode?: string
    file_path?: string
    target_language?: string
    is_upgrade?: boolean
  }
  steps: { step: string; skipped: boolean; reason: string }[]
  searches: DecisionLogSearch[]
  upgrade?: { approved: boolean; reason: string; old_score: number; new_score: number }
  final?: DecisionLogFinal
  truncated?: boolean
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

// â”€â”€â”€ Standalone Mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
  wanted_count?: number
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
  wanted?: boolean
  created_at: string
  updated_at: string
  profile_name?: string
  profile_id?: number | null
}

export interface MovieDetail extends StandaloneMovie {
  wanted_count?: number
}

export interface StandaloneStatus {
  enabled: boolean
  watcher_running: boolean
  folders_count: number
  scanner_scanning: boolean
  arr_configured: boolean
  auto_activated: boolean
}

export interface StandaloneScanResult {
  folders_scanned: number
  series_found: number
  movies_found: number
  wanted_added: number
  duration_seconds: number
}

// â”€â”€â”€ Statistics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface SeriesQuality {
  title: string
  avg_score: number
  avg_score_pct: number
  download_count: number
  last_download: string | null
  formats: string[]
}

export interface QualityTrend {
  date: string
  avg_score: number
  issues_count: number
  files_checked: number
}

export interface StatisticsData {
  daily: import('./core').DailyStat[]
  providers: Record<string, ProviderHealthStats>
  downloads_by_provider: Array<{ provider_name: string; count: number; avg_score: number }>
  backend_stats: Array<{ backend_name: string; total_requests: number; successful_translations: number; failed_translations: number; total_characters: number }>
  upgrades: Array<{ type: string; count: number }>
  by_format: Record<string, number>
  quality_trend: QualityTrend[]
  series_quality: SeriesQuality[]
  range: string
}

// â”€â”€â”€ Backup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Scheduler Tasks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface SchedulerTask {
  name: string
  display_name: string
  running: boolean
  last_run: string | null
  next_run: string | null
  interval_hours: number | null
  enabled: boolean
  cancellable?: boolean
  progress?: { processed: number; total: number } | null
}

export interface TasksResponse {
  tasks: SchedulerTask[]
}

// â”€â”€â”€ Subtitle Editor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

export interface SubtitleBackupContent {
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

export interface SubtitleCueSyllable {
  /** Visible syllable text. */
  text: string
  /** Offset from cue start, in seconds. */
  start: number
  /** Offset from cue start, in seconds (= start + duration). */
  end: number
}

export interface SubtitleCue {
  start: number
  end: number
  text: string
  style: string
  quality_score?: number
  /** ASS karaoke syllable timings (Plan B8 Task 9). Absent for SRT. */
  syllables?: SubtitleCueSyllable[]
}

export interface SubtitleParseResult {
  cues: SubtitleCue[]
  total_duration: number
  cue_count: number
  format: string
  styles: Record<string, string> | null
  has_quality_scores?: boolean
}

// â”€â”€â”€ Health Check & Quality â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Comparison â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Chapter Sync â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface Chapter {
  id: number
  title: string
  start_ms: number
  end_ms: number
}

export interface ChapterList {
  video_path: string
  chapters: Chapter[]
}

// â”€â”€â”€ Sync â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Cleanup System â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
  /** Set by the backend when files in the group belong to different episodes
   * (distinct SxxEyy codes, or a mix of files with and without codes).
   * Typically means the same subtitle was misfiled â€” deleting one leaves
   * the wrong file behind; the UI surfaces a warning. */
  cross_episode?: boolean
}

export interface CleanupRule {
  id: number
  name: string
  rule_type: 'dedup' | 'orphaned' | 'old_backups' | 'old_subtitle_baks' | 'language_filter' | 'format_upgrade' | 'orphan_files' | 'orphan_db' | 'foreign_tracks'
  config_json: Record<string, unknown>
  enabled: boolean
  schedule: 'manual' | 'daily' | 'weekly' | 'after_scan'
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

// â”€â”€â”€ Notification Templates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
  // Wire format: the backend stores these as JSON-encoded strings, e.g. "[0,1,2,3,4,5,6]"
  days_of_week: string
  exception_events: string
  // Wire format: 1/0 integer per the backend model
  enabled: number
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

// â”€â”€â”€ External Integrations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€â”€ Subtitle Diff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface SubtitleDiffCue {
  start: number
  end: number
  text: string
  style: string
}

export type SubtitleDiffType = 'unchanged' | 'modified' | 'added' | 'removed'

export interface SubtitleDiffEntry {
  type: SubtitleDiffType
  original: SubtitleDiffCue | null
  modified: SubtitleDiffCue | null
}

export interface SubtitleDiffResult {
  diffs: SubtitleDiffEntry[]
  total: number
  changed: number
}

// â”€â”€â”€ Web Player â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface PlayerSubtitleTrack {
  path: string
  language: string
  format: 'ass' | 'srt' | 'vtt'
  label: string
}

export interface PlayerModalProps {
  videoPath: string
  subtitleTracks: PlayerSubtitleTrack[]
  initialTrackIndex?: number
  onClose: () => void
  onSeekRequest?: (seekFn: (seconds: number) => void) => void
}

// â”€â”€â”€ Support â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface SupportTopError {
  message: string
  count: number
  last_seen: string
}

export interface SupportProviderStatus {
  name: string
  active: boolean
}

export interface SupportDiagnostic {
  version: string
  timestamp_utc: string
  uptime_minutes: number | null
  memory_mb: number | null
  top_errors: SupportTopError[]
  provider_status: SupportProviderStatus[]
  wanted: { total: number; pending: number; extracted: number; failed: number }
  translations: { total_requests: number; successful: number; failed: number }
  last_scan_ago_minutes: number | null
  config_entries_count: number
  db_stats_error?: string
}

export interface SupportRedactionSummary {
  log_files_found: number
  ips_redacted: number
  api_keys_redacted: number
  paths_redacted: number
  emails_redacted: number
  hostnames_redacted: number
  example_path_before: string
  example_path_after: string
  example_ip_before: string
  example_ip_after: string
}

export interface SupportPreview {
  diagnostic: SupportDiagnostic
  redaction_summary: SupportRedactionSummary
}

// â”€â”€â”€ Scheduler â€” Phase 5 Rollout 2 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export type TriggerInterval = {
  type: 'interval'
  seconds?: number
  minutes?: number
  hours?: number
}

export type TriggerCron = {
  type: 'cron'
  year?: string
  month?: string
  day?: string
  week?: string
  day_of_week?: string
  hour?: string
  minute?: string
  second?: string
}

export type Trigger = TriggerInterval | TriggerCron

export type SchedulerStatus = 'ok' | 'error' | 'timeout' | 'missed' | 'skipped_overlap'
export type SchedulerTriggeredBy = 'schedule' | 'manual' | 'startup'

export type SchedulerJobRun = {
  id: number
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  status: SchedulerStatus
  triggered_by: SchedulerTriggeredBy
  error_type: string | null
  error_msg: string | null
}

export type SchedulerJob = {
  id: string
  description: string
  owner_module: string
  trigger: Trigger
  trigger_is_default: boolean
  paused: boolean
  next_run_time: string | null
  last_run: Omit<SchedulerJobRun, 'id' | 'triggered_by'> | null
  stats_7d: Record<SchedulerStatus, number>
}
