// ─── Subtitle Health ─────────────────────────────────────────────────────────

export type HealthIssueType =
  | 'ass_escape_leak'
  | 'language_mislabel'
  | 'empty_or_tiny'
  | 'encoding_mojibake'
  | 'timing_sanity'
  | 'missing_language'
  | 'format_mismatch'
  | 'unicode_control_chars'
  | 'container_metadata_drift'

export type HealthSeverity = 'confirmed' | 'suspicious' | 'info'
export type HealthTargetKind = 'sidecar' | 'embedded'

export interface HealthIssue {
  id?: number
  type: HealthIssueType
  severity: HealthSeverity
  episode_id: number | null
  target_kind: HealthTargetKind
  target_path: string
  stream_index: number | null
  lang: string
  count: number
  snippets: string[]
  raw_hash: string
  fixable: boolean
  suggested_fix: string | null
}

export interface EpisodeHealthResult {
  episode_id: number | null
  video_path: string
  healthy: boolean
  issue_count: number
  issues: HealthIssue[]
}

export interface HealthFixResult {
  changed: boolean
  fix_id?: number
  status?: string
  reason?: string
}

export interface HealthReport {
  total_findings: number
  by_type: Record<string, number>
  affected_episodes: number
}
