/** Core / shared types — job queue, auth, health, stats, batch. */

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

export interface AuthStatus {
  configured: boolean
  enabled: boolean
  authenticated: boolean
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy'
  version: string
  services: Record<string, string>
}

export interface UpdateInfo {
  available: boolean
  latest: string | null
  current: string
  url: string | null
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
  total_subtitles?: number
  downloads_today?: number
  average_score?: number
  low_score_count?: number
  success_rate?: number
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

export interface AppConfig {
  [key: string]: string | number | boolean | undefined
  wanted_auto_extract?: boolean
  wanted_auto_translate?: boolean
}
