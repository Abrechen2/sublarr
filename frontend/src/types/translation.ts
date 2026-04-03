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
