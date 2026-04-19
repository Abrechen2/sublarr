/** Translation backend types. */

export interface RetranslateStatus {
  current_hash: string
  outdated_count: number
  ollama_model: string
  target_language: string
}

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

// ─── Whisper Types ────────────────────────────────────────────────────────────

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
  audio_track_index: number | null
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

// ─── Translation telemetry — Phase A1 ────────────────────────────────────────

export interface TranslationCostWindow {
  cost_usd: number
  events: number
  cache_hits: number
}

export interface TranslationCostSummary {
  today: TranslationCostWindow
  last_7d: TranslationCostWindow
  last_30d: TranslationCostWindow
}

export interface TranslationBackendCost {
  backend: string
  events: number
  cost_usd: number
  avg_latency_ms: number
  error_rate: number
}

/**
 * A1 memory telemetry (rows, size_bytes, hit_rate_7d).
 * Distinct from the older `TranslationMemoryStats` (entries, cache_size_bytes)
 * which backs the `/translation-memory/stats` endpoint.
 */
export interface TranslationMemoryTelemetry {
  rows: number
  size_bytes: number
  hit_rate_7d: number
}

export interface TranslationConcurrencyEntry {
  backend: string
  limit: number
}

export interface TranslationConcurrency {
  backends: TranslationConcurrencyEntry[]
}

// Translation queue — Phase A2
export type TranslationActiveJob = {
  job_id: string
  file_path: string
  source_lang: string
  target_lang: string
  backend: string
  progress: { done: number; total: number; pct: number }
  started_at: string
  eta_seconds: number | null
  cost_so_far_micro_usd: number
  cancel_requested: boolean
}

export type TranslationRecentJob = {
  job_id: string
  file_path: string
  source_lang: string
  target_lang: string
  backend: string
  lines: number
  status: string
  error_type: string | null
  finished_at: string
  duration_s: number
  cost_micro_usd: number
}

export type TranslationQueueSnapshot = {
  active: TranslationActiveJob[]
  recent: TranslationRecentJob[]
}
